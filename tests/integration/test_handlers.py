"""Integration tests for Keev framework"""
import pytest
from keev import Application, Router, JSONResponse, RequestContext, BaseMiddleware
from keev.static import StaticFiles
from pydantic import BaseModel
import os
import tempfile
import json
from typing import Optional, List

# Test Models
class TestItem(BaseModel):
    name: str
    price: float
    tags: List[str] = []
    in_stock: bool = True

# Test Middleware
class HeaderMiddleware(BaseMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.add_header("x-test", "test-value")
        return response

class TimingMiddleware(BaseMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.add_header("x-time", "0.001")
        return response

@pytest.fixture
def test_app():
    """Create a test application with routes and middleware"""
    app = Application(debug=True)
    router = Router()
    
    # In-memory storage
    items = {}
    
    @router.get("/")
    async def home():
        return JSONResponse({"status": "ok"})
    
    @router.post("/items")
    async def create_item(item: TestItem):
        item_dict = item.model_dump()
        items[len(items) + 1] = item_dict
        return JSONResponse({"id": len(items), **item_dict}, status_code=201)
    
    @router.get("/items/{item_id}")
    async def get_item(item_id: int):
        if item_id not in items:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse({"id": item_id, **items[item_id]})
    
    app.router = router
    app.add_middleware(HeaderMiddleware())
    app.add_middleware(TimingMiddleware())
    return app

@pytest.fixture
def static_app():
    """Create an app with static file handling"""
    app = Application(debug=True)
    router = Router()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test files
        index_path = os.path.join(temp_dir, "index.html")
        with open(index_path, "w") as f:
            f.write("<h1>Test Page</h1>")
            
        static = StaticFiles(temp_dir)
        
        @router.get("/static/{path:str}")
        async def serve_static(ctx: RequestContext, path: str):
            return await static(ctx.request)
        
        app.router = router
        yield app

@pytest.mark.asyncio
async def test_middleware_chain(test_app):
    """Test that multiple middleware are executed in the correct order"""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "asgi": {"version": "3.0"}
    }
    
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    
    responses = []
    async def send(message):
        responses.append(message)
    
    await test_app(scope, receive, send)
    
    # Check that both middleware headers are present
    start_messages = [m for m in responses if m["type"] == "http.response.start"]
    assert start_messages
    headers = dict(start_messages[0]["headers"])
    assert headers[b"x-test"] == b"test-value"
    assert headers[b"x-time"] == b"0.001"

@pytest.mark.asyncio
async def test_crud_operations(test_app):
    """Test create and read operations with JSON data"""
    # Create item
    create_scope = {
        "type": "http",
        "method": "POST",
        "path": "/items",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
        "asgi": {"version": "3.0"}
    }
    
    test_item = {
        "name": "Test Item",
        "price": 9.99,
        "tags": ["test", "example"],
        "in_stock": True
    }
    
    create_responses = []
    async def create_send(message):
        create_responses.append(message)
    
    request_sent = False
    async def create_receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": TestItem(**test_item).model_dump_json().encode(), "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}
    
    await test_app(create_scope, create_receive, create_send)
    
    # Verify item was created
    body_messages = [m for m in create_responses if m["type"] == "http.response.body"]
    assert body_messages
    assert any(m["type"] == "http.response.start" and m["status"] == 201 for m in create_responses)
    
    # Get created item
    get_scope = {
        "type": "http",
        "method": "GET",
        "path": "/items/1",
        "headers": [],
        "query_string": b"",
        "asgi": {"version": "3.0"}
    }
    
    get_responses = []
    async def get_send(message):
        get_responses.append(message)
    
    async def get_receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    
    await test_app(get_scope, get_receive, get_send)
    
    # Verify item can be retrieved
    assert any(m["type"] == "http.response.start" and m["status"] == 200 for m in get_responses)

@pytest.mark.asyncio
async def test_static_file_serving(static_app):
    """Test static file serving with proper content types"""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/static/index.html",
        "headers": [],
        "query_string": b"",
        "asgi": {"version": "3.0"}
    }
    
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    
    responses = []
    async def send(message):
        responses.append(message)
    
    await static_app(scope, receive, send)
    
    # Verify response
    assert any(
        m["type"] == "http.response.start" and
        m["status"] == 200 and
        (b"content-type", b"text/html") in m["headers"]
        for m in responses
    )
    
    # Verify content
    body_messages = [m for m in responses if m["type"] == "http.response.body"]
    assert body_messages
    assert b"<h1>Test Page</h1>" in body_messages[0]["body"]

@pytest.mark.asyncio
async def test_error_handling(test_app):
    """Test error responses and status codes"""
    # Test 404 Not Found
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items/999",
        "headers": [],
        "query_string": b"",
        "asgi": {"version": "3.0"}
    }
    
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    
    responses = []
    async def send(message):
        responses.append(message)
    
    await test_app(scope, receive, send)
    
    # Verify 404 response
    assert any(m["type"] == "http.response.start" and m["status"] == 404 for m in responses)
    
    # Test validation error
    scope["method"] = "POST"
    scope["path"] = "/items"
    
    invalid_item = {"name": "Test", "price": "invalid"}  # price should be float
    
    request_sent = False
    async def invalid_receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": json.dumps(invalid_item).encode(), "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}
    
    responses.clear()
    await test_app(scope, invalid_receive, send)
    
    # Verify 422 response for validation error
    assert any(m["type"] == "http.response.start" and m["status"] == 422 for m in responses)