// DividendsTab.jsx — highest dividend-yielding stocks via yfinance's screener.
// Controls → SSE progress → ranked table → per-row / bulk fundamentals handoff,
// reusing the same /api/score engine the Discovery tab uses.
//
// The ranking is by RAW trailing yield, which puts yield traps at the top by
// construction. The trap column below is the mitigation the table itself can
// offer: a yield far above its own 5-year average usually means the price fell,
// not that the dividend grew.
import { useState, useRef, useEffect } from 'react'
import { C, Chip, SL, TH, TD, safe } from '../../ui.jsx'
import ScoreDetail from '../ScoreDetail.jsx'

const VCOL = { 'STRONG BUY': C.green, BUY: '#5c9670', HOLD: C.amber, WEAK: '#c2703f', AVOID: C.red }
const GCOL = { 'A+': C.green, A: C.green, 'B+': '#5c9670', B: '#5c9670', 'C+': C.amber, C: C.amber, D: '#c2703f', F: C.red }

const fPct = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(2)}%` : '—'
const fRatio = v => v != null && isFinite(Number(v)) ? Number(v).toFixed(2) : '—'
const fCap = v => {
  const n = Number(v)
  if (v == null || !isFinite(n)) return '—'
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
  return `$${n.toFixed(0)}`
}
const fUsd = v => v != null && isFinite(Number(v)) ? `$${Number(v).toFixed(2)}` : '—'

// Ratio of current yield to its own 5-year average. >1.5x is the classic
// signature of a price collapse rather than a dividend increase.
function trapSignal(row) {
  const y = Number(row.dividend_yield), avg = Number(row.five_year_avg_yield)
  const payout = Number(row.payout_ratio)
  if (isFinite(payout) && payout > 1) return { label: 'Payout > 100%', color: C.red, sort: 3 }
  if (isFinite(y) && isFinite(avg) && avg > 0) {
    const r = y / avg
    if (r >= 2) return { label: `${r.toFixed(1)}x 5y avg`, color: C.red, sort: 3 }
    if (r >= 1.5) return { label: `${r.toFixed(1)}x 5y avg`, color: C.amber, sort: 2 }
    return { label: `${r.toFixed(1)}x 5y avg`, color: C.muted, sort: 1 }
  }
  if (isFinite(payout) && payout > 0.7) return { label: `Payout ${(payout * 100).toFixed(0)}%`, color: C.amber, sort: 2 }
  return { label: 'no 5y avg', color: C.muted, sort: 0 }
}

export default function DividendsTab() {
  const [minYield, setMinYield] = useState(4)
  const [minCap, setMinCap] = useState(2)      // $B
  const [limit, setLimit] = useState(50)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [steps, setSteps] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [scores, setScores] = useState({})
  const [scoring, setScoring] = useState({})
  const [expanded, setExpanded] = useState(null)
  const evtRef = useRef(null)

  useEffect(() => () => evtRef.current?.close(), [])

  const runScreen = () => {
    if (loading) return
    setLoading(true); setProgress(0); setSteps([]); setResult(null)
    setError(null); setScores({}); setExpanded(null)
    const qs = new URLSearchParams({
      min_yield: String(minYield),
      min_cap: String(Number(minCap) * 1e9),
      limit: String(limit),
    })
    const es = new EventSource(`/api/dividends/stream?${qs}`)
    evtRef.current = es
    es.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'thinking') { setProgress(msg.progress); setSteps(s => [...s, msg.step]) }
      else if (msg.type === 'done') {
        es.close(); setLoading(false); setProgress(100)
        const r = msg.result || {}
        setResult(r)
        if (r.error) setError(r.error)
      }
    }
    es.onerror = () => { es.close(); setLoading(false); setError('Stream closed before results arrived.') }
  }

  const runFundamentals = async ticker => {
    setScoring(s => ({ ...s, [ticker]: true }))
    try {
      const res = await fetch('/api/score', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: [ticker] }),
      })
      const arr = await res.json()
      setScores(s => ({ ...s, [ticker]: arr[0] })); setExpanded(ticker)
    } catch {
      setScores(s => ({ ...s, [ticker]: { ticker, error: 'request failed' } }))
    } finally { setScoring(s => ({ ...s, [ticker]: false })) }
  }
  const scoreAll = async () => {
    for (const c of (result?.candidates || [])) if (!scores[c.ticker]) await runFundamentals(c.ticker)
  }

  const rows = result?.candidates || []

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 14, lineHeight: 1.7 }}>
        Screens US-listed equities by <strong style={{ color: C.text }}>trailing dividend yield</strong> using
        Yahoo's screener, then hands candidates to the same 5-dimension fundamentals engine as Discovery.
        The yield field is resolved at runtime from the installed yfinance version rather than hardcoded.
      </div>

      {/* The single most important thing on this tab. */}
      <div style={{ background: `${C.amber}0c`, border: `1px solid ${C.amber}35`, borderRadius: 10,
        padding: '11px 14px', marginBottom: 16, fontSize: 10.5, color: C.muted, lineHeight: 1.65 }}>
        <strong style={{ color: C.amber }}>⚠ Ranking by raw yield surfaces yield traps.</strong>{' '}
        Yield is dividend ÷ price, so the fastest route to the top of this list is a collapsing price —
        usually the market pricing in a cut that hasn't been announced. Market-cap and payout filters are
        partial mitigations, not a solution. The <span style={{ color: C.text }}>vs 5y avg</span> column
        flags names yielding far above their own history. Treat this as a research list, never a buy list.
      </div>

      <div style={{ background: C.card, border: `1px solid ${C.border2}`, borderRadius: 12, padding: 18, marginBottom: 14 }}>
        <SL text="Screen criteria" />
        <div style={{ display: 'flex', gap: 22, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Field label="Min yield %" value={minYield} onChange={setMinYield} step="0.5" />
          <Field label="Min market cap ($B)" value={minCap} onChange={setMinCap} step="0.5" />
          <Field label="Max results" value={limit} onChange={setLimit} step="10" />
          <button onClick={runScreen} disabled={loading} style={{
            background: loading ? C.mist : C.text, color: loading ? C.slate : C.bg, border: 'none',
            borderRadius: 9, padding: '9px 20px', fontWeight: 800, fontSize: 12,
            cursor: loading ? 'not-allowed' : 'pointer', fontVariantNumeric: 'tabular-nums' }}>
            {loading ? '💰 Screening…' : '💰 Run Screen'}
          </button>
        </div>
        <div style={{ fontSize: 9, color: C.muted, marginTop: 10 }}>
          Region us · exchanges NMS + NYQ · sorted descending by trailing yield · paginated past Yahoo's 250-row cap.
        </div>
      </div>

      {loading && (
        <div style={{ background: C.card, border: `1px solid ${C.cyan}30`, borderRadius: 12, padding: 18, marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: C.cyan, fontWeight: 700 }}>Screening…</span>
            <span style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums', color: C.cyan }}>{progress}%</span>
          </div>
          <div style={{ height: 4, background: C.dim, borderRadius: 2, overflow: 'hidden', marginBottom: 14 }}>
            <div style={{ width: `${progress}%`, height: '100%', background: C.cyan, borderRadius: 2, transition: 'width 0.4s' }} />
          </div>
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
              background: `${C.cyan}0a`, borderRadius: 8, padding: '8px 14px' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: C.cyan, flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: C.text }}>{s}</span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div style={{ background: `${C.red}0d`, border: `1px solid ${C.red}35`, borderRadius: 10,
          padding: '12px 15px', marginBottom: 14, fontSize: 11, color: C.red, lineHeight: 1.6 }}>
          ⚠ {error}
        </div>
      )}

      {result && rows.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            margin: '4px 0 12px', flexWrap: 'wrap', gap: 10 }}>
            <div style={{ fontSize: 12, color: C.text, fontWeight: 700 }}>
              {rows.length} candidates
              {result.yield_field && (
                <span style={{ fontSize: 9.5, color: C.muted, marginLeft: 8, fontWeight: 400 }}>
                  · yield field resolved to <code>{result.yield_field}</code>
                </span>
              )}
              {result.payout_field_available === false && (
                <span style={{ fontSize: 9.5, color: C.amber, marginLeft: 8, fontWeight: 400 }}>
                  · no payout field in this yfinance version
                </span>
              )}
            </div>
            <button onClick={scoreAll} style={{ background: 'transparent', color: C.cyan,
              border: `1px solid ${C.cyan}`, borderRadius: 7, padding: '6px 14px', fontSize: 10,
              fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }}>
              Run fundamentals on all
            </button>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
                <TH>Ticker</TH><TH>Name</TH><TH>Sector</TH><TH>Price</TH><TH>Yield</TH>
                <TH>Div/Share</TH><TH>5y Avg</TH><TH>vs 5y avg</TH><TH>Payout</TH><TH>Mkt Cap</TH>
                <TH>Fundamentals</TH><TH />
              </tr></thead>
              <tbody>
                {rows.map((c, i) => {
                  const sc = scores[c.ticker]
                  const isOpen = expanded === c.ticker
                  const bad = sc && (sc.error || sc.composite_score == null)
                  const trap = trapSignal(c)
                  return [
                    <tr key={c.ticker} style={{
                      borderBottom: `1px solid ${isOpen ? C.cyan + '28' : C.border}`,
                      background: isOpen ? `${C.cyan}06` : i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent' }}>
                      <TD style={{ fontWeight: 800, color: C.cyan, fontSize: 12 }}>{c.ticker}</TD>
                      <TD style={{ color: C.text, maxWidth: 190, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name || '—'}</TD>
                      {/* Yahoo's screener rows often omit sector/industry; the
                          fundamentals result carries both, so scoring a row
                          back-fills this cell with no extra requests. */}
                      <TD style={{ color: C.muted, fontSize: 10 }}>
                        {(c.sector || sc?.sector) || '—'}
                        {(c.industry || sc?.industry) &&
                          <div style={{ fontSize: 8.5, color: C.slate, marginTop: 1 }}>{c.industry || sc?.industry}</div>}
                      </TD>
                      <TD style={{ color: C.text }}>{fUsd(c.price)}</TD>
                      <TD style={{ fontWeight: 800, color: C.green }}>{fPct(c.dividend_yield)}</TD>
                      <TD style={{ color: C.text }}>{fUsd(c.dividend_rate)}<span style={{ color: C.muted, fontSize: 8.5 }}>/yr</span></TD>
                      <TD style={{ color: C.muted }}>{fPct(c.five_year_avg_yield)}</TD>
                      <TD><Chip label={trap.label} color={trap.color} /></TD>
                      <TD style={{ color: safe(c.payout_ratio) > 0.7 ? C.amber : C.muted }}>{fRatio(c.payout_ratio)}</TD>
                      <TD style={{ color: C.text }}>{fCap(c.market_cap)}</TD>
                      <TD>
                        {!sc ? <span style={{ color: C.muted, fontSize: 10 }}>—</span>
                          : bad ? <Chip label={sc.insufficient_data ? 'Insufficient data' : 'No data'} color={C.amber} />
                          : <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums', fontWeight: 700,
                                color: GCOL[sc.composite_grade] || C.muted }}>{sc.composite_score}/100 {sc.composite_grade}</span>
                              <Chip label={sc.verdict} color={VCOL[sc.verdict] || C.muted} />
                            </div>}
                      </TD>
                      <TD>
                        {!sc
                          ? <button onClick={() => runFundamentals(c.ticker)} disabled={scoring[c.ticker]}
                              style={btn(C.cyan, scoring[c.ticker] ? 'wait' : 'pointer')}>
                              {scoring[c.ticker] ? 'Scoring…' : 'Run fundamentals'}</button>
                          : !bad
                            ? <button onClick={() => setExpanded(isOpen ? null : c.ticker)} style={btn(C.muted, 'pointer')}>
                                {isOpen ? 'Hide' : 'Details'}</button>
                            : null}
                      </TD>
                    </tr>,
                    isOpen && sc && !bad ? (
                      <tr key={c.ticker + '-d'}>
                        <td colSpan={12} style={{ padding: '0 16px 18px', background: `${C.cyan}04`, borderBottom: `1px solid ${C.border}` }}>
                          <ScoreDetail sc={sc} />
                        </td>
                      </tr>
                    ) : null,
                  ]
                })}
              </tbody>
            </table>
          </div>

          {result.note && (
            <div style={{ fontSize: 9.5, color: C.muted, marginTop: 12, lineHeight: 1.6 }}>{result.note}</div>
          )}
        </>
      )}

      {result && rows.length === 0 && !loading && !error && (
        <div style={{ color: C.muted, textAlign: 'center', padding: 30 }}>
          No stocks matched. Try lowering the minimum yield or market cap.
        </div>
      )}
    </div>
  )
}

function Field({ label, value, onChange, step }) {
  return (
    <div>
      <div style={{ fontSize: 9, color: C.slate, textTransform: 'uppercase', letterSpacing: '0.08em',
        fontWeight: 500, marginBottom: 7 }}>{label}</div>
      <input type="number" step={step} value={value} onChange={e => onChange(e.target.value)}
        style={{ width: 96, background: C.fog, color: C.text, border: `1px solid ${C.mist}`,
          borderRadius: 8, padding: '8px 10px', fontSize: 12, fontVariantNumeric: 'tabular-nums', outline: 'none' }} />
    </div>
  )
}

function btn(color, cursor) {
  return { background: 'transparent', color, border: `1px solid ${color}55`, borderRadius: 6,
    padding: '4px 10px', fontSize: 9, fontWeight: 700, cursor, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
}
