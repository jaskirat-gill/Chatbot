from fastapi import APIRouter, HTTPException, Header
from ..models.chat import ChatMessage, ChatResponse
from ..services import rag_service

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage, tenant_id: str = Header(alias="X-Tenant-ID")):
    """
    Chat endpoint that processes user messages and returns AI responses.
    Uses RAG to provide context-aware answers about JD AI Marketing Solutions.
    """
    try:
        rag = rag_service.get_tenant_rag(tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        # Get or create chat history for this session
        if message.session_id not in rag["chat_history"]:
            rag["chat_history"][message.session_id] = []

        # Query the conversation chain
        result = rag["conversation_chain"].invoke(message.message)

        # Update chat history
        rag["chat_history"][message.session_id].append((message.message, result))

        # Keep only last 10 exchanges to manage memory
        if len(rag["chat_history"][message.session_id]) > 10:
            rag["chat_history"][message.session_id] = rag["chat_history"][message.session_id][-10:]

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
async def reset_session(session_id: str = "default", tenant_id: str = Header(alias="X-Tenant-ID")):
    """Reset chat history for a session."""
    try:
        rag = rag_service.get_tenant_rag(tenant_id)
        if session_id in rag["chat_history"]:
            rag["chat_history"][session_id] = []
        return {"message": f"Session {session_id} reset successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
