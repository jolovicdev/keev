from typing import Any, Dict, Optional, List

class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = None, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.detail = detail or "An error occurred"
        self.headers = headers or {}

class ValidationError(HTTPException):
    def __init__(self, detail: str = "Validation error"):
        super().__init__(422, detail)

class RateLimitExceeded(HTTPException):
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(429, detail, {"Retry-After": "60"})

class CSRFError(HTTPException):
    def __init__(self, detail: str = "CSRF token missing or invalid"):
        super().__init__(403, detail)

class DependencyError(HTTPException):
    def __init__(self, detail: str = "Dependency resolution failed"):
        super().__init__(500, detail)

class ConfigurationError(Exception):
    def __init__(self, detail: str = "Configuration error"):
        self.detail = detail
        super().__init__(detail)

class NotFound(HTTPException):
    def __init__(self, detail: str = "Not Found"):
        super().__init__(404, detail)

class BadRequest(HTTPException):
    def __init__(self, detail: str = "Bad Request"):
        super().__init__(400, detail)

class Unauthorized(HTTPException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(401, detail, {"WWW-Authenticate": "Bearer"})

class Forbidden(HTTPException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(403, detail)

class MethodNotAllowed(HTTPException):
    def __init__(self, allowed_methods: List[str], detail: str = "Method not allowed"):
        super().__init__(405, detail, {"Allow": ", ".join(allowed_methods)})

class NotAcceptable(HTTPException):
    def __init__(self, detail: str = "Not Acceptable"):
        super().__init__(406, detail)

class RequestTimeout(HTTPException):
    def __init__(self, detail: str = "Request timeout"):
        super().__init__(408, detail)

class Conflict(HTTPException):
    def __init__(self, detail: str = "Conflict"):
        super().__init__(409, detail)

class Gone(HTTPException):
    def __init__(self, detail: str = "Gone"):
        super().__init__(410, detail)

class UnsupportedMediaType(HTTPException):
    def __init__(self, detail: str = "Unsupported Media Type"):
        super().__init__(415, detail)

class UnprocessableEntity(HTTPException):
    def __init__(self, detail: str = "Unprocessable Entity"):
        super().__init__(422, detail)

class TooManyRequests(HTTPException):
    def __init__(self, detail: str = "Too Many Requests"):
        super().__init__(429, detail)

class InternalServerError(HTTPException):
    def __init__(self, detail: str = "Internal Server Error"):
        super().__init__(500, detail)

class NotImplemented(HTTPException):
    def __init__(self, detail: str = "Not Implemented"):
        super().__init__(501, detail)

class BadGateway(HTTPException):
    def __init__(self, detail: str = "Bad Gateway"):
        super().__init__(502, detail)

class ServiceUnavailable(HTTPException):
    def __init__(self, detail: str = "Service Unavailable"):
        super().__init__(503, detail, {"Retry-After": "60"})

class GatewayTimeout(HTTPException):
    def __init__(self, detail: str = "Gateway Timeout"):
        super().__init__(504, detail)

class WebSocketError(HTTPException):
    def __init__(self, detail: str = "WebSocket Error"):
        super().__init__(1011, detail)
class PluginError(Exception):
    def __init__(self, detail: str = "Plugin Error"):
        self.detail = detail
        super().__init__(detail)