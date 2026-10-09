import { useState } from 'react'
import ErrorBanner from '../ErrorBanner.jsx'
import { formatCell } from '../../lib/format.js'

// Pieces shared by the four charts: the card with a chart/table switch, the loading gate, the axis style, the tooltip and a plain data table.
// The table view is not decoration: it holds exactly the numbers drawn, so a chart is never the only way to read a result.

export const TICK = { fill: 'var(--ink2)', fontSize: 12 }
export const AXIS_LINE = { stroke: 'var(--axis)' }
export const legendText = (value) => <span style={{ color: 'var(--ink)' }}>{value}</span>

// One colour per entity, the same on every chart: our system is blue, the comparison is orange, the second comparison is aqua. Bands keep the band colours.
export const COLORS = {
  ours: 'var(--s1)',
  comparison: 'var(--s2)',
  comparison2: 'var(--s3)',
  low: 'var(--band-low)',
  suspicious: 'var(--band-sus)',
  high: 'var(--band-high)',
}

export function ChartTooltip({ active, payload, label, rows }) {
  if (!active || !payload || payload.length === 0) return null
  const extra = rows ? rows(payload[0].payload) : null
  return (
    <div className="rounded-lg border border-line bg-surface p-2 text-sm shadow-sm">
      <div className="mb-1 font-medium">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2">
          <span className="swatch" style={{ '--hl': entry.color || entry.fill }} aria-hidden="true" />
          <span>{entry.name}:</span>
          <span className="tabular-nums">{entry.payload.tooltip ? entry.payload.tooltip[entry.dataKey] : formatCell(entry.value)}</span>
        </div>
      ))}
      {extra && <div className="hint mt-1">{extra}</div>}
    </div>
  )
}

export function DataTable({ columns, rows }) {
  return (
    <div className="max-h-96 overflow-auto">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.num ? 'num' : ''}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? 'num' : ''}>
                  {c.format ? c.format(row[c.key], row) : formatCell(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// state: from useResult. children(rows) draws the chart; table = {columns, rows} for the table view.
export function ChartCard({ id, title, question, state, caveat, children, table, summary }) {
  const [view, setView] = useState('chart')
  return (
    <figure className="card m-0" aria-labelledby={`${id}-title`}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h3 id={`${id}-title`} className="m-0 text-base font-semibold">
          {title}
        </h3>
        <div role="group" aria-label={`View of ${title}`} className="ml-auto flex gap-1">
          <button type="button" className="tab" aria-current={view === 'chart' ? 'page' : undefined} onClick={() => setView('chart')}>
            Chart
          </button>
          <button type="button" className="tab" aria-current={view === 'table' ? 'page' : undefined} onClick={() => setView('table')}>
            Table
          </button>
        </div>
      </div>
      <p className="hint m-0 mb-2">{question}</p>
      {state.status === 'loading' && (
        <p className="m-0 flex items-center gap-2" role="status">
          <span className="spinner" aria-hidden="true" /> Loading...
        </p>
      )}
      {state.status === 'error' && (
        <div>
          <ErrorBanner error={state.error} title="Could not load" />
          <button type="button" className="btn mt-2" onClick={state.retry}>
            Try again
          </button>
        </div>
      )}
      {state.status === 'ready' && (
        <div>
          {view === 'chart' ? (
            <div role="img" aria-label={summary}>
              {children}
            </div>
          ) : (
            <DataTable columns={table.columns} rows={table.rows} />
          )}
          {caveat && <figcaption className="hint mt-2">{caveat}</figcaption>}
        </div>
      )}
    </figure>
  )
}
