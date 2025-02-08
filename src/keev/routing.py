from typing import Callable, Dict, List, Optional, Awaitable, Any, Type, Union, TypeVar, Generic, get_type_hints, cast
from keev.requests import Request
from keev.responses import Response, JSONResponse
from keev.utils import get_logger, ColoredFormatter
from keev.exceptions import HTTPException, ValidationError, MethodNotAllowed
from pydantic import BaseModel, create_model, ValidationError as PydanticValidationError
import re
import inspect
from functools import wraps, lru_cache
from dataclasses import dataclass
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = get_logger("keev.routing")

T = TypeVar('T')

@dataclass
class RouteMetadata:
    """Metadata for route documentation and validation"""
    summary: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    deprecated: bool = False
    response_model: Optional[Type[BaseModel]] = None
    request_model: Optional[Type[BaseModel]] = None
    responses: Dict[int, Dict[str, Any]] = field(default_factory=dict)

class RequestContext:
    """Context object passed to route handlers that need request access"""
    def __init__(self, request: Request):
        self.request = request

class Depends:
    def __init__(self, dependency: Callable[..., T]):
        self.dependency = dependency
        self._cache = {}

    async def __call__(self, request: Request) -> T:
        if self.dependency in self._cache:
            return self._cache[self.dependency]

        sig = inspect.signature(self.dependency)
        kwargs = {}

        for param_name, param in sig.parameters.items():
            if param_name == "request":
                kwargs[param_name] = request
            elif isinstance(param.default, Depends):
                kwargs[param_name] = await param.default(request)

        result = await self.dependency(**kwargs) if inspect.iscoroutinefunction(self.dependency) else self.dependency(**kwargs)
        self._cache[self.dependency] = result
        return result

@dataclass
class RateLimit:
    requests: int
    window: int
    by: str = "ip"

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    async def is_allowed(self, key: str, limit: RateLimit) -> bool:
        now = time.time()
        self.requests[key] = [ts for ts in self.requests[key] if now - ts < limit.window]
        if len(self.requests[key]) >= limit.requests:
            return False
        self.requests[key].append(now)
        return True

class Route:
    __slots__ = ("path", "handler", "methods", "param_types", "regex", "name", "version", 
                 "dependencies", "rate_limit", "csrf_protect", "secure_headers", "response_model",
                 "_compiled_regex", "_param_converters", "metadata", "_needs_request")
    
    def __init__(
        self, 
        path: str, 
        handler: Callable[..., Awaitable[Response]], 
        methods: List[str], 
        param_types: Dict[str, Type] = None,
        name: str = None,
        version: str = None,
        dependencies: List[Depends] = None,
        rate_limit: Optional[RateLimit] = None,
        csrf_protect: bool = False,
        secure_headers: bool = True,
        response_model: Optional[Type[BaseModel]] = None,
        metadata: Optional[RouteMetadata] = None
    ):
        self.path = path
        self.handler = handler
        self.methods = methods
        self.param_types = param_types or {}
        self.name = name or handler.__name__
        self.version = version
        self.dependencies = dependencies or []
        self.rate_limit = rate_limit
        self.csrf_protect = csrf_protect
        self.secure_headers = secure_headers
        self.response_model = response_model
        self._compiled_regex = None
        self._param_converters = {}
        self.metadata = metadata or RouteMetadata()
        
        # Check if handler needs request object
        sig = inspect.signature(handler)
        self._needs_request = "request" in sig.parameters or "ctx" in sig.parameters

        # Extract type hints from handler for path parameters
        type_hints = get_type_hints(handler)
        for param_name, param_type in type_hints.items():
            if param_name not in ("request", "ctx") and param_name not in self.param_types:
                self.param_types[param_name] = param_type

        self._compile()

    def _compile(self):
        """Pre-compile regex and parameter converters for better performance"""
        # Replace {param} with regex pattern and store converter
        path_regex = self.path
        for name, type_ in self.param_types.items():
            # Handle both {param:type} and {param} formats
            param_pattern = f"{{{name}(?::[^}}]+)?}}"
            path_regex = re.sub(param_pattern, f"(?P<{name}>[^/]+)", path_regex)
            
            # Set up converter based on type hint
            if type_ == int:
                self._param_converters[name] = int
            elif type_ == float:
                self._param_converters[name] = float
            elif type_ == bool:
                self._param_converters[name] = lambda x: x.lower() == "true"
            else:
                self._param_converters[name] = str

        self._compiled_regex = re.compile(f"^{path_regex}/?$")

    def match(self, path: str) -> Optional[Dict[str, Any]]:
        match = self._compiled_regex.match(path)
        if not match:
            return None
            
        params = {}
        for name, value in match.groupdict().items():
            if converter := self._param_converters.get(name):
                try:
                    params[name] = converter(value)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Parameter conversion failed for {name}: {value} - {str(e)}")
                    return None
            else:
                params[name] = value
        return params

class Router:
    __slots__ = ("routes", "prefix", "version", "logger", "_method_routes", "_path_tree")

    def __init__(self, prefix: str = "", version: str = None):
        self.routes: List[Route] = []
        self.prefix = prefix
        self.version = version
        self.logger = get_logger(f"keev.router{'.'+version if version else ''}")
        self._method_routes = defaultdict(list)  # Method -> [Route]
        self._path_tree = {}  # Radix tree for faster lookups

    def _build_path(self, path: str) -> str:
        """Build full path including prefix and version"""
        parts = []
        if self.version:
            parts.append(f"/v{self.version}")
        if self.prefix:
            parts.append(self.prefix.strip("/"))
        parts.append(path.lstrip("/"))
        return "/" + "/".join(filter(None, parts))

    async def _extract_body_params(self, request: Request, param_type: Type[BaseModel]) -> Any:
        """Extract and validate parameters from request body"""
        try:
            body = await request.json()
            return param_type.model_validate(body)
        except Exception as e:
            logger.error(f"Parameter validation error: {e}")
            raise ValidationError(str(e))

    def route(
        self,
        path: str,
        methods: Union[str, List[str]] = None,
        name: str = None,
        dependencies: List[Depends] = None,
        rate_limit: Optional[RateLimit] = None,
        csrf_protect: bool = False,
        secure_headers: bool = True,
        response_model: Optional[Type[BaseModel]] = None,
        **kwargs
    ):
        if isinstance(methods, str):
            methods = [methods]
        methods = methods or ["GET"]
        methods = [m.upper() for m in methods]

        def decorator(handler: Callable[..., Awaitable[Response]]) -> Callable[..., Awaitable[Response]]:
            route_path = self._build_path(path)
            param_types = {}
            
            sig = inspect.signature(handler)
            type_hints = get_type_hints(handler)
            
            for param_name, param in sig.parameters.items():
                if param_name in ("request", "ctx"):
                    continue
                    
                # Use type hints if available, fallback to parameter annotation
                param_type = type_hints.get(param_name, param.annotation)
                param_types[param_name] = param_type if param_type != inspect.Parameter.empty else str

            route = Route(
                route_path,
                handler,
                methods,
                param_types,
                name=name,
                version=self.version,
                dependencies=dependencies,
                rate_limit=rate_limit,
                csrf_protect=csrf_protect,
                secure_headers=secure_headers,
                response_model=response_model,
                metadata=RouteMetadata(response_model=response_model)
            )
            self.add_route(route)
            return handler
        return decorator

    def get(self, path: str, **kwargs):
        return self.route(path, methods=["GET"], **kwargs)

    def post(self, path: str, **kwargs):
        return self.route(path, methods=["POST"], **kwargs)

    def put(self, path: str, **kwargs):
        return self.route(path, methods=["PUT"], **kwargs)

    def delete(self, path: str, **kwargs):
        return self.route(path, methods=["DELETE"], **kwargs)

    def patch(self, path: str, **kwargs):
        return self.route(path, methods=["PATCH"], **kwargs)

    def options(self, path: str, **kwargs):
        return self.route(path, methods=["OPTIONS"], **kwargs)

    def add_route(self, route: Route) -> None:
        self.routes.append(route)
        for method in route.methods:
            self._method_routes[method].append(route)
        self.logger.debug(f"Added route: {route.methods} {route.path}")

    def include_router(self, router: 'Router', prefix: str = "") -> None:
        """Include another router's routes with an optional prefix"""
        for route in router.routes:
            new_path = f"{prefix.rstrip('/')}/{route.path.lstrip('/')}"
            new_route = Route(
                new_path,
                route.handler,
                route.methods,
                route.param_types,
                name=route.name,
                version=route.version,
                dependencies=route.dependencies,
                rate_limit=RateLimit,
                csrf_protect=route.csrf_protect,
                secure_headers=route.secure_headers,
                response_model=route.response_model
            )
            self.add_route(new_route)

    async def handle_request(self, request: Request) -> Response:
        path = request.path.rstrip('/')
        if not path:
            path = "/"

        # Fast lookup by method first
        method_routes = self._method_routes.get(request.method, [])
        matched_route = None
        params = None

        # First try to find a route that matches both path and method
        for route in method_routes:
            route_params = route.match(path)
            if route_params is not None:
                matched_route = route
                params = route_params
                break

        # If no route matches both path and method, check if the path exists for any method
        if not matched_route:
            allowed_methods = set()
            for route in self.routes:
                if route.match(path):
                    allowed_methods.update(route.methods)

            if allowed_methods:
                # Path exists but method not allowed
                return JSONResponse(
                    {"error": "Method Not Allowed", "allowed_methods": list(allowed_methods)},
                    status_code=405,
                    headers={"Allow": ", ".join(allowed_methods)}
                )

            # Path not found
            self.logger.warning(f"Route not found: {request.method} {request.path}")
            return JSONResponse({"error": "Not Found"}, status_code=404)

        # Process the matched route
        request.path_params = params
        handler_sig = inspect.signature(matched_route.handler)
        handler_params = {}

        try:
            # Add path parameters
            handler_params.update(params)

            # Add request context if needed
            if "ctx" in handler_sig.parameters:
                handler_params["ctx"] = RequestContext(request)
            elif "request" in handler_sig.parameters:
                handler_params["request"] = request

            # Add body parameters for models
            for name, param in handler_sig.parameters.items():
                if name not in handler_params and issubclass(param.annotation, BaseModel):
                    handler_params[name] = await self._extract_body_params(request, param.annotation)

            return await matched_route.handler(**handler_params)
        except ValidationError as e:
            return JSONResponse({"error": str(e)}, status_code=422)
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            raise
