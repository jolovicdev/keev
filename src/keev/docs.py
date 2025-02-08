from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel
import json
from dataclasses import dataclass, field
from keev.responses import HTMLResponse
from keev.routing import Route, Router
import inspect
import re

@dataclass
class APIEndpoint:
    path: str
    methods: List[str]
    summary: str
    description: str
    tags: List[str]
    response_model: Optional[Type[BaseModel]] = None
    request_model: Optional[Type[BaseModel]] = None
    parameters: List[Dict[str, Any]] = field(default_factory=list)

class APIDocumentation:
    def __init__(self, title: str = "Keev API", version: str = "1.0.0"):
        self.title = title
        self.version = version
        self.endpoints: List[APIEndpoint] = []

    def add_router(self, router: Router) -> None:
        """Add routes from a router to the documentation"""
        for route in router.routes:
            if not route.metadata:
                continue

            parameters = []
            openapi_path = route.path
            
            if route.param_types:
                for name, type_ in route.param_types.items():
                    openapi_path = re.sub(f"{{{name}:[^}}]+}}", f"{{{name}}}", openapi_path)
                    parameters.append({
                        "name": name,
                        "in": "path",
                        "required": True,
                        "schema": {"type": self._get_type_name(type_)}
                    })

            request_model = None
            for param_name, param in inspect.signature(route.handler).parameters.items():
                if hasattr(param.annotation, 'model_json_schema'):
                    request_model = param.annotation
                    break

            endpoint = APIEndpoint(
                path=openapi_path,
                methods=route.methods,
                summary=route.metadata.summary or route.handler.__doc__ or "",
                description=route.metadata.description or route.handler.__doc__ or "",
                tags=route.metadata.tags or [],
                response_model=route.metadata.response_model,
                request_model=request_model,
                parameters=parameters
            )
            self.endpoints.append(endpoint)

    def _get_type_name(self, type_: Type) -> str:
        """Convert Python type to OpenAPI type"""
        if type_ == str:
            return "string"
        elif type_ == int:
            return "integer"
        elif type_ == float:
            return "number"
        elif type_ == bool:
            return "boolean"
        return "string"

    def _generate_openapi_spec(self) -> Dict[str, Any]:
        """Generate OpenAPI specification"""
        paths: Dict[str, Dict[str, Any]] = {}
        schemas: Dict[str, Any] = {}

        # Group endpoints by path
        for endpoint in self.endpoints:
            if endpoint.path not in paths:
                paths[endpoint.path] = {}

            for method in endpoint.methods:
                method = method.lower()
                operation: Dict[str, Any] = {
                    "summary": endpoint.summary,
                    "description": endpoint.description,
                    "tags": endpoint.tags,
                    "parameters": endpoint.parameters,
                    "responses": {
                        "200": {
                            "description": "Successful Response"
                        },
                        "422": {
                            "description": "Validation Error",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                if endpoint.request_model and method in ["post", "put", "patch"]:
                    schema = endpoint.request_model.model_json_schema()
                    schemas[endpoint.request_model.__name__] = schema
                    operation["requestBody"] = {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{endpoint.request_model.__name__}"}
                            }
                        }
                    }

                # Add response schema if available
                if endpoint.response_model:
                    schema = endpoint.response_model.model_json_schema()
                    schemas[endpoint.response_model.__name__] = schema
                    operation["responses"]["200"]["content"] = {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{endpoint.response_model.__name__}"}
                        }
                    }

                paths[endpoint.path][method] = operation

        return {
            "openapi": "3.0.2",
            "info": {
                "title": self.title,
                "version": self.version
            },
            "paths": paths,
            "components": {
                "schemas": schemas
            }
        }

    def get_swagger_ui(self) -> str:
        """Generate Swagger UI HTML"""
        spec = self._generate_openapi_spec()
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>{self.title} - API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        window.onload = () => {{
            window.ui = SwaggerUIBundle({{
                spec: {json.dumps(spec)},
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
            }});
        }};
    </script>
</body>
</html>
"""

    def get_redoc(self) -> str:
        """Generate ReDoc HTML"""
        spec = self._generate_openapi_spec()
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>{self.title} - API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
</head>
<body>
    <div id="redoc"></div>
    <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
    <script>
        Redoc.init({json.dumps(spec)}, {{
            scrollYOffset: 50
        }}, document.getElementById('redoc'));
    </script>
</body>
</html>
"""

def get_docs_routes(app: Any) -> Router:
    """Create routes for API documentation"""
    docs_router = Router()
    docs = APIDocumentation()

    if hasattr(app, 'router'):
        docs.add_router(app.router)

    @docs_router.get("/docs")
    async def swagger_ui(request):
        """Swagger UI documentation"""
        return HTMLResponse(docs.get_swagger_ui())

    @docs_router.get("/redoc")
    async def redoc(request):
        """ReDoc documentation"""
        return HTMLResponse(docs.get_redoc())

    @docs_router.get("/openapi.json")
    async def openapi_spec(request):
        """OpenAPI specification"""
        return docs._generate_openapi_spec()

    return docs_router