from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.config import settings
from app.routes.health import router as health_router
from app.routes.chat import router as chat_router

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    print("Starting up...")
    yield
    # Shutdown (cleanup if needed)
    print("Shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="JD AI Marketing Chatbot API",
    lifespan=lifespan
)

# Configure CORS
origins = [o.strip() for o in settings.frontend_origins.split(",") if o.strip()] if settings.frontend_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # Changed to False to allow "*" origins
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with API versioning
app.include_router(health_router, prefix="/v1", tags=["health"])
app.include_router(chat_router, prefix="/v1/api", tags=["chat"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
