from typing import Callable, Awaitable, List
from keev.requests import Request
from keev.responses import Response

class BaseMiddleware:
    """Base class for middleware"""
    
    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Execute middleware"""
        return await call_next(request)

class CORSMiddleware(BaseMiddleware):
    """CORS middleware for handling Cross-Origin Resource Sharing"""
    
    def __init__(self, allow_origins: List[str] = None):
        self.allow_origins = allow_origins or ["*"]

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        
        # Get origin from request
        origin = next(
            (v.decode("latin1") for k, v in request.scope["headers"] 
             if k.decode("latin1").lower() == "origin"),
            None
        )
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            response.add_header("access-control-allow-origin", "*" if "*" in self.allow_origins else origin or "")
            response.add_header("access-control-allow-methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS")
            response.add_header("access-control-allow-headers", "Content-Type, Authorization")
            response.add_header("access-control-max-age", "3600")
            return response

        # Handle regular requests
        if "*" in self.allow_origins:
            response.add_header("access-control-allow-origin", "*")
        elif origin and origin in self.allow_origins:
            response.add_header("access-control-allow-origin", origin)
            response.add_header("vary", "Origin")

        return response