import os
import mimetypes
from pathlib import Path
from typing import List, Optional
from keev.responses import Response
import aiofiles
from keev.responses import JSONResponse
from keev.utils import get_logger

logger = get_logger("keev.static")

class StaticFiles:
    def __init__(self, directory: str):
        """Initialize static file handler with a directory"""
        self.directory = Path(directory)
        if not self.directory.exists():
            os.makedirs(str(self.directory))
        logger.info(f"Serving static files from: {self.directory}")

    async def __call__(self, request) -> Optional[Response]:
        """Handle static file request"""
        path = request.path_params.get("path", "")
        file_path = self.directory / path

        # Security check - prevent directory traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(self.directory.resolve())):
                logger.warning(f"Attempted directory traversal: {path}")
                return JSONResponse({"error": "Not Found"}, status_code=404)
        except Exception:
            logger.warning(f"Invalid path: {path}")
            return JSONResponse({"error": "Not Found"}, status_code=404)

        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"File not found: {path}")
            return JSONResponse({"error": "Not Found"}, status_code=404)

        try:
            # Get proper content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            if not content_type:
                # Default to octet-stream if type cannot be guessed
                content_type = "application/octet-stream"

            async with aiofiles.open(file_path, mode="rb") as f:
                content = await f.read()

            logger.info(f"Serving file: {path}")
            return Response(
                content,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                    "Cache-Control": "public, max-age=3600",
                }
            )
        except Exception as e:
            logger.error(f"Error serving file {path}: {e}")
            return JSONResponse({"error": "Internal Server Error"}, status_code=500)

    def write_file(self, path: str, content: str) -> None:
        """Write content to a static file"""
        file_path = self.directory / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        logger.info(f"Created static file: {path}")

    def read_file(self, path: str) -> Optional[str]:
        """Read content from a static file"""
        file_path = self.directory / path
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"File not found: {path}")
            return None
        try:
            with open(file_path, "r") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return None

    def delete_file(self, path: str) -> bool:
        """Delete a static file"""
        file_path = self.directory / path
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"File not found: {path}")
            return False
        try:
            os.remove(file_path)
            logger.info(f"Deleted file: {path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")
            return False

    def list_files(self) -> List[str]:
        """List all static files"""
        files = []
        for file_path in self.directory.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(self.directory))
                files.append(rel_path)
        return files