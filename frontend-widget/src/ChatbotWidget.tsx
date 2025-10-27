import React, { useState, useRef, useEffect } from 'react'
import axios from 'axios'

interface Config {
    tenantId: string
    primaryColor: string
    secondaryColor: string
    apiUrl: string
}

interface Message {
    role: 'user' | 'assistant'
    content: string
}

const ChatbotWidget: React.FC<{ config: Config }> = ({ config }) => {
    const [isOpen, setIsOpen] = useState(false)
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: 'Hi! I\'m the JD AI Marketing Solutions assistant. How can I help you today?'
        }
    ])
    const [input, setInput] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!input.trim() || isLoading) return

        const userMessage = input.trim()
        setInput('')
        setMessages(prev => [...prev, { role: 'user', content: userMessage }])
        setIsLoading(true)

        try {
            const response = await axios.post(`${config.apiUrl}/v1/api/chat`, {
                message: userMessage,
                session_id: 'default'
            }, {
                headers: {
                    'X-Tenant-ID': config.tenantId
                }
            })

            setMessages(prev => [...prev, {
                role: 'assistant',
                content: response.data.response
            }])
        } catch (error) {
            console.error('Error:', error)
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.'
            }])
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <>
            {/* Widget Button */}
            <div
                style={{
                    position: 'fixed',
                    bottom: '20px',
                    right: '20px',
                    width: '60px',
                    height: '60px',
                    backgroundColor: config.primaryColor,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    zIndex: 1000
                }}
                onClick={() => setIsOpen(!isOpen)}
            >
        <span style={{ color: config.secondaryColor, fontSize: '24px' }}>
          {isOpen ? '×' : '💬'}
        </span>
            </div>

            {/* Chat Panel */}
            {isOpen && (
                <div
                    style={{
                        position: 'fixed',
                        bottom: '90px',
                        right: '20px',
                        width: '350px',
                        height: '500px',
                        backgroundColor: config.secondaryColor,
                        borderRadius: '12px',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
                        display: 'flex',
                        flexDirection: 'column',
                        zIndex: 1000,
                        border: `2px solid ${config.primaryColor}`
                    }}
                >
                    {/* Header */}
                    <div
                        style={{
                            backgroundColor: config.primaryColor,
                            color: config.secondaryColor,
                            padding: '12px',
                            borderRadius: '10px 10px 0 0',
                            fontWeight: 'bold'
                        }}
                    >
                        JD AI Chat Assistant
                    </div>

                    {/* Messages */}
                    <div
                        style={{
                            flex: 1,
                            overflowY: 'auto',
                            padding: '12px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                        }}
                    >
                        {messages.map((msg, index) => (
                            <div
                                key={index}
                                style={{
                                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                    backgroundColor: msg.role === 'user' ? config.primaryColor : '#f0f0f0',
                                    color: msg.role === 'user' ? config.secondaryColor : '#000',
                                    padding: '8px 12px',
                                    borderRadius: '8px',
                                    maxWidth: '80%'
                                }}
                            >
                                {msg.content}
                            </div>
                        ))}
                        {isLoading && (
                            <div style={{ alignSelf: 'flex-start', fontStyle: 'italic' }}>
                                Typing...
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <form onSubmit={handleSubmit} style={{ padding: '12px', borderTop: '1px solid #ddd' }}>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder="Type your message..."
                                style={{
                                    flex: 1,
                                    padding: '8px',
                                    border: '1px solid #ddd',
                                    borderRadius: '4px'
                                }}
                                disabled={isLoading}
                            />
                            <button
                                type="submit"
                                disabled={isLoading || !input.trim()}
                                style={{
                                    backgroundColor: config.primaryColor,
                                    color: config.secondaryColor,
                                    border: 'none',
                                    padding: '8px 12px',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                }}
                            >
                                Send
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </>
    )
}

export default ChatbotWidget
