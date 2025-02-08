"""Unit tests for request and response handling"""
import pytest
from keev.requests import Request
from keev.responses import JSONResponse, HTMLResponse, Response
import json

@pytest.fixture
def mock_scope():
    return {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [
            (b"content-type", b"application/json"),
            (b"x-test-header", b"test-value")
        ],
        "query_string": b"key=value",
    }

@pytest.mark.asyncio
async def test_request_headers(mock_scope):
    """Test request headers parsing"""
    async def receive():
        return {"type": "http.request", "body": b""}
        
    request = Request(mock_scope, receive)
    assert request.headers["content-type"] == "application/json"
    assert request.headers["x-test-header"] == "test-value"

@pytest.mark.asyncio
async def test_request_query_params(mock_scope):
    """Test query parameter parsing"""
    async def receive():
        return {"type": "http.request", "body": b""}
        
    request = Request(mock_scope, receive)
    assert request.query_params["key"] == ["value"]

@pytest.mark.asyncio
async def test_json_request_body():
    """Test JSON request body parsing"""
    test_data = {"test": "value"}
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(b"content-type", b"application/json")],
    }
    
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(test_data).encode(),
            "more_body": False
        }
        
    request = Request(scope, receive)
    body = await request.json()
    assert body == test_data

@pytest.mark.asyncio
async def test_json_response():
    """Test JSON response formatting"""
    data = {"message": "test"}
    response = JSONResponse(data, status_code=201, headers={"X-Test": "test"})
    
    assert response.status_code == 201
    assert response.headers["content-type"] == "application/json"
    assert response.headers["X-Test"] == "test"
    
    # Test response encoding
    encoded = response._encode_content()
    decoded = json.loads(encoded)
    assert decoded == data

@pytest.mark.asyncio
async def test_html_response():
    """Test HTML response"""
    html = "<h1>Test</h1>"
    response = HTMLResponse(html, status_code=200)
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html"
    assert response._encode_content().decode() == html

@pytest.mark.asyncio
async def test_response_headers():
    """Test response headers handling"""
    response = Response(
        "test",
        status_code=200,
        headers={
            "X-Custom": "value",
            "Content-Type": "text/plain"
        }
    )
    
    assert response.headers["x-custom"] == "value"
    assert response.headers["content-type"] == "text/plain"

@pytest.mark.asyncio
async def test_response_send():
    """Test response sending through ASGI interface"""
    response = JSONResponse({"test": "value"})
    
    messages = []
    async def send(message):
        messages.append(message)
    
    await response(None, None, send)
    
    # Check start message
    assert any(
        m["type"] == "http.response.start" and
        m["status"] == 200 and
        (b"content-type", b"application/json") in m["headers"]
        for m in messages
    )
    
    # Check body message
    assert any(
        m["type"] == "http.response.body" and
        json.loads(m["body"]) == {"test": "value"}
        for m in messages
    )