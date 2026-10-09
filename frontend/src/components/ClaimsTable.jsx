import { humanize } from '../lib/format.js'

// The claims the extractor found in the text, and where each was sent. A claim is a statement the email makes about itself ("this is David from Finance",
// "wire this before 3 PM"); the verifiers then compare it with evidence.
function outcomeOf(rows) {
  if (rows.length === 0) return { label: 'No verifier', key: 'na' }
  if (rows.some((r) => r.contradiction === true)) return { label: 'Contradicted', key: 'high' }
  if (rows.some((r) => r.contradiction === false)) return { label: 'Consistent', key: 'ok' }
  return { label: 'Not checkable', key: 'na' }
}

export default function ClaimsTable({ report }) {
  const rowsByClaim = new Map()
  for (const row of report.ledger) {
    if (row.claim_id === 'thread') continue
    rowsByClaim.set(row.claim_id, [...(rowsByClaim.get(row.claim_id) || []), row])
  }
  const routedTo = new Map(report.routing.map((r) => [r.claim_id, r.verifiers]))
  return (
    <section className="card" aria-labelledby="claims-title">
      <h2 id="claims-title">Claims found</h2>
      {report.claims.length === 0 ? (
        <p className="m-0">The extractor found no claim of a type that can be checked. That says nothing about whether the email is honest.</p>
      ) : (
        <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Table, scrolls sideways on a narrow screen">
          <table className="table min-w-[34rem]">
            <thead>
              <tr>
                <th>Type</th>
                <th>Text</th>
                <th>Strength</th>
                <th>Found in</th>
                <th>Checked by</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {report.claims.map((claim) => {
                const outcome = outcomeOf(rowsByClaim.get(claim.claim_id) || [])
                return (
                  <tr key={claim.claim_id}>
                    <td>{humanize(claim.type)}</td>
                    <td className="mono [overflow-wrap:anywhere]">"{claim.text}"</td>
                    <td>{claim.confidence >= 0.9 ? 'Strong' : 'Weak'}</td>
                    <td>{claim.attributes && claim.attributes.zone === 'signature' ? 'Signature' : 'Body'}</td>
                    <td>{(routedTo.get(claim.claim_id) || []).join(', ') || 'none'}</td>
                    <td>
                      <span className={`chip sev-${outcome.key}`}>{outcome.label}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint m-0 mt-2">
        A weak claim (matched by a looser rule) lowers the severity of its finding by one step. A claim that is missing is never evidence of honesty: the extractor finds
        only some of what an email claims.
      </p>
    </section>
  )
}
