import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const developmentApi = 'http://localhost:8000/api/v1'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const configured = env.VITE_API_BASE_URL?.trim().replace(/\/$/, '')
  const apiBaseUrl = configured || (mode === 'development' ? developmentApi : '')

  if (!apiBaseUrl) {
    throw new Error('Для production-сборки задайте VITE_API_BASE_URL, например https://sklad.example.ru/api/v1')
  }
  if (mode !== 'development' && !apiBaseUrl.startsWith('https://')) {
    throw new Error('Production VITE_API_BASE_URL должен использовать HTTPS')
  }

  // Старые компоненты используют единый development-маркер. На этапе сборки Vite
  // заменяет его на явно заданный production URL, поэтому localhost не попадает в bundle.
  const apiBasePlugin: Plugin = {
    name: 'ceh-api-base-url',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes('/src/') || !code.includes(developmentApi)) return null
      return { code: code.replaceAll(developmentApi, apiBaseUrl), map: null }
    },
  }

  return {
    plugins: [react(), apiBasePlugin],
    server: {
      port: 5173,
    },
  }
})
