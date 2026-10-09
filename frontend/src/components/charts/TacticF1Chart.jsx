import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useResult } from '../../lib/useResult.js'
import { tacticLabel } from '../../lib/format.js'
import { AXIS_LINE, COLORS, ChartCard, ChartTooltip, TICK, legendText } from './parts.jsx'

// Chart 1: F1 per tactic on the real validation emails (Phase 6). F1 is shown only where the tactic has at least 10 positives; the others are counted.
const SYSTEMS = [
  { key: 'distilbert', name: 'DistilBERT (mix)', color: COLORS.ours },
  { key: 'keyword_tuned', name: 'Keyword baseline, tuned', color: COLORS.comparison },
  { key: 'keyword_default', name: 'Keyword baseline, default', color: COLORS.comparison2 },
]
const ORDER = ['authority', 'urgency', 'scarcity', 'secrecy', 'macro_main4']

export function tacticRows(rows) {
  const real = rows.filter((r) => r.data === 'real_validation')
  const data = ORDER.map((tactic) => {
    const point = { tactic, label: tactic === 'macro_main4' ? 'Mean of the four' : tacticLabel(tactic), tooltip: {} }
    for (const system of SYSTEMS) {
      const row = real.find((r) => r.system === system.key && r.tactic === tactic)
      point[system.key] = row && typeof row.f1 === 'number' ? row.f1 : null
      point.tooltip[system.key] = row && typeof row.f1 === 'number' ? `F1 ${row.f1.toFixed(3)}` + (row.positives ? ` (${row.positives} positives)` : '') : 'not available'
    }
    return point
  })
  const counted = real
    .filter((r) => r.system === 'distilbert' && typeof r.reported === 'string' && r.reported.startsWith('count only'))
    .map((r) => `${tacticLabel(r.tactic)} (${r.positives} positives)`)
  return { data, counted }
}

export default function TacticF1Chart() {
  const state = useResult('tactic_validation_scores')
  const { data, counted } = state.status === 'ready' ? tacticRows(state.data.rows) : { data: [], counted: [] }
  const table = {
    columns: [{ key: 'label', label: 'Tactic' }, ...SYSTEMS.map((s) => ({ key: s.key, label: s.name, num: true, format: (v) => (v === null ? '' : v.toFixed(3)) }))],
    rows: data,
  }
  return (
    <ChartCard
      id="chart-tactics"
      title="Finding the pressure tactics"
      question="F1 of the tactic classifier against the keyword baseline on the real validation emails. Higher is better."
      state={state}
      table={table}
      summary="Grouped bars of F1 per tactic for DistilBERT and two keyword baselines. The values are in the table view."
      caveat={`Validation emails only (137 real). The labels come from language models of one family, and each tactic has 12 to 39 positives, so differences of a few points are noise. Counted only, too few positives for an F1: ${counted.join(', ') || 'none'}. The test split is scored once, in Phase 13.`}
    >
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }} barGap={2} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => v.toFixed(2)} tick={TICK} tickLine={false} axisLine={false} width={44} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--line)', opacity: 0.5 }} isAnimationActive={false} />
          <Legend iconType="square" formatter={legendText} itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
          {SYSTEMS.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} stroke="var(--surface)" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
