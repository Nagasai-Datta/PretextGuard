import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useResult } from '../../lib/useResult.js'
import { AXIS_LINE, COLORS, ChartCard, ChartTooltip, TICK, legendText } from './parts.jsx'

// Chart 2: the hijack benchmark (Phase 9 and 10). How often a hijacked thread reaches "Suspicious" or "High risk": with every check, against the
// Phase 8 verifiers alone (which see only the headers of the one message). The whiskers are 95% bootstrap intervals.
const VARIANTS = [
  ['apache', 'A', 'Apache A'],
  ['apache', 'B', 'Apache B'],
  ['apache', 'C', 'Apache C'],
  ['enron', 'A', 'Enron A'],
  ['enron', 'C', 'Enron C'],
]

export function benchmarkRows(rows) {
  const pick = (source, variant, metric) => rows.find((r) => r.split === 'validation' && r.source === source && r.variant === variant && r.metric === metric)
  return VARIANTS.map(([source, variant, label]) => {
    const full = pick(source, variant, 'suspicious_or_high_full')
    const old = pick(source, variant, 'suspicious_or_high_phase8')
    const point = { label, n: full ? full.n : null, tooltip: {} }
    for (const [key, row] of [['full', full], ['phase8', old]]) {
      point[key] = row ? row.rate * 100 : null
      point[`${key}_err`] = row ? [(row.rate - row.ci_low) * 100, (row.ci_high - row.rate) * 100] : [0, 0]
      point.tooltip[key] = row ? `${(row.rate * 100).toFixed(1)}% (${row.hits} of ${row.n}; interval ${(row.ci_low * 100).toFixed(1)} to ${(row.ci_high * 100).toFixed(1)})` : 'not available'
    }
    return point
  })
}

export function falseAlarmNote(rows) {
  const parts = []
  for (const source of ['apache', 'enron']) {
    for (const variant of ['neg_real', 'neg_synth']) {
      const row = rows.find((r) => r.split === 'validation' && r.source === source && r.variant === variant && r.metric === 'suspicious_or_high_full')
      if (row) parts.push(`${source} ${variant}: ${row.hits} of ${row.n}`)
    }
  }
  return parts.join('; ')
}

export default function BenchmarkChart() {
  const state = useResult('score_benchmark_check')
  const ready = state.status === 'ready'
  const data = ready ? benchmarkRows(state.data.rows) : []
  const table = {
    columns: [
      { key: 'label', label: 'Case' },
      { key: 'n', label: 'Threads', num: true },
      { key: 'full', label: 'All checks (%)', num: true, format: (v) => (v === null ? '' : v.toFixed(1)) },
      { key: 'phase8', label: 'Phase 8 verifiers only (%)', num: true, format: (v) => (v === null ? '' : v.toFixed(1)) },
    ],
    rows: data,
  }
  return (
    <ChartCard
      id="chart-hijack"
      title="Catching a hijacked conversation"
      question="Share of hijacked threads that reach Suspicious or High risk, with every check against the sender checks alone. A takeover (A) keeps genuine headers, a look-alike swap (B) changes the sending path, a forged thread (C) breaks the reply identifiers."
      state={state}
      table={table}
      summary="Grouped bars of detection rate per hijack case for all checks and for the Phase 8 verifiers alone. The values are in the table view."
      caveat={`Validation threads only. The hijacked messages and their headers are synthetic, written by a language model and by code, so this shows what the checks can see, not how often real attackers are caught. Whiskers: 95% bootstrap interval. A missing bar is 0%. Benign threads that were wrongly flagged (all checks): ${ready ? falseAlarmNote(state.data.rows) || 'none listed' : ''}.`}
    >
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }} barGap={2} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} tick={TICK} tickLine={false} axisLine={false} width={48} />
          <Tooltip content={<ChartTooltip rows={(point) => (point.n ? `${point.n} threads` : null)} />} cursor={{ fill: 'var(--line)', opacity: 0.5 }} isAnimationActive={false} />
          <Legend iconType="square" formatter={legendText} itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
          <Bar dataKey="full" name="All checks" fill={COLORS.ours} stroke="var(--surface)" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false}>
            <ErrorBar dataKey="full_err" width={4} stroke="var(--ink2)" strokeWidth={1.5} />
          </Bar>
          <Bar dataKey="phase8" name="Sender checks only (Phase 8)" fill={COLORS.comparison} stroke="var(--surface)" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false}>
            <ErrorBar dataKey="phase8_err" width={4} stroke="var(--ink2)" strokeWidth={1.5} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
