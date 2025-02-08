from typing import Awaitable, Callable, Dict, List, Optional, Any
from contextlib import asynccontextmanager
from keev.middleware import BaseMiddleware
from keev.requests import Request
from keev.responses import Response, JSONResponse
from keev.utils import get_logger
from keev.plugins import PluginManager, Plugin
from keev.exceptions import HTTPException, InternalServerError
import asyncio
import traceback

logger = get_logger("keev.app")

class Application:
    def __init__(self, debug: bool = False, title: str = "Keev API", version: str = "1.0.0", enable_plugins: bool = False):
        self.middleware: List[BaseMiddleware] = []
        self.router = None
        self.debug = debug
        self.title = title
        self.version = version
        self.state: Dict[str, Any] = {}
        self._lifespan_manager = None
        self._startup_complete = False
        self._shutdown_complete = False
        self._startup_handlers = []
        self._shutdown_handlers = []
        self.plugin_manager = PluginManager() if enable_plugins else None
        self._plugins_enabled = enable_plugins
        
    @asynccontextmanager
    async def lifespan(self):
        try:
            await self.startup()
            yield
        finally:
            await self.shutdown()

    async def startup(self):
        if self._startup_complete:
            return
        
        try:
            logger.info("Starting up application")
            
            # Run startup handlers
            for handler in self._startup_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error(f"Error in startup handler: {e}")
                    if self.debug:
                        traceback.print_exc()
                    raise
            
            if self._plugins_enabled:
                await self.plugin_manager.startup()
            
            if self._lifespan_manager:
                try:
                    await self._lifespan_manager.__aenter__()
                except Exception as e:
                    logger.error(f"Error during startup: {e}")
                    if self.debug:
                        traceback.print_exc()
                    raise
            
            self._startup_complete = True
            logger.info("Application startup complete")
        except Exception as e:
            logger.error(f"Startup failed: {e}")
            if self.debug:
                traceback.print_exc()
            raise

    async def shutdown(self):
        if self._shutdown_complete:
            return
        
        try:
            logger.info("Shutting down application")
            
            # Run shutdown handlers
            for handler in self._shutdown_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error(f"Error in shutdown handler: {e}")
                    if self.debug:
                        traceback.print_exc()

            if self._plugins_enabled:
                await self.plugin_manager.shutdown()
            
            if self._lifespan_manager:
                try:
                    await self._lifespan_manager.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Error during shutdown: {e}")
                    if self.debug:
                        traceback.print_exc()
            
            self._shutdown_complete = True
            logger.info("Application shutdown complete")
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            if self.debug:
                traceback.print_exc()
            raise

    def register_plugin(self, plugin: Plugin) -> None:
        """Register a custom plugin"""
        if not self._plugins_enabled:
            raise RuntimeError("Plugins are disabled. Enable plugins by setting enable_plugins=True in Application constructor.")
        self.plugin_manager.register(plugin) 

    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        if not self.router:
            raise RuntimeError("No router configured. Set app.router before running the application.")

        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return
            
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
            return
            
        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return
            
        raise ValueError(f"Unknown scope type: {scope['type']}")

    async def _handle_lifespan(self, scope: Dict, receive: Callable, send: Callable) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self.startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return
            elif message["type"] == "lifespan.shutdown":
                try:
                    await self.shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as e:
                    await send({"type": "lifespan.shutdown.failed", "message": str(e)})
                return

    async def _handle_http(self, scope: Dict, receive: Callable, send: Callable) -> None:
        try:
            request = Request(scope, receive)
            
            # Run plugin pre-request hooks if enabled
            if self._plugins_enabled:
                await self.plugin_manager.run_pre_request(request)
            
            response = await self.handle_request(request)
            
            # Run plugin post-request hooks if enabled
            if self._plugins_enabled:
                await self.plugin_manager.run_post_request(request, response)
            
            await response(scope, receive, send)
            
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            if self.debug:
                traceback.print_exc()
            error_response = JSONResponse(
                {
                    "error": str(e) if self.debug else "Internal Server Error",
                    "status_code": 500,
                    "path": scope.get("path", "")
                },
                status_code=500
            )
            await error_response(scope, receive, send)

    async def _handle_websocket(self, scope: Dict, receive: Callable, send: Callable) -> None:
        try:
            response = await self.router.handle_request(Request(scope, receive))
            if response:
                await response(scope, receive, send)
            else:
                logger.warning(f"No WebSocket handler found for path: {scope['path']}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if self.debug:
                traceback.print_exc()

    async def handle_request(self, request: Request) -> Response:
        try:
            # Get base response from router
            response = await self.router.handle_request(request)

            # Apply middleware in reverse order
            for middleware in reversed(self.middleware):
                try:
                    async def call_next(req: Request) -> Response:
                        return response
                    response = await middleware(request, call_next)
                except Exception as e:
                    logger.error(f"Middleware error: {e}")
                    if self.debug:
                        traceback.print_exc()
                    raise

            return response
                
        except Exception as e:
            if isinstance(e, HTTPException):
                return JSONResponse(
                    {"error": e.detail, "status_code": e.status_code},
                    status_code=e.status_code,
                    headers=e.headers
                )
            raise InternalServerError(str(e) if self.debug else None) from e

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        """Add middleware to the application"""
        logger.debug(f"Adding middleware: {middleware.__class__.__name__}")
        if not isinstance(middleware, BaseMiddleware):
            raise TypeError("Middleware must be an instance of BaseMiddleware")
        self.middleware.append(middleware)
        logger.debug(f"Added middleware: {middleware.__class__.__name__}")

    def mount(self, path: str, app: 'Application') -> None:
        """Mount another application at the specified path"""
        if not path.startswith("/"):
            path = f"/{path}"
        if not self.router:
            raise RuntimeError("No router configured. Set app.router before mounting applications.")
        self.router.include_router(app.router, prefix=path)
        logger.debug(f"Mounted application at path: {path}")

    def on_event(self, event_type: str):
        """Decorator for registering event handlers"""
        def decorator(func: Callable):
            if event_type == "startup":
                self._startup_handlers.append(func)
            elif event_type == "shutdown":
                self._shutdown_handlers.append(func)
            else:
                raise ValueError(f"Unknown event type: {event_type}")
            return func
        return decorator