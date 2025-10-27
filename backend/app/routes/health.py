from fastapi import APIRouter
from ..config import tenants

router = APIRouter()

@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "JD AI Marketing Chatbot API",
        "status": "running",
        "version": "1.0.0"
    }

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "tenants_loaded": len(tenants) > 0
    }
