import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell } from 'recharts'
import { C, MBox, SL, Card, pct, f2, grc, safe, RANK } from '../../ui.jsx'

export default function OverviewTab({ data }) {
  const p = data.portfolio || {}
  const best = data.combinations?.[0]
  // A holding younger than the lookback shrinks the window available to the
  // covariance-based views (efficient frontier, strategy backtests). The
  // portfolio curve itself now spans the full history, so say when they differ.
  const hDays = p.history_days, cDays = p.common_days
  const thinCommon = hDays && cDays && cDays < hDays * 0.9
  const boxes = [
    ['Total Return', pct(p.total_return), grc(p.total_return)],
    ['Ann. Return', pct(p.annualized_return), grc(p.annualized_return)],
    ['Ann. Volatility', pct(p.annualized_volatility), C.amber],
    ['Sharpe', f2(p.sharpe), grc(p.sharpe)],
    ['Sortino', f2(p.sortino), grc(p.sortino)],
    ['Beta', f2(p.beta), C.muted],
    ['Alpha', pct(p.alpha), grc(p.alpha)],
    ['Max Drawdown', pct(p.max_drawdown), C.red],
    ['Calmar', f2(p.calmar), grc(p.calmar)],
    ['HHI', safe(p.hhi).toFixed(4), C.muted, p.weighting === 'custom' ? 'your sizes' : 'equal weight'],
    ['Effective N', f2(p.effective_n), C.cyan, p.weighting === 'custom' ? 'your sizes' : `= n (equal weight)`],
    ['Div. Ratio', f2(p.div_ratio), C.cyan, p.weighting === 'custom' ? 'your sizes' : 'equal weight'],
  ]
  return (
    <div>
      {best && (
        <div style={{ background: `${C.cyan}0c`, border: `1px solid ${C.cyan}28`, borderRadius: 12,
          padding: '11px 16px', marginBottom: 18, fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
          🏆 Top strategy: <strong style={{ color: C.cyan }}>{best.name}</strong> — {best.desc}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10, marginBottom: 18 }}>
        {boxes.map(([l, v, c, sub]) => <MBox key={l} label={l} value={v} color={c} sub={sub} />)}
      </div>
      {p.weighting === 'equal' && (
        <div style={{ background: `${C.card}`, border: `1px solid ${C.border2}`, borderRadius: 10,
          padding: '9px 14px', marginBottom: 16, fontSize: 10.5, color: C.muted, lineHeight: 1.6 }}>
          Running equal-weight — HHI and Effective N are structural constants (1/n and n), not measurements.
          Add position sizes in the sidebar as <span style={{ color: C.cyan }}>TICKER:Theme:Amount</span> to
          measure your real book and rank it against every strategy.
        </div>
      )}
      {thinCommon && (
        <div style={{ background: `${C.amber}0c`, border: `1px solid ${C.amber}30`, borderRadius: 10,
          padding: '9px 14px', marginBottom: 16, fontSize: 10.5, color: C.muted, lineHeight: 1.6 }}>
          ⚠ Portfolio metrics above span <strong style={{ color: C.text }}>{hDays}</strong> trading days, but at least
          one holding is younger than the lookback — the efficient frontier and strategy backtests can only use the{' '}
          <strong style={{ color: C.text }}>{cDays}</strong> days where every holding traded.
        </div>
      )}

      {(data.equity_curve || []).length > 0 && (
        <Card>
          <SL text="Portfolio vs Benchmark (indexed to 100)" />
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data.equity_curve}>
              <CartesianGrid strokeDasharray="2 6" stroke={C.border} />
              <XAxis dataKey="date" tick={{ fontSize: 8, fill: C.muted }} tickLine={false}
                interval={Math.floor((data.equity_curve.length || 60) / 8)} />
              <YAxis tick={{ fontSize: 8, fill: C.muted }} tickLine={false} width={38} />
              <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border2}`, fontSize: 10, borderRadius: 8 }} />
              <Line dataKey="portfolio" stroke={C.green} strokeWidth={2.5} dot={false} name="Portfolio" />
              <Line dataKey="benchmark" stroke={C.muted} strokeWidth={1.5} dot={false} name={data.benchmark} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {(data.combinations || []).length > 0 && (
        <Card>
          <SL text="Strategy Scores (Price + Fundamentals)" />
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={data.combinations.map(c => ({ name: c.name, score: safe(c.score) }))} layout="vertical" margin={{ left: 120 }}>
              <CartesianGrid strokeDasharray="2 6" stroke={C.border} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 8, fill: C.muted }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: C.muted }} width={118} tickLine={false} />
              <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border2}`, fontSize: 10, borderRadius: 8 }} />
              <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                {data.combinations.map((_, i) => <Cell key={i} fill={RANK[i] || C.border2} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}
