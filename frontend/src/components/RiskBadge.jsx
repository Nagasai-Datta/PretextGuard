import { BANDS } from '../lib/format.js'

// The headline: the score as a big number, its band as a word on a coloured chip (never colour alone), a meter with the band limits, and what to do.
// "Low risk" is blue on purpose: green would read as "safe", which this tool never says.
const CUTS = [35, 70]

export default function RiskBadge({ report }) {
  const band = BANDS[report.verdict]
  const key = band ? band.key : 'low'
  const score = Math.max(0, Math.min(100, report.score))
  return (
    <section className="card" aria-labelledby="risk-title">
      <h2 id="risk-title">Result</h2>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-baseline gap-1">
          <span className="text-6xl font-semibold leading-none tabular-nums" aria-label={`Risk score ${report.score} out of 100`}>
            {report.score}
          </span>
          <span className="hint">/ 100</span>
        </div>
        <div>
          <span className="chip text-base" style={{ background: `var(--band-${key})`, color: `var(--band-${key}-ink)` }}>
            {report.verdict}
          </span>
          {band && <p className="hint m-0 mt-1">{band.meaning}</p>}
        </div>
        <p className="hint m-0 ml-auto">
          {report.mode === 'thread' ? 'Thread: the newest message was judged' : 'One email'} · request {report.request_id}
        </p>
      </div>
      <div className="mt-4">
        <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label="Risk score">
          <span style={{ width: `${score}%`, background: `var(--band-${key})` }} />
        </div>
        <div className="meter-ticks">
          <span style={{ left: '0%', transform: 'none' }}>0</span>
          {CUTS.map((cut) => (
            <span key={cut} style={{ left: `${cut}%` }}>
              {cut}
            </span>
          ))}
          <span style={{ left: '100%', transform: 'translateX(-100%)' }}>100</span>
        </div>
      </div>
      <p className="m-0 mt-1">
        <span className="font-medium">What to do: </span>
        {report.action}
      </p>
      <p className="hint m-0 mt-2">
        Score {report.versions.score}, rules {report.versions.rules}, thread rules {report.versions.thread_rules}, claim patterns {report.versions.claim_patterns}. The score
        is built from contradictions only; see "How the score was built" below.
      </p>
    </section>
  )
}
