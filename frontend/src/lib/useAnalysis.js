// The flow of one analysis, kept out of the page so the page only draws.
//
//   1. POST /analyze (about 0.05 s): the score, the findings and the claims. Shown at once.
//   2. POST /explain (a second or more): the same report with LIME highlights. It replaces the first report (same score and findings, plus highlights).
//
// The API runs one analysis at a time, so there is never more than one request in flight from here: a new run cancels the old one. If step 2 fails
// (a rate limit, a busy classifier) the report from step 1 stays and the page says the highlights are missing.

import { useCallback, useEffect, useRef, useState } from 'react'
import { analyze, ApiError, explain } from '../api.js'

const isAbort = (error) => error && error.name === 'AbortError'
const asApiError = (error) => (error instanceof ApiError ? error : new ApiError({ code: 'unexpected', detail: 'Something unexpected went wrong in the interface.' }))

// explainDone: the second call finished. `report.explained` alone cannot say so: the API sets it only when LIME ran, and LIME does not run when no tactic fired.
const IDLE = { phase: 'idle', report: null, error: null, explainError: null, explainDone: false }

export function useAnalysis() {
  const [state, setState] = useState(IDLE)
  const controller = useRef(null)

  useEffect(() => () => controller.current?.abort(), [])

  const run = useCallback(async (request, wantExplain) => {
    controller.current?.abort()
    const mine = new AbortController()
    controller.current = mine
    setState({ ...IDLE, phase: 'analyzing' })
    try {
      const report = await analyze(request, mine.signal)
      if (mine.signal.aborted) return
      setState({ ...IDLE, phase: wantExplain ? 'explaining' : 'done', report })
      if (!wantExplain) return
      try {
        const explained = await explain(request, mine.signal)
        if (mine.signal.aborted) return
        setState({ ...IDLE, phase: 'done', report: explained, explainDone: true })
      } catch (error) {
        if (isAbort(error)) return
        setState((s) => ({ ...s, phase: 'done', explainError: asApiError(error) }))
      }
    } catch (error) {
      if (isAbort(error)) return
      setState({ ...IDLE, phase: 'error', error: asApiError(error) })
    }
  }, [])

  // The word highlights alone, for a report that was run without them: the score and findings stay, the report is replaced by the explained one.
  const explainReport = useCallback(async (request) => {
    controller.current?.abort()
    const mine = new AbortController()
    controller.current = mine
    setState((s) => ({ ...s, phase: 'explaining', explainError: null }))
    try {
      const explained = await explain(request, mine.signal)
      if (mine.signal.aborted) return
      setState({ ...IDLE, phase: 'done', report: explained, explainDone: true })
    } catch (error) {
      if (isAbort(error)) return
      setState((s) => ({ ...s, phase: 'done', explainError: asApiError(error) }))
    }
  }, [])

  const reset = useCallback(() => {
    controller.current?.abort()
    setState(IDLE)
  }, [])

  return { ...state, run, explainReport, reset, busy: state.phase === 'analyzing' || state.phase === 'explaining' }
}

// Seconds left until a refused request may be tried again (the API's Retry-After), counting down once a second.
export function useRetryTimer(error) {
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (!error || !error.retryAfter) {
      setLeft(0)
      return undefined
    }
    const until = Date.now() + error.retryAfter * 1000
    const tick = () => setLeft(Math.max(0, Math.ceil((until - Date.now()) / 1000)))
    tick()
    const id = setInterval(tick, 500)
    return () => clearInterval(id)
  }, [error])
  return left
}
