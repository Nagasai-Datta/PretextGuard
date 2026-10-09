import { useMemo, useState } from 'react'
import ErrorBanner from './ErrorBanner.jsx'
import { formatCell } from '../lib/format.js'
import { useResult } from '../lib/useResult.js'

// One saved result table, loaded when its block is opened. A filter box narrows the rows (all columns, any case); only the first rows are drawn until
// "show all" is pressed, because some tables have hundreds of rows. Every cell is text; a `status` column of a checks table gets a word on a chip.
const PAGE = 100

function Cell({ column, value }) {
  if (column === 'status' && typeof value === 'string') {
    const key = value === 'PASS' ? 'ok' : value === 'FAIL' ? 'high' : 'na'
    return <span className={`chip sev-${key}`}>{value}</span>
  }
  return formatCell(value)
}

export default function ResultTable({ name, columns }) {
  const state = useResult(name)
  const [filter, setFilter] = useState('')
  const [all, setAll] = useState(false)
  const rows = state.status === 'ready' ? state.data.rows : []
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) => columns.some((c) => formatCell(row[c]).toLowerCase().includes(needle)))
  }, [rows, filter, columns])
  const visible = all ? shown : shown.slice(0, PAGE)

  if (state.status === 'loading') {
    return (
      <p className="m-0 flex items-center gap-2" role="status">
        <span className="spinner" aria-hidden="true" /> Loading...
      </p>
    )
  }
  if (state.status === 'error') {
    return (
      <div>
        <ErrorBanner error={state.error} title="Could not load" />
        <button type="button" className="btn mt-2" onClick={state.retry}>
          Try again
        </button>
      </div>
    )
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="hint">Filter</span>
          <input className="input w-56" value={filter} onChange={(event) => setFilter(event.target.value)} spellCheck={false} autoComplete="off" aria-label={`Filter the rows of ${name}`} />
        </label>
        <span className="hint">
          {shown.length === rows.length ? `${rows.length} rows` : `${shown.length} of ${rows.length} rows`}
        </span>
      </div>
      <div className="max-h-96 overflow-auto rounded-lg border border-line">
        <table className="table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c} className={typeof row[c] === 'number' ? 'num' : '[overflow-wrap:anywhere]'}>
                    <Cell column={c} value={row[c]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!all && shown.length > PAGE && (
        <button type="button" className="btn mt-2" onClick={() => setAll(true)}>
          Show all {shown.length} rows
        </button>
      )}
    </div>
  )
}
