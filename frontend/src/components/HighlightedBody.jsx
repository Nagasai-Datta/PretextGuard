import { useMemo, useState } from 'react'
import { buildSegments, strongestTactic, topWords } from '../lib/segments.js'
import { humanize, percent, tacticClass, tacticLabel } from '../lib/format.js'

// The text the analysis read, with two kinds of marks:
//   - a wash of the tactic's colour on the words that pushed a detected tactic up (LIME, only after the second call),
//   - a dashed underline under each claim the extractor found.
// Offsets come from the API in Python characters, so buildSegments cuts the text by code points. Every piece is drawn as a text node: nothing is
// interpreted as HTML, so an email full of tags shows as tags. The text here is the redacted text (links, addresses and file names replaced).

function claimSpans(claims, zone) {
  return claims
    .filter((claim) => (claim.attributes && claim.attributes.zone) === zone && Array.isArray(claim.span))
    .map((claim) => ({ kind: 'claim', start: claim.span[0], end: claim.span[1], claim }))
}

function Pieces({ text, spans, showTactics, showClaims }) {
  const { segments, skipped } = useMemo(() => buildSegments(text, spans), [text, spans])
  return (
    <>
      {segments.map((segment) => {
        const active = segment.spans.filter((span) => (span.kind === 'tactic' ? showTactics : showClaims))
        if (active.length === 0) return <span key={segment.start}>{segment.text}</span>
        const tactic = strongestTactic(active)
        const claim = active.find((span) => span.kind === 'claim')
        const classes = [tactic ? `hl ${tacticClass(tactic.tactic)}` : '', claim ? 'claim' : ''].filter(Boolean).join(' ')
        const title = [
          tactic ? `${tacticLabel(tactic.tactic)}: weight ${tactic.weight}` : '',
          claim ? `Claim: ${humanize(claim.claim.type)}` : '',
        ]
          .filter(Boolean)
          .join(' · ')
        const Tag = tactic ? 'mark' : 'span'
        return (
          <Tag key={segment.start} className={classes} title={title}>
            {segment.text}
          </Tag>
        )
      })}
      {skipped > 0 && <span className="hint block">({skipped} marks did not fit the text and were left out.)</span>}
    </>
  )
}

export default function HighlightedBody({ report, explainStatus, explainError, retryLeft, onExplain }) {
  const [showTactics, setShowTactics] = useState(true)
  const [showClaims, setShowClaims] = useState(true)

  const highlights = useMemo(
    () => report.tactics.flatMap((t) => t.highlights.map((h) => ({ ...h, kind: 'tactic', tactic: t.name }))),
    [report.tactics],
  )
  const bodySpans = useMemo(() => [...highlights, ...claimSpans(report.claims, 'body')], [highlights, report.claims])
  const signatureSpans = useMemo(() => claimSpans(report.claims, 'signature'), [report.claims])
  const words = useMemo(() => topWords(highlights), [highlights])
  const withWords = report.tactics.filter((t) => t.highlights.length > 0)

  return (
    <section className="card" aria-labelledby="text-title">
      <h2 id="text-title">The text that was read</h2>
      <p className="hint m-0 mb-2">
        Links, addresses and file names are replaced by [URL], [EMAIL], [FILE] and [DOMAIN] before any model sees the text. Only the first 2,000 characters are read.
      </p>
      <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={showTactics} onChange={(event) => setShowTactics(event.target.checked)} />
          Words behind the tactics
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={showClaims} onChange={(event) => setShowClaims(event.target.checked)} />
          <span className="claim">Claims</span>
        </label>
        {withWords.length > 0 && (
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0" aria-label="Colour key">
            {withWords.map((t) => (
              <li key={t.name} className={`flex items-center gap-1 ${tacticClass(t.name)}`}>
                <span className="swatch" aria-hidden="true" />
                {tacticLabel(t.name)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mono max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-line p-3 [overflow-wrap:anywhere]" tabIndex={0} aria-label="Text of the email">
        <Pieces text={report.text_read} spans={bodySpans} showTactics={showTactics} showClaims={showClaims} />
      </div>

      {report.signature_read && (
        <details className="mt-2">
          <summary className="text-sm">Signature block that was read</summary>
          <div className="mono mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line p-3 [overflow-wrap:anywhere]">
            <Pieces text={report.signature_read} spans={signatureSpans} showTactics={false} showClaims={showClaims} />
          </div>
        </details>
      )}

      <div className="mt-3" aria-live="polite">
        {explainStatus === 'working' && (
          <p className="m-0 flex items-center gap-2">
            <span className="spinner" aria-hidden="true" /> Finding the words behind the tactics. The score above does not depend on this.
          </p>
        )}
        {explainStatus === 'off' && (
          <p className="m-0 flex flex-wrap items-center gap-3">
            <span className="hint">Word highlights were not asked for.</span>
            <button type="button" className="btn" onClick={onExplain}>
              Find the words
            </button>
          </p>
        )}
        {explainStatus === 'failed' && (
          <p className="m-0 flex flex-wrap items-center gap-3">
            <span className="text-critical">The highlights could not be made: {explainError ? explainError.detail : 'unknown error'}</span>
            <button type="button" className="btn" onClick={onExplain} disabled={retryLeft > 0}>
              {retryLeft > 0 ? `Try again in ${retryLeft} s` : 'Try again'}
            </button>
          </p>
        )}
        {explainStatus === 'done' && withWords.length === 0 && <p className="hint m-0">No tactic was detected, so there are no words to mark.</p>}
        {explainStatus === 'done' && withWords.length > 0 && (
          <div>
            <p className="m-0 font-medium">Words that weighed most</p>
            <ul className="m-0 mt-1 list-none p-0 text-sm">
              {withWords.map((t) => (
                <li key={t.name} className={tacticClass(t.name)}>
                  <span className="swatch" aria-hidden="true" /> <span className="font-medium">{tacticLabel(t.name)}</span>
                  {' '}({percent(t.probability)}):{' '}
                  {(words[t.name] || []).map((w) => w.word).join(', ')}
                </li>
              ))}
            </ul>
            <p className="hint m-0 mt-2">
              These come from a local explanation (LIME) of the classifier only. The exact words can change from one run to the next, and many are ordinary words around the real cue.
              The verifiers and the score do not use them.
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
