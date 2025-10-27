import ReactDOM from 'react-dom/client'
import ChatbotWidget from './ChatbotWidget'
import './index.css'

// Get config from script data attributes
const script = document.currentScript as HTMLScriptElement
console.log('Script loaded:', script)
const tenantId = script?.getAttribute('data-tenant') || 'jd_ai'
console.log('Tenant ID:', tenantId)
const primaryColor = script?.getAttribute('data-primary-color') || '#007bff'
const secondaryColor = script?.getAttribute('data-secondary-color') || '#ffffff'
const apiUrl = script?.getAttribute('data-api-url') || 'http://localhost:8000'
const companyName = script?.getAttribute('data-company-name') || 'Company'

const config = { tenantId, primaryColor, secondaryColor, apiUrl, companyName }
console.log('Config:', config)

// Inject the widget into the page
const widgetContainer = document.createElement('div')
widgetContainer.id = 'jd-chatbot-widget'
console.log('Injecting widget container')
document.body.appendChild(widgetContainer)
console.log('Widget container added to body')

const root = ReactDOM.createRoot(widgetContainer)
console.log('Creating React root')
root.render(<ChatbotWidget config={config} />)
console.log('Widget rendered')
