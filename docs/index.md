# Keev API Guide

## Routing

Define routes using decorators:

```python
from keev import Router

router = Router()

@router.get("/items")
async def list_items():
    return {"items": []}

@router.post("/items")
async def create_item(item: Item):
    return item

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    return {"id": item_id}
```

## Request Validation

Use Pydantic models for automatic validation:

```python
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    in_stock: bool = True

@router.post("/items")
async def create_item(item: Item):
    return item
```

## Middleware

Create custom middleware:

```python
from keev import BaseMiddleware
from typing import Callable, Awaitable
import time

class TimingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        response.headers["X-Process-Time"] = f"{duration:.3f}"
        return response

# Add to application
app.add_middleware(TimingMiddleware())
```

## Database Integration

SQLAlchemy integration example:

```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Setup
engine = create_engine("sqlite:///./test.db")
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class ItemDB(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String)

Base.metadata.create_all(bind=engine)

# Use in routes
def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

@router.get("/items")
async def list_items():
    db = get_db()
    items = db.query(ItemDB).all()
    return items
```

## Static Files

Serve static files:

```python
from keev.static import StaticFiles
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
static = StaticFiles(static_dir)

@router.get("/static/{path:str}")
async def serve_static(ctx: RequestContext, path: str):
    return await static(ctx.request)
```

## Plugin System

Create custom plugins:

```python
from keev.plugins import Plugin

class LoggingPlugin(Plugin):
    async def pre_request(self, request):
        print(f"Processing {request.method} {request.path}")
        
    async def post_request(self, request, response):
        print(f"Completed {request.method} {request.path}")

# Enable and register
app = Application(enable_plugins=True)
app.register_plugin(LoggingPlugin())
```

## API Documentation

Documentation is automatically generated. Access at:
- /docs - Swagger UI
- /redoc - ReDoc UI
- /openapi.json - OpenAPI specification

## Testing

Create tests using pytest:

```python
import pytest
from keev import Application, Router, JSONResponse

@pytest.fixture
def app():
    app = Application()
    router = Router()
    
    @router.get("/")
    async def home():
        return JSONResponse({"message": "Hello"})
    
    app.router = router
    return app

@pytest.mark.asyncio
async def test_home_route(app):
    # Your test code here
    pass
```

## Performance

Run benchmarks:

```bash
python benchmark.py
```

This will compare performance against FastAPI in various scenarios.