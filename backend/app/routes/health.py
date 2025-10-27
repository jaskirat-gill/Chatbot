from fastapi import APIRouter
from ..services import rag_service

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
        "rag_initialized": rag_service.vectorstore is not None and rag_service.conversation_chain is not None
    }
