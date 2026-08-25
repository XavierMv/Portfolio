import { useState } from 'react'
import { C, Chip, SL, Card, HBar, TH, TD, pct, f1, f2, grc, safe, tc, HCOL, SCOL, rankColor } from '../../ui.jsx'

export default function CombinationsTab({ data }) {
  const [sel, setSel] = useState(null)
  const [sort, setSort] = useState({ k: 'score', dir: -1 })

  // Medals belong to the composite-score ranking, not to wherever a row happens
  // to land in the current sort. Resolve each strategy's rank ONCE by score, then
  // carry it through any re-sort — otherwise sorting by MaxDD handed 🥇 to
  // whatever floated to the top.
  const base = data.combinations || []
  const rankByName = new Map(
    [...base].sort((a, b) => safe(b.score) - safe(a.score)).map((c, i) => [c.name, i])
  )
  const combos = [...base].sort((a, b) => sort.dir * (safe(b[sort.k]) - safe(a[sort.k])))
  const sortBy = k => setSort(s => ({ k, dir: s.k === k ? -s.dir : -1 }))
  // Track the expanded row by name, so re-sorting keeps the same strategy open
  // instead of swapping in whichever strategy now sits at that index.
  const selected = sel != null ? base.find(c => c.name === sel) : null
  const hasFund = combos.some(c => c.has_fundamentals)
  const approx = combos.some(c => c.exact_metrics === false)
  // The engine allocates across every holding; `top_weights` is only the largest
  // few, so its total is partial by design. Derive the full count and the
  // remainder so the panel can account for what it isn't listing.
  const heldCount = (data.stocks || []).filter(s => !s.error).length
  const mine   = base.find(c => c.is_actual)
  const myRank = mine ? rankByName.get(mine.name) : null
  const conv   = base.find(c => c.name === 'Conviction Weighted')
  const ranked = [...base].sort((a, b) => safe(b.score) - safe(a.score))
  const COLS = [['score', 'Score'], ['ret', 'Return'], ['vol', 'Vol'], ['sharpe', 'Sharpe'],
    ['fund_composite', 'Fund'], ['alpha', 'Alpha'], ['beta', 'Beta'], ['mdd', 'MaxDD'], ['calmar', 'Calmar']]
  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 14, lineHeight: 1.6 }}>
        <strong style={{ color: C.text }}>{combos.length} strategies</strong> ranked by composite score
        ( <span style={{ color: C.cyan }}>price</span>{hasFund && <> + <span style={{ color: C.green }}>fundamentals</span></>} ).
        Medals always reflect the score ranking, whatever column you sort by. Click a row to expand.
        {mine && (
          <span> <span style={{ color: C.purple }}>Your Portfolio</span> and{' '}
            <span style={{ color: C.green }}>Conviction Weighted</span> are scored on the same basis, not idealised.</span>
        )}
        <div style={{ fontSize: 10, marginTop: 4, color: approx ? C.amber : C.muted }}>
          {approx
            ? '⚠ Risk stats are weighted per-stock averages — no return history was available to backtest these weights.'
            : 'Return / Vol / MaxDD / Sharpe are backtested: each strategy\'s weights applied to actual daily returns over the lookback.'}
        </div>
      </div>
      {mine && (
        <div style={{ background: `${C.purple}0c`, border: `1px solid ${C.purple}30`, borderRadius: 12,
          padding: '11px 16px', marginBottom: 14, fontSize: 11, color: C.muted, lineHeight: 1.7 }}>
          <strong style={{ color: C.purple }}>Your Portfolio</strong> ranks{' '}
          <strong style={{ color: C.text }}>#{myRank + 1} of {base.length}</strong> (score {f1(mine.score)}).
          {ranked[0] && ranked[0].name !== mine.name && (
            <> Best is <strong style={{ color: C.cyan }}>{ranked[0].name}</strong> at {f1(ranked[0].score)},
              a gap of <strong style={{ color: C.text }}>{f1(ranked[0].score - mine.score)}</strong>.</>
          )}
          {conv && conv.name !== mine.name && (
            <> This app's own sizing (<strong style={{ color: C.green }}>Conviction Weighted</strong>) scores {f1(conv.score)}.</>
          )}
        </div>
      )}
      <div style={{ overflowX: 'auto', marginBottom: 18 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
            <TH>#</TH><TH>Strategy</TH>
            {COLS.map(([k, l]) => <TH key={k} onClick={() => sortBy(k)} active={sort.k === k}>{l}{sort.k === k ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}</TH>)}
            <TH>Flags</TH>
          </tr></thead>
          <tbody>
            {combos.map((c, i) => {
              const active = sel === c.name, fc = c.fund_composite || 0
              const rank = rankByName.get(c.name) ?? i
              return (
                <tr key={c.name} onClick={() => setSel(active ? null : c.name)} style={{
                  background: active ? `${C.cyan}0a`
                    : c.is_actual ? `${C.purple}0c`
                    : c.is_reference ? `${C.green}07`
                    : i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent',
                  borderBottom: `1px solid ${active ? C.cyan + '28' : C.border}`,
                  borderLeft: c.is_actual ? `2px solid ${C.purple}`
                    : c.is_reference ? `2px solid ${C.green}` : '2px solid transparent',
                  cursor: 'pointer' }}>
                  <TD style={{ textAlign: 'center', fontSize: 13, fontWeight: 800, color: rankColor(rank) }}>
                    {rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : `#${rank + 1}`}</TD>
                  <TD><div style={{ fontSize: 12, fontWeight: 800, marginBottom: 4,
                    color: c.is_actual ? C.purple : c.is_reference ? C.green : C.text }}>{c.name}</div>
                    <Chip label={c.style} color={c.is_actual ? C.purple : c.is_reference ? C.green : (SCOL[c.style] || C.muted)} /></TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 800, color: rankColor(rank) }}>{f1(c.score)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(c.ret) }}>{pct(c.ret)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.amber }}>{pct(c.vol)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: c.sharpe > 1.2 ? C.green : c.sharpe > 0.5 ? C.amber : C.red }}>{f2(c.sharpe)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: fc > 65 ? C.green : fc > 45 ? C.amber : C.muted }}>{c.has_fundamentals ? `${fc}` : '—'}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(c.alpha) }}>{pct(c.alpha)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: c.beta > 1.5 ? C.red : C.muted }}>{f2(c.beta)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.red }}>{pct(c.mdd)}</TD>
                  <TD style={{ fontVariantNumeric: 'tabular-nums', color: grc(c.calmar) }}>{f2(c.calmar)}</TD>
                  <TD><div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', maxWidth: 180 }}>
                    {(c.flags || []).slice(0, 2).map((f, fi) => <Chip key={fi} label={f.label} color={f.color} />)}</div></TD>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {selected && (() => {
        const rows      = selected.top_weights || []
        const rowsShown = rows.length
        const shownSum  = rows.reduce((a, h) => a + safe(h.weight), 0)
        const remainder = Math.max(0, 1 - shownSum)
        return (
        <Card style={{ border: `1px solid ${C.cyan}30` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, color: C.text, marginBottom: 4 }}>{selected.name}</div>
              <div style={{ fontSize: 11, color: C.muted, maxWidth: 520, lineHeight: 1.6 }}>{selected.desc}</div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <Chip label={`${selected.horizon}-Term`} color={HCOL[selected.horizon] || C.muted} />
              <Chip label={`Score ${selected.score}`} color={C.cyan} />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <SL text="Performance & Risk" />
              <HBar label="Exp.Ret" value={selected.ret} max={3} color={grc(selected.ret)} />
              <HBar label="Vol" value={selected.vol} max={1.5} color={C.amber} />
              <HBar label="Sharpe" value={selected.sharpe} max={3} ratio color={selected.sharpe > 1 ? C.green : C.amber} />
              <HBar label="Alpha" value={selected.alpha} max={0.8} color={grc(selected.alpha)} />
              <HBar label="Max DD" value={Math.abs(selected.mdd)} max={1} color={C.red} />
              {selected.has_fundamentals && <HBar label="Fund" value={selected.fund_composite / 100} max={1} color={selected.fund_composite > 65 ? C.green : C.amber} />}
              <HBar label="Calmar" value={selected.calmar} max={6} ratio color={grc(selected.calmar)} />
            </div>
            <div>
              {/* The engine allocates across EVERY holding, but only the largest
                  few are listed here — so these rows deliberately do not sum to
                  100%. Say how many are shown and account for the rest, or the
                  partial total reads as a bug. */}
              <SL text={rowsShown < heldCount
                ? `Allocation — top ${rowsShown} of ${heldCount} holdings`
                : 'Allocation'} />
              {(selected.top_weights || []).map(h => (
                <div key={h.ticker} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
                  <div style={{ width: 44, fontSize: 10, fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(h.theme) }}>{h.ticker}</div>
                  <div style={{ flex: 1, height: 5, background: C.dim, borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(h.weight * 500, 100)}%`, height: '100%', background: tc(h.theme), borderRadius: 3 }} />
                  </div>
                  <div style={{ width: 38, fontSize: 10, fontVariantNumeric: 'tabular-nums', color: tc(h.theme), textAlign: 'right' }}>{(h.weight * 100).toFixed(1)}%</div>
                  {h.fundamental_grade && <Chip label={h.fundamental_grade} color={C.green} />}
                </div>
              ))}

              {remainder > 0.0005 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
                  <div style={{ width: 44, fontSize: 9.5, color: C.slate, textAlign: 'left' }}>
                    +{heldCount - rowsShown}
                  </div>
                  <div style={{ flex: 1, height: 5, background: C.dim, borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(remainder * 500, 100)}%`, height: '100%', background: C.mist, borderRadius: 3 }} />
                  </div>
                  <div style={{ width: 38, fontSize: 10, fontVariantNumeric: 'tabular-nums', color: C.slate, textAlign: 'right' }}>
                    {(remainder * 100).toFixed(1)}%
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, paddingTop: 9,
                borderTop: `1px solid ${C.mist}` }}>
                <div style={{ flex: 1, fontSize: 9.5, color: C.slate, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                  {remainder > 0.0005 ? `Remaining ${heldCount - rowsShown} holdings included` : 'Total'}
                </div>
                <div style={{ width: 38, fontSize: 10.5, fontWeight: 500, color: C.text,
                  fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                  {(shownSum + remainder > 0 ? (shownSum + remainder) * 100 : 0).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>
        </Card>
        )
      })()}
    </div>
  )
}
