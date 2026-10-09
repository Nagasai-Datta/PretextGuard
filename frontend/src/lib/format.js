// Small formatting helpers and the fixed vocabularies of the report. Everything returns plain strings or numbers; nothing returns HTML.

export const TACTICS = ['authority', 'urgency', 'scarcity', 'reciprocity', 'social_proof', 'liking', 'secrecy']

const TACTIC_LABELS = {
  authority: 'Authority',
  urgency: 'Urgency',
  scarcity: 'Scarcity',
  reciprocity: 'Reciprocity',
  social_proof: 'Social proof',
  liking: 'Liking',
  secrecy: 'Secrecy',
}

export function tacticLabel(name) {
  return TACTIC_LABELS[name] || humanize(name)
}

// Only these have a colour class in index.css; anything else the API might send gets none.
export function tacticClass(name) {
  return TACTICS.includes(name) ? `t-${name}` : ''
}

export function humanize(text) {
  const words = String(text ?? '').replace(/_/g, ' ').trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : ''
}

const integer = new Intl.NumberFormat('en')

// A table cell: null is empty, whole numbers get thousands separators, other numbers lose floating-point noise, everything else is shown as text.
export function formatCell(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value)
    return Number.isInteger(value) ? integer.format(value) : String(Number(value.toFixed(4)))
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function percent(fraction, digits = 0) {
  return `${(fraction * 100).toFixed(digits)}%`
}

export const BANDS = {
  'Low risk': { key: 'low', meaning: 'No contradiction was found among the claims that could be checked.' },
  Suspicious: { key: 'sus', meaning: 'At least one claim is contradicted by the evidence.' },
  'High risk': { key: 'high', meaning: 'Strong or several contradictions, usually with pressure tactics.' },
}

// How a ledger row is shown: a word (never colour alone) and a style key.
export function rowKind(row) {
  if (row.contradiction === true) return { label: `Contradiction (${row.severity})`, key: row.severity }
  if (row.contradiction === false) return { label: 'Consistent', key: 'ok' }
  return { label: 'Not checkable', key: 'na' }
}
