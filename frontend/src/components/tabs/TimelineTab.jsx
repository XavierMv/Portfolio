import { useState } from 'react'
import { C, Chip, SL, Card, MBox, TH, TD, safe, tc, HCOL } from '../../ui.jsx'

const CONV_COLOR = { 'Very High': C.green, High: '#5c9670', Moderate: C.amber, Low: '#c2703f', Speculative: C.red }

export default function TimelineTab({ data }) {
  const timelines = data.timelines || []
  const pt = data.portfolio_timeline || {}
  const [open, setOpen] = useState(null)
  if (!timelines.length) return <div style={{ color: C.muted, textAlign: 'center', padding: 40 }}>No timeline data.</div>

  const mix = pt.horizon_mix || {}
  const boxes = [
    ['Ready to Enter', `${pt.ready_count ?? 0}/${pt.total_stocks ?? timelines.length}`, C.green, 'entry checklist ≥60%'],
    ['Clears Hurdle', `${pt.hurdle_pass_count ?? 0}/${pt.total_stocks ?? timelines.length}`, C.cyan, 'return > risk hurdle'],
    ['Avg Expected', `${safe(pt.avg_expected_return).toFixed(1)}%`, C.text, 'annualized'],
    ['Avg Hurdle', `${safe(pt.avg_hurdle_return).toFixed(1)}%`, C.amber, 'required return'],
    ['Port vs Hurdle', `${pt.port_vs_hurdle > 0 ? '+' : ''}${safe(pt.port_vs_hurdle).toFixed(1)}%`, pt.port_vs_hurdle > 0 ? C.green : C.red, 'margin'],
    ['Next Review', pt.next_review_date || '—', C.cyan, 'avg entry window'],
  ]

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10, marginBottom: 14 }}>
        {boxes.map(([l, v, c, sub]) => <MBox key={l} label={l} value={v} color={c} sub={sub} />)}
      </div>

      <Card>
        <SL text="Horizon Mix" />
        <div style={{ display: 'flex', gap: 10 }}>
          {['Short', 'Medium', 'Long'].map(h => {
            const m = mix[h] || { count: 0, pct: 0, avg_conviction: 0 }
            return (
              <div key={h} style={{ flex: 1, background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 10, padding: '10px 12px' }}>
                <Chip label={h} color={HCOL[h]} />
                <div style={{ fontSize: 18, fontWeight: 800, color: C.text, fontVariantNumeric: 'tabular-nums', marginTop: 6 }}>{m.count} <span style={{ fontSize: 11, color: C.muted }}>({m.pct}%)</span></div>
                <div style={{ fontSize: 9, color: C.muted, marginTop: 3 }}>avg conviction {m.avg_conviction}</div>
              </div>
            )
          })}
        </div>
        {pt.rebal_recommendation && <div style={{ fontSize: 10.5, color: C.muted, marginTop: 12, lineHeight: 1.5 }}>↻ {pt.rebal_recommendation}</div>}
      </Card>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
            <TH>Ticker</TH><TH>Horizon</TH><TH>Hold Range</TH><TH>Conviction</TH><TH>Size</TH><TH>Entry</TH><TH>Hurdle</TH><TH /></tr></thead>
          <tbody>
            {timelines.map((t, i) => {
              const isOpen = open === t.ticker
              return [
                <tr key={t.ticker} style={{ borderBottom: `1px solid ${isOpen ? C.cyan + '28' : C.border}`,
                  background: isOpen ? `${C.cyan}06` : i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent' }}>
                  <TD style={{ fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(t.theme), fontSize: 12 }}>{t.ticker}</TD>
                  <TD><Chip label={t.best_horizon} color={HCOL[t.best_horizon] || C.muted} /></TD>
                  <TD style={{ color: C.text, fontVariantNumeric: 'tabular-nums' }}>{t.hold_range}</TD>
                  <TD><Chip label={t.conviction} color={CONV_COLOR[t.conviction] || C.muted} /></TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.cyan }}>{t.size_range}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: t.ready_to_enter ? C.green : C.amber }}>{t.entry_pct}%</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: t.meets_hurdle ? C.green : C.red }}>{t.meets_hurdle ? '✓' : '✕'} {safe(t.expected_return).toFixed(0)}/{safe(t.required_return).toFixed(0)}%</TD>
                  <TD><button onClick={() => setOpen(isOpen ? null : t.ticker)} style={{ background: 'transparent', color: C.muted, border: `1px solid ${C.border2}`, borderRadius: 6, padding: '4px 10px', fontSize: 9, fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }}>{isOpen ? 'Hide' : 'Details'}</button></TD>
                </tr>,
                isOpen ? (
                  <tr key={t.ticker + '-d'}><td colSpan={8} style={{ padding: '0 16px 18px', background: `${C.cyan}04`, borderBottom: `1px solid ${C.border}` }}>
                    <div style={{ paddingTop: 12, fontSize: 11, color: C.text, lineHeight: 1.6, marginBottom: 12 }}>{t.narrative}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                      <div>
                        <SL text={`Entry checklist (${t.entry_met}/${t.entry_total})`} />
                        {(t.entry_signals || []).map((e, ei) => (
                          <div key={ei} style={{ fontSize: 10, color: e.met ? C.green : C.muted, marginBottom: 5 }}>{e.met ? '✓' : '○'} {e.label}</div>
                        ))}
                      </div>
                      <div>
                        <SL text="Exit triggers" />
                        {(t.exit_triggers || []).map((e, ei) => (
                          <div key={ei} style={{ fontSize: 10, color: e.color, marginBottom: 5 }}>• {e.label}</div>
                        ))}
                      </div>
                    </div>
                    <SL text="Catalysts" />
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {(t.catalysts || []).map((c, ci) => (
                        <div key={ci} style={{ fontSize: 9.5, color: C.muted, background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 6, padding: '5px 9px' }}>
                          {c.event} <span style={{ color: C.amber }}>· {c.timing} · {c.impact}</span>
                        </div>
                      ))}
                    </div>
                  </td></tr>
                ) : null
              ]
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
