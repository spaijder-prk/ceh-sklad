import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AuditPanel from './AuditPanel'
import ManagementExtensions from './ManagementExtensions'
import SystemStatusPanel from './SystemStatusPanel'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <SystemStatusPanel />
    <ManagementExtensions />
    <AuditPanel />
  </React.StrictMode>,
)
