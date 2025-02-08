"""Integration tests for application lifecycle and plugin system"""
import pytest
from keev import Application, Router, JSONResponse
from keev.plugins import Plugin
from typing import List, Dict, Any

class TestPlugin(Plugin):
    def __init__(self):
        self.startup_called = False
        self.shutdown_called = False
        self.request_count = 0
        self.processed_paths: List[str] = []
        self.responses: List[Dict[str, Any]] = []
        
    async def pre_request(self, request):
        self.request_count += 1
        self.processed_paths.append(request.path)
        
    async def post_request(self, request, response):
        self.responses.append({
            "path": request.path,
            "status": response.status_code
        })
        
    async def on_startup(self):
        self.startup_called = True
        
    async def on_shutdown(self):
        self.shutdown_called = True

@pytest.fixture
def app_with_plugins():
    """Create test application with plugins enabled"""
    app = Application(debug=True, enable_plugins=True)
    router = Router()
    
    @router.get("/")
    async def home():
        return JSONResponse({"status": "ok"})
        
    @router.get("/error")
    async def error():
        return JSONResponse({"error": "test error"}, status_code=500)
    
    app.router = router
    return app

@pytest.mark.asyncio
async def test_plugin_lifecycle(app_with_plugins):
    """Test complete plugin lifecycle with application"""
    plugin = TestPlugin()
    app_with_plugins.register_plugin(plugin)
    
    # Test startup
    await app_with_plugins.startup()
    assert plugin.startup_called
    
    # Test request processing
    for path in ["/", "/error", "/nonexistent"]:
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "asgi": {"version": "3.0"}
        }
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        async def send(message):
            pass
            
        await app_with_plugins(scope, receive, send)
    
    # Verify plugin tracked requests
    assert plugin.request_count == 3
    assert "/" in plugin.processed_paths
    assert "/error" in plugin.processed_paths
    assert "/nonexistent" in plugin.processed_paths
    
    # Verify response tracking
    assert any(r["path"] == "/" and r["status"] == 200 for r in plugin.responses)
    assert any(r["path"] == "/error" and r["status"] == 500 for r in plugin.responses)
    assert any(r["path"] == "/nonexistent" and r["status"] == 404 for r in plugin.responses)
    
    # Test shutdown
    await app_with_plugins.shutdown()
    assert plugin.shutdown_called

@pytest.mark.asyncio
async def test_multiple_plugins(app_with_plugins):
    """Test multiple plugins working together"""
    plugin1 = TestPlugin()
    plugin2 = TestPlugin()
    
    app_with_plugins.register_plugin(plugin1)
    app_with_plugins.register_plugin(plugin2)
    
    await app_with_plugins.startup()
    assert plugin1.startup_called and plugin2.startup_called
    
    # Make a request
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
    
    async def send(message):
        pass
        
    await app_with_plugins(scope, receive, send)
    
    # Verify both plugins processed the request
    assert plugin1.request_count == 1 and plugin2.request_count == 1
    assert len(plugin1.responses) == 1 and len(plugin2.responses) == 1
    
    await app_with_plugins.shutdown()
    assert plugin1.shutdown_called and plugin2.shutdown_called

@pytest.mark.asyncio
async def test_plugin_disabled_by_default():
    """Test that plugins are disabled by default"""
    app = Application(debug=True)  # plugins not enabled
    
    with pytest.raises(RuntimeError, match="Plugins are disabled"):
        app.register_plugin(TestPlugin())

@pytest.mark.asyncio
async def test_application_events(app_with_plugins):
    """Test application event handlers"""
    startup_called = False
    shutdown_called = False
    
    @app_with_plugins.on_event("startup")
    async def on_startup():
        nonlocal startup_called
        startup_called = True
    
    @app_with_plugins.on_event("shutdown")
    async def on_shutdown():
        nonlocal shutdown_called
        shutdown_called = True
    
    await app_with_plugins.startup()
    assert startup_called
    
    await app_with_plugins.shutdown()
    assert shutdown_called