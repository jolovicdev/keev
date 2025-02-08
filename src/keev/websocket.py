from typing import Any, Dict, Callable, Awaitable, Optional
from keev.utils import get_logger
import websockets
import json
import asyncio
from dataclasses import dataclass

logger = get_logger("keev.websocket")

@dataclass
class WebSocketState:
    """WebSocket connection state"""
    connected: bool = False
    closed: bool = False
    close_code: Optional[int] = None
    close_reason: Optional[str] = None

class WebSocket:
    def __init__(self, scope: Dict, receive: Callable, send: Callable):
        self.scope = scope
        self.receive = receive
        self.send = send
        self.state = WebSocketState()
        self._ws: Optional[websockets.WebSocketServerProtocol] = None

    async def accept(self, subprotocol: Optional[str] = None):
        """Accept the WebSocket connection"""
        if self.state.connected:
            return

        await self.send({
            "type": "websocket.accept",
            "subprotocol": subprotocol
        })
        self.state.connected = True
        logger.info("WebSocket connection accepted")

    async def receive_text(self) -> str:
        """Receive text message"""
        message = await self.receive()
        
        if message["type"] == "websocket.disconnect":
            self.state.closed = True
            self.state.close_code = message.get("code", 1000)
            raise websockets.ConnectionClosed(
                self.state.close_code,
                message.get("reason", "")
            )
            
        if message["type"] != "websocket.receive":
            raise ValueError(f"Unexpected message type: {message['type']}")
            
        return message.get("text", "")

    async def receive_json(self) -> Any:
        """Receive JSON message"""
        text = await self.receive_text()
        return json.loads(text)

    async def receive_bytes(self) -> bytes:
        """Receive bytes message"""
        message = await self.receive()
        
        if message["type"] == "websocket.disconnect":
            self.state.closed = True
            self.state.close_code = message.get("code", 1000)
            raise websockets.ConnectionClosed(
                self.state.close_code,
                message.get("reason", "")
            )
            
        if message["type"] != "websocket.receive":
            raise ValueError(f"Unexpected message type: {message['type']}")
            
        return message.get("bytes", b"")

    async def send_text(self, text: str):
        """Send text message"""
        if self.state.closed:
            raise websockets.ConnectionClosed(
                self.state.close_code or 1006,
                "WebSocket is closed"
            )
            
        await self.send({
            "type": "websocket.send",
            "text": text
        })

    async def send_json(self, data: Any):
        """Send JSON message"""
        await self.send_text(json.dumps(data))

    async def send_bytes(self, data: bytes):
        """Send bytes message"""
        if self.state.closed:
            raise websockets.ConnectionClosed(
                self.state.close_code or 1006,
                "WebSocket is closed"
            )
            
        await self.send({
            "type": "websocket.send",
            "bytes": data
        })

    async def close(self, code: int = 1000, reason: str = ""):
        """Close the WebSocket connection"""
        if not self.state.closed:
            await self.send({
                "type": "websocket.close",
                "code": code,
                "reason": reason
            })
            self.state.closed = True
            self.state.close_code = code
            self.state.close_reason = reason
            logger.info(f"WebSocket connection closed: {code} {reason}")

class WebSocketRoute:
    """Base class for WebSocket routes"""
    encoding: str = "text"  # or "bytes" or "json"

    async def on_connect(self, websocket: WebSocket) -> bool:
        """Called when client connects. Return True to accept."""
        return True

    async def on_receive(self, websocket: WebSocket, data: Any):
        """Called when data is received"""
        pass

    async def on_disconnect(self, websocket: WebSocket, close_code: int):
        """Called when client disconnects"""
        pass

    async def __call__(self, scope: Dict, receive: Callable, send: Callable):
        websocket = WebSocket(scope, receive, send)
        
        try:
            # Handle connection
            if await self.on_connect(websocket):
                await websocket.accept()
            else:
                await websocket.close(1003, "Rejected")
                return

            # Main message loop
            while True:
                try:
                    if self.encoding == "text":
                        data = await websocket.receive_text()
                    elif self.encoding == "bytes":
                        data = await websocket.receive_bytes()
                    elif self.encoding == "json":
                        data = await websocket.receive_json()
                    else:
                        raise ValueError(f"Invalid encoding: {self.encoding}")
                        
                    await self.on_receive(websocket, data)
                    
                except websockets.ConnectionClosed:
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if not websocket.state.closed:
                await websocket.close(1011, "Internal error")
                
        finally:
            if not websocket.state.closed:
                await websocket.close()
            await self.on_disconnect(websocket, websocket.state.close_code or 1006)

class WebSocketPool:
    """Manage multiple WebSocket connections"""
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Add a WebSocket connection to the pool"""
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from the pool"""
        async with self._lock:
            self.active_connections.remove(websocket)

    async def broadcast_text(self, message: str):
        """Broadcast text message to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except websockets.ConnectionClosed:
                await self.disconnect(connection)

    async def broadcast_json(self, data: Any):
        """Broadcast JSON message to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except websockets.ConnectionClosed:
                await self.disconnect(connection)

    async def broadcast_bytes(self, data: bytes):
        """Broadcast bytes message to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_bytes(data)
            except websockets.ConnectionClosed:
                await self.disconnect(connection)