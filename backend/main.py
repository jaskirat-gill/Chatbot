from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

# Load environment variables
load_dotenv()

# Global variables for RAG components
vectorstore = None
conversation_chain = None
chat_history = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    print("Starting up...")
    success = initialize_rag_system()
    if not success:
        print("Warning: RAG system failed to initialize. Check your configuration.")
    yield
    # Shutdown (cleanup if needed)
    print("Shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="JD AI Marketing Chatbot API",
    lifespan=lifespan
)

# Configure CORS
allowed_origins = os.getenv("FRONTEND_ORIGINS")
if allowed_origins:
    # Parse comma-separated origins
    origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
else:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

# Custom prompt template
CUSTOM_PROMPT = """You are a helpful AI assistant for JD AI Marketing Solutions, a company that helps small businesses implement AI solutions. 

Use the following pieces of context to answer the question at the end. If you don't know the answer or the information is not in the context, politely say that you don't have that specific information and offer to help with something else related to JD AI Marketing Solutions.

Be friendly, professional, and concise. When discussing our services, be enthusiastic but not pushy. Always prioritize providing value to the user.

Context:
{context}

Question: {question}

Helpful Answer:"""

def initialize_rag_system():
    """Initialize the RAG system with document loading and vector store creation."""
    global vectorstore, conversation_chain
    
    try:
        # Check if OpenAI API key is set
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Load documents
        print("Loading documents...")
        loader = DirectoryLoader(
            './documents',
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        documents = loader.load()
        print(f"Loaded {len(documents)} documents")
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        splits = text_splitter.split_documents(documents)
        print(f"Created {len(splits)} document chunks")
        
        # Create embeddings and vector store
        print("Creating embeddings and vector store...")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Check if vector store already exists
        chroma_db_path = "./chroma_db"
        if os.path.exists(chroma_db_path):
            print("Loading existing vector store...")
            vectorstore = Chroma(
                persist_directory=chroma_db_path,
                embedding_function=embeddings
            )
        else:
            print("Creating new vector store...")
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding=embeddings,
                persist_directory=chroma_db_path
            )
        print("Vector store ready")
        
        # Initialize LLM
        llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Create custom prompt
        qa_prompt = PromptTemplate.from_template(CUSTOM_PROMPT)
        
        # Create retrieval chain
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        # Configure retriever with better search parameters
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 6}  # Retrieve top 6 most relevant chunks
        )
        
        conversation_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | qa_prompt
            | llm
            | StrOutputParser()
        )
        
        print("RAG system initialized successfully")
        return True
        
    except Exception as e:
        print(f"Error initializing RAG system: {str(e)}")
        return False

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "JD AI Marketing Chatbot API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "rag_initialized": vectorstore is not None and conversation_chain is not None
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Chat endpoint that processes user messages and returns AI responses.
    Uses RAG to provide context-aware answers about JD AI Marketing Solutions.
    """
    if not conversation_chain or not vectorstore:
        raise HTTPException(
            status_code=503,
            detail="RAG system not initialized. Please check server logs and ensure OPENAI_API_KEY is set."
        )
    
    try:
        # Get or create chat history for this session
        if message.session_id not in chat_history:
            chat_history[message.session_id] = []
        
        # Query the conversation chain
        result = conversation_chain.invoke(message.message)
        
        # Update chat history
        chat_history[message.session_id].append((message.message, result))
        
        # Keep only last 10 exchanges to manage memory
        if len(chat_history[message.session_id]) > 10:
            chat_history[message.session_id] = chat_history[message.session_id][-10:]
        
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

@app.post("/api/reset")
async def reset_session(session_id: str = "default"):
    """Reset chat history for a session."""
    if session_id in chat_history:
        chat_history[session_id] = []
    return {"message": f"Session {session_id} reset successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
