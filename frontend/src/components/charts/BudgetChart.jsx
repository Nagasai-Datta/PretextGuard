import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useResult } from '../../lib/useResult.js'
import { AXIS_LINE, COLORS, ChartCard, ChartTooltip, TICK, legendText } from './parts.jsx'

// Chart 4: the false-alarm budget (Phase 10). Legitimate mail (ham) per source, and real conversations, must stay under 5% Suspicious-or-above and
// 1% High risk. The budget was declared before the validation emails were read. Groups with fewer than 20 checked messages are shown but not judged.
const BUDGETS = { suspicious: 5, high: 1 }

export function budgetRows(rows) {
  return rows
    .filter((r) => r.split === 'validation' && (r.kind === 'email' || r.kind === 'thread'))
    .map((r) => {
      const small = r.checked_n < 20
      const over = r.budget === 'OVER'
      const label = `${r.kind === 'thread' ? 'threads' : 'ham'}: ${r.group}${over ? ' (over budget)' : ''}${small ? ' (under 20)' : ''}`
      return {
        label,
        n: r.checked_n,
        budget: r.budget,
        suspicious: r.suspicious_or_high_pct,
        high: r.high_pct,
        suspicious_err: [r.suspicious_or_high_pct - r.suspicious_ci_low, r.suspicious_ci_high - r.suspicious_or_high_pct],
        high_err: [r.high_pct - r.high_ci_low, r.high_ci_high - r.high_pct],
        tooltip: {
          suspicious: `${r.suspicious_or_high_pct.toFixed(2)}% (${r.suspicious_or_high_n} of ${r.checked_n}; interval ${r.suspicious_ci_low.toFixed(2)} to ${r.suspicious_ci_high.toFixed(2)})`,
          high: `${r.high_pct.toFixed(2)}% (${r.high_n} of ${r.checked_n}; interval ${r.high_ci_low.toFixed(2)} to ${r.high_ci_high.toFixed(2)})`,
        },
      }
    })
}

export default function BudgetChart() {
  const state = useResult('score_budget')
  const data = state.status === 'ready' ? budgetRows(state.data.rows) : []
  const fmt = (v) => (typeof v === 'number' ? v.toFixed(2) : '')
  const table = {
    columns: [
      { key: 'label', label: 'Group' },
      { key: 'n', label: 'Checked', num: true },
      { key: 'suspicious', label: 'Suspicious or above (%)', num: true, format: fmt },
      { key: 'high', label: 'High risk (%)', num: true, format: fmt },
      { key: 'budget', label: 'Budget' },
    ],
    rows: data,
  }
  const over = data.filter((d) => d.budget === 'OVER').map((d) => d.label)
  return (
    <ChartCard
      id="chart-budget"
      title="False alarms on legitimate mail"
      question="Share of legitimate emails and real conversation messages that the score flags. Each group should stay left of the dashed lines: 1% for High risk, 5% for Suspicious or above."
      state={state}
      table={table}
      summary="Horizontal bars of the false-alarm rate per group of legitimate mail, with the 1% and 5% budgets as dashed lines. The values are in the table view."
      caveat={`Validation emails. Groups with fewer than 20 checked messages are shown but not judged. A row with no bar is at 0%. The axis stops at 10%: a whisker that leaves the plot belongs to a small group, and the table view has the exact interval. ${over.length ? `Over budget: ${over.join(', ')}; the cause is the quote check, which is also the only rule that finds forged Enron threads. ` : ''}The rule that defines 'legitimate mail' was corrected after the validation emails were read, so these figures are a check, not a clean measurement: the test split is.`}
    >
      <ResponsiveContainer width="100%" height={Math.max(260, data.length * 54 + 70)}>
        <BarChart data={data} layout="vertical" margin={{ top: 16, right: 24, bottom: 8, left: 8 }} barGap={2} barCategoryGap="26%">
          <CartesianGrid horizontal={false} stroke="var(--line)" />
          <XAxis type="number" domain={[0, 10]} allowDataOverflow ticks={[0, 1, 2, 4, 5, 6, 8, 10]} tickFormatter={(v) => `${v}%`} tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
          <YAxis type="category" dataKey="label" tick={TICK} tickLine={false} axisLine={false} width={210} />
          <Tooltip content={<ChartTooltip rows={(point) => `${point.n} checked messages; budget: ${point.budget}`} />} cursor={{ fill: 'var(--line)', opacity: 0.5 }} isAnimationActive={false} />
          <Legend iconType="square" formatter={legendText} itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
          <ReferenceLine x={BUDGETS.high} stroke="var(--ink2)" strokeDasharray="4 3" label={{ value: '1%', position: 'top', fill: 'var(--ink2)', fontSize: 12 }} />
          <ReferenceLine x={BUDGETS.suspicious} stroke="var(--ink2)" strokeDasharray="4 3" label={{ value: '5%', position: 'top', fill: 'var(--ink2)', fontSize: 12 }} />
          <Bar dataKey="suspicious" name="Suspicious or above" fill={COLORS.suspicious} stroke="var(--surface)" strokeWidth={2} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false}>
            <ErrorBar dataKey="suspicious_err" direction="x" width={4} stroke="var(--ink2)" strokeWidth={1.5} />
          </Bar>
          <Bar dataKey="high" name="High risk" fill={COLORS.high} stroke="var(--surface)" strokeWidth={2} radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false}>
            <ErrorBar dataKey="high_err" direction="x" width={4} stroke="var(--ink2)" strokeWidth={1.5} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
