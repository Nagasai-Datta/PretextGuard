// Phase 12: Vite configuration. Two jobs: build the app, and forward /api to the local API with the key added.
//
// THE KEY STAYS OUT OF THE BROWSER. The browser calls /api/analyze on THIS server (same origin, so no CORS). This server forwards the request to the
// API at 127.0.0.1:8000 and adds the X-API-Key header itself, read here from the project's .env (../.env). Vite only ever hands the browser
// variables whose names start with VITE_ (envPrefix below), and the key is not one of them, so it is not in the bundle. `npm run check` proves it
// by searching dist/ for the key after a build.
//
// Two ways to run it:
//   npm run dev                  development: hot reload
//   npm run build && npm run preview     the built app, served with the security headers below (a Content-Security-Policy that allows only our own
//                                        scripts). Use this one for the demo.

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API = 'http://127.0.0.1:8000'

// Headers for every answer of the interface server. The CSP is only for the built app: the dev server needs inline scripts for hot reload.
const COMMON_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY',
  'Cross-Origin-Resource-Policy': 'same-origin',
}
const CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join('; ')

export default defineConfig(({ command, mode }) => {
  // Only the PRETEXTGUARD_* names are read, from ../.env and the real environment. They stay in this file.
  const env = loadEnv(mode, '..', 'PRETEXTGUARD_')
  const key = env.PRETEXTGUARD_API_KEY || ''

  if (command === 'serve' && (key.length < 24 || key.toLowerCase() === 'change-me')) {
    throw new Error(
      'PRETEXTGUARD_API_KEY is missing or still the placeholder in ../.env. Make one with:  python -m src.api.settings --new-key  ' +
        '(the same key the API server uses), then start this again.',
    )
  }

  const proxy = {
    '/api': {
      target: API,
      changeOrigin: false, // keep the browser's Host (localhost or 127.0.0.1): the API accepts only those
      rewrite: (path) => path.replace(/^\/api/, ''),
      headers: { 'X-API-Key': key }, // added to every forwarded request; replaces anything the browser sent
    },
  }

  return {
    plugins: [react(), tailwindcss()],
    envPrefix: 'VITE_',
    build: { outDir: 'dist', sourcemap: false },
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy, headers: COMMON_HEADERS },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy, headers: { ...COMMON_HEADERS, 'Content-Security-Policy': CSP } },
  }
})
