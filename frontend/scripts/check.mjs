// Phase 12 checks on the interface, run with:   npm run check      (from frontend/, after npm run build)
//
// It reads files and runs the small pure functions of src/lib; it needs no browser and no API. It prints one line per check and writes
// results/frontend_checks.csv (check, item, value, expected, status; PASS, FAIL or info). It exits with 1 if any check failed.
//
// What it proves:
//   1. SOURCE   the source never turns text into HTML (no dangerouslySetInnerHTML, innerHTML, eval, document.write ...), has no links, stores nothing
//               in the browser and logs nothing to the console.
//   2. PINS     every package in package.json has an exact version, package-lock.json holds that same version, and `npm audit` finds nothing
//               (skipped when PG_SKIP_AUDIT=1, which the mutation check sets, or when there is no network).
//   3. BUNDLE   the built app (dist/) does not contain the API key, loads nothing from another host, and its index.html has no inline script, style
//               or event handler (so the strict Content-Security-Policy of `npm run preview` can hold).
//   4. LOGIC    the code that turns the API's offsets into pieces of text (src/lib/segments.js) and checks the size limits (src/lib/limits.js) gives the
//               right answers on hand-made cases, including emoji (Python and JavaScript count characters differently) and crooked offsets.
// The browser side (nothing runs, nothing leaves the page, the CSP holds) is checked by `npm run browser-check` (scripts/browser_check.mjs).

import { execFileSync } from 'node:child_process'
import { readFileSync, readdirSync, statSync, existsSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..') // frontend/
const PROJECT = resolve(ROOT, '..')
const OUT = join(PROJECT, 'results', 'frontend_checks.csv')

const rows = []
const add = (check, item, value, expected, status) => rows.push({ check, item, value: String(value), expected: String(expected), status })
const must = (check, item, value, expected, pass) => add(check, item, value, expected, pass ? 'PASS' : 'FAIL')
const info = (check, item, value, expected = '') => add(check, item, value, expected, 'info')

function walk(dir, keep) {
  const out = []
  if (!existsSync(dir)) return out
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) out.push(...walk(path, keep))
    else if (keep(path)) out.push(path)
  }
  return out
}
const read = (path) => readFileSync(path, 'utf8')

// ---------------------------------------------------------------------------------------------------------------------------------- 1. SOURCE
const sources = walk(join(ROOT, 'src'), (p) => /\.(jsx?|css)$/.test(p))
const code = sources.filter((p) => /\.jsx?$/.test(p))
// examples.js holds the hand-made emails (some with script payloads on purpose), so it is a data file, not code.
const codeNoData = code.filter((p) => !p.endsWith(join('lib', 'examples.js')))

const FORBIDDEN = [
  ['dangerouslySetInnerHTML', /dangerouslySetInnerHTML/],
  ['innerHTML or outerHTML', /\b(inner|outer)HTML\b/],
  ['insertAdjacentHTML', /insertAdjacentHTML/],
  ['document.write', /document\s*\.\s*write/],
  ['eval(', /\beval\s*\(/],
  ['new Function', /new\s+Function\s*\(/],
  ['inline event attribute set from code', /setAttribute\s*\(\s*['"`]on/],
  ['javascript: URL', /javascript:/i],
  ['a link element (<a )', /<a[\s>]/],
  ['an iframe', /<iframe/i],
  ['localStorage, sessionStorage, cookie or IndexedDB', /\b(localStorage|sessionStorage|indexedDB)\b|document\s*\.\s*cookie/],
  ['console output', /\bconsole\s*\./],
  ['a web socket or event source', /\b(WebSocket|EventSource)\b/],
  ['sendBeacon', /sendBeacon/],
]
for (const [label, pattern] of FORBIDDEN) {
  const hits = codeNoData.filter((p) => pattern.test(read(p))).map((p) => relative(ROOT, p))
  must('source', label, hits.length === 0 ? 0 : hits.join(' '), 0, hits.length === 0)
}
// Every address in the code is a relative path to our own API, never a full URL. (A URL in a comment is fine only if it is not http.)
const absolute = codeNoData.filter((p) => /https?:\/\//.test(read(p))).map((p) => relative(ROOT, p))
must('source', 'files with an http(s) URL', absolute.length === 0 ? 0 : absolute.join(' '), 0, absolute.length === 0)
info('source', 'source files read (code and CSS)', sources.length)

// examples.js: only ASCII, so no hidden or look-alike character can sit in a hand-made email.
const examplesPath = join(ROOT, 'src', 'lib', 'examples.js')
if (existsSync(examplesPath)) {
  const text = read(examplesPath)
  const nonAscii = [...text].filter((ch) => ch.codePointAt(0) > 126 || (ch.codePointAt(0) < 32 && ch !== '\n')).length
  must('source', 'non-ASCII characters in examples.js', nonAscii, 0, nonAscii === 0)
} else {
  must('source', 'examples.js exists', 'missing', 'present', false)
}

// ---------------------------------------------------------------------------------------------------------------------------------- 2. PINS
const pkg = JSON.parse(read(join(ROOT, 'package.json')))
const lockPath = join(ROOT, 'package-lock.json')
const lock = existsSync(lockPath) ? JSON.parse(read(lockPath)) : null
must('pins', 'package-lock.json exists', lock ? 'yes' : 'no', 'yes', Boolean(lock))
for (const section of ['dependencies', 'devDependencies']) {
  for (const [name, version] of Object.entries(pkg[section] || {})) {
    const exact = /^\d+\.\d+\.\d+$/.test(version)
    must('pins', `${name} is pinned exactly`, version, 'x.y.z', exact)
    if (lock) {
      const locked = lock.packages && lock.packages[`node_modules/${name}`] ? lock.packages[`node_modules/${name}`].version : 'not in lock file'
      must('pins', `${name} in the lock file`, locked, version, locked === version)
    }
  }
}

info('environment', 'node', process.version)
if (process.env.PG_SKIP_AUDIT === '1') {
  info('pins', 'npm audit', 'skipped (PG_SKIP_AUDIT=1)')
} else {
  let audit = null
  try {
    audit = JSON.parse(execFileSync('npm', ['audit', '--json'], { cwd: ROOT, encoding: 'utf8', timeout: 90_000, stdio: ['ignore', 'pipe', 'pipe'] }))
  } catch (error) {
    // npm audit exits with 1 when it finds something and still prints the JSON; no network gives no JSON.
    try {
      audit = JSON.parse(String(error.stdout || ''))
    } catch {
      audit = null
    }
  }
  if (audit && audit.metadata && audit.metadata.vulnerabilities) {
    const found = audit.metadata.vulnerabilities.total
    must('pins', 'npm audit: known vulnerabilities in the locked packages', found, 0, found === 0)
    info('pins', 'packages npm audit looked at', audit.metadata.dependencies ? audit.metadata.dependencies.total : '?')
  } else {
    info('pins', 'npm audit', 'could not run (no network?); run `npm audit` by hand')
  }
}

// ---------------------------------------------------------------------------------------------------------------------------------- 3. BUNDLE
const DIST = join(ROOT, 'dist')
const built = existsSync(join(DIST, 'index.html'))
must('bundle', 'dist/index.html exists (run npm run build first)', built ? 'yes' : 'no', 'yes', built)
if (built) {
  const files = walk(DIST, (p) => /\.(js|css|html|map|json|txt)$/.test(p))
  const everything = files.map((p) => [p, read(p)])

  // The API key must not be anywhere in what the browser receives.
  const envPath = join(PROJECT, '.env')
  const secrets = []
  if (existsSync(envPath)) {
    for (const line of read(envPath).split(/\r?\n/)) {
      const m = /^\s*(PRETEXTGUARD_[A-Z_]*KEY)\s*=\s*(.+?)\s*$/.exec(line)
      if (m) secrets.push([m[1], m[2].replace(/^['"]|['"]$/g, '')])
    }
  }
  if (secrets.length === 0) {
    info('bundle', 'API key searched for in dist/', 'no key found in ../.env, so nothing to search for', 'a key in .env')
  }
  for (const [name, secret] of secrets) {
    if (secret.length < 8) continue
    const where = everything.filter(([, text]) => text.includes(secret)).map(([p]) => relative(ROOT, p))
    must('bundle', `${name} (${secret.length} characters) appears in dist/`, where.length === 0 ? 'no' : where.join(' '), 'no', where.length === 0)
  }
  const header = everything.filter(([, text]) => /x-api-key/i.test(text)).map(([p]) => relative(ROOT, p))
  must('bundle', 'the header name X-API-Key appears in dist/', header.length === 0 ? 'no' : header.join(' '), 'no', header.length === 0)
  // The NAME of the setting appears in a help message ("Check PRETEXTGUARD_API_KEY in .env"). That is text for the reader, not the secret: only the value is a secret.
  const names = everything.filter(([, text]) => /PRETEXTGUARD_/.test(text)).map(([p]) => relative(ROOT, p))
  info('bundle', 'files that name a PRETEXTGUARD_ setting (help text only)', names.length === 0 ? 'none' : names.join(' '), 'names are not secrets; values were checked above')
  must('bundle', 'source maps shipped', everything.filter(([p]) => p.endsWith('.map')).length, 0, everything.filter(([p]) => p.endsWith('.map')).length === 0)

  // index.html: no inline script, no style attribute, no event handler, no absolute address for a script or style sheet.
  const html = read(join(DIST, 'index.html'))
  const inlineScripts = (html.match(/<script(?![^>]*\bsrc=)[^>]*>/gi) || []).length
  must('bundle', 'inline <script> in index.html', inlineScripts, 0, inlineScripts === 0)
  must('bundle', 'style attributes or <style> in index.html', (html.match(/\sstyle\s*=|<style/gi) || []).length, 0, (html.match(/\sstyle\s*=|<style/gi) || []).length === 0)
  must('bundle', 'on... event attributes in index.html', (html.match(/\son[a-z]+\s*=/gi) || []).length, 0, (html.match(/\son[a-z]+\s*=/gi) || []).length === 0)
  const external = (html.match(/(?:src|href)\s*=\s*["']https?:/gi) || []).length
  must('bundle', 'script or style sheet loaded from another host (index.html)', external, 0, external === 0)

  // CSS: nothing is fetched (no @import url or url() to a host).
  const css = everything.filter(([p]) => p.endsWith('.css'))
  const cssFetch = css.filter(([, text]) => /@import\s+(url\()?["']?https?:|url\(\s*["']?https?:/i.test(text)).map(([p]) => relative(ROOT, p))
  must('bundle', 'CSS that fetches from another host', cssFetch.length === 0 ? 0 : cssFetch.join(' '), 0, cssFetch.length === 0)

  // JS: nothing can open a connection except fetch() to our own relative address, and no address in a fetch/import is absolute.
  const js = everything.filter(([p]) => p.endsWith('.js'))
  for (const [label, pattern] of [
    ['fetch() to an absolute address', /fetch\(\s*["'`]https?:/],
    ['import() of an absolute address', /import\(\s*["'`]https?:/],
    ['sendBeacon', /sendBeacon\s*\(/],
    ['new WebSocket', /new\s+WebSocket\s*\(/],
    ['new EventSource', /new\s+EventSource\s*\(/],
    ['importScripts', /importScripts\s*\(/],
  ]) {
    const hits = js.filter(([, text]) => pattern.test(text)).map(([p]) => relative(ROOT, p))
    must('bundle', `JS with ${label}`, hits.length === 0 ? 0 : hits.join(' '), 0, hits.length === 0)
  }
  // Address strings that sit in the libraries as text (XML namespaces, links in error messages). They are never loaded; listed so none is a surprise.
  const hosts = new Map()
  for (const [, text] of js) {
    for (const m of text.matchAll(/https?:\/\/([A-Za-z0-9.-]+)/g)) hosts.set(m[1], (hosts.get(m[1]) || 0) + 1)
  }
  for (const [host, count] of [...hosts.entries()].sort()) info('bundle', `host named as text in the JS: ${host}`, `${count} times`, 'text only, never fetched')
  info('bundle', 'files in dist/', files.length)
  info('bundle', 'total size of dist/ (KB)', Math.round(files.reduce((sum, p) => sum + statSync(p).size, 0) / 1000))
}

// ---------------------------------------------------------------------------------------------------------------------------------- 4. LOGIC
const segments = await import(pathToFileURL(join(ROOT, 'src', 'lib', 'segments.js')))
const limits = await import(pathToFileURL(join(ROOT, 'src', 'lib', 'limits.js')))
const format = await import(pathToFileURL(join(ROOT, 'src', 'lib', 'format.js')))

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const test = (item, got, expected) => must('logic', item, JSON.stringify(got), JSON.stringify(expected), same(got, expected))
const pieces = (text, spans) => segments.buildSegments(text, spans).segments.map((s) => s.text)

// buildSegments
test('no spans: the whole text is one piece', pieces('hello world', []), ['hello world'])
test('empty text gives no pieces', pieces('', []), [])
test('one span cuts three pieces', pieces('hello big world', [{ start: 6, end: 9 }]), ['hello ', 'big', ' world'])
{
  // "a😀b cat": Python counts the emoji as one character, so "cat" is characters 4 to 7. JavaScript's own slice counts it as two units.
  const text = 'a\u{1F600}b cat'
  test('JavaScript slice at Python offsets is wrong with an emoji (why code points are used)', text.slice(4, 7) === 'cat', false)
  test('emoji before the span: offsets count code points', pieces(text, [{ start: 4, end: 7 }]), ['a\u{1F600}b ', 'cat'])
  test('a span covering the emoji is not cut in half', pieces(text, [{ start: 1, end: 2 }]), ['a', '\u{1F600}', 'b cat'])
}
{
  const result = segments.buildSegments('0123456789', [{ id: 'x', start: 0, end: 5 }, { id: 'y', start: 3, end: 8 }])
  test('overlap: pieces', result.segments.map((s) => s.text), ['012', '34', '567', '89'])
  test('overlap: the middle piece carries both spans', result.segments.map((s) => s.spans.map((sp) => sp.id)), [['x'], ['x', 'y'], ['y'], []])
}
for (const [label, span] of [
  ['start equal to end', { start: 2, end: 2 }],
  ['start after end', { start: 5, end: 2 }],
  ['negative start', { start: -1, end: 3 }],
  ['end past the text', { start: 0, end: 99 }],
  ['a fraction', { start: 0.5, end: 3 }],
  ['text instead of numbers', { start: '0', end: '3' }],
  ['missing numbers', {}],
]) {
  const result = segments.buildSegments('hello', [span])
  must('logic', `crooked span skipped and counted: ${label}`, `skipped ${result.skipped}, pieces ${result.segments.length}`, 'skipped 1, pieces 1', result.skipped === 1 && result.segments.length === 1 && result.segments[0].text === 'hello')
}
test('a non-string text is read as empty', pieces(null, [{ start: 0, end: 1 }]), [])
{
  // Fuzz: random texts (with emoji and combining marks) and random spans, valid or not. The pieces must always join back into the text, never overlap
  // and never hold an invalid span.
  let state = 20261009
  const random = () => {
    state = (state + 0x6d2b79f5) | 0
    let t = Math.imul(state ^ (state >>> 15), 1 | state)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  const alphabet = ['a', 'b', ' ', '\n', '\u{1F600}', 'é', 'é', '中', '\u{1D11E}']
  let bad = 0
  for (let i = 0; i < 300; i += 1) {
    const text = Array.from({ length: Math.floor(random() * 40) }, () => alphabet[Math.floor(random() * alphabet.length)]).join('')
    const length = Array.from(text).length
    const spans = Array.from({ length: Math.floor(random() * 6) }, () => ({ start: Math.floor(random() * (length + 4)) - 1, end: Math.floor(random() * (length + 4)) - 1 }))
    const { segments: parts } = segments.buildSegments(text, spans)
    let ok = parts.map((s) => s.text).join('') === text
    for (let j = 0; j + 1 < parts.length; j += 1) if (parts[j].end !== parts[j + 1].start) ok = false
    for (const part of parts) for (const span of part.spans) if (!(span.start <= part.start && span.end >= part.end && span.start < span.end)) ok = false
    if (!ok) bad += 1
  }
  must('logic', 'fuzz: 300 random texts and spans rebuild the text exactly', `${bad} failures`, '0 failures', bad === 0)
}
test('strongestTactic picks the heaviest tactic span', segments.strongestTactic([{ kind: 'claim', weight: 9 }, { kind: 'tactic', weight: 0.2, id: 1 }, { kind: 'tactic', weight: 0.5, id: 2 }]).id, 2)
test('strongestTactic is null without a tactic span', segments.strongestTactic([{ kind: 'claim', weight: 1 }]), null)
{
  const words = segments.topWords([
    { tactic: 'urgency', word: 'Urgent', weight: 0.3 },
    { tactic: 'urgency', word: 'urgent', weight: 0.5 },
    { tactic: 'urgency', word: 'today', weight: 0.4 },
    { tactic: 'secrecy', word: 'secret', weight: 0.2 },
  ])
  test('topWords merges case and sorts by weight', words.urgency.map((w) => [w.word, w.weight, w.count]), [['urgent', 0.5, 2], ['today', 0.4, 1]])
}

// limits
const bytes = (n) => 'x'.repeat(n)
test('an email of exactly the limit is accepted', limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES)), null)
must('logic', 'an email one byte over the limit is refused', limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES + 1)), 'a message', typeof limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES + 1)) === 'string')
must('logic', 'the refusal names both sizes exactly', limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES + 1)), '300,001 and 300,000 bytes', /300,001 bytes/.test(limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES + 1))) && /300,000 bytes/.test(limits.emailProblem(bytes(limits.MAX_EMAIL_BYTES + 1))))
test('bytes are counted, not characters (a euro sign is 3 bytes)', limits.emailProblem('€'.repeat(100_001)) !== null, true)
test('an empty email is refused', limits.emailProblem('   \n') !== null, true)
test('a thread of 0 messages is refused', limits.threadProblem([]) !== null, true)
test('a thread of 51 messages is refused', limits.threadProblem(Array.from({ length: 51 }, () => ({ text: 'hi there' }))) !== null, true)
test('a thread of 50 short messages is accepted', limits.threadProblem(Array.from({ length: 50 }, () => ({ text: 'hi there' }))), null)
test('a thread over the total size is refused', limits.threadProblem(Array.from({ length: 6 }, () => ({ text: bytes(290_000) }))) !== null, true)
for (const [value, ok] of [['', true], ['acmecorp.com', true], ['Acme-Corp.co.uk.', true], ['bad domain!', false], ['-bad.com', false], ['a..b.com', false], ['x'.repeat(64) + '.com', false], ['a.'.repeat(130) + 'com', false]]) {
  test(`domain ${JSON.stringify(value.length > 20 ? value.slice(0, 12) + '...' : value)} ${ok ? 'accepted' : 'refused'}`, limits.domainProblem(value) === null, ok)
}

// format
test('formatCell: null is empty', format.formatCell(null), '')
test('formatCell: floating-point noise is removed', format.formatCell(0.30000000000000004), '0.3')
test('formatCell: whole numbers get separators', format.formatCell(14879), '14,879')
test('formatCell: booleans are words', format.formatCell(true), 'yes')
test('humanize', format.humanize('affiliation_internal'), 'Affiliation internal')
test('tacticClass refuses a name it does not know', format.tacticClass('x" onmouseover="alert(1)'), '')
test('tacticLabel falls back to readable text', format.tacticLabel('new_thing'), 'New thing')

// ---------------------------------------------------------------------------------------------------------------------------------- output
const quote = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, ['check,item,value,expected,status', ...rows.map((r) => [r.check, r.item, r.value, r.expected, r.status].map(quote).join(','))].join('\n') + '\n')

let failed = 0
for (const r of rows) {
  if (r.status === 'FAIL') failed += 1
  if (r.status !== 'info') console.log(`${r.status}  [${r.check}] ${r.item}${r.status === 'FAIL' ? `  (got ${r.value}, expected ${r.expected})` : ''}`)
}
const count = (s) => rows.filter((r) => r.status === s).length
console.log(`\n${count('PASS')} PASS, ${count('FAIL')} FAIL, ${count('info')} info. Written to ${relative(PROJECT, OUT)}`)
process.exit(failed === 0 ? 0 : 1)
