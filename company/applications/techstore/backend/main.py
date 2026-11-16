
from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes.auth import router as auth_router
from routes.orders import router as orders_router

import json

# Configure structured JSON logging
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "application": "techstore",
            "message": record.getMessage()
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())

logger = logging.getLogger("techstore")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(handler)
logger.propagate = False

# Locate the frontend directory
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Create the FastAPI application
app = FastAPI(
    title="TechStore API",
    description="Backend API for the TechStore electronics store",
    version="1.0.0"
)

# Register API routers
app.include_router(auth_router)
app.include_router(orders_router)

# Serve frontend CSS and JavaScript
app.mount(
    "/src",
    StaticFiles(directory=FRONTEND_DIR / "src"),
    name="static"
)

# Temporary products for testing
products = [
    {
        "id": 1,
        "name": "Gaming Laptop",
        "price": 1299.99,
        "description": "High-performance laptop for gaming."
    },
    {
        "id": 2,
        "name": "Wireless Mouse",
        "price": 39.99,
        "description": "Wireless mouse with adjustable DPI."
    },
    {
        "id": 3,
        "name": "Mechanical Keyboard",
        "price": 89.99,
        "description": "Mechanical keyboard with RGB lighting."
    }
]


@app.get("/")
def home():
    logger.info("TechStore homepage accessed")
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/products")
def get_products():
    logger.info("Product list requested")
    return products


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    logger.info("Product requested: ID %s", product_id)

    for product in products:
        if product["id"] == product_id:
            return product

    logger.warning("Product not found: ID %s", product_id)
    raise HTTPException(status_code=404, detail="Product not found")
