// The only place that talks to the network. Every call goes to /api/..., which the interface server (vite.config.js) forwards to the local API and adds
// the X-API-Key header to. The key is not in this file or in the browser.
//
// Errors: the API answers every error as JSON {detail, code, request_id, errors?} with a fixed sentence. This file turns any failure (an API error, a
// network error, an unexpected answer) into one ApiError with the same fields, so the interface has one thing to handle.

const BASE = '/api'
const TIMEOUT_MS = 120_000

export class ApiError extends Error {
  constructor({ status = 0, code = 'unknown', detail = 'The request failed.', requestId = null, retryAfter = null, errors = null, network = false }) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
    this.requestId = requestId
    this.retryAfter = retryAfter
    this.errors = errors
    this.network = network
  }
}

const isText = (value) => typeof value === 'string' && value.length <= 500

function parseErrors(value) {
  if (!Array.isArray(value)) return null
  return value
    .slice(0, 10)
    .filter((item) => item && Array.isArray(item.loc) && isText(item.type))
    .map((item) => ({ loc: item.loc.filter((part) => typeof part === 'string' || typeof part === 'number'), type: item.type }))
}

// Merge the caller's AbortSignal (the user pressed Analyze again) with a timeout.
function signalWithTimeout(signal) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('Timed out', 'TimeoutError')), TIMEOUT_MS)
  const onAbort = () => controller.abort(signal.reason)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const done = () => {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
  return { signal: controller.signal, done }
}

async function request(method, path, body, outerSignal) {
  const { signal, done } = signalWithTimeout(outerSignal)
  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
      signal,
    })
  } catch (error) {
    done()
    if (error && error.name === 'AbortError' && outerSignal && outerSignal.aborted) throw error // cancelled by the user: not an error to show
    const timedOut = error && (error.name === 'TimeoutError' || error.name === 'AbortError')
    throw new ApiError({
      network: true,
      code: timedOut ? 'timeout' : 'network',
      detail: timedOut ? 'The API took too long to answer.' : 'The interface could not reach the API.',
    })
  }
  let parsed = null
  try {
    parsed = JSON.parse(await response.text())
  } catch {
    parsed = null
  }
  done()

  if (response.ok) {
    if (parsed === null || typeof parsed !== 'object') {
      throw new ApiError({ status: response.status, code: 'bad_answer', detail: 'The API answered with something that is not JSON.' })
    }
    return parsed
  }

  const header = Number.parseInt(response.headers.get('retry-after') || '', 10)
  // The interface server answers 500, 502 or 504 with no JSON when the API behind it is not running.
  const unreachable = !parsed && response.status >= 500
  throw new ApiError({
    status: response.status,
    code: parsed && isText(parsed.code) ? parsed.code : unreachable ? 'network' : `http_${response.status}`,
    detail: parsed && isText(parsed.detail) ? parsed.detail : unreachable ? 'The interface could not reach the API.' : 'The API answered with an error.',
    requestId: parsed && isText(parsed.request_id) ? parsed.request_id : null,
    retryAfter: Number.isFinite(header) && header >= 0 && header <= 3600 ? header : null,
    errors: parsed ? parseErrors(parsed.errors) : null,
    network: unreachable,
  })
}

// request: {kind: 'email', email, orgDomain} or {kind: 'thread', messages: [text, ...], orgDomain}
function bodyOf(req) {
  const body = req.kind === 'thread' ? { messages: req.messages } : { email: req.email }
  if (req.orgDomain && req.orgDomain.trim()) body.org_domain = req.orgDomain.trim()
  return body
}

export const analyze = (req, signal) => request('POST', req.kind === 'thread' ? '/analyze/thread' : '/analyze', bodyOf(req), signal)
export const explain = (req, signal) => request('POST', '/explain', bodyOf(req), signal)
export const getHealth = (signal) => request('GET', '/health', undefined, signal)
export const getResults = (signal) => request('GET', '/results', undefined, signal)
export const getResult = (name, signal) => request('GET', `/results?name=${encodeURIComponent(name)}`, undefined, signal)
