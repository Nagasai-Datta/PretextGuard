// The limits the API enforces (src/api/settings.py), checked here first so a request that the API would refuse is not sent. The API stays the authority:
// these numbers only save a round trip and give a clearer message.

export const MAX_EMAIL_BYTES = 300_000
export const MAX_THREAD_MESSAGES = 50
export const MAX_THREAD_BYTES = 1_500_000
export const MAX_DOMAIN_CHARS = 253

const encoder = new TextEncoder()

// Size in UTF-8 bytes, which is what the API counts (a euro sign is 3 bytes, not 1 character).
export function byteLength(text) {
  return encoder.encode(text).length
}

export function formatBytes(n) {
  if (n < 1000) return `${n} bytes`
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`
}

// Exact, for a message that says by how much a limit was missed (300,001 bytes against 300,000 must not both read "300 KB").
const exactBytes = (n) => `${n.toLocaleString('en')} bytes`

// A message for each way an email can be unusable, or null when it is fine.
export function emailProblem(text) {
  if (!text || !text.trim()) return 'The email is empty.'
  const size = byteLength(text)
  if (size > MAX_EMAIL_BYTES) return `The email is ${exactBytes(size)}; the limit is ${exactBytes(MAX_EMAIL_BYTES)}.`
  return null
}

export function threadProblem(messages) {
  if (messages.length === 0) return 'Add at least one message.'
  if (messages.length > MAX_THREAD_MESSAGES) return `A thread can have at most ${MAX_THREAD_MESSAGES} messages.`
  let total = 0
  for (let i = 0; i < messages.length; i += 1) {
    const problem = emailProblem(messages[i].text)
    if (problem) return `Message ${i + 1}: ${problem}`
    total += byteLength(messages[i].text)
  }
  if (total > MAX_THREAD_BYTES) return `The thread is ${exactBytes(total)}; the limit is ${exactBytes(MAX_THREAD_BYTES)} in total.`
  return null
}

// Letters, digits, hyphens and dots; labels of 1 to 63 characters that neither start nor end with a hyphen (as the API checks it). Empty is fine (not given).
export function domainProblem(value) {
  let text = value.trim().toLowerCase()
  if (text.endsWith('.')) text = text.slice(0, -1)
  if (!text) return null
  if (text.length > MAX_DOMAIN_CHARS) return 'The organisation domain is too long.'
  for (const label of text.split('.')) {
    if (label.length < 1 || label.length > 63 || label.startsWith('-') || label.endsWith('-') || !/^[a-z0-9-]+$/.test(label)) {
      return 'The organisation domain should look like acmecorp.com (letters, digits, hyphens and dots).'
    }
  }
  return null
}
