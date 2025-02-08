from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from keev.requests import Request
from keev.responses import Response
from keev.utils import get_logger
from keev.exceptions import PluginError
import time
from dataclasses import dataclass, field
import traceback

logger = get_logger("keev.plugins")

@runtime_checkable
class Plugin(Protocol):
    """Protocol that all plugins must implement"""
    
    async def pre_request(self, request: Request) -> None:
        """Called before request handling"""
        ...

    async def post_request(self, request: Request, response: Response) -> None:
        """Called after request handling"""
        ...

    async def on_startup(self) -> None:
        """Called during application startup"""
        ...

    async def on_shutdown(self) -> None:
        """Called during application shutdown"""
        ...

class PluginManager:
    def __init__(self):
        self.plugins: List[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        """Register a new plugin"""
        if not isinstance(plugin, Plugin):
            raise PluginError(f"Plugin must implement Plugin protocol: {plugin}")
        self.plugins.append(plugin)
        logger.info(f"Registered plugin: {plugin.__class__.__name__}")

    async def run_pre_request(self, request: Request) -> None:
        """Run all pre-request plugin hooks"""
        for plugin in self.plugins:
            try:
                await plugin.pre_request(request)
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} pre_request error: {e}")
                traceback.print_exc()

    async def run_post_request(self, request: Request, response: Response) -> None:
        """Run all post-request plugin hooks"""
        for plugin in self.plugins:
            try:
                await plugin.post_request(request, response)
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} post_request error: {e}")
                traceback.print_exc()

    async def startup(self) -> None:
        """Run all plugin startup hooks"""
        for plugin in self.plugins:
            try:
                await plugin.on_startup()
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} startup error: {e}")
                traceback.print_exc()

    async def shutdown(self) -> None:
        """Run all plugin shutdown hooks"""
        for plugin in self.plugins:
            try:
                await plugin.on_shutdown()
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} shutdown error: {e}")
                traceback.print_exc()

# Built-in plugins
class MetricsPlugin(Plugin):
    def __init__(self):
        self.request_count = 0
        self.request_times: Dict[str, List[float]] = {}

    async def pre_request(self, request: Request) -> None:
        request.state.start_time = time.time()
        self.request_count += 1

    async def post_request(self, request: Request, response: Response) -> None:
        duration = time.time() - request.state.start_time
        path = request.path
        if path not in self.request_times:
            self.request_times[path] = []
        self.request_times[path].append(duration)

    async def on_startup(self) -> None:
        logger.info("Metrics plugin started")

    async def on_shutdown(self) -> None:
        logger.info("Metrics plugin stopped")

class SecurityPlugin(Plugin):
    def __init__(self, 
                 allowed_hosts: List[str] = None,
                 max_content_length: int = 1024 * 1024,  # 1MB
                 secure_headers: bool = True):
        self.allowed_hosts = allowed_hosts or ["*"]
        self.max_content_length = max_content_length
        self.secure_headers = secure_headers

    async def pre_request(self, request: Request) -> None:
        # Host validation
        host = request.headers.get("host", "")
        if "*" not in self.allowed_hosts and host not in self.allowed_hosts:
            raise PluginError(f"Host not allowed: {host}")

        # Content length validation
        content_length = int(request.headers.get("content-length", 0))
        if content_length > self.max_content_length:
            raise PluginError("Content too large")

    async def post_request(self, request: Request, response: Response) -> None:
        if self.secure_headers:
            response.headers.update({
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                "Content-Security-Policy": "default-src 'self'"
            })

class CachePlugin(Plugin):
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, Any] = {}
        self.max_size = max_size

    def _get_cache_key(self, request: Request) -> str:
        return f"{request.method}:{request.path}"

    async def pre_request(self, request: Request) -> None:
        if request.method == "GET":
            key = self._get_cache_key(request)
            if key in self.cache:
                request.state.cached_response = self.cache[key]

    async def post_request(self, request: Request, response: Response) -> None:
        if request.method == "GET" and response.status_code == 200:
            key = self._get_cache_key(request)
            if len(self.cache) >= self.max_size:
                # Simple LRU: remove first item
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = response

    async def on_startup(self) -> None:
        logger.info("Cache plugin started")

    async def on_shutdown(self) -> None:
        logger.info("Cache plugin stopped")