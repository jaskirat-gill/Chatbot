# Quick Reference Guide

## 🚀 Quick Start Commands

### One-Time Setup
```powershell
# Run the automated setup script
.\setup.ps1
```

### Manual Setup

#### Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OpenAI API key
```

#### Frontend
```powershell
cd frontend
npm install
```

## ▶️ Running the Application

### Start Backend (Terminal 1)
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python main.py
```
**Backend URL**: http://localhost:8000

### Start Frontend (Terminal 2)
```powershell
cd frontend
npm run dev
```
**Frontend URL**: http://localhost:5173

## 🔑 Environment Variables

Create `backend/.env`:
```
OPENAI_API_KEY=sk-your-api-key-here
```

## 📡 API Endpoints

### Chat
```powershell
# PowerShell
$body = @{
    message = "What services do you offer?"
    session_id = "test-session"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/chat" -Method POST -Body $body -ContentType "application/json"
```

### Health Check
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Method GET
```

### Reset Session
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/reset?session_id=test-session" -Method POST
```

## 📝 Example Queries to Test

Try asking the chatbot:

- "What is JD AI Marketing Solutions?"
- "What services do you offer?"
- "Tell me about your chatbot solution"
- "Show me some case studies"
- "How much do your solutions cost?"
- "Do you have experience in retail?"
- "What's your implementation timeline?"
- "Can you integrate with Shopify?"

## 🛠️ Common Tasks

### Add a New Document
1. Create a `.md` file in `backend/documents/`
2. Restart the backend server
3. Documents will be automatically indexed

### Change the AI Model
Edit `backend/main.py`:
```python
llm = ChatOpenAI(
    model_name="gpt-4",  # Change this
    temperature=0.7,
)
```

### Customize the Prompt
Edit `CUSTOM_PROMPT` in `backend/main.py`

### Change Colors/Styling
Edit `frontend/src/App.css`

### Adjust Chunk Size
Edit `backend/main.py`:
```python
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,      # Adjust this
    chunk_overlap=200,    # Adjust this
)
```

### Change Number of Retrieved Chunks
Edit `backend/main.py`:
```python
retriever=vectorstore.as_retriever(search_kwargs={"k": 4})  # Change k value
```

## 🐛 Troubleshooting

### Backend won't start
```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Verify OpenAI API key
Get-Content backend\.env
```

### Frontend can't connect
```powershell
# Test backend directly
Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Method GET

# Check if backend is running
Get-Process python
```

### Dependencies issues
```powershell
# Backend - reinstall
cd backend
.\venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt

# Frontend - reinstall
cd frontend
Remove-Item -Recurse -Force node_modules
npm install
```

### Clear ChromaDB cache
```powershell
cd backend
Remove-Item -Recurse -Force chroma_db
# Restart backend to rebuild
```

## 📦 Build for Production

### Backend
```powershell
# Install production server
pip install gunicorn

# Run with gunicorn (Linux/Mac)
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# For Windows, use waitress
pip install waitress
waitress-serve --port=8000 main:app
```

### Frontend
```powershell
cd frontend
npm run build
# Output will be in frontend/dist/
```

## 📊 Monitoring

### Check API Docs
http://localhost:8000/docs

### View Logs
Backend logs are printed to console where `python main.py` is running

### Test Performance
```powershell
# PowerShell simple benchmark
Measure-Command {
    Invoke-RestMethod -Uri "http://localhost:8000/api/chat" -Method POST -Body '{"message":"What do you do?"}' -ContentType "application/json"
}
```

## 🔐 Security Checklist

- [ ] OpenAI API key is in `.env` (not committed)
- [ ] `.gitignore` includes `.env` files
- [ ] CORS is restricted to specific origins (not *)
- [ ] Rate limiting implemented (for production)
- [ ] Input validation added (for production)
- [ ] HTTPS enabled (for production)

## 📈 Performance Tips

1. **Use persistent ChromaDB**: The vector store is automatically persisted
2. **Limit chat history**: Currently limited to 10 exchanges per session
3. **Cache responses**: Consider caching frequent queries
4. **Use streaming**: Implement streaming for better UX
5. **Optimize chunk size**: Balance between context and retrieval speed

## 🎯 Testing Checklist

- [ ] Backend starts without errors
- [ ] Frontend loads at localhost:5173
- [ ] Health check returns `{"status": "healthy"}`
- [ ] Can send chat message and receive response
- [ ] Reset button clears conversation
- [ ] Multiple questions maintain context
- [ ] Error messages display properly
- [ ] Mobile responsive design works

## 📚 Useful Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com
- **LangChain Docs**: https://python.langchain.com
- **OpenAI API**: https://platform.openai.com/docs
- **React Docs**: https://react.dev
- **Vite Docs**: https://vitejs.dev

## 🆘 Getting Help

1. Check the README.md for detailed setup
2. Review ARCHITECTURE.md for system design
3. Check `/docs` endpoint for API documentation
4. Review console logs for error messages
5. Verify environment variables are set correctly

## 🎨 Customization Ideas

- Add user authentication
- Implement streaming responses
- Add voice input/output
- Create mobile app version
- Add file upload capability
- Implement feedback mechanism
- Add multi-language support
- Create admin dashboard
- Add analytics tracking
- Implement A/B testing

---

**Pro Tip**: Keep your OpenAI API key secure and never commit it to version control!
