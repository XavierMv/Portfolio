// CompareTab.jsx — compare PORTFOLIO STRATEGIES (combinations) side by side.
// Multi-select up to 5 strategies → comparison table + strategy radar + growth curves.
import { useState } from 'react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { C, SL, Card, Chip, pct, f1, f2, grc, safe, HCOL } from '../../ui.jsx'

const LCOL = [C.green, C.cyan, C.amber, C.purple, C.pink]

export default function CompareTab({ data }) {
  const combos = data.combinations || []
  const [sel, setSel] = useState(() => [0, 1, 2].filter(i => i < combos.length))
  const toggle = i => setSel(s => s.includes(i) ? s.filter(x => x !== i) : (s.length < 5 ? [...s, i] : s))
  const chosen = sel.map(i => combos[i]).filter(Boolean)

  // parseInt('6mo') === 6, which used to label a 6-month backtest "~6y".
  // Read the unit, and prefer the actual number of days the backtest covered.
  const periodLabel = (() => {
    const raw = String(data.period || '5y')
    const m = raw.match(/^(\d+)\s*(mo|y)$/i)
    if (m) return m[2].toLowerCase() === 'mo' ? `${m[1]}mo` : `${m[1]}y`
    return raw
  })()

  // Strategy radar — normalized 0-100 across six attributes
  const radarData = ['Return', 'Sharpe', 'Fund.Score', 'Low DD', 'Alpha', 'Calmar'].map(attr => {
    const row = { attr }
    chosen.forEach((c, i) => {
      row[`p${i}`] = +(
        attr === 'Return'     ? Math.min(safe(c.ret) / 3 * 100, 100) :
        attr === 'Sharpe'     ? Math.min(safe(c.sharpe) / 3 * 100, 100) :
        attr === 'Fund.Score' ? safe(c.fund_composite) :
        attr === 'Low DD'     ? Math.max(0, (1 + safe(c.mdd)) * 100) :
        attr === 'Alpha'      ? Math.min(safe(c.alpha) / 0.8 * 100, 100) :
                                Math.min(safe(c.calmar) / 6 * 100, 100)
      ).toFixed(1)
    })
    return row
  })

  // Real backtest curves from the backend (combo.curve + shared dates + benchmark).
  const curveDates = data.combo_curve_dates || []
  const benchCurve = data.benchmark_curve || []
  const hasCurves = chosen.length > 0 && curveDates.length > 0 &&
    chosen.every(c => Array.isArray(c.curve) && c.curve.length === curveDates.length)
  const eq = hasCurves ? curveDates.map((d, k) => {
    const row = { t: k, date: d }
    chosen.forEach((c, i) => { row[`p${i}`] = c.curve[k] })
    if (benchCurve[k] != null) row.bench = benchCurve[k]
    return row
  }) : []

  const tableRows = [
    ['Score', c => f1(c.score), () => C.cyan],
    ['Return', c => pct(c.ret), c => grc(c.ret)],
    ['Volatility', c => pct(c.vol), () => C.amber],
    ['Sharpe', c => f2(c.sharpe), c => c.sharpe > 1.2 ? C.green : c.sharpe > 0.5 ? C.amber : C.red],
    ['Fund.Score', c => c.has_fundamentals ? `${c.fund_composite}/100` : '—', c => c.fund_composite > 65 ? C.green : c.fund_composite > 50 ? C.amber : C.muted],
    ['Alpha', c => pct(c.alpha), c => grc(c.alpha)],
    ['Beta', c => f2(c.beta), c => c.beta > 1.5 ? C.red : C.muted],
    ['Max DD', c => pct(c.mdd), () => C.red],
    ['Calmar', c => f2(c.calmar), c => grc(c.calmar)],
    ['Horizon', c => String(c.horizon), c => HCOL[c.horizon] || C.muted],
  ]

  if (!combos.length) return <div style={{ color: C.muted, textAlign: 'center', padding: 40 }}>Run an analysis to generate strategies.</div>

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 12 }}>
        Select up to 5 strategies to compare. The <span style={{ color: C.green }}>Fund.Score</span> axis reflects
        blended fundamental quality.
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 20 }}>
        {combos.map((c, i) => {
          const on = sel.includes(i)
          const col = on ? (LCOL[sel.indexOf(i)] || C.cyan) : C.muted
          return (
            <button key={i} onClick={() => toggle(i)} style={{ padding: '5px 12px', borderRadius: 6, fontSize: 10,
              fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums',
              background: on ? `${col}18` : 'transparent', border: `1px solid ${on ? col : C.border2}`, color: col }}>
              {c.name}
            </button>
          )
        })}
      </div>

      {chosen.length > 0 ? (
        <>
          <div style={{ overflowX: 'auto', marginBottom: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
                <th style={{ padding: '8px 12px', textAlign: 'left', color: C.muted, fontSize: 9, fontWeight: 700, textTransform: 'uppercase' }}>Metric</th>
                {chosen.map((c, i) => <th key={i} style={{ padding: '8px 12px', textAlign: 'left', color: LCOL[i], fontSize: 10, fontWeight: 800 }}>{c.name}</th>)}
              </tr></thead>
              <tbody>
                {tableRows.map(([label, vFn, cFn]) => (
                  <tr key={label} style={{ borderBottom: `1px solid ${C.border}`, background: 'rgba(32,32,32,0.022)' }}>
                    <td style={{ padding: '8px 12px', color: C.muted, fontSize: 10 }}>{label}</td>
                    {chosen.map((c, i) => <td key={i} style={{ padding: '8px 12px', fontVariantNumeric: 'tabular-nums', fontSize: 11, fontWeight: 700, color: cFn(c) }}>{vFn(c)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <Card>
              <SL text="Strategy Radar (incl. Fundamentals)" />
              <ResponsiveContainer width="100%" height={250}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke={C.border2} />
                  <PolarAngleAxis dataKey="attr" tick={{ fill: C.muted, fontSize: 9 }} />
                  {chosen.map((c, i) => (
                    <Radar key={i} name={c.name} dataKey={`p${i}`} stroke={LCOL[i]} fill={LCOL[i]} fillOpacity={0.08} strokeWidth={2} />
                  ))}
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border2}`, fontSize: 10, borderRadius: 8 }} />
                </RadarChart>
              </ResponsiveContainer>
            </Card>

            <Card>
              <SL text={`Backtested Growth — indexed to 100 (${periodLabel}, vs ${data.benchmark || 'SPY'})`} />
              {hasCurves ? (
                <>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={eq}>
                      <CartesianGrid strokeDasharray="2 6" stroke={C.border} />
                      <XAxis dataKey="date" tick={{ fontSize: 8, fill: C.muted }} tickLine={false} interval={Math.floor(eq.length / 6) || 1} />
                      <YAxis tick={{ fontSize: 8, fill: C.muted }} tickLine={false} width={40} />
                      <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border2}`, fontSize: 10, borderRadius: 8 }} />
                      {chosen.map((c, i) => (
                        <Line key={i} dataKey={`p${i}`} name={c.name} stroke={LCOL[i]} strokeWidth={2} dot={false} />
                      ))}
                      <Line dataKey="bench" name={data.benchmark || 'SPY'} stroke={C.muted} strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                    </LineChart>
                  </ResponsiveContainer>
                  <div style={{ fontSize: 8.5, color: C.muted, marginTop: 6 }}>
                    Real backtest — each strategy's weights applied to historical daily returns over the lookback, compounded and indexed to 100.
                  </div>
                </>
              ) : (
                <div style={{ color: C.muted, fontSize: 11, padding: '34px 10px', textAlign: 'center' }}>
                  Backtest curves unavailable — re-run the analysis to generate them.
                </div>
              )}
            </Card>
          </div>
        </>
      ) : (
        <div style={{ color: C.muted, textAlign: 'center', padding: 30 }}>Select at least one strategy above.</div>
      )}
    </div>
  )
}
