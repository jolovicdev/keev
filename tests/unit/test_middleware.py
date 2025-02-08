"""Unit tests for middleware functionality"""
import pytest
from keev.middleware import BaseMiddleware, CORSMiddleware
from keev.responses import Response, JSONResponse
from keev.requests import Request

@pytest.fixture
def mock_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
    }
    async def receive():
        return {"type": "http.request", "body": b""}
    return Request(scope, receive)

class TestMiddleware(BaseMiddleware):
    def __init__(self):
        self.called = False
        
    async def __call__(
        self,
        request: Request,
        call_next
    ) -> Response:
        self.called = True
        response = await call_next(request)
        response.add_header("x-test", "test")
        return response

@pytest.mark.asyncio
async def test_base_middleware(mock_request):
    """Test base middleware functionality"""
    middleware = BaseMiddleware()
    
    async def next_handler(request):
        return JSONResponse({"status": "ok"})
    
    response = await middleware(mock_request, next_handler)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_custom_middleware(mock_request):
    """Test custom middleware adds headers"""
    middleware = TestMiddleware()
    
    async def next_handler(request):
        return JSONResponse({"status": "ok"})
    
    response = await middleware(mock_request, next_handler)
    assert response.headers["x-test"] == "test"
    assert middleware.called

@pytest.mark.asyncio
async def test_cors_middleware_defaults():
    """Test CORS middleware with default settings"""
    middleware = CORSMiddleware()
    scope = {
        "type": "http",
        "method": "OPTIONS",
        "path": "/test",
        "headers": [(b"origin", b"http://localhost:8000")],
    }
    request = Request(scope, lambda: {"type": "http.request", "body": b""})
    
    async def next_handler(request):
        return JSONResponse({"status": "ok"})
    
    response = await middleware(request, next_handler)
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-methods" in response.headers

@pytest.mark.asyncio
async def test_cors_middleware_custom_origins():
    """Test CORS middleware with custom origins"""
    allowed_origins = ["http://localhost:8000"]
    middleware = CORSMiddleware(allow_origins=allowed_origins)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(b"origin", b"http://localhost:8000")],
    }
    request = Request(scope, lambda: {"type": "http.request", "body": b""})
    
    async def next_handler(request):
        return JSONResponse({"status": "ok"})
    
    response = await middleware(request, next_handler)
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"