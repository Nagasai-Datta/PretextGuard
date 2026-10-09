import { humanize } from '../lib/format.js'

// What to tell the person for each error the API (or the network) can give. The API's own sentence is fixed and holds no email content, so it is
// safe to show; the extra line says what to do.
const ADVICE = {
  unauthorized: 'The API did not accept the key this page sends. Check PRETEXTGUARD_API_KEY in .env, then restart the API and this page\'s server.',
  rate_limited: 'Too many requests in a minute. Wait for the counter on the button, then try again.',
  busy: 'The classifier is busy with another analysis. Try again in a moment.',
  model_unavailable: 'The API is running but its model is not loaded. Look at the terminal where the API runs.',
  too_large: 'The text is over the size limit. Cut it down or send fewer messages.',
  unsupported_media_type: 'The API accepts only JSON from this page. This is a bug in the interface.',
  invalid_request: 'The API refused the request. The fields it did not like are listed below.',
  internal_error: 'The analysis failed on the API side. Quote the request id when you report it.',
  network: 'The interface could not reach the API. Start it with: python -m src.api.main',
  timeout: 'The API took too long to answer. Try again, or turn off the word highlights.',
  bad_answer: 'The API answered with something this page cannot read.',
}

const where = (loc) => loc.filter((part) => part !== 'body').join(' > ') || 'request'

export default function ErrorBanner({ error, title = 'The analysis did not run' }) {
  if (!error) return null
  const advice = ADVICE[error.code] || (error.network ? ADVICE.network : null)
  return (
    <div role="alert" className="card border-critical">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="chip sev-high">{title}</span>
        <span className="font-medium">{error.detail}</span>
      </div>
      {advice && <p className="m-0 text-sm">{advice}</p>}
      {error.errors && error.errors.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm">
          {error.errors.map((item, index) => (
            <li key={index}>
              <span className="mono">{where(item.loc)}</span>: {humanize(item.type)}
            </li>
          ))}
        </ul>
      )}
      <p className="hint m-0 mt-2">
        {error.status ? `HTTP ${error.status}` : 'No answer'} · {error.code}
        {error.requestId ? ` · request id ${error.requestId}` : ''}
        {error.retryAfter ? ` · retry after ${error.retryAfter} s` : ''}
      </p>
    </div>
  )
}
