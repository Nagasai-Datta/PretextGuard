import { useMemo, useState } from 'react'
import BenchmarkChart from '../components/charts/BenchmarkChart.jsx'
import BudgetChart from '../components/charts/BudgetChart.jsx'
import DistributionChart from '../components/charts/DistributionChart.jsx'
import TacticF1Chart from '../components/charts/TacticF1Chart.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import ResultTable from '../components/ResultTable.jsx'
import { useResultList } from '../lib/useResult.js'

// The evaluation dashboard: four charts that answer the questions of the project, then every saved result table. All numbers are read from the API,
// which serves a fixed list of files from results/. Nothing here is typed in by hand: change a script, run it, and the page shows the new numbers.

const GROUPS = [
  ['Data', ['staged', 'split', 'header', 'preprocess', 'label', 'synthetic']],
  ['Keyword baseline', ['keyword']],
  ['Tactic classifier', ['tactic']],
  ['Claim extractor', ['claim']],
  ['Header and request verifiers', ['verifier']],
  ['Thread verifier and hijack benchmark', ['thread', 'hijack']],
  ['Risk score', ['score']],
  ['Explanations', ['lime']],
  ['API and interface', ['api', 'frontend']],
]

export function groupFiles(files) {
  const used = new Set()
  const groups = GROUPS.map(([title, prefixes]) => {
    const members = files.filter((file) => prefixes.includes(file.name.split('_')[0]))
    members.forEach((file) => used.add(file.name))
    return { title, files: members }
  })
  const rest = files.filter((file) => !used.has(file.name))
  if (rest.length) groups.push({ title: 'Other', files: rest })
  return groups.filter((group) => group.files.length > 0)
}

function FileBlock({ file }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="rounded-lg border border-line px-3 py-2" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <span className="font-medium mono">{file.name}</span> <span className="hint">· {file.rows} rows · {file.description}</span>
      </summary>
      <div className="mt-2">{open && <ResultTable name={file.name} columns={file.columns} />}</div>
    </details>
  )
}

function AllTables() {
  const list = useResultList()
  const groups = useMemo(() => (list.status === 'ready' ? groupFiles(list.data.files) : []), [list])
  if (list.status === 'loading') {
    return (
      <p className="m-0 flex items-center gap-2" role="status">
        <span className="spinner" aria-hidden="true" /> Loading the list of results...
      </p>
    )
  }
  if (list.status === 'error') {
    return (
      <div>
        <ErrorBanner error={list.error} title="Could not load" />
        <button type="button" className="btn mt-2" onClick={list.retry}>
          Try again
        </button>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-5">
      {list.data.missing.length > 0 && (
        <p className="hint m-0">Not found on this machine (the script that writes them has not been run here): {list.data.missing.join(', ')}.</p>
      )}
      {groups.map((group) => (
        <div key={group.title}>
          <h3 className="m-0 mb-2 text-base font-semibold">{group.title}</h3>
          <div className="flex flex-col gap-2">
            {group.files.map((file) => (
              <FileBlock key={file.name} file={file} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      <section className="card">
        <h2>How to read these results</h2>
        <p className="m-0 text-sm">
          Every number comes from a script in <span className="mono">src/</span> and is saved in <span className="mono">results/</span>; this page only draws the files. Scores here are on the{' '}
          <span className="font-medium">validation</span> split, which was used to choose thresholds and settings, so they are slightly optimistic. The test split is scored once, in Phase 13.
          The labels are produced by language models of one family, not by people, and the hijacked threads are synthetic. Each chart has a table view with the exact values.
        </p>
      </section>
      <div className="grid gap-5 lg:grid-cols-2">
        <TacticF1Chart />
        <DistributionChart />
        <BenchmarkChart />
        <BudgetChart />
      </div>
      <section className="card">
        <h2>All saved results</h2>
        <p className="hint m-0 mb-3">Open a block to load its table. Checks tables list each check with PASS, FAIL or info.</p>
        <AllTables />
      </section>
    </div>
  )
}
