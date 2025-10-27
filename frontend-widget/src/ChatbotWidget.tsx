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
                    background: `linear-gradient(135deg, ${config.primaryColor}, ${config.primaryColor}dd)`,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
                    transition: 'all 0.3s ease',
                    zIndex: 1000,
                    border: '2px solid rgba(255,255,255,0.2)'
                }}
                onClick={() => setIsOpen(!isOpen)}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.1)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
            >
                <span style={{
                    color: config.secondaryColor,
                    fontSize: '24px',
                    filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))'
                }}>
          {isOpen ? '✕' : '💬'}
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
                        background: `linear-gradient(145deg, ${config.secondaryColor}, ${config.secondaryColor}ee)`,
                        borderRadius: '20px',
                        boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                        display: 'flex',
                        flexDirection: 'column',
                        zIndex: 1000,
                        border: `1px solid ${config.primaryColor}33`,
                        backdropFilter: 'blur(10px)',
                        animation: 'slideUp 0.3s ease-out'
                    }}
                >
                    {/* Header */}
                    <div
                        style={{
                            background: `linear-gradient(135deg, ${config.primaryColor}, ${config.primaryColor}cc)`,
                            color: config.secondaryColor,
                            padding: '16px 20px',
                            borderRadius: '20px 20px 0 0',
                            fontWeight: '600',
                            fontSize: '16px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            boxShadow: '0 2px 10px rgba(0,0,0,0.1)'
                        }}
                    >
                        <span>🤖</span>
                        JD AI Chat Assistant
                    </div>

                    {/* Messages */}
                    <div
                        style={{
                            flex: 1,
                            overflowY: 'auto',
                            padding: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '12px',
                            background: 'transparent'
                        }}
                    >
                        {messages.map((msg, index) => (
                            <div
                                key={index}
                                style={{
                                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                    background: msg.role === 'user'
                                        ? `linear-gradient(135deg, ${config.primaryColor}, ${config.primaryColor}aa)`
                                        : 'rgba(255,255,255,0.9)',
                                    color: msg.role === 'user' ? config.secondaryColor : '#333',
                                    padding: '12px 16px',
                                    borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                                    maxWidth: '80%',
                                    wordWrap: 'break-word',
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                                    border: msg.role === 'user' ? 'none' : '1px solid rgba(0,0,0,0.05)',
                                    animation: 'fadeIn 0.3s ease-out'
                                }}
                            >
                                {msg.content}
                            </div>
                        ))}
                        {isLoading && (
                            <div style={{
                                alignSelf: 'flex-start',
                                background: 'rgba(255,255,255,0.9)',
                                color: '#666',
                                padding: '12px 16px',
                                borderRadius: '18px 18px 18px 4px',
                                fontStyle: 'italic',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                            }}>
                                <span>Typing</span>
                                <span className="typing-dots">...</span>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <form onSubmit={handleSubmit} style={{
                        padding: '16px',
                        borderTop: '1px solid rgba(0,0,0,0.1)',
                        background: 'rgba(255,255,255,0.5)',
                        borderRadius: '0 0 20px 20px'
                    }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder="Type your message..."
                                style={{
                                    flex: 1,
                                    padding: '12px 16px',
                                    border: '1px solid rgba(0,0,0,0.2)',
                                    borderRadius: '25px',
                                    outline: 'none',
                                    fontSize: '14px',
                                    background: 'white',
                                    transition: 'border-color 0.2s ease',
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                                }}
                                onFocus={(e) => e.target.style.borderColor = config.primaryColor}
                                onBlur={(e) => e.target.style.borderColor = 'rgba(0,0,0,0.2)'}
                                disabled={isLoading}
                            />
                            <button
                                type="submit"
                                disabled={isLoading || !input.trim()}
                                style={{
                                    width: '40px',
                                    height: '40px',
                                    background: `linear-gradient(135deg, ${config.primaryColor}, ${config.primaryColor}aa)`,
                                    color: config.secondaryColor,
                                    border: 'none',
                                    borderRadius: '50%',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    transition: 'all 0.2s ease',
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
                                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                            >
                                <span style={{ fontSize: '16px' }}>➤</span>
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {/* CSS for animations */}
            <style>
                {`
                    @keyframes slideUp {
                        from { opacity: 0; transform: translateY(20px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                    @keyframes fadeIn {
                        from { opacity: 0; transform: translateY(10px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                    .typing-dots::after {
                        content: '';
                        animation: typing 1.5s infinite;
                    }
                    @keyframes typing {
                        0%, 60%, 100% { opacity: 0; }
                        30% { opacity: 1; }
                    }
                `}
            </style>
        </>
    )
}

export default ChatbotWidget
