from fastapi import APIRouter, HTTPException
from ..models.chat import ChatMessage, ChatResponse
from ..services import rag_service

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Chat endpoint that processes user messages and returns AI responses.
    Uses RAG to provide context-aware answers about JD AI Marketing Solutions.
    """
    if not rag_service.conversation_chain or not rag_service.vectorstore:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized. Please check server logs and ensure OPENAI_API_KEY is set."
        )

    try:
        # Get or create chat history for this session
        if message.session_id not in rag_service.chat_history:
            rag_service.chat_history[message.session_id] = []

        # Query the conversation chain
        result = rag_service.conversation_chain.invoke(message.message)

        # Update chat history
        rag_service.chat_history[message.session_id].append((message.message, result))

        # Keep only last 10 exchanges to manage memory
        if len(rag_service.chat_history[message.session_id]) > 10:
            rag_service.chat_history[message.session_id] = rag_service.chat_history[message.session_id][-10:]

        return ChatResponse(
            response=result,
            session_id=message.session_id
        )

    except Exception as e:
        print(f"Error processing chat message: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )

@router.post("/reset")
async def reset_session(session_id: str = "default"):
    """Reset chat history for a session."""
    if session_id in rag_service.chat_history:
        rag_service.chat_history[session_id] = []
    return {"message": f"Session {session_id} reset successfully"}
