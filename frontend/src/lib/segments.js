// Turning character offsets into pieces of text that can be drawn.
//
// The API gives every highlight and claim as an offset into the text it read (`text_read`). Those offsets count Python characters, that is Unicode code
// points. JavaScript strings count UTF-16 units, where an emoji is two units, so slicing a JavaScript string at the API's offsets would cut an emoji in
// half and shift everything after it. Array.from(text) splits a string into code points, so the offsets fit.
//
// buildSegments(text, spans) returns the whole text as consecutive pieces, each with the list of spans that cover it. The pieces never overlap and
// together give back the text exactly. A span that does not fit the text (not whole numbers, start not before end, outside the text) is skipped and
// counted, never drawn wrongly.
//
// Nothing here makes HTML: a piece is plain text, and the component that draws it puts it in a text node.

export function buildSegments(text, spans) {
  const points = Array.from(typeof text === 'string' ? text : '')
  const length = points.length
  const valid = []
  let skipped = 0
  for (const span of spans || []) {
    const { start, end } = span
    if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && start < end && end <= length) valid.push(span)
    else skipped += 1
  }

  const cuts = new Set([0, length])
  for (const span of valid) {
    cuts.add(span.start)
    cuts.add(span.end)
  }
  const ordered = [...cuts].sort((a, b) => a - b)

  const segments = []
  for (let i = 0; i + 1 < ordered.length; i += 1) {
    const start = ordered[i]
    const end = ordered[i + 1]
    segments.push({
      start,
      end,
      text: points.slice(start, end).join(''),
      spans: valid.filter((span) => span.start <= start && span.end >= end),
    })
  }
  return { segments, skipped }
}

// The strongest tactic span of a piece (by weight), or null: it decides the colour of the piece.
export function strongestTactic(segmentSpans) {
  let best = null
  for (const span of segmentSpans) {
    if (span.kind === 'tactic' && (best === null || span.weight > best.weight)) best = span
  }
  return best
}

// The words that carried the most weight per tactic, for a list below the text (so the highlights are also readable without hovering).
export function topWords(highlights, perTactic = 6) {
  const byTactic = new Map()
  for (const h of highlights) {
    const words = byTactic.get(h.tactic) || new Map()
    const word = String(h.word || '').toLowerCase()
    const entry = words.get(word) || { word, weight: 0, count: 0 }
    entry.weight = Math.max(entry.weight, h.weight)
    entry.count += 1
    words.set(word, entry)
    byTactic.set(h.tactic, words)
  }
  const result = {}
  for (const [tactic, words] of byTactic) {
    result[tactic] = [...words.values()].sort((a, b) => b.weight - a.weight).slice(0, perTactic)
  }
  return result
}
