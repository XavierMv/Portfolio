// MonteCarloView.jsx — portfolio & per-stock simulation display
// Drop into frontend/src/components/. Renders the output of /api/montecarlo.
//
// Usage (standalone tab): <MonteCarloView runId={runId} />
// Or embed a compact per-stock verdict: <MonteCarloMini sim={stock.montecarlo} />

import { useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { C, FONT_DISPLAY, remap } from '../ui.jsx'

const VERDICT_COLOR = {
  FAVORABLE: "#3d7a4f", BALANCED: "#816729", RISKY: "#c2703f", UNFAVORABLE: "#b3402f",
}
const DRIFT_MODES = [
  ["dampened", "Dampened", "history shrunk toward market — recommended"],
  ["raw", "Raw", "full historical drift — optimistic for past winners"],
  ["market", "Market", "flat ~7% drift — most conservative"],
]
const mult = v => v == null ? "—" : `${Number(v).toFixed(2)}×`
const pct = v => v == null ? "—" : `${(Number(v) * 100).toFixed(0)}%`

export default function MonteCarloView({ runId }) {
  const [horizon, setHorizon] = useState(5)
  const [drift, setDrift] = useState("dampened")
  const [target, setTarget] = useState(50)        // % target return
  const [loading, setLoading] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)

  const run = async () => {
    if (!runId) { setErr("Run a portfolio analysis first."); return }
    setLoading(true); setErr(null)
    try {
      const r = await fetch("/api/montecarlo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId, horizon_years: Number(horizon),
          drift_mode: drift, target_return: Number(target) / 100 }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || "Simulation failed")
      setRes(await r.json())
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 16, lineHeight: 1.7 }}>
        <strong style={{ color: C.text }}>Monte Carlo simulation</strong> projects thousands of correlated future paths for your
        holdings, calibrated to each name's historical drift and volatility. It shows the <em>range</em> of outcomes and the
        <em> probability</em> of hitting your goals or suffering deep drawdowns — so position decisions rest on a distribution,
        not a single guess. <span style={{ color: C.muted }}>Equity portfolio logic (not options). GBM model — a probabilistic
        estimate, not a forecast.</span>
      </div>

      <div style={{ background: C.card, border: `1px solid ${C.mist}`, borderRadius: 8, padding: 22, marginBottom: 18 }}>
        <div style={{ display: "flex", gap: 22, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <div style={lbl}>Horizon (years)</div>
            <div style={{ display: "flex", gap: 4 }}>
              {[1, 3, 5, 10].map(y => (
                <button key={y} onClick={() => setHorizon(y)} style={pill(horizon === y)}>{y}y</button>
              ))}
            </div>
          </div>
          <div>
            <div style={lbl}>Drift assumption</div>
            <div style={{ display: "flex", gap: 4 }}>
              {DRIFT_MODES.map(([m, label, tip]) => (
                <button key={m} title={tip} onClick={() => setDrift(m)} style={pill(drift === m)}>{label}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={lbl}>Target return %</div>
            <input type="number" value={target} onChange={e => setTarget(e.target.value)} style={inp} />
          </div>
          <button onClick={run} disabled={loading} style={{
            background: loading ? C.mist : C.text, color: loading ? C.slate : C.bg, border: "none",
            borderRadius: 0, padding: "12px 26px", fontWeight: 500, fontSize: 12,
            cursor: loading ? "not-allowed" : "pointer" }}>{loading ? "Simulating…" : "Run Simulation"}</button>
        </div>
        <div style={{ fontSize: 9, color: C.muted, marginTop: 10 }}>
          Drift note: historical returns weakly predict the future. <strong>Dampened</strong> (default) shrinks each stock's
          historical drift halfway toward a conservative ~7% market assumption to avoid over-extrapolating past winners.
        </div>
      </div>

      {err && <div style={{ background: `${C.red}12`, border: `1px solid ${C.red}40`, borderRadius: 10,
        padding: "12px 16px", marginBottom: 16, fontSize: 11, color: C.red }}>⚠ {err}</div>}

      {res?.portfolio?.available && <PortfolioResult p={res.portfolio} horizon={horizon} target={target} weighting={res.weighting} />}
      {res?.stocks && <StockTable stocks={res.stocks} />}
    </div>
  )
}

function PortfolioResult({ p, horizon, target, weighting }) {
  const vc = remap(VERDICT_COLOR[p.verdict]) || C.muted
  // build a fan-chart dataset from the bands (linear interpolation start→end for illustration)
  const fan = []
  const steps = 24
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const interp = (end) => +(1 + (end - 1) * t).toFixed(3)
    fan.push({
      t: +(t * horizon).toFixed(2),
      p5: interp(p.bands.p5), p25: interp(p.bands.p25), p50: interp(p.bands.p50),
      p75: interp(p.bands.p75), p95: interp(p.bands.p95),
    })
  }
  return (
    <div style={{ background: C.card, border: `1px solid ${vc}44`, borderRadius: 12, padding: 18, marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 9, color: C.muted, letterSpacing: "0.12em", textTransform: "uppercase" }}>Portfolio Simulation · {p.n_paths.toLocaleString()} paths · {p.horizon_years}y</div>
          <div style={{ fontSize: 13, color: C.text, marginTop: 3 }}>
            {p.tickers.length} holdings · {p.drift_mode} drift ·{' '}
            <span style={{ color: weighting === 'custom' ? C.green : C.amber }}>
              {weighting === 'custom' ? 'your position sizes' : 'equal weight assumed'}
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 9, color: C.muted, textTransform: "uppercase" }}>Risk / Return Verdict</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: vc }}>{p.verdict}</div>
        </div>
      </div>

      {/* fan chart */}
      <ResponsiveContainer width="100%" height={230}>
        <AreaChart data={fan} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="band95" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={C.cyan} stopOpacity={0.18} /><stop offset="100%" stopColor={C.cyan} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="2 6" stroke={C.border} />
          <XAxis dataKey="t" tick={{ fontSize: 9, fill: C.muted }} tickLine={false} tickFormatter={v => `${v}y`} />
          <YAxis tick={{ fontSize: 9, fill: C.muted }} tickLine={false} width={42} tickFormatter={v => `${v}×`} />
          <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border2}`, fontSize: 11, borderRadius: 8 }}
            labelFormatter={v => `Year ${v}`} formatter={(val, n) => [`${val}×`, n.toUpperCase()]} />
          <Area dataKey="p95" stroke="none" fill="url(#band95)" isAnimationActive={false} />
          <Area dataKey="p5" stroke="none" fill={C.bg} isAnimationActive={false} />
          <Area dataKey="p75" stroke={C.cyan} strokeWidth={1} strokeDasharray="3 3" fill="none" isAnimationActive={false} />
          <Area dataKey="p25" stroke={C.cyan} strokeWidth={1} strokeDasharray="3 3" fill="none" isAnimationActive={false} />
          <Area dataKey="p50" stroke={C.green} strokeWidth={2.5} fill="none" isAnimationActive={false} />
          <ReferenceLine y={1} stroke={C.muted} strokeDasharray="2 4" label={{ value: "start", fill: C.muted, fontSize: 8, position: "insideLeft" }} />
          <ReferenceLine y={1 + target / 100} stroke={C.amber} strokeDasharray="2 4" label={{ value: `target`, fill: C.amber, fontSize: 8, position: "insideTopLeft" }} />
        </AreaChart>
      </ResponsiveContainer>
      <div style={{ fontSize: 8, color: C.muted, textAlign: "center", marginTop: 2 }}>
        median (green) · 25–75th & 5–95th percentile bands · ending value as a multiple of today
      </div>

      {/* outcome bands */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8, margin: "16px 0" }}>
        {[["P5 (worst)", p.bands.p5, C.red], ["P25", p.bands.p25, C.amber], ["P50 (median)", p.bands.p50, C.text],
          ["P75", p.bands.p75, "#5c9670"], ["P95 (best)", p.bands.p95, C.green]].map(([l, v, c]) => (
          <div key={l} style={box}>
            <div style={boxLbl}>{l}</div>
            <div style={{ ...boxVal, color: c }}>{mult(v)}</div>
            <div style={{ fontSize: 8, color: C.muted }}>{v >= 1 ? "+" : ""}{((v - 1) * 100).toFixed(0)}%</div>
          </div>
        ))}
      </div>

      {/* goal/risk probabilities */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
        <ProbGauge label={`Hit +${target}% target`} value={p.prob_target} good />
        <ProbGauge label="End at a loss" value={p.prob_loss} good={false} />
        <ProbGauge label="Touch −20% drawdown" value={p.prob_drawdown_20} good={false} />
        <ProbGauge label="Touch −30% drawdown" value={p.prob_drawdown_30} good={false} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 8 }}>
        <div style={box}><div style={boxLbl}>Median CAGR</div><div style={{ ...boxVal, color: p.cagr.p50 >= 0 ? C.green : C.red }}>{p.cagr.p50}%/yr</div></div>
        <div style={box}><div style={boxLbl}>CAGR range (P5–P95)</div><div style={{ ...boxVal, fontSize: 13 }}>{p.cagr.p5}% — {p.cagr.p95}%</div></div>
        <div style={box}><div style={boxLbl}>Value-at-Risk (P5 end)</div><div style={{ ...boxVal, color: C.red }}>{mult(p.var5_ending_multiple)}</div></div>
      </div>

      <div style={{ fontSize: 9, color: C.muted, marginTop: 14, lineHeight: 1.5, background: `${vc}0a`,
        borderLeft: `2px solid ${vc}`, borderRadius: "0 6px 6px 0", padding: "8px 12px" }}>
        <strong style={{ color: vc }}>{p.verdict}.</strong> Over {p.horizon_years} years the median path ends near {mult(p.bands.p50)}
        ({p.cagr.p50}%/yr), with a {pct(p.prob_target)} chance of hitting your +{target}% target and a {pct(p.prob_loss)} chance of
        ending in the red. This verdict feeds the investment decision trigger.
      </div>
    </div>
  )
}

function ProbGauge({ label, value, good }) {
  const v = Math.max(0, Math.min(1, value || 0))
  // for "good" metrics higher=green; for "bad" metrics higher=red
  const col = good ? (v >= 0.6 ? C.green : v >= 0.35 ? C.amber : C.red)
                   : (v <= 0.2 ? C.green : v <= 0.45 ? C.amber : C.red)
  return (
    <div style={box}>
      <div style={boxLbl}>{label}</div>
      <div style={{ ...boxVal, color: col }}>{pct(value)}</div>
      <div style={{ height: 4, background: C.dim, borderRadius: 2, overflow: "hidden", marginTop: 4 }}>
        <div style={{ width: `${v * 100}%`, height: "100%", background: col, borderRadius: 2 }} />
      </div>
    </div>
  )
}

function StockTable({ stocks }) {
  const [open, setOpen] = useState(null)
  const rows = (stocks || []).filter(s => s.sim?.available)
  if (!rows.length) return null
  return (
    <div style={{ background: C.card, border: `1px solid ${C.border2}`, borderRadius: 12, padding: 18 }}>
      <div style={{ fontSize: 9, color: C.muted, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 12 }}>
        Per-stock simulation ({rows.length} names)
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
            {["Ticker", "Median", "P5–P95 range", "Median CAGR", "P(double)", "P(loss)", "P(−30%)"].map(h => (
              <th key={h} style={{ padding: "8px 10px", textAlign: "left", color: C.muted, fontSize: 9, fontWeight: 700, textTransform: "uppercase" }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map((s, i) => {
              const m = s.sim
              return (
                <tr key={s.ticker} style={{ borderBottom: `1px solid ${C.border}`, background: i % 2 ? "transparent" : "rgba(32,32,32,0.022)" }}>
                  <td style={{ padding: "9px 10px", fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: C.cyan }}>{s.ticker}</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: m.bands.p50 >= 1 ? C.green : C.red }}>{mult(m.bands.p50)}</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: C.muted }}>{mult(m.bands.p5)} – {mult(m.bands.p95)}</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: m.cagr.p50 >= 0 ? C.green : C.red }}>{m.cagr.p50}%</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: C.green }}>{pct(m.prob_double)}</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: m.prob_loss > 0.4 ? C.red : C.amber }}>{pct(m.prob_loss)}</td>
                  <td style={{ padding: "9px 10px", fontVariantNumeric: 'tabular-nums', color: m.prob_drawdown_30 > 0.4 ? C.red : C.muted }}>{pct(m.prob_drawdown_30)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Compact per-stock verdict for embedding in candidate detail
export function MonteCarloMini({ sim }) {
  if (!sim?.available) return null
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 10, color: C.muted }}>
      <span>MC median <b style={{ color: sim.bands.p50 >= 1 ? C.green : C.red, fontVariantNumeric: 'tabular-nums' }}>{mult(sim.bands.p50)}</b></span>
      <span>P(double) <b style={{ color: C.green, fontVariantNumeric: 'tabular-nums' }}>{pct(sim.prob_double)}</b></span>
      <span>P(loss) <b style={{ color: C.amber, fontVariantNumeric: 'tabular-nums' }}>{pct(sim.prob_loss)}</b></span>
      <span>P(−30%) <b style={{ color: C.muted, fontVariantNumeric: 'tabular-nums' }}>{pct(sim.prob_drawdown_30)}</b></span>
    </div>
  )
}

const lbl = { fontSize: 9, color: C.slate, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 500, marginBottom: 7 }
const inp = { width: 76, background: C.fog, color: C.text, border: `1px solid ${C.mist}`, borderRadius: 8, padding: "8px 10px", fontSize: 12, fontVariantNumeric: "tabular-nums", outline: "none" }
const box = { background: C.fog, borderRadius: 8, padding: "11px 13px" }
const boxLbl = { fontSize: 9, color: C.slate, letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 500, marginBottom: 5 }
const boxVal = { fontSize: 18, fontWeight: 400, fontFamily: FONT_DISPLAY, letterSpacing: "-0.02em", color: C.text, fontVariantNumeric: "tabular-nums" }
const pill = on => ({ padding: "7px 14px", borderRadius: 200, fontSize: 11, fontWeight: 500, cursor: "pointer",
  background: on ? C.text : "transparent", border: `1px solid ${on ? C.text : C.rule || C.border2}`, color: on ? C.bg : C.muted })
