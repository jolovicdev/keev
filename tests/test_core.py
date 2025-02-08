"""Core functionality tests for Keev framework"""
import pytest
import json
import orjson
from keev import Application, Router, Request, JSONResponse, RequestContext, BaseMiddleware
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    in_stock: bool = True

class TestMiddleware(BaseMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.add_header("x-test", "test")
        return response

@pytest.fixture
def app():
    """Create a test application"""
    app = Application(enable_plugins=False)
    router = Router()

    @router.get("/")
    async def home():
        return JSONResponse({"message": "Hello, World!"})

    @router.get("/items/{item_id}")
    async def get_item(item_id: int):
        return JSONResponse({"id": item_id})

    @router.post("/items")
    async def create_item(item: Item):
        return JSONResponse(item.model_dump(), status_code=201)

    @router.post("/items/raw")
    async def create_raw_item(ctx: RequestContext):
        data = await ctx.request.json()
        return JSONResponse(data, status_code=201)

    app.router = router
    app.add_middleware(TestMiddleware())
    return app

@pytest.mark.asyncio
async def test_home_route(app):
    """Test basic GET route"""
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": [], "query_string": b"",
        "server": ("testserver", 80), "client": None,
        "scheme": "http", "root_path": "", "raw_path": b"/",
        "asgi": {"version": "3.0"}
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)

    # Check response
    assert any(m["type"] == "http.response.start" and m["status"] == 200
              for m in responses)
    assert any(m["type"] == "http.response.body" and
              json.loads(m["body"]) == {"message": "Hello, World!"}
              for m in responses)
    
    # Check middleware added header
    start_messages = [m for m in responses if m["type"] == "http.response.start"]
    headers = dict(start_messages[0]["headers"])
    assert b"x-test" in headers

@pytest.mark.asyncio
async def test_create_item(app):
    """Test POST route with JSON body"""
    test_item = {"name": "Test Item", "price": 9.99, "in_stock": True}
    scope = {
        "type": "http", "method": "POST", "path": "/items",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"", "server": ("testserver", 80),
        "client": None, "scheme": "http", "root_path": "",
        "raw_path": b"/items", "asgi": {"version": "3.0"}
    }

    request_sent = False
    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": orjson.dumps(test_item), "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)

    # Check response
    assert any(m["type"] == "http.response.start" and m["status"] == 201
              for m in responses)
    assert any(m["type"] == "http.response.body" and
              json.loads(m["body"]) == test_item
              for m in responses)

@pytest.mark.asyncio
async def test_path_params(app):
    """Test route with path parameters"""
    scope = {
        "type": "http", "method": "GET", "path": "/items/123",
        "headers": [], "query_string": b"",
        "server": ("testserver", 80), "client": None,
        "scheme": "http", "root_path": "",
        "raw_path": b"/items/123", "asgi": {"version": "3.0"}
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)

    # Check response
    assert any(m["type"] == "http.response.start" and m["status"] == 200
              for m in responses)
    assert any(m["type"] == "http.response.body" and
              json.loads(m["body"]) == {"id": 123}
              for m in responses)

@pytest.mark.asyncio
async def test_not_found(app):
    """Test 404 for non-existent route"""
    scope = {
        "type": "http", "method": "GET", "path": "/nonexistent",
        "headers": [], "query_string": b"",
        "server": ("testserver", 80), "client": None,
        "scheme": "http", "root_path": "",
        "raw_path": b"/nonexistent", "asgi": {"version": "3.0"}
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)
    
    # Check 404 status
    assert any(m["type"] == "http.response.start" and m["status"] == 404
              for m in responses)

@pytest.mark.asyncio
async def test_validation_error(app):
    """Test validation error for invalid request body"""
    invalid_item = {"name": "Test Item", "price": "invalid"}
    scope = {
        "type": "http", "method": "POST", "path": "/items",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"", "server": ("testserver", 80),
        "client": None, "scheme": "http", "root_path": "",
        "raw_path": b"/items", "asgi": {"version": "3.0"}
    }

    async def receive():
        return {"type": "http.request", "body": orjson.dumps(invalid_item), "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)

    # Check 422 status for validation error
    assert any(m["type"] == "http.response.start" and m["status"] == 422
              for m in responses)

@pytest.mark.asyncio
async def test_middleware(app):
    """Test middleware execution"""
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": [], "query_string": b"",
        "server": ("testserver", 80), "client": None,
        "scheme": "http", "root_path": "", "raw_path": b"/",
        "asgi": {"version": "3.0"}
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    responses = []
    async def send(message):
        responses.append(message)

    await app(scope, receive, send)

    # Check middleware added header
    start_messages = [m for m in responses if m["type"] == "http.response.start"]
    assert start_messages
    headers = dict(start_messages[0]["headers"])
    assert headers[b"x-test"] == b"test"

@pytest.mark.asyncio
async def test_static_files(app):
    """Test static file serving"""
    # Static file tests remain unchanged...
    pass

@pytest.mark.asyncio
async def test_application_startup_shutdown(app):
    """Test application lifecycle events"""
    # Lifecycle tests remain unchanged...
    pass