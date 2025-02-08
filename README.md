# Keev

A lightweight ASGI web framework for Python that focuses on simplicity and performance.

## Features

- FastAPI-like route decorators
- Built-in request validation using Pydantic
- Automatic OpenAPI docs (Swagger UI & ReDoc)
- SQLAlchemy integration
- Static file serving
- Middleware support
- Plugin system
- Colored logging

## Installation

```bash
pip install keev
```

## Quick Start

```python
from keev import Application, Router, JSONResponse
from pydantic import BaseModel

app = Application()
router = Router()

class Item(BaseModel):
    name: str
    price: float

@router.get("/")
async def read_root():
    return JSONResponse({"message": "Hello World"})

@router.post("/items")
async def create_item(item: Item):
    return JSONResponse(item.model_dump(), status_code=201)

app.router = router

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Running the Example

1. Clone the repository:
```bash
git clone https://github.com/yourusername/keev.git
cd keev
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the example app:
```bash
python example.py
```

The server will start at http://localhost:8000. Visit:
- http://localhost:8000/ - API root
- http://localhost:8000/docs - Swagger UI documentation
- http://localhost:8000/redoc - ReDoc documentation

## Development

### Running Tests

```bash
pytest tests/
```

### Running Benchmarks

```bash
python benchmark.py
```

## Project Status

This is a hobby project created for learning purposes. While functional, it's not recommended for production use.

## License

MIT