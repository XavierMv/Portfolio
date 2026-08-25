import { C, Chip, tc } from '../../ui.jsx'

const TYPE_COLOR = { BUY_WATCH: C.green, MOMENTUM: C.cyan, UNDERVALUED: C.blue, RISK_FLAG: C.red, DRAG: C.amber }
const PRIO_COLOR = { HIGH: C.red, MEDIUM: C.amber, LOW: C.muted }

export default function WatchlistTab({ data }) {
  const signals = data.watchlist || []
  if (!signals.length) return <div style={{ color: C.muted, textAlign: 'center', padding: 40 }}>No watchlist signals generated.</div>
  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 14 }}>
        <strong style={{ color: C.text }}>{signals.length} signals</strong> across your holdings, sorted by priority.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(340px,1fr))', gap: 12 }}>
        {signals.map((s, i) => {
          const col = TYPE_COLOR[s.type] || C.muted
          return (
            <div key={i} style={{ background: C.card, border: `1px solid ${C.border2}`, borderRadius: 12,
              padding: 14, borderLeft: `3px solid ${col}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(s.theme), fontSize: 13 }}>{s.ticker}</span>
                  <Chip label={s.type.replace('_', ' ')} color={col} />
                </div>
                <Chip label={s.priority} color={PRIO_COLOR[s.priority] || C.muted} />
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.text, marginBottom: 5 }}>{s.title}</div>
              <div style={{ fontSize: 10.5, color: C.muted, lineHeight: 1.55, marginBottom: 8 }}>{s.desc}</div>
              <div style={{ fontSize: 10.5, color: col, lineHeight: 1.5, background: `${col}0c`, borderRadius: 6, padding: '7px 10px' }}>
                → {s.action}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
