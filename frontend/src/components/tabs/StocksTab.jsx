import { useState } from 'react'
import { C, Chip, TH, TD, pct, f2, grc, safe, tc, HCOL } from '../../ui.jsx'

export default function StocksTab({ data }) {
  const stocks = (data.stocks || []).filter(s => !s.error)
  const [sort, setSort] = useState({ k: 'annualized_return', dir: -1 })
  const sortBy = k => setSort(s => ({ k, dir: s.k === k ? -s.dir : -1 }))
  const sorted = [...stocks].sort((a, b) => sort.dir * (safe(b[sort.k]) - safe(a[sort.k])))
  const COLS = [['ticker', 'Ticker'], ['theme', 'Theme'], ['annualized_return', 'Ann.Ret'],
    ['annualized_volatility', 'Vol'], ['sharpe', 'Sharpe'], ['sortino', 'Sortino'],
    ['beta', 'Beta'], ['alpha', 'Alpha'], ['max_drawdown', 'MaxDD'], ['calmar', 'Calmar'],
    ['recovery_factor', 'Recov']]
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
          {COLS.map(([k, l]) => <TH key={k} onClick={() => sortBy(k)} active={sort.k === k}>{l}{sort.k === k ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}</TH>)}
          <TH>Horizon</TH>
        </tr></thead>
        <tbody>
          {sorted.map((s, i) => (
            <tr key={s.ticker} style={{ borderBottom: `1px solid ${C.border}`, background: i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent' }}>
              <TD style={{ fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(s.theme), fontSize: 12 }}>{s.ticker}</TD>
              <TD><Chip label={s.theme} color={tc(s.theme)} /></TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(s.annualized_return) }}>{pct(s.annualized_return)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.amber }}>{pct(s.annualized_volatility)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: s.sharpe > 1 ? C.green : s.sharpe > 0 ? C.amber : C.red }}>{f2(s.sharpe)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.muted }}>{f2(s.sortino)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: s.beta > 1.5 ? C.red : C.muted }}>{f2(s.beta)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(s.alpha) }}>{pct(s.alpha)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.red }}>{pct(s.max_drawdown)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(s.calmar) }}>{f2(s.calmar)}</TD>
              <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.muted }}>{f2(s.recovery_factor)}</TD>
              <TD><Chip label={(s.horizon || {}).best || 'Medium'} color={HCOL[(s.horizon || {}).best] || C.muted} /></TD>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
