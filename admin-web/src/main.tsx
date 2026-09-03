import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AuditPanel from './AuditPanel'
import ManagementExtensions from './ManagementExtensions'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <ManagementExtensions />
    <AuditPanel />
  </React.StrictMode>,
)
