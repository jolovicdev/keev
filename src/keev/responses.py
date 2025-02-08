from typing import Any, Dict, List, Optional, Union
from http import HTTPStatus
from keev.utils import json_dumps

class Response:
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: Optional[str] = None,
    ):
        self.content = content
        self.status_code = status_code
        self._headers: Dict[str, str] = {}
        
        # Initialize default headers first
        if media_type:
            self._headers["content-type"] = media_type
        else:
            self._headers["content-type"] = "text/plain"
            
        # Add custom headers
        if headers:
            for key, value in headers.items():
                self._headers[key.lower()] = str(value)

    def add_header(self, key: str, value: str) -> None:
        """Add a header with case-insensitive key"""
        self._headers[key.lower()] = str(value)

    @property
    def headers(self) -> Dict[str, str]:
        """Get headers with case-insensitive access"""
        return CaseInsensitiveDict(self._headers)

    async def __call__(self, scope, receive, send) -> None:
        body = self._encode_content()
        headers = self._prepare_headers()

        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })

    def _encode_content(self) -> bytes:
        if isinstance(self.content, (str, bytes)):
            return self.content.encode("utf-8") if isinstance(self.content, str) else self.content
        return str(self.content).encode("utf-8")

    def _prepare_headers(self) -> List[tuple]:
        return [
            (k.lower().encode("latin-1"), str(v).encode("latin-1"))
            for k, v in self._headers.items()
        ]

class CaseInsensitiveDict(dict):
    """Dictionary with case-insensitive key access"""
    def __init__(self, data: Dict[str, str]):
        self._store: Dict[str, str] = {}
        for key, value in data.items():
            self._store[key.lower()] = value

    def __getitem__(self, key: str) -> str:
        return self._store[key.lower()]

    def __setitem__(self, key: str, value: str) -> None:
        self._store[key.lower()] = value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._store

class JSONResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            content,
            status_code=status_code,
            headers=headers,
            media_type="application/json"
        )

    def _encode_content(self) -> bytes:
        return json_dumps(self.content)

class HTMLResponse(Response):
    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            content,
            status_code=status_code,
            headers=headers,
            media_type="text/html"
        )

class StreamingResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: Optional[str] = None,
    ):
        super().__init__(
            content,
            status_code=status_code,
            headers=headers,
            media_type=media_type
        )

    async def __call__(self, scope, receive, send) -> None:
        headers = self._prepare_headers()

        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": headers,
        })

        async for chunk in self.content:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            elif not isinstance(chunk, bytes):
                chunk = str(chunk).encode("utf-8")

            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": True,
            })

        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })