# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         User Browser                         │
│                     (http://localhost:5173)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ HTTP/REST API
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      Vite + React                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    App.jsx                              │ │
│  │  - Chat Interface                                       │ │
│  │  - Message Display                                      │ │
│  │  - User Input                                           │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ axios POST /api/chat
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI Backend                          │
│                  (http://localhost:8000)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    main.py                              │ │
│  │                                                          │ │
│  │  Endpoints:                                             │ │
│  │  - POST /api/chat    -> Process chat messages          │ │
│  │  - POST /api/reset   -> Reset conversation             │ │
│  │  - GET  /api/health  -> Health check                   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ RAG Pipeline
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    LangChain RAG System                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. Document Loader                                  │   │
│  │     └─> Load .md files from documents/              │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │  2. Text Splitter                                    │   │
│  │     └─> Split into chunks (1000 chars, 200 overlap) │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │  3. OpenAI Embeddings                                │   │
│  │     └─> Convert text to vectors                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │  4. ChromaDB Vector Store                            │   │
│  │     └─> Store and search embeddings                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │  5. Retriever                                        │   │
│  │     └─> Find top 4 relevant chunks                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │  6. Conversational Chain                             │   │
│  │     ├─> GPT-3.5-turbo LLM                           │   │
│  │     ├─> Custom prompt template                       │   │
│  │     └─> Conversation memory                          │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ API Calls
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      OpenAI API                              │
│  - Embeddings (text-embedding-ada-002)                      │
│  - Chat Completion (gpt-3.5-turbo)                          │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Initial Setup (Startup)

1. **Load Documents**: Read all `.md` files from `backend/documents/`
2. **Split Text**: Break documents into 1000-character chunks with 200-character overlap
3. **Create Embeddings**: Convert each chunk to a vector using OpenAI's embedding model
4. **Build Vector Store**: Store embeddings in ChromaDB (persisted to `chroma_db/`)
5. **Initialize Chain**: Set up the conversational retrieval chain with memory

### Chat Request Flow

```
User Input → Frontend
           ↓
POST /api/chat with message
           ↓
Backend receives request
           ↓
Retriever searches ChromaDB
           ↓
Top 4 relevant chunks retrieved
           ↓
LLM receives:
  - User question
  - Retrieved context
  - Chat history
  - Custom prompt
           ↓
GPT-3.5-turbo generates response
           ↓
Response returned to frontend
           ↓
Display to user
```

## Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **LangChain**: Framework for building LLM applications
- **OpenAI**: GPT-3.5-turbo for chat, text-embedding-ada-002 for embeddings
- **ChromaDB**: Vector database for semantic search
- **Python-dotenv**: Environment variable management

### Frontend
- **React**: UI library for building interactive interfaces
- **Vite**: Next-generation frontend build tool
- **Axios**: HTTP client for API requests
- **CSS3**: Styling with gradients and animations

## Key Components

### Backend (`main.py`)

- **`initialize_rag_system()`**: Sets up the RAG pipeline on startup
- **`chat()`**: Main endpoint for processing chat messages
- **`reset_session()`**: Clears conversation history
- **`chat_history`**: In-memory dictionary storing conversation state

### Frontend (`App.jsx`)

- **Message Display**: Shows conversation history
- **Input Form**: Captures user messages
- **Loading State**: Shows animated dots while waiting
- **Error Handling**: Displays API errors gracefully

## Scalability Considerations

### Current Implementation (POC)
- Single server instance
- In-memory chat history
- Local ChromaDB storage
- No authentication

### Production Improvements
- **Database**: PostgreSQL with pgvector for vector storage
- **Session Management**: Redis for distributed chat history
- **Authentication**: JWT tokens or OAuth
- **Rate Limiting**: Prevent API abuse
- **Caching**: Cache frequent queries
- **Load Balancing**: Multiple backend instances
- **Monitoring**: Logging, metrics, error tracking
- **CDN**: Serve frontend assets globally

## Performance Metrics

- **Initial Load**: ~5-10 seconds (document indexing)
- **Subsequent Starts**: ~1-2 seconds (loads from persisted ChromaDB)
- **Query Response**: ~2-4 seconds (retrieval + LLM generation)
- **Memory Usage**: ~500MB (embeddings + model)

## Security Considerations

### Current
- CORS enabled for localhost
- API key in environment variable
- No data persistence beyond session

### Production Needs
- HTTPS/TLS encryption
- API key rotation
- Rate limiting
- Input validation & sanitization
- SQL injection prevention (if using SQL DB)
- XSS protection
- CSRF tokens
- Audit logging
- Data encryption at rest

## Cost Estimation

### OpenAI API Usage (Approximate)
- **Embeddings**: $0.0001 per 1K tokens
- **GPT-3.5-turbo**: $0.0015 per 1K input tokens, $0.002 per 1K output tokens

### Example Monthly Costs (1000 queries)
- Document embedding (one-time): ~$0.05
- Chat queries: ~$3-5/month
- Total: ~$5/month for moderate usage

## Extending the System

### Add New Features
1. **Streaming Responses**: Use SSE or WebSockets for real-time streaming
2. **File Upload**: Allow users to upload documents for analysis
3. **Multi-language**: Add i18n support
4. **Voice Input**: Integrate speech-to-text
5. **Analytics**: Track usage patterns and popular queries

### Customize Behavior
1. **Prompt Engineering**: Modify `CUSTOM_PROMPT` for different personalities
2. **Model Selection**: Switch to GPT-4 for better quality
3. **Retrieval Tuning**: Adjust chunk size, overlap, and k value
4. **Memory Management**: Implement sliding window or summary memory

### Integration Options
1. **Slack/Discord**: Create bot integrations
2. **Mobile App**: Build React Native version
3. **WordPress Plugin**: Embed chatbot in websites
4. **API Gateway**: Expose as public API
5. **Zapier/Make**: Connect to automation workflows
