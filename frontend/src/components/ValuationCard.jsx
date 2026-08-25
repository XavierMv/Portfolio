// ValuationCard.jsx — fair-value triangulation + trigger display
// Drop into frontend/src/components/ and render where you show fundamentals
// (e.g. inside the candidate detail in DiscoveryTab and the Stocks/Fundamentals view).
//
// Usage:  <ValuationCard val={scored.valuation_analysis} />
// where scored.valuation_analysis is the object returned by /api/score (compute_valuation).

import { C, FONT_DISPLAY, remap } from '../ui.jsx'

const TRIGGER_COLOR = {
  "STRONG BUY": "#2f6b41", "BUY": "#5c9670", "HOLD": "#816729",
  "TRIM": "#c2703f", "AVOID": "#b3402f",
}
const METHOD_LABEL = {
  dcf: "DCF (intrinsic)", peer_multiple: "Peer multiple",
  historical_multiple: "Historical multiple", analyst_target: "Analyst target",
  sales_multiple: "Sales multiple (P/S)",
}
const f = v => v == null ? "—" : `$${Number(v).toFixed(2)}`

export default function ValuationCard({ val }) {
  if (!val) return null
  if (!val.available) {
    return (
      <div style={{ background: `${C.amber}0c`, border: `1px solid ${C.amber}30`, borderRadius: 10, padding: "12px 14px" }}>
        <div style={{ fontSize: 10, color: C.amber, fontWeight: 700, marginBottom: 4 }}>⚠ Valuation not available</div>
        <div style={{ fontSize: 10, color: C.muted, lineHeight: 1.5 }}>{val.reason}</div>
      </div>
    )
  }

  const tc = remap(TRIGGER_COLOR[val.trigger]) || C.muted
  const mos = val.margin_of_safety
  const price = val.current_price
  const fair = val.fair_value
  // position price vs fair-value range on a simple bar
  const lo = Math.min(val.fair_value_low, price), hi = Math.max(val.fair_value_high, price)
  const span = hi - lo || 1
  const pricePct = ((price - lo) / span) * 100
  const fairPct = ((fair - lo) / span) * 100

  return (
    <div style={{ background: C.card, border: `1px solid ${tc}44`, borderRadius: 11, padding: 16 }}>
      {/* header: trigger + confidence */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 9, color: C.muted, letterSpacing: "0.12em", textTransform: "uppercase" }}>Valuation Trigger</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: tc, marginTop: 2 }}>{val.trigger}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 9, color: C.muted, textTransform: "uppercase" }}>Margin of Safety</div>
          <div style={{ fontSize: 23, fontWeight: 400, fontFamily: FONT_DISPLAY, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums', color: mos >= 0 ? C.green : C.red }}>
            {mos >= 0 ? "+" : ""}{mos}%
          </div>
        </div>
      </div>

      <div style={{ fontSize: 10, color: C.muted, lineHeight: 1.5, marginBottom: 14 }}>{val.trigger_desc}</div>

      {/* price vs fair value */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: C.muted }}>Trades at <b style={{ color: C.text, fontVariantNumeric: 'tabular-nums' }}>{f(price)}</b></span>
        <span style={{ fontSize: 11, color: C.muted }}>Worth <b style={{ color: tc, fontVariantNumeric: 'tabular-nums' }}>{f(fair)}</b></span>
      </div>
      {/* range bar */}
      <div style={{ position: "relative", height: 8, background: C.dim, borderRadius: 4, marginBottom: 6 }}>
        {!val.speculative_basis && (
          <div style={{ position: "absolute", left: `${((val.fair_value_low - lo) / span) * 100}%`,
            width: `${((val.fair_value_high - val.fair_value_low) / span) * 100}%`, top: 0, bottom: 0,
            background: `${tc}33`, borderRadius: 4 }} />
        )}
        <div style={{ position: "absolute", left: `${fairPct}%`, top: -3, width: 2, height: 14, background: tc, transform: "translateX(-1px)" }} />
        <div style={{ position: "absolute", left: `${pricePct}%`, top: -3, width: 2, height: 14, background: C.cyan, transform: "translateX(-1px)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, color: C.muted, marginBottom: 14 }}>
        <span style={{ color: C.cyan }}>● price</span>
        {!val.speculative_basis && <span>fair-value range {f(val.fair_value_low)} – {f(val.fair_value_high)}</span>}
        <span style={{ color: tc }}>● fair value</span>
      </div>

      {/* per-method breakdown */}
      <div style={{ fontSize: 9, color: C.muted, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8,
        borderTop: `1px solid ${C.border2}`, paddingTop: 10 }}>
        Methods ({val.method_count} used · {val.confidence} confidence{val.dispersion != null ? ` · ${val.dispersion}% spread` : ""})
      </div>
      {Object.entries(val.methods).map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
          <span style={{ fontSize: 10, color: val.methods_used.includes(k) ? C.text : C.muted }}>
            {val.methods_used.includes(k) ? "✓" : "○"} {METHOD_LABEL[k] || k}
          </span>
          <span style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums',
            color: v == null ? C.muted : v > price ? C.green : C.red }}>{f(v)}</span>
        </div>
      ))}

      {val.speculative_basis && (
        <div style={{ marginTop: 12, fontSize: 9, color: C.amber, background: `${C.amber}0c`,
          borderLeft: `2px solid ${C.amber}`, borderRadius: "0 6px 6px 0", padding: "7px 10px", lineHeight: 1.5 }}>
          ⚠ Speculative basis: this name has no earnings or positive cash flow, so intrinsic methods (DCF, P/E)
          can't run. The trigger rests on sales-multiple and analyst anchors only — treat as low-confidence.
        </div>
      )}
    </div>
  )
}
