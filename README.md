# JD AI Marketing Solutions - RAG Chatbot POC

A proof-of-concept chatbot powered by OpenAI, LangChain, and FastAPI that demonstrates Retrieval-Augmented Generation (RAG) technology for JD AI Marketing Solutions, an AI consultancy helping small businesses implement AI solutions.

## 🌟 Features

- **RAG-based Architecture**: Uses Retrieval-Augmented Generation to provide accurate, context-aware responses
- **Vector Database**: Powered by ChromaDB for efficient document retrieval
- **Modern UI**: Clean, responsive React interface built with Vite
- **FastAPI Backend**: High-performance Python API
- **Conversational Memory**: Maintains context across conversations
- **Document-Grounded**: Responses based on actual company documents

## 📁 Project Structure

```
Chatbot/
├── backend/
│   ├── documents/               # Reference documents for RAG
│   │   ├── company_overview.md
│   │   ├── solutions_catalog.md
│   │   ├── case_studies.md
│   │   └── faq.md
│   ├── main.py                 # FastAPI application
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example           # Environment variables template
│   └── .gitignore
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main React component
│   │   ├── App.css            # Styles
│   │   ├── main.jsx           # Entry point
│   │   └── index.css          # Global styles
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── .gitignore
└── README.md
```

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- Node.js 18 or higher
- OpenAI API key

### Backend Setup

1. **Navigate to the backend directory:**
   ```powershell
   cd backend
   ```

2. **Create a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```powershell
   cp .env.example .env
   ```
   
   Edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-your-api-key-here
   ```

5. **Run the backend server:**
   ```powershell
   python main.py
   ```
   
   The API will be available at `http://localhost:8000`
   - API docs: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/api/health`

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```powershell
   cd frontend
   ```

2. **Install dependencies:**
   ```powershell
   npm install
   ```

3. **Run the development server:**
   ```powershell
   npm run dev
   ```
   
   The frontend will be available at `http://localhost:5173`

## 🔧 How It Works

### RAG Pipeline

1. **Document Loading**: Markdown documents are loaded from the `backend/documents/` directory
2. **Text Splitting**: Documents are split into chunks for efficient retrieval
3. **Embedding**: Text chunks are converted to embeddings using OpenAI's embedding model
4. **Vector Storage**: Embeddings are stored in ChromaDB for similarity search
5. **Retrieval**: When a user asks a question, relevant document chunks are retrieved
6. **Generation**: The LLM generates a response using the retrieved context

### API Endpoints

- `GET /` - Root endpoint
- `GET /api/health` - Health check endpoint
- `POST /api/chat` - Chat endpoint
  ```json
  {
    "message": "What services do you offer?",
    "session_id": "optional-session-id"
  }
  ```
- `POST /api/reset` - Reset chat history for a session

## 📚 Reference Documents

The chatbot uses the following reference documents:

1. **company_overview.md** - Information about JD AI Marketing Solutions
2. **solutions_catalog.md** - Detailed catalog of AI solutions offered
3. **case_studies.md** - Customer success stories and case studies
4. **faq.md** - Frequently asked questions

## 🎨 Customization

### Adding New Documents

1. Add markdown files to `backend/documents/`
2. Restart the backend server to reindex documents

### Modifying the Prompt

Edit the `CUSTOM_PROMPT` variable in `backend/main.py` to customize the chatbot's behavior and personality.

### Changing the Model

Modify the `ChatOpenAI` initialization in `backend/main.py`:
```python
llm = ChatOpenAI(
    model_name="gpt-4",  # Change to gpt-4, gpt-3.5-turbo, etc.
    temperature=0.7,
)
```

### Styling the Frontend

Edit `frontend/src/App.css` to customize colors, layout, and appearance.

## 🔐 Security Notes

- Never commit `.env` files containing API keys
- Keep your OpenAI API key secure
- In production, implement proper authentication and rate limiting
- Use environment-specific configurations

## 📊 Performance Considerations

- Vector store is persisted to `backend/chroma_db/` for faster restarts
- Chat history is stored in memory (limited to last 10 exchanges per session)
- Retrieval returns top 4 most relevant document chunks

## 🐛 Troubleshooting

### Backend won't start
- Ensure OpenAI API key is set in `.env`
- Check Python version (3.9+)
- Verify all dependencies are installed

### Frontend can't connect to backend
- Ensure backend is running on port 8000
- Check CORS settings in `backend/main.py`
- Verify proxy settings in `frontend/vite.config.js`

### Poor response quality
- Add more relevant documents to `backend/documents/`
- Adjust chunk size and overlap in `main.py`
- Increase number of retrieved chunks (k value)
- Try a different OpenAI model

## 📦 Deployment

### Backend Deployment

Consider deploying to:
- **Render**: Easy Python app deployment
- **Railway**: Simple deployment with environment variables
- **AWS EC2**: Full control over infrastructure
- **Google Cloud Run**: Serverless container deployment

### Frontend Deployment

Build and deploy to:
- **Vercel**: Optimized for Vite/React apps
- **Netlify**: Simple static site hosting
- **Cloudflare Pages**: Fast global deployment
- **AWS S3 + CloudFront**: Traditional static hosting

## 🤝 Contributing

This is a POC project. Feel free to:
- Add new features
- Improve the UI/UX
- Add more reference documents
- Enhance the RAG pipeline

## 📄 License

This project is for demonstration purposes. Modify as needed for your use case.

## 🙋 Support

For questions or issues:
- Check the API documentation at `/docs`
- Review the troubleshooting section
- Inspect browser console and server logs

## 🎯 Next Steps

Potential enhancements:
- [ ] Add user authentication
- [ ] Implement streaming responses
- [ ] Add file upload capability
- [ ] Create admin panel for document management
- [ ] Add analytics and usage tracking
- [ ] Implement rate limiting
- [ ] Add support for multiple languages
- [ ] Create mobile app version
- [ ] Add voice input/output
- [ ] Implement feedback mechanism

---

**Built with ❤️ using OpenAI, LangChain, FastAPI, and React**
