import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import CubeBodyExport from './components/CubeBodyExport.jsx'

const isExport = window.location.hash === '#export'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {isExport ? <CubeBodyExport /> : <App />}
  </StrictMode>,
)
