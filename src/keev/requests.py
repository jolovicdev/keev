from typing import Callable, Dict, List, Optional, Union
from urllib.parse import parse_qs

class Request:
    def __init__(self, scope: Dict, receive: Callable):
        self.scope = scope
        self.receive = receive
        self._body: Optional[bytes] = None

    @property
    def method(self) -> str:
        return self.scope["method"]

    @property
    def path(self) -> str:
        return self.scope["path"]

    @property
    def headers(self) -> Dict[str, str]:
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in self.scope["headers"]
        }

    @property
    def query_params(self) -> Dict[str, List[str]]:
        return parse_qs(self.scope["query_string"].decode("latin-1"))

    async def body(self) -> bytes:
        if self._body is None:
            self._body = b""
            more_body = True
            while more_body:
                message = await self.receive()
                self._body += message.get("body", b"")
                more_body = message.get("more_body", False)
        return self._body

    async def json(self) -> Union[Dict, List]:
        import json
        return json.loads(await self.body())