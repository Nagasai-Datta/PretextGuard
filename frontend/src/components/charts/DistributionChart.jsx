import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useResult } from '../../lib/useResult.js'
import { AXIS_LINE, COLORS, ChartCard, ChartTooltip, TICK, legendText } from './parts.jsx'

// Chart 3: where the validation emails land (Phase 10), per category, among the emails that had at least one claim that could be checked. The other
// emails can only score from the tactics (at most 12 points) and always land in Low risk, so they are left out and counted in the caption.
const CATEGORIES = ['ham', 'spam', 'phishing', 'fraud']

export function distributionRows(rows) {
  return CATEGORIES.map((category) => {
    const row = rows.find((r) => r.split === 'validation' && r.group_by === 'category' && r.group === category)
    if (!row || !row.checked_emails) return { label: category, n: 0, low: null, suspicious: null, high: null, tooltip: {} }
    const share = (count) => (count / row.checked_emails) * 100
    const point = {
      label: `${category} (${row.checked_emails})`,
      n: row.checked_emails,
      all: row.emails,
      low: share(row.checked_low),
      suspicious: share(row.checked_suspicious),
      high: share(row.checked_high),
    }
    point.tooltip = {
      low: `${point.low.toFixed(1)}% (${row.checked_low})`,
      suspicious: `${point.suspicious.toFixed(1)}% (${row.checked_suspicious})`,
      high: `${point.high.toFixed(1)}% (${row.checked_high})`,
    }
    return point
  })
}

export default function DistributionChart() {
  const state = useResult('score_distribution')
  const ready = state.status === 'ready'
  const data = ready ? distributionRows(state.data.rows) : []
  const fmt = (v) => (v === null ? '' : v.toFixed(1))
  const table = {
    columns: [
      { key: 'label', label: 'Category (checked emails)' },
      { key: 'all', label: 'All emails', num: true },
      { key: 'low', label: 'Low risk (%)', num: true, format: fmt },
      { key: 'suspicious', label: 'Suspicious (%)', num: true, format: fmt },
      { key: 'high', label: 'High risk (%)', num: true, format: fmt },
    ],
    rows: data,
  }
  return (
    <ChartCard
      id="chart-distribution"
      title="Where the emails land"
      question="Share of validation emails in each band, per category, among emails with at least one checkable claim (the number is in brackets)."
      state={state}
      table={table}
      summary="Stacked bars of the share of Low risk, Suspicious and High risk emails for ham, spam, phishing and fraud. The values are in the table view."
      caveat="Validation emails only. Attacks and legitimate mail come from different collections with different headers, so the contrast between categories is partly a contrast between collections: read it per source in the tables below. There are no contradiction labels, so these are rates, not precision or recall."
    >
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} tick={TICK} tickLine={false} axisLine={false} width={48} />
          <Tooltip content={<ChartTooltip rows={(point) => (point.all ? `${point.n} of ${point.all} emails had a checked claim` : null)} />} cursor={{ fill: 'var(--line)', opacity: 0.5 }} isAnimationActive={false} />
          <Legend iconType="square" formatter={legendText} itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
          <Bar dataKey="low" name="Low risk" stackId="band" fill={COLORS.low} stroke="var(--surface)" strokeWidth={2} maxBarSize={24} isAnimationActive={false} />
          <Bar dataKey="suspicious" name="Suspicious" stackId="band" fill={COLORS.suspicious} stroke="var(--surface)" strokeWidth={2} maxBarSize={24} isAnimationActive={false} />
          <Bar dataKey="high" name="High risk" stackId="band" fill={COLORS.high} stroke="var(--surface)" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
