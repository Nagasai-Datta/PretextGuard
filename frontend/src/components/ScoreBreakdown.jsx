import { humanize, tacticLabel } from '../lib/format.js'

// The score, step by step, so nothing in the number is hidden. Only contradictions add points; the strongest row of each claim counts and the k-th
// claim counts half as much as the one before (so ten weak findings cannot outweigh one strong one).
const fixed = (n) => (Math.round(n * 100) / 100).toString()

export default function ScoreBreakdown({ detail }) {
  const groups = detail.groups
  return (
    <section className="card" aria-labelledby="score-title">
      <h2 id="score-title">How the score was built</h2>
      {groups.length === 0 ? (
        <p className="m-0">No contradiction was found, so no contradiction points were added.</p>
      ) : (
        <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Table, scrolls sideways on a narrow screen">
          <table className="table min-w-[34rem]">
            <thead>
              <tr>
                <th>Claim</th>
                <th>Rule</th>
                <th>Severity</th>
                <th className="num">Base</th>
                <th className="num">Reliability</th>
                <th className="num">Weight</th>
                <th className="num">Counted</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={`${g.claim_id}|${g.rule}`}>
                  <td>{humanize(g.claim_type)}</td>
                  <td className="mono">{g.rule}</td>
                  <td>
                    <span className={`chip sev-${g.severity}`}>{g.severity}</span>
                  </td>
                  <td className="num">{fixed(g.base)}</td>
                  <td className="num">{fixed(g.reliability)}</td>
                  <td className="num">{fixed(g.weight)}</td>
                  <td className="num">{fixed(g.counted)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ol className="mt-3 list-decimal pl-5 text-sm">
        <li>
          Contradiction points: <span className="font-medium tabular-nums">{fixed(detail.contradiction_points)}</span> (base points for the severity, times the rule's
          reliability, times the weight of the claim's place in the list).
        </li>
        <li>
          Pressure multiplier: <span className="font-medium tabular-nums">x {fixed(detail.multiplier)}</span>
          {detail.pressure.length > 0 ? ` (${detail.pressure.map(tacticLabel).join(' and ')} detected next to a contradiction, +25% each)` : ' (no urgency or secrecy next to a contradiction)'}.
        </li>
        <li>
          Tactic points: <span className="font-medium tabular-nums">+ {fixed(detail.tactic_points)}</span>
          {detail.scored_tactics.length > 0 ? ` (${detail.scored_tactics.map(tacticLabel).join(', ')}; 4 each, at most 12)` : ' (no scored tactic detected)'}.
        </li>
        <li>
          Total <span className="tabular-nums">{fixed(detail.raw)}</span>
          {detail.capped ? ', capped at 100' : ''}, rounded: <span className="font-medium tabular-nums">{detail.score}</span>, which is {detail.band}.
        </li>
      </ol>
      <p className="hint m-0 mt-2">The bands are 0 to 34 Low risk, 35 to 69 Suspicious, 70 to 100 High risk. Rule reliability and the point values come from `src/router/score.py` (score version {detail.version}).</p>
    </section>
  )
}
