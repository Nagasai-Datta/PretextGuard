// How much of the email could be checked. This is shown next to every result because a low score with little checked is not reassurance.
const LIMIT_LABELS = {
  headers_missing: 'No headers',
  no_from: 'No From address',
  no_authentication: 'No SPF/DKIM/DMARC result',
  no_org_domain: 'No organisation domain',
  org_domain_ignored: 'Organisation domain ignored',
  single_email: 'Single email',
  thread_truncated: 'Thread cut at 50',
  thread_unordered: 'Messages not dated',
  text_truncated: 'Text cut at the limit',
  mime_too_deep: 'Nested parts not separated',
}

const Count = ({ n, label }) => (
  <div>
    <div className="text-xl font-semibold tabular-nums">{n}</div>
    <div className="hint">{label}</div>
  </div>
)

export default function CoverageNote({ report }) {
  const c = report.coverage
  const lowButBlind = report.verdict === 'Low risk' && (c.checked === 0 || c.limits.includes('headers_missing'))
  return (
    <section className="card" aria-labelledby="coverage-title">
      <h2 id="coverage-title">What could be checked</h2>
      <div className="flex flex-wrap gap-x-8 gap-y-2">
        <Count n={c.claims} label="claims found" />
        <Count n={c.checked} label="could be checked" />
        <Count n={c.contradicted} label="contradicted" />
        <Count n={c.consistent} label="consistent" />
        <Count n={c.not_checkable} label="not checkable" />
        {report.mode === 'thread' && <Count n={c.signals} label="thread checks" />}
      </div>
      <p className="m-0 mt-3">{c.note}</p>
      {c.limits.length > 0 && (
        <ul className="m-0 mt-2 flex list-none flex-wrap gap-2 p-0" aria-label="Limits that applied">
          {c.limits.map((code) => (
            <li key={code} className="chip sev-na">
              {LIMIT_LABELS[code] || code}
            </li>
          ))}
        </ul>
      )}
      {lowButBlind && (
        <p role="note" className="m-0 mt-3 rounded-lg border border-line p-3">
          <span className="font-medium">A low score is not a clean bill of health here.</span> Little or nothing about the sender could be checked, so the score can only
          come from the pressure tactics (at most 12 points). Paste the full email with its headers, and give your organisation's domain, for a real check.
        </p>
      )}
      {report.verdict === 'Low risk' && !lowButBlind && (
        <p className="hint m-0 mt-2">Low risk means no contradiction was found among the claims that could be checked. It does not mean the email is safe.</p>
      )}
    </section>
  )
}
