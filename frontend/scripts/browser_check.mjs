// Phase 12 browser checks, run with:   npm run browser-check      (from frontend/)
//
// It needs the API and the built interface to be running:
//     terminal 1 (project root, venv):   python -m src.api.main
//     terminal 2 (frontend/):            npm run build && npm run preview
//     terminal 3 (frontend/):            npm run browser-check
// and a Chromium-based browser: Google Chrome or Edge if installed, or `npx playwright-core install chromium`, or CHROMIUM_PATH=/path/to/chrome.
//
// It opens the page in a real (headless) browser, uses it like a person, and writes results/frontend_browser_checks.csv (check, item, value, expected,
// status). The checks compare what is DRAWN with what the API ANSWERED, so they hold whichever model is loaded; the scores themselves are reported as
// info, never asserted. Error states (429, 503, 413, 401, 422, an unreachable API, a failed explanation) are produced by answering the page's requests
// with made-up responses, which tests the page, not the API (the API's own refusals are tested by `python -m src.api.selftest`).
//
// Rate limits: the API allows 6 /explain calls a minute. The script counts its real ones and waits when it would go over, so it can take a minute or two.

import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const HERE = dirname(fileURLToPath(import.meta.url))
const PROJECT = resolve(HERE, '..', '..')
const OUT = join(PROJECT, 'results', 'frontend_browser_checks.csv')
const BASE = process.env.BASE || 'http://127.0.0.1:4173/'
const API = process.env.API || 'http://127.0.0.1:8000'

const rows = []
const add = (check, item, value, expected, status) => rows.push({ check, item, value: String(value), expected: String(expected), status })
const must = (check, item, pass, value = '', expected = '') => add(check, item, pass ? value || 'ok' : value || 'not ok', expected || 'ok', pass ? 'PASS' : 'FAIL')
const info = (check, item, value) => add(check, item, value, '', 'info')

// ------------------------------------------------------------------------------------------------------------------------------ browser
async function launch() {
  const args = typeof process.getuid === 'function' && process.getuid() === 0 ? ['--no-sandbox'] : []
  if (process.env.CHROMIUM_PATH) return chromium.launch({ executablePath: process.env.CHROMIUM_PATH, args })
  for (const channel of ['chrome', 'msedge']) {
    try {
      return await chromium.launch({ channel, args })
    } catch {
      // not installed: try the next one
    }
  }
  try {
    return await chromium.launch({ args })
  } catch {
    console.error('No browser found. Install Google Chrome, or run:  npx playwright-core install chromium   (or set CHROMIUM_PATH).')
    process.exit(2)
  }
}

// Five real /explain calls fit in a minute. Wait before a step that would be the sixth.
const explainTimes = []
async function pace(extra = 1) {
  const now = Date.now()
  while (explainTimes.length && now - explainTimes[0] > 60_000) explainTimes.shift()
  if (explainTimes.length + extra > 5) {
    const wait = explainTimes[0] + 61_000 - now
    console.log(`  (waiting ${Math.ceil(wait / 1000)} s for the explain rate limit)`)
    await new Promise((r) => setTimeout(r, Math.max(wait, 0)))
    explainTimes.length = 0
  }
  for (let i = 0; i < extra; i += 1) explainTimes.push(Date.now())
}

const dialogs = []
const pageErrors = []
const cspViolations = []
const consoleErrors = []
const realRateLimited = []

async function fresh(browser, viewport = { width: 1280, height: 900 }) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  page.on('pageerror', (e) => pageErrors.push(e.message))
  page.on('response', (r) => {
    if (r.status() === 429 && r.headers()['x-pg-mock'] !== '1') realRateLimited.push(new URL(r.url()).pathname)
  })
  page.on('dialog', async (d) => {
    dialogs.push(d.message())
    await d.dismiss()
  })
  page.on('console', (m) => {
    // A refused request (429, 503 ...) is logged by the browser itself; those are the made-up errors of this script and are expected.
    if (m.type() === 'error' && !/Failed to load resource: the server responded with a status of (4|5)\d\d/.test(m.text())) consoleErrors.push(m.text())
  })
  await page.addInitScript(() => {
    window.__csp = []
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`))
  })
  await page.goto(BASE)
  await page.waitForSelector('h1')
  page.close_all = async () => {
    cspViolations.push(...(await page.evaluate(() => window.__csp).catch(() => [])))
    await context.close()
  }
  return page
}

// The made-up answers carry a marker header, so a real refusal by the rate limiter can be told from one of ours.
const json = (status, body, headers = {}) => ({ status, contentType: 'application/json', headers: { ...headers, 'x-pg-mock': '1' }, body: JSON.stringify(body) })
const example = (page, id) => page.selectOption('select[aria-label="Load an example email"]', id)
const text = async (page, selector) => (await page.textContent(selector)) ?? ''

// Run an example through the page and return the API's report (captured from the response) next to what the page drew.
async function runExample(page, id, { explain }) {
  await example(page, id)
  if (explain) await page.check('input[type=checkbox]')
  else await page.uncheck('input[type=checkbox]')
  const analyzed = page.waitForResponse((r) => /\/api\/analyze(\/thread)?$/.test(new URL(r.url()).pathname) && r.request().method() === 'POST')
  if (explain) await pace()
  await page.click('button[type=submit]')
  const response = await analyzed
  let report = await response.json()
  await page.waitForSelector('#risk-title', { timeout: 30_000 })
  // With the second call the page replaces the report by the explained one: same score and findings, plus the words.
  if (explain) await page.waitForSelector('text=/Words that weighed most|No tactic was detected|could not be made/', { timeout: 90_000 })
  return report
}

async function drawn(page) {
  return page.evaluate(() => {
    const q = (s) => document.querySelector(s)
    const count = (s) => document.querySelectorAll(s).length
    return {
      score: q('[aria-label^="Risk score"]')?.textContent ?? null,
      verdict: q('section[aria-labelledby="risk-title"] .chip.text-base')?.textContent ?? null,
      contradictionRows: count('section[aria-labelledby="findings-title"] > div[role="region"] tbody tr'),
      claimRows: count('section[aria-labelledby="claims-title"] tbody tr'),
      tacticItems: count('section[aria-labelledby="tactics-title"] li'),
      detected: [...document.querySelectorAll('section[aria-labelledby="tactics-title"] .chip')].filter((c) => c.textContent === 'Detected').length,
      bodyText: q('div[aria-label="Text of the email"]')?.textContent ?? null,
      marks: [...document.querySelectorAll('div[aria-label="Text of the email"] mark')].map((m) => m.textContent),
      timeline: count('ol[aria-label="Messages in order"] > li'),
      scripts: count('main script, main iframe, main img, main a, main object, main embed'),
      requestId: q('section[aria-labelledby="risk-title"] p.hint')?.textContent ?? '',
    }
  })
}

// ------------------------------------------------------------------------------------------------------------------------------ the checks
const browser = await launch()
const started = Date.now()

try {

// 0. The page and the API
{
  const head = await fetch(BASE, { method: 'HEAD' }).catch(() => null)
  must('serve', 'the interface answers at ' + BASE, Boolean(head && head.ok), head ? String(head.status) : 'no answer', '200')
  const csp = head ? head.headers.get('content-security-policy') || '' : ''
  must('serve', 'it sends a Content-Security-Policy (so this is `npm run preview`, not the dev server)', /script-src 'self'/.test(csp), csp ? csp.slice(0, 60) : 'none', "script-src 'self'")
  for (const [name, expected] of [['x-content-type-options', 'nosniff'], ['x-frame-options', 'DENY'], ['referrer-policy', 'no-referrer'], ['cross-origin-resource-policy', 'same-origin']]) {
    const value = head ? head.headers.get(name) : null
    must('serve', `header ${name}`, value === expected, value ?? 'missing', expected)
  }
  const health = await fetch(new URL('api/health', BASE)).then((r) => r.json()).catch(() => null)
  must('serve', 'GET /api/health through the interface server: API up and model loaded', Boolean(health && health.model_loaded), health ? JSON.stringify({ status: health.status, model_loaded: health.model_loaded }) : 'no answer', 'model_loaded true')
  if (!head || !head.ok || !health || !health.model_loaded) {
    console.error('The interface or the API is not running (see the top of this file). Nothing else was checked.')
    process.exit(2)
  }
  // The key is added by the interface server. A call through it with no key of its own works; the same call straight to the API is refused.
  const body = JSON.stringify({ email: 'Subject: hi\n\nhello there, a short test message.' })
  const headers = { 'content-type': 'application/json' }
  const viaProxy = await fetch(new URL('api/analyze', BASE), { method: 'POST', headers, body }).then((r) => r.status)
  must('serve', 'POST /api/analyze through the interface server with no key of our own: accepted (the server adds it)', viaProxy === 200, String(viaProxy), '200')
  const direct = await fetch(API + '/analyze', { method: 'POST', headers, body }).then((r) => r.status, () => null)
  if (direct === null) info('serve', `the API was not reachable directly at ${API} (set API=... to test the key requirement)`, 'skipped')
  else must('serve', 'the same call straight to the API with no key: refused', direct === 401, String(direct), '401')
}

// 1. Real analyses: what is drawn equals what the API answered
const SAMPLES = [
  { id: 'david', explain: true },
  { id: 'xss', explain: true },
  { id: 'honest', explain: false },
  { id: 'body', explain: false },
  { id: 'takeover', explain: false },
]
for (const sample of SAMPLES) {
  const page = await fresh(browser)
  const report = await runExample(page, sample.id, { explain: sample.explain })
  const d = await drawn(page)
  let shown = report
  if (sample.explain) {
    // The page replaced the report by the explained one; the score and findings are the same, so compare those with the first answer.
    must(sample.id, 'the explained report keeps the score and the verdict', d.score === String(report.score) && d.verdict === report.verdict, `${d.score} ${d.verdict}`, `${report.score} ${report.verdict}`)
  } else {
    must(sample.id, 'score drawn equals score answered', d.score === String(report.score), String(d.score), String(report.score))
    must(sample.id, 'verdict drawn equals verdict answered', d.verdict === report.verdict, String(d.verdict), report.verdict)
  }
  const contradictions = shown.ledger.filter((row) => row.contradiction === true).length
  must(sample.id, 'contradiction rows drawn equal contradictions answered', d.contradictionRows === contradictions, String(d.contradictionRows), String(contradictions))
  must(sample.id, 'claim rows drawn equal claims answered', d.claimRows === shown.claims.length, String(d.claimRows), String(shown.claims.length))
  must(sample.id, 'seven tactics drawn', d.tacticItems === 7, String(d.tacticItems), '7')
  const fired = shown.tactics.filter((t) => t.fired).length
  must(sample.id, 'detected tactics drawn equal tactics that fired', d.detected === fired, String(d.detected), String(fired))
  must(sample.id, 'the text drawn is exactly the text the API read (no piece lost, doubled or changed)', d.bodyText === shown.text_read, `${(d.bodyText || '').length} characters`, `${shown.text_read.length} characters`)
  must(sample.id, 'no script, frame, image, link or object in the result', d.scripts === 0, String(d.scripts), '0')
  if (sample.explain) {
    const inside = d.marks.every((m) => shown.text_read.includes(m))
    must(sample.id, 'every highlighted piece is a piece of the text read', inside, `${d.marks.length} marks`, 'all inside the text')
  }
  if (shown.mode === 'thread') {
    must(sample.id, 'one timeline card per message', d.timeline === shown.thread.messages, String(d.timeline), String(shown.thread.messages))
  }
  info(sample.id, `what the model made of this example (not asserted)`, `${report.verdict} ${report.score}; fired: ${shown.tactics.filter((t) => t.fired).map((t) => t.name).join(', ') || 'none'}; contradictions ${contradictions}`)
  if (sample.id === 'xss') {
    must('xss', 'no alert box opened', dialogs.length === 0, String(dialogs.length), '0')
    const literal = await page.evaluate(() => document.querySelector('div[aria-label="Text of the email"]').textContent.includes('<') === false)
    must('xss', 'the result holds no angle brackets (the API already replaced them) and the page added none', literal, 'no < in the text block', 'no <')
    must('xss', 'nothing the payloads name was created in the page', (await page.$$eval('main b, main u, main math, main marquee, main [onerror], main [onload], main [onclick]', (e) => e.length)) === 0, '0 elements', '0')
  }
  await page.close_all()
}

// 2. Explain on demand ("Find the words")
{
  const page = await fresh(browser)
  await example(page, 'david')
  await page.uncheck('input[type=checkbox]')
  await page.click('button[type=submit]')
  await page.waitForSelector('#risk-title')
  must('explain', 'no highlights before the second call', (await page.$$eval('div[aria-label="Text of the email"] mark', (e) => e.length)) === 0)
  await pace()
  await page.click('button:has-text("Find the words")')
  await page.waitForSelector('text=/Words that weighed most|No tactic was detected/', { timeout: 90_000 })
  must('explain', '"Find the words" completes the report', true)
  await page.close_all()
}

// 2b. The second call succeeds but no tactic fired. The API then says `explained: false` (LIME does not run), and the page must still say the words were
// looked for and not offer to ask again. Which real emails fire no tactic depends on the model, so the answer is rewritten here (the call itself is real).
{
  const page = await fresh(browser)
  await page.route('**/api/explain', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.explained = false
    for (const tactic of body.tactics) tactic.highlights = []
    await route.fulfill({ response, json: body, headers: { ...response.headers(), 'x-pg-mock': '1' } })
  })
  await example(page, 'david')
  await page.check('input[type=checkbox]')
  await pace()
  await page.click('button[type=submit]')
  await page.waitForSelector('#risk-title')
  await page.waitForSelector('text=No tactic was detected', { timeout: 90_000 })
  must('explain', 'explanation done with no tactic fired: the page says so', true)
  must('explain', 'and does not offer to ask again', (await page.$$('button:has-text("Find the words")')).length === 0)
  await page.close_all()
}

// 3. Error states, with made-up answers
const mocked = [
  [429, { detail: 'Too many requests. Try again later.', code: 'rate_limited', request_id: 'req-429' }, { 'retry-after': '3' }, ['rate_limited', 'req-429', 'Too many requests'], '429: banner with detail, code and request id'],
  [422, { detail: 'The request is not valid.', code: 'invalid_request', request_id: 'r422', errors: [{ loc: ['body', 'org_domain'], type: 'string_pattern_mismatch' }] }, {}, ['org_domain', 'String pattern mismatch'], '422: the field that was refused is listed'],
  [503, { detail: 'The classifier is busy. Try again in a moment.', code: 'busy', request_id: 'r503' }, {}, ['busy', 'classifier is busy'], '503: busy'],
  [413, { detail: 'The request is too large.', code: 'too_large', request_id: 'r413' }, {}, ['too_large', 'size limit'], '413: too large'],
  [401, { detail: 'A valid API key is required.', code: 'unauthorized', request_id: 'r401' }, {}, ['unauthorized', 'PRETEXTGUARD_API_KEY'], '401: tells the reader where the key is set'],
]
for (const [status, body, headers, expect, label] of mocked) {
  const page = await fresh(browser)
  await page.route('**/api/analyze', (route) => route.fulfill(json(status, body, headers)))
  await page.fill('#email-text', 'Subject: hi\n\nhello there my friend')
  await page.click('button[type=submit]')
  await page.waitForSelector('[role=alert]')
  const shown = await text(page, '[role=alert]')
  must('errors', label, expect.every((e) => shown.includes(e)), shown.slice(0, 90), expect.join(' + '))
  if (status === 429) {
    const label2 = await text(page, 'button[type=submit]')
    must('errors', '429: the button counts down and is disabled', /Try again in [1-3] s/.test(label2) && (await page.isDisabled('button[type=submit]')), label2, 'Try again in N s')
    await page.waitForTimeout(3600)
    must('errors', '429: the button works again after Retry-After', !(await page.isDisabled('button[type=submit]')), await text(page, 'button[type=submit]'), 'Analyze')
  }
  await page.close_all()
}
{
  const page = await fresh(browser)
  await page.route('**/api/analyze', (route) => route.fulfill({ status: 502, contentType: 'text/plain', body: 'Bad Gateway' }))
  await page.fill('#email-text', 'Subject: hi\n\nhello there my friend')
  await page.click('button[type=submit]')
  await page.waitForSelector('[role=alert]')
  const shown = await text(page, '[role=alert]')
  must('errors', '502 with no JSON reads as "cannot reach the API" and says how to start it', shown.includes('could not reach the API') && shown.includes('python -m src.api.main'), shown.slice(0, 90), 'unreachable + start command')
  await page.close_all()
}
{
  // The score stays when only the explanation fails, and a retry fills in the words.
  const page = await fresh(browser)
  await page.route('**/api/explain', (route) => route.fulfill(json(429, { detail: 'Too many requests. Try again later.', code: 'rate_limited', request_id: 'rx' }, { 'retry-after': '3' })))
  await example(page, 'david')
  await page.check('input[type=checkbox]')
  await page.click('button[type=submit]')
  await page.waitForSelector('#risk-title')
  await page.waitForSelector('text=The highlights could not be made')
  const score = await text(page, '[aria-label^="Risk score"]')
  must('errors', 'when the explanation fails the score and findings stay', /^\d+$/.test(score.trim()), score, 'a score')
  const retry = await text(page, 'button:has-text("Try again")')
  must('errors', 'the retry button counts down', /Try again in [1-3] s/.test(retry), retry, 'Try again in N s')
  await page.unroute('**/api/explain')
  await page.waitForTimeout(3600)
  await pace()
  await page.click('button:has-text("Try again")')
  await page.waitForSelector('text=/Words that weighed most|No tactic was detected/', { timeout: 90_000 })
  must('errors', 'retrying after the wait fills in the words', true)
  await page.close_all()
}

// 4. The page refuses what the API would refuse, and sends nothing
{
  const page = await fresh(browser)
  let sent = 0
  await page.route('**/api/analyze**', (route) => {
    sent += 1
    route.abort()
  })
  await page.fill('#email-text', 'x'.repeat(300_001))
  await page.waitForTimeout(200)
  const note = await text(page, 'span.text-critical')
  must('limits', 'an email over 300,000 bytes: message names both sizes', note.includes('300,001 bytes') && note.includes('300,000 bytes'), note.slice(0, 80), '300,001 bytes and 300,000 bytes')
  must('limits', 'and the Analyze button is disabled', await page.isDisabled('button[type=submit]'))
  await page.fill('#email-text', 'fine text here')
  await page.fill('#org-domain', 'bad domain!')
  await page.waitForTimeout(100)
  must('limits', 'a malformed organisation domain disables Analyze', await page.isDisabled('button[type=submit]'))
  must('limits', 'nothing was sent', sent === 0, String(sent), '0')
  await page.close_all()
}
{
  const page = await fresh(browser)
  await page.setInputFiles('input[type=file]', { name: 'a.eml', mimeType: 'message/rfc822', buffer: Buffer.from('From: a@b.example\nSubject: file\n\nhello from a file') })
  await page.waitForFunction(() => document.querySelector('#email-text').value.includes('hello from a file'))
  must('input', 'a .eml file is read into the text box', true)
  await page.click('button:has-text("A thread")')
  await page.click('button:has-text("Add a message")')
  must('input', 'thread: add a message', (await page.$$eval('ol > li textarea', (e) => e.length)) === 2)
  await page.click('li:has-text("Message 2") button:has-text("Remove")')
  must('input', 'thread: remove a message', (await page.$$eval('ol > li textarea', (e) => e.length)) === 1)
  await page.setInputFiles('input[type=file]', [
    { name: 'm1.eml', mimeType: 'message/rfc822', buffer: Buffer.from('Subject: one\n\nfirst') },
    { name: 'm2.eml', mimeType: 'message/rfc822', buffer: Buffer.from('Subject: two\n\nsecond') },
  ])
  await page.waitForFunction(() => document.querySelectorAll('ol > li textarea').length === 2)
  must('input', 'thread: two files fill two messages (the empty first box is replaced)', true)
  await page.close_all()
}

// 5. A second Analyze cancels the first
{
  const page = await fresh(browser)
  let calls = 0
  await page.route('**/api/analyze', async (route) => {
    calls += 1
    if (calls === 1) await new Promise((r) => setTimeout(r, 1500))
    route.continue()
  })
  await example(page, 'honest')
  await page.uncheck('input[type=checkbox]')
  await page.click('button[type=submit]')
  await page.waitForSelector('text=Checking the claims')
  must('input', 'the button is disabled while a request is running', await page.isDisabled('button[type=submit]'))
  await page.waitForSelector('#risk-title', { timeout: 20_000 })
  must('input', 'one request, one result', calls === 1 && (await page.$$('#risk-title')).length === 1, String(calls), '1')
  await page.close_all()
}

// 6. The dashboard: drawn from the API's tables
{
  const page = await fresh(browser)
  await page.click('nav button:has-text("Dashboard")')
  await page.waitForSelector('#chart-tactics-title', { timeout: 30_000 })
  await page.waitForSelector('figure svg.recharts-surface', { timeout: 30_000 })
  await page.waitForTimeout(800)
  for (const id of ['tactics', 'distribution', 'hijack', 'budget']) {
    must('dashboard', `chart "${id}" is drawn`, (await page.$$(`figure[aria-labelledby="chart-${id}-title"] svg.recharts-surface`)).length >= 1)
  }
  // The table view of each chart holds the numbers drawn; compare a few with the API's own table.
  const api = (name) => fetch(new URL(`api/results?name=${name}`, BASE)).then((r) => r.json())
  const scores = await api('tactic_validation_scores')
  await page.click('#chart-tactics-title ~ div button:has-text("Table")')
  const cells = await page.$$eval('figure[aria-labelledby="chart-tactics-title"] tbody tr', (trs) => trs.map((tr) => [...tr.children].map((td) => td.textContent)))
  const authority = scores.rows.find((r) => r.data === 'real_validation' && r.system === 'distilbert' && r.tactic === 'authority')
  const row = cells.find((c) => c[0] === 'Authority')
  must('dashboard', 'F1 of DistilBERT for authority in the chart table equals the API table', Boolean(row && authority && row[1] === authority.f1.toFixed(3)), row ? row[1] : 'missing', authority ? authority.f1.toFixed(3) : 'missing')
  const budget = await api('score_budget')
  await page.click('#chart-budget-title ~ div button:has-text("Table")')
  const budgetRows = await page.$$eval('figure[aria-labelledby="chart-budget-title"] tbody tr', (e) => e.length)
  const expectedRows = budget.rows.filter((r) => r.split === 'validation' && (r.kind === 'email' || r.kind === 'thread')).length
  must('dashboard', 'rows of the budget chart table equal the API table (ham and thread groups)', budgetRows === expectedRows, String(budgetRows), String(expectedRows))
  const list = await fetch(new URL('api/results', BASE)).then((r) => r.json())
  const blocks = await page.$$eval('details > summary > span.mono', (e) => e.length)
  must('dashboard', 'one block per result file listed by the API', blocks === list.files.length, String(blocks), String(list.files.length))
  await page.click('summary:has-text("score_budget")')
  await page.waitForSelector('details[open] table')
  const opened = await page.$$eval('details[open] tbody tr', (e) => e.length)
  must('dashboard', 'opening a block loads its rows', opened === budget.rows.length, String(opened), String(budget.rows.length))
  await page.close_all()
}

// 7. A phone-width screen has no sideways page scroll
{
  const page = await fresh(browser, { width: 375, height: 800 })
  await example(page, 'david')
  await page.uncheck('input[type=checkbox]')
  await page.click('button[type=submit]')
  await page.waitForSelector('#risk-title')
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  must('phone', 'analyzer result at 375 px wide: no sideways scroll', over <= 0, `${over} px`, '0 px')
  await page.click('nav button:has-text("Dashboard")')
  await page.waitForSelector('figure svg.recharts-surface')
  await page.waitForTimeout(600)
  const over2 = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  must('phone', 'dashboard at 375 px wide: no sideways scroll', over2 <= 0, `${over2} px`, '0 px')
  await page.close_all()
}

// 8. Dark mode draws the same page without errors
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'dark' })
  const page = await context.newPage()
  page.on('pageerror', (e) => pageErrors.push(e.message))
  await page.goto(BASE)
  await page.waitForSelector('h1')
  const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  must('dark', 'dark colour scheme gives a dark page', /rgb\((\d+), (\d+), (\d+)\)/.test(dark) && Number(/rgb\((\d+)/.exec(dark)[1]) < 60, dark, 'a dark background')
  await context.close()
}

} catch (error) {
  add('whole run', 'the script ran to its end', `stopped: ${String(error.message).split('\n')[0].slice(0, 160)}`, 'ran to the end', 'FAIL')
}

// 9. Whole run
if (realRateLimited.length > 0) {
  add('whole run', 'a real call was refused by the API rate limit (the limit is per minute: wait a minute and run again)', realRateLimited.join(' '), 'none', 'FAIL')
}
must('whole run', 'no content-security-policy violation in any page', cspViolations.length === 0, cspViolations.slice(0, 3).join(' | ') || '0', '0')
must('whole run', 'no script error in any page', pageErrors.length === 0, pageErrors.slice(0, 3).join(' | ') || '0', '0')
must('whole run', 'no console error in any page (apart from the refused requests this script made up)', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | ') || '0', '0')
must('whole run', 'no alert, confirm or prompt box opened', dialogs.length === 0, String(dialogs.length), '0')
info('whole run', 'browser', browser.version())
info('whole run', 'seconds', Math.round((Date.now() - started) / 1000))
await browser.close()

// ------------------------------------------------------------------------------------------------------------------------------ output
const quote = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, ['check,item,value,expected,status', ...rows.map((r) => [r.check, r.item, r.value, r.expected, r.status].map(quote).join(','))].join('\n') + '\n')
let failed = 0
for (const r of rows) {
  if (r.status === 'FAIL') failed += 1
  console.log(`${r.status.padEnd(4)}  [${r.check}] ${r.item}${r.status === 'FAIL' ? `  (got ${r.value}, expected ${r.expected})` : r.status === 'info' ? `: ${r.value}` : ''}`)
}
const count = (s) => rows.filter((r) => r.status === s).length
console.log(`\n${count('PASS')} PASS, ${count('FAIL')} FAIL, ${count('info')} info. Written to ${relative(PROJECT, OUT)}`)
process.exit(failed === 0 ? 0 : 1)
