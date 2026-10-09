import { humanize } from '../lib/format.js'

// The thread checks (N2): the newest message is compared with the earlier ones. The timeline shows every message with the worst finding on it, and marks
// the message where the thread's behaviour changed (the flip point).
const kindOf = (severity) => (severity ? { label: severity, key: severity } : { label: 'clean', key: 'ok' })

export default function ThreadTimeline({ thread }) {
  return (
    <section className="card" aria-labelledby="thread-title">
      <h2 id="thread-title">The conversation</h2>
      <p className="m-0 text-sm">
        {thread.messages} messages. The newest (message {thread.judged_index + 1}) was judged against the earlier ones.{' '}
        {thread.flip_index === null ? 'No message changed the thread\'s behaviour.' : `The behaviour changes at message ${thread.flip_index + 1}.`}
      </p>
      <ol className="mt-3 flex list-none gap-2 overflow-x-auto p-0" aria-label="Messages in order">
        {thread.timeline.map((m) => {
          const kind = kindOf(m.worst)
          const isFlip = thread.flip_index === m.index
          return (
            <li key={m.index} className="min-w-40 flex-1 rounded-lg border p-2 text-sm" style={{ borderColor: isFlip ? 'var(--critical)' : 'var(--line)', borderWidth: isFlip ? 2 : 1 }}>
              <div className="flex items-center gap-2">
                <span className="font-medium">Message {m.index + 1}</span>
                {m.index === thread.judged_index && <span className="chip sev-ok">judged</span>}
              </div>
              <div className="mono [overflow-wrap:anywhere]">{m.from_domain || 'unknown sender'}</div>
              <div className="hint [overflow-wrap:anywhere]">{m.subject || '(no subject)'}</div>
              <div className="mt-1">
                <span className={`chip sev-${kind.key}`}>{kind.label}</span>
              </div>
              {isFlip && <div className="mt-1 font-medium">Flip point</div>}
              {m.rules.length > 0 && <div className="hint mono mt-1 [overflow-wrap:anywhere]">{m.rules.join(', ')}</div>}
            </li>
          )
        })}
      </ol>
      {thread.signals.length > 0 && (
        <ul className="mt-3 list-none p-0 text-sm">
          {thread.signals.map((signal) => (
            <li key={signal.rule} className="mb-2 flex flex-wrap gap-2">
              <span className={`chip sev-${signal.severity}`}>{signal.severity}</span>
              <span className="font-medium">{humanize(signal.claim_type)}</span>
              <span className="[overflow-wrap:anywhere]">{signal.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
