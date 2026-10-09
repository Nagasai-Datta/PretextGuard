import { formatCell, humanize, rowKind } from '../lib/format.js'

// The verdict ledger: one row per check. Each row names the claim, the rule that ran, the evidence it used, whether it contradicted the claim and why.
// Contradictions come first (strongest first). Rows that were consistent or could not be checked are kept in a closed block: they are part of the
// record ("not checkable" is never "fine"), but they are not the finding.

const STRENGTH = { high: 0, medium: 1, low: 2, none: 3, not_checkable: 4 }

function Evidence({ evidence }) {
  const entries = Object.entries(evidence || {})
  if (entries.length === 0) return <span className="hint">none</span>
  return (
    <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-ink2">{key}</dt>
          <dd className="m-0 mono [overflow-wrap:anywhere]">{value === null ? 'not known' : formatCell(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function Table({ rows, claimsById, countedBy }) {
  return (
    <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Table, scrolls sideways on a narrow screen">
      <table className="table min-w-[34rem]">
        <thead>
          <tr>
            <th>Outcome</th>
            <th>What was claimed</th>
            <th>Why</th>
            <th className="num">Points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const kind = rowKind(row)
            const claim = claimsById.get(row.claim_id)
            const counted = countedBy.get(`${row.claim_id}|${row.rule}`)
            return (
              <tr key={`${row.claim_id}-${row.rule}-${index}`}>
                <td>
                  <span className={`chip sev-${kind.key}`}>{kind.label}</span>
                  <div className="hint mt-1">{row.verifier} verifier</div>
                </td>
                <td>
                  <div className="font-medium">{humanize(row.claim_type)}</div>
                  {claim && <div className="mono [overflow-wrap:anywhere]">"{claim.text}"</div>}
                </td>
                <td>
                  <div>{row.reason}</div>
                  <details className="mt-1">
                    <summary className="hint">Rule {row.rule} and its evidence</summary>
                    <div className="mt-1">
                      <Evidence evidence={row.evidence} />
                    </div>
                  </details>
                </td>
                <td className="num">{counted !== undefined ? counted.toFixed(1) : ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function FindingsTable({ report }) {
  const claimsById = new Map(report.claims.map((claim) => [claim.claim_id, claim]))
  const countedBy = new Map(report.score_detail.groups.map((group) => [`${group.claim_id}|${group.rule}`, group.counted]))
  const bySeverity = (a, b) => (STRENGTH[a.severity] ?? 9) - (STRENGTH[b.severity] ?? 9)
  const contradictions = report.ledger.filter((row) => row.contradiction === true).sort(bySeverity)
  const others = report.ledger.filter((row) => row.contradiction !== true)
  return (
    <section className="card" aria-labelledby="findings-title">
      <h2 id="findings-title">Findings: what the email says against what the evidence shows</h2>
      {contradictions.length === 0 ? (
        <p className="m-0">No claim was contradicted.</p>
      ) : (
        <Table rows={contradictions} claimsById={claimsById} countedBy={countedBy} />
      )}
      {others.length > 0 && (
        <details className="mt-3">
          <summary className="font-medium">
            {others.length} other {others.length === 1 ? 'check' : 'checks'}: consistent or not checkable
          </summary>
          <div className="mt-2">
            <Table rows={others} claimsById={claimsById} countedBy={countedBy} />
          </div>
        </details>
      )}
    </section>
  )
}
