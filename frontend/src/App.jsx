import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { getHealth } from './api.js'
import AnalyzerPage from './pages/AnalyzerPage.jsx'

// The dashboard (and the chart library it needs) is fetched the first time its tab is opened, so the analyzer starts fast.
const DashboardPage = lazy(() => import('./pages/DashboardPage.jsx'))

const PAGES = [
  { id: 'analyzer', label: 'Analyzer' },
  { id: 'dashboard', label: 'Dashboard' },
]

// Is the API there, and is its model loaded? /health needs no key.
function useHealth() {
  const [health, setHealth] = useState({ state: 'checking' })
  const check = useCallback(() => {
    const controller = new AbortController()
    setHealth({ state: 'checking' })
    getHealth(controller.signal)
      .then((body) => setHealth({ state: body.model_loaded ? 'ok' : 'no_model' }))
      .catch((error) => {
        if (error && error.name === 'AbortError') return
        setHealth({ state: error.status === 503 ? 'no_model' : 'unreachable' })
      })
    return () => controller.abort()
  }, [])
  useEffect(() => check(), [check])
  return [health, check]
}

function HealthBanner({ health, onRetry }) {
  if (health.state === 'ok' || health.state === 'checking') return null
  const text =
    health.state === 'no_model'
      ? 'The API is running but its model is not loaded. Look at the terminal where you started it (python -m src.api.main).'
      : 'The interface cannot reach the API. Start it in another terminal with: python -m src.api.main  (then check again).'
  return (
    <div role="alert" className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-2 text-sm">
        <span className="chip" style={{ background: 'var(--band-high)', color: 'var(--band-high-ink)' }}>
          API not ready
        </span>
        <span className="flex-1">{text}</span>
        <button type="button" className="btn" onClick={onRetry}>
          Check again
        </button>
      </div>
    </div>
  )
}

export default function App() {
  const [page, setPage] = useState('analyzer')
  const [dashboardSeen, setDashboardSeen] = useState(false)
  const [health, recheck] = useHealth()

  const go = (id) => {
    setPage(id)
    if (id === 'dashboard') setDashboardSeen(true)
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <div>
            <h1 className="m-0 text-xl font-semibold">PretextGuard</h1>
            <p className="hint m-0">Checks what an email claims about itself against its headers and its conversation.</p>
          </div>
          <nav aria-label="Pages" className="ml-auto flex gap-1">
            {PAGES.map((p) => (
              <button key={p.id} type="button" className="tab" aria-current={page === p.id ? 'page' : undefined} onClick={() => go(p.id)}>
                {p.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <HealthBanner health={health} onRetry={recheck} />
      <main className="mx-auto max-w-6xl px-4 py-5">
        <div hidden={page !== 'analyzer'}>
          <AnalyzerPage />
        </div>
        {dashboardSeen && (
          <div hidden={page !== 'dashboard'}>
            <Suspense
              fallback={
                <p className="flex items-center gap-2" role="status">
                  <span className="spinner" aria-hidden="true" /> Loading the dashboard...
                </p>
              }
            >
              <DashboardPage />
            </Suspense>
          </div>
        )}
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 hint">
        Emails go only to the API on this computer (127.0.0.1), through this page's own server. They are held in memory for the request and never stored. The API key is
        not in this page.
      </footer>
    </div>
  )
}
