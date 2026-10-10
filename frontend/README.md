# frontend/

Phase 12: the **interface**. Two pages in one small React app: the **Analyzer** (paste an email or a thread, get the score, the findings and the reasons) and the **Dashboard** (the evaluation numbers, drawn from `results/`). It talks only to the local API of Phase 11 (`src/api`) and stores nothing: the email is held in the page's memory and is gone when the tab closes.

Plain JavaScript (no TypeScript), React 19, Vite 6, Tailwind 4, Recharts 3. No router library, no state library, no UI kit, no CDN, no web fonts: everything the page loads comes from its own server.

## Run it

Three terminals, all from the project root unless stated. The API needs the trained model, so this runs on the Mac.

```bash
source venv/bin/activate
python -m src.api.main
```

```bash
cd frontend
npm install
npm run build
npm run preview
```

Open <http://127.0.0.1:4173>. `npm run preview` serves the built app with the strict security headers (see below); use it for the demo. `npm run dev` (port 5173) gives hot reload for development but cannot send the Content-Security-Policy.

The key is read from the project's `.env` (`PRETEXTGUARD_API_KEY`, the same value the API uses; `python -m src.api.settings --new-key` makes one). If it is missing, short or still the placeholder, the interface server refuses to start and says how to fix it.

Needs Node 18 or newer (`node -v`); `brew install node` if it is missing.

## What you see

**Analyzer.** One email or a thread (several emails; the newest by its Date header is judged against the earlier ones), by pasting text or loading `.eml` files, plus seven hand-made examples (the David email, an exact-domain spoof, a credential request, an honest email, a body without headers, an account takeover in a thread, and an email full of script payloads). An optional organisation domain tells the checks what "internal" means. Then, in this order:

| Block | What it shows |
|---|---|
| Result | The score (0 to 100) as a large number, the band (Low risk, Suspicious, High risk) as a word on a coloured chip, a meter with ticks at 35 and 70, and the recommended action. "Low risk" is blue, not green, on purpose: it never means "safe" |
| What could be checked | Claims found, checked, contradicted, consistent, not checkable; the limits that applied (no headers, no organisation domain, single email); the API's sentence. When the band is Low risk but little could be checked, a note says so |
| Findings | One row per contradiction, strongest first: the claim, the reason in plain English, the points it added; the rule and its evidence are one click away. Consistent and not-checkable rows are in a closed block |
| The conversation | (threads) one card per message with its worst finding, and the flip point: the message where the thread changed behaviour |
| The text that was read | The redacted text the models saw, with the words behind each detected tactic marked in that tactic's colour (LIME) and each claim underlined with a dashed line; a list of the words that weighed most |
| Pressure tactics | The seven tactics with the classifier's probability and its threshold (the black tick); reciprocity, social proof and liking are shown, not scored |
| How the score was built | The table of counted rows, then the four steps: contradiction points, pressure multiplier, tactic points, cap |
| Claims found, What the headers say | The claims with their strength, where they were found and what checked them; the header facts the checks used |

The score and findings come from `POST /analyze` (about 0.05 s) and appear first; the highlights come from a second call, `POST /explain` (about 5 s), because the score does not depend on them. If that call fails, the score stays and a button offers to try again.

**Dashboard.** Four charts, each with a table view that holds exactly the numbers drawn, then every result file the API serves (`GET /results`), grouped by phase, each opened on demand and filterable:

1. Finding the pressure tactics: F1 of DistilBERT against the keyword baseline per tactic, on the real validation emails.
2. Where the emails land: the share of Low risk, Suspicious and High risk emails per category.
3. Catching a hijacked conversation: detection with every check against the sender checks alone, with 95% intervals.
4. False alarms on legitimate mail: per group against the 1% and 5% budgets.

Every chart says under it what it cannot show (validation split only, labels from language models of one family, synthetic hijacks, attacks and ordinary mail from different collections).

## How it is built

| Path | What it does |
|---|---|
| `vite.config.js` | Builds the app and runs the **same-origin proxy**: `/api/...` is forwarded to `http://127.0.0.1:8000/...` with the `X-API-Key` header added. Also the security headers of `npm run preview` |
| `index.html`, `src/main.jsx`, `src/App.jsx` | Entry, the header with the two pages, and a banner that appears when the API is not running or its model is not loaded |
| `src/api.js` | The only file that uses the network. Every failure (an API error, the network, an unreadable answer) becomes one `ApiError` with the same fields; a request has a 2 minute timeout and can be cancelled |
| `src/pages/AnalyzerPage.jsx` | Holds what the person typed, checks it against the API's limits first, runs the analysis |
| `src/lib/useAnalysis.js` | The two-call flow, cancellation and the Retry-After counter |
| `src/components/` | One component per block above, `EmailInput.jsx` for the form, `ErrorBanner.jsx`, `ResultTable.jsx` for the result files |
| `src/components/charts/` | The four charts and their shared pieces (the card with the chart/table switch, the tooltip, the colours) |
| `src/pages/DashboardPage.jsx`, `src/lib/useResult.js` | The dashboard and the hook that loads one result table |
| `src/lib/segments.js` | Turns the API's character offsets into pieces of text that can be drawn (below) |
| `src/lib/limits.js` | The API's size limits, checked before anything is sent; the API stays the authority |
| `src/lib/format.js` | Labels and number formatting; the fixed list of tactic names |
| `src/lib/examples.js` | The seven examples. **Generated** by `scripts/make_examples.py` from the hand-made emails of `src/router/selftest.py`; do not edit by hand. ASCII only |
| `src/index.css` | Tailwind and the colour tokens (light and dark) |
| `scripts/check.mjs` | `npm run check`: static checks (below) |
| `scripts/browser_check.mjs` | `npm run browser-check`: drives the built app in a real browser |
| `scripts/mutation_check.mjs` | `npm run mutation-check`: breaks things on purpose and confirms `check.mjs` notices |
| `scripts/make_examples.py` | Writes `src/lib/examples.js` (`PYTHONPATH=. python frontend/scripts/make_examples.py` from the project root) |

### Security design (what this phase adds to Section 10 of the master document)

- **The key never reaches the browser.** The page calls `/api/analyze` on its own server; that server adds the key. Vite only gives the browser variables whose names start with `VITE_` (`envPrefix`), and the key is read inside `vite.config.js` with `loadEnv(mode, '..', 'PRETEXTGUARD_')`. `npm run check` searches the built bundle for the key and for the header name.
- **No CORS needed.** The browser only talks to the origin that served the page, so the API's CORS switch (`CORS_ALLOW_ANY_ORIGIN` in `src/api/main.py`, open for testing) does not matter to the interface and can be set to `False` before any deployment.
- **Every string is drawn as text.** Email text, claims, reasons and highlights are React text nodes; there is no `dangerouslySetInnerHTML`, no `innerHTML`, no markdown, no links and no `eval` anywhere in `src/` (`npm run check` scans for each). The API already replaces `<`, `>` and backticks, so this is a second line of defence.
- **A strict Content-Security-Policy** on `npm run preview`: `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` and `Cross-Origin-Resource-Policy: same-origin`. Even an injected script could not run or send anything to another host. The browser check fails if the policy is missing and reports any violation.
- **Nothing is stored in the browser** (no localStorage, cookies or IndexedDB) and nothing is logged to the console.
- **Files are read as text in the browser** (`File.text()`), after a size check; they are never uploaded as files, and attachments are never opened.
- **Pinned packages**: exact versions in `package.json`, `package-lock.json` committed, `npm audit` clean (recorded by `npm run check`).

### Offsets: why `segments.js` exists

The API gives every highlight and claim as an offset into the text it read. Python counts characters as Unicode code points; JavaScript strings count UTF-16 units, so an emoji is two units there. Slicing a JavaScript string at the API's offsets would cut an emoji in half and shift everything after it. `buildSegments` splits the text with `Array.from` (code points), cuts it at every span boundary, and returns consecutive pieces that together give back the text exactly. A span that does not fit (not whole numbers, start not before end, outside the text) is skipped and counted, never drawn wrongly.

## Checks

```bash
npm run check
```

About 95 PASS lines and `results/frontend_checks.csv`: the source (no HTML injection, links, storage, console output, outside addresses), the pins and `npm audit`, the bundle (no key, no header name, no outside host, no inline script or style in `index.html`), and the logic (`buildSegments` on emoji, overlaps, crooked spans and 300 random cases; the size limits; domain shape).

```bash
npm run mutation-check
```

Breaks 26 things one at a time in a scratch copy (an `innerHTML`, the key in the bundle, UTF-16 slicing, an off-by-one size limit, a version range, an inline script, ...) and confirms the check fails each time; writes `results/frontend_mutations.csv`. Needs `npm run build` first.

```bash
npm run browser-check
```

Needs the API (`python -m src.api.main`) and `npm run preview` running, and Google Chrome (or Edge, or `npx playwright-core install chromium`, or `CHROMIUM_PATH=...`). It uses the page like a person would and compares **what is drawn with what the API answered** (score, band, number of findings, claims and tactics, the text itself character for character), then checks the error states (429 with its counter, 422, 503, 413, 401, an unreachable API, a failed explanation), the size limits, files and threads, the dashboard against the API's tables, a phone-width screen, dark mode, and that no script error, console error, alert box or Content-Security-Policy violation happened anywhere. It writes `results/frontend_browser_checks.csv`. The API allows 6 explanations a minute; the script counts its own and waits when needed, so wait a minute between two runs.

The error states are made by answering the page's own requests with made-up responses, so they test the page, not the API (the API's refusals are tested by `python -m src.api.selftest`).

## Known limits

- The Content-Security-Policy is sent only by `npm run preview`. The dev server needs inline scripts for hot reload, so it cannot.
- Everything the proxy forwards comes from one address, so all users of one interface server share one rate-limit allowance: fine for a single-user demo.
- Only a Chromium-based browser was driven by the checks. Safari and Firefox were not tested; no screen reader and no automated accessibility audit was run. Labels, roles, keyboard focus and a text label beside every colour are in place.
- The four charts show validation results. Phase 13 added the test-split result files to `RESULT_FILES` in `src/api/results.py` and their prefixes to `GROUPS` in `src/pages/DashboardPage.jsx`, so they appear as tables under their own headings (evaluation protocol, N1, N2, N3 and architecture, supporting experiments); the test-split charts of the report are PNG files drawn by `src/eval/charts.py`. A further result file is shown only after its name is added to `RESULT_FILES` and appears under "Other" until its prefix is added to `GROUPS`.
- A result is not kept across a reload (nothing is stored on purpose).
- The charts use Recharts, which adds about 415 KB (120 KB compressed) to the dashboard; it is loaded only when the Dashboard tab is first opened.
