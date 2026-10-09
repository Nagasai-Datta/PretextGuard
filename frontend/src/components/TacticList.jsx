import { percent, tacticClass, tacticLabel } from '../lib/format.js'

// The seven manipulation tactics: the classifier's probability, the threshold it must reach (the black tick), and whether it counts towards the score.
// Reciprocity, social proof and liking are shown but never scored (too few labelled examples to trust them).
export default function TacticList({ tactics }) {
  return (
    <section className="card" aria-labelledby="tactics-title">
      <h2 id="tactics-title">Pressure tactics</h2>
      <ul className="m-0 grid list-none gap-x-8 gap-y-3 p-0 md:grid-cols-2">
        {tactics.map((t) => (
          <li key={t.name} className={tacticClass(t.name)}>
            <div className="mb-1 flex items-center gap-2">
              <span className="swatch" aria-hidden="true" />
              <span className="font-medium">{tacticLabel(t.name)}</span>
              {t.fired ? <span className="chip sev-medium">Detected</span> : <span className="chip sev-ok">Not detected</span>}
              {!t.scored && <span className="hint">shown, not scored</span>}
              <span className="ml-auto tabular-nums">{percent(t.probability)}</span>
            </div>
            <div className="pbar" role="img" aria-label={`${tacticLabel(t.name)}: probability ${percent(t.probability)}, threshold ${percent(t.threshold)}`}>
              <span style={{ width: `${Math.max(0, Math.min(1, t.probability)) * 100}%` }} />
              <i style={{ left: `${Math.max(0, Math.min(1, t.threshold)) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
      <p className="hint m-0 mt-3">The black tick is the threshold the probability must reach. A detected tactic adds a few points (and raises a contradiction's weight for urgency and secrecy); it never adds a contradiction by itself.</p>
    </section>
  )
}
