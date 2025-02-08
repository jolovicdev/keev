from keev import Application, Router, Request, JSONResponse, BaseMiddleware
from keev.routing import RequestContext
from keev.utils import get_logger, setup_logging
from keev.static import StaticFiles
from keev.docs import get_docs_routes
from pydantic import BaseModel
from typing import Optional, List, Callable, Awaitable
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
import os
import time
from keev.responses import Response

# Set up logging with colors
setup_logging()
logger = get_logger("example")

# SQLAlchemy setup
DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Modern SQLAlchemy declarative base
class Base(DeclarativeBase):
    pass

# SQLAlchemy model
class ItemDB(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    in_stock = Column(Boolean, default=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic model
class Item(BaseModel):
    id: Optional[int] = None
    name: str
    price: float
    in_stock: bool = True

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "name": "Sample Item",
                "price": 9.99,
                "in_stock": True
            }
        }
    }

# Custom middleware
class TimingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        if isinstance(response, Response):
            response.headers["X-Process-Time"] = f"{duration:.3f}"
        return response

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        logger.info(f"Processing {request.method} {request.path}")
        response = await call_next(request)
        if isinstance(response, Response):
            logger.info(f"Completed {request.method} {request.path} - {response.status_code}")
        return response

# Database dependency
def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Create the application
app = Application(
    debug=True,
    title="Keev Example API",
    version="1.0.0",
    enable_plugins=False  # Plugins are optional and disabled by default
)

# Create a router
router = Router()

# Set up static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

# Create example static file
index_html = os.path.join(static_dir, "index.html")
if not os.path.exists(index_html):
    with open(index_html, "w") as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Keev Example</title>
        </head>
        <body>
            <h1>Welcome to Keev</h1>
            <p>A fast and simple ASGI framework</p>
            <ul>
                <li><a href="/items">List Items</a></li>
                <li><a href="/docs">API Documentation</a></li>
            </ul>
        </body>
        </html>
        """)

static = StaticFiles(static_dir)

# Define routes
@router.get("/")
async def home():
    """Root endpoint returning welcome message"""
    return JSONResponse({
        "message": "Welcome to Keev API",
        "endpoints": {
            "GET /": "This message",
            "GET /items": "List all items",
            "POST /items": "Create an item",
            "GET /items/{id}": "Get an item by ID",
            "GET /static/index.html": "Static HTML page",
            "GET /docs": "API Documentation (Swagger UI)",
            "GET /redoc": "API Documentation (ReDoc)"
        }
    })

@router.get("/items")
async def list_items():
    """Get all items from the database"""
    try:
        db = get_db()
        items = db.query(ItemDB).all()
        return JSONResponse([Item.model_validate(item).model_dump() for item in items])
    except Exception as e:
        logger.error(f"Error listing items: {e}")
        return JSONResponse({"error": "Failed to list items"}, status_code=500)

@router.post("/items")
async def create_item(ctx: RequestContext, item: Item):
    """Create a new item
    
    Expects a JSON object with the following fields:
    - name: string (required)
    - price: number (required)
    - in_stock: boolean (optional, default: true)
    """
    try:
        # Check content type
        content_type = ctx.request.headers.get("content-type", "").lower()
        if not content_type.startswith("application/json"):
            return JSONResponse(
                {"error": "Content-Type must be application/json"}, 
                status_code=415
            )
        
        # Item validation is handled by Pydantic
        db = get_db()
        try:
            db_item = ItemDB(**item.model_dump(exclude={"id"}))
            db.add(db_item)
            db.commit()
            db.refresh(db_item)
            
            return JSONResponse(Item.model_validate(db_item).model_dump(), status_code=201)
        except Exception as e:
            logger.error(f"Error creating item: {e}")
            db.rollback()
            return JSONResponse({"error": "Failed to create item in database"}, status_code=500)
        finally:
            db.close()
            
    except ValueError as e:
        return JSONResponse({
            "error": "Invalid request data",
            "detail": str(e),
            "expected_format": Item.model_json_schema()
        }, status_code=422)

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    """Get an item by ID
    
    Args:
        item_id: The numeric ID of the item to retrieve
    """
    try:
        db = get_db()
        item = db.query(ItemDB).filter(ItemDB.id == item_id).first()
        if not item:
            return JSONResponse({"error": "Item not found"}, status_code=404)
        return JSONResponse(Item.model_validate(item).model_dump())
    except Exception as e:
        logger.error(f"Error getting item {item_id}: {e}")
        return JSONResponse({"error": "Failed to get item"}, status_code=500)

@router.get("/static/{path:str}")
async def serve_static(ctx: RequestContext, path: str):
    """Serve static files"""
    try:
        return await static(ctx.request)
    except Exception as e:
        logger.error(f"Error serving static file {path}: {e}")
        return JSONResponse({"error": "Failed to serve file"}, status_code=500)

# Mount router and add middleware
app.router = router

# Add documentation routes
docs_router = get_docs_routes(app)
router.include_router(docs_router)

# Add middleware
app.add_middleware(LoggingMiddleware())
app.add_middleware(TimingMiddleware())

# Log registered routes once
logger.info("Registered routes:")
for route in router.routes:
    logger.info(f"  {', '.join(route.methods)} {route.path}")

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting server...")
    uvicorn.run(
        "example:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )