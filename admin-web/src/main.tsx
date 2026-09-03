import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AuditPanel from './AuditPanel'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <AuditPanel />
  </React.StrictMode>,
)
