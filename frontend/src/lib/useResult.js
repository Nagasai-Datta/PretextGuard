// Loads one result table from the API (GET /results?name=...). Three states: loading, ready, error. `retry` loads it again.
import { useCallback, useEffect, useState } from 'react'
import { getResult, getResults } from '../api.js'

function useLoaded(load, key) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading', data: null, error: null })
    load(controller.signal)
      .then((data) => setState({ status: 'ready', data, error: null }))
      .catch((error) => {
        if (error && error.name === 'AbortError') return
        setState({ status: 'error', data: null, error })
      })
    return () => controller.abort()
    // `load` is a function made fresh on every render, so the effect depends on `key` (what is loaded) and `attempt` (the retry counter) only.
  }, [key, attempt])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return { ...state, retry }
}

export const useResult = (name) => useLoaded((signal) => getResult(name, signal), name)
export const useResultList = () => useLoaded((signal) => getResults(signal), 'list')
