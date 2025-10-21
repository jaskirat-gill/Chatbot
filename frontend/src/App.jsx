import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hi! I\'m the JD AI Marketing Solutions assistant. I can help you learn about our AI solutions for small businesses. How can I help you today?'
    }
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput('')
    setError(null)

    // Add user message to chat
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setIsLoading(true)

    try {
      const response = await axios.post('http://localhost:8000/api/chat', {
        message: userMessage,
        session_id: 'default'
      })

      // Add assistant response to chat
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.data.response
      }])
    } catch (err) {
      console.error('Error:', err)
      setError(err.response?.data?.detail || 'Failed to get response. Please try again.')
      // Remove the user message if there was an error
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = async () => {
    try {
      await axios.post('http://localhost:8000/api/reset?session_id=default')
      setMessages([
        {
          role: 'assistant',
          content: 'Hi! I\'m the JD AI Marketing Solutions assistant. I can help you learn about our AI solutions for small businesses. How can I help you today?'
        }
      ])
      setError(null)
    } catch (err) {
      console.error('Error resetting chat:', err)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-content">
          <h1>JD AI Marketing Solutions</h1>
          <p>AI-Powered Assistant</p>
        </div>
        <button onClick={handleReset} className="reset-button">
          Reset Chat
        </button>
      </header>

      <div className="chat-container">
        <div className="messages">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
            >
              <div className="message-avatar">
                {message.role === 'user' ? '👤' : '🤖'}
              </div>
              <div className="message-content">
                {message.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="message assistant-message">
              <div className="message-avatar">🤖</div>
              <div className="message-content loading">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="input-form">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask me about our AI solutions..."
            disabled={isLoading}
            className="message-input"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="send-button"
          >
            Send
          </button>
        </form>
      </div>

      <footer className="footer">
        <p>RAG-based Chatbot Demo</p>
      </footer>
    </div>
  )
}

export default App
