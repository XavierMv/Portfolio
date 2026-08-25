// FundamentalsTab.jsx — 5-dimension fundamental scoring for held holdings.
// Streams /api/fundamentals/stream/{run_id}; MBox summary, TH/TD table,
// expandable radar + metric grid + per-dimension signal breakdown.
import { useState, useRef, useEffect, useCallback } from 'react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { C, Chip, SL, Card, MBox, TH, TD, safe, tc } from '../../ui.jsx'
import ValuationCard from '../ValuationCard.jsx'

const VCOL = { 'STRONG BUY': C.green, BUY: '#5c9670', HOLD: C.amber, WEAK: '#c2703f', AVOID: C.red }
const GCOL = { 'A+': C.green, A: C.green, 'B+': '#5c9670', B: '#5c9670', 'C+': C.amber, C: C.amber, D: '#c2703f', F: C.red }
const fX = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}x` : '—'
const fP = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}%` : '—'
const fR = v => v != null && isFinite(Number(v)) ? Number(v).toFixed(2) : '—'
const sCol = s => s >= 55 ? C.green : s >= 35 ? C.amber : C.red

export default function FundamentalsTab({ data, onScores }) {
  const runId = data?.run_id
  const [scores, setScores]   = useState({})
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [expanded, setExpanded] = useState(null)
  const [sort, setSort] = useState({ k: 'composite_score', dir: -1 })
  const evtRef = useRef(null)

  const held = (data?.stocks || []).filter(s => !s.error)

  // Sort can target the composite OR any dimension score (nested under sc[dim].score)
  const DIM_KEYS = { valuation: 1, profitability: 1, health: 1, growth: 1, quality: 1 }
  const scoreOf = (sc, k) => {
    if (!sc) return 0
    if (k in DIM_KEYS) return safe((sc[k] || {}).score)
    return safe(sc[k])
  }
  const SORT_BTNS = [['composite_score', 'Overall'], ['profitability', 'Profitability'],
    ['valuation', 'Valuation'], ['growth', 'Growth'], ['health', 'Health'], ['quality', 'Quality']]
  const DIM_LABEL = { valuation: 'Valuation', profitability: 'Profitability', health: 'Health', growth: 'Growth', quality: 'Quality' }

  const runScoring = useCallback(() => {
    if (!runId || loading) return
    setLoading(true); setProgress(0); setExpanded(null); setScores({})
    // Accumulate locally too — setScores is async, so the `done` handler can't
    // read the finished map off state to hand back to App.
    const acc = {}
    const es = new EventSource(`/api/fundamentals/stream/${runId}`)
    evtRef.current = es
    es.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'result') {
        acc[msg.ticker] = msg.data
        setProgress(msg.progress); setScores(prev => ({ ...prev, [msg.ticker]: msg.data }))
      } else if (msg.type === 'done') {
        es.close(); setLoading(false); setProgress(100)
        // Feed the scores back so Combinations and Timeline can re-rank.
        onScores?.(acc)
      }
    }
    es.onerror = () => { es.close(); setLoading(false) }
  }, [runId, loading, onScores])

  useEffect(() => () => evtRef.current?.close(), [])
  useEffect(() => { if (runId && Object.keys(scores).length === 0 && !loading) runScoring() }, [runId])

  const rows = held.map(s => ({ ticker: s.ticker, theme: s.theme, sc: scores[s.ticker] }))
  const ok = r => r.sc && !r.sc.error && r.sc.composite_score != null
  const scored = rows.filter(ok)
  const sortBy = k => setSort(s => ({ k, dir: s.k === k ? -s.dir : -1 }))
  const sorted = [...rows].sort((a, b) => sort.dir * (scoreOf(b.sc, sort.k) - scoreOf(a.sc, sort.k)))
  const activeDim = sort.k in DIM_KEYS ? sort.k : null  // shows that dimension's grade as a column

  const avg = k => scored.length ? scored.reduce((a, r) => a + safe(r.sc[k]), 0) / scored.length : null
  const verdicts = scored.reduce((m, r) => { m[r.sc.verdict] = (m[r.sc.verdict] || 0) + 1; return m }, {})
  const buys = (verdicts['STRONG BUY'] || 0) + (verdicts.BUY || 0)
  const failed = rows.filter(r => r.sc && r.sc.error).length
  const thin   = rows.filter(r => r.sc && r.sc.insufficient_data).length
  const avgComp = avg('composite_score')
  const summary = [
    ['Scored', `${scored.length}/${held.length}`, C.cyan,
      thin || failed ? [thin && `${thin} insufficient`, failed && `${failed} failed`].filter(Boolean).join(' · ') : 'all covered'],
    ['Avg Composite', avgComp != null ? avgComp.toFixed(1) : '—', avgComp != null ? sCol(avgComp) : C.muted, '0–100'],
    ['Buy / Strong Buy', String(buys), buys ? C.green : C.muted, 'verdict count'],
    ['Avg ROIC', fP(avg('roic')), C.text, 'vs ~10% WACC'],
    ['Avg Rev Grw', fP(avg('revenue_growth_yoy')), C.text, 'YoY'],
    ['Avg FCF Yield', fP(avg('fcf_yield')), C.text, 'cash / mkt cap'],
  ]

  const COLS = [['composite_score', 'Score'], ['verdict', 'Verdict'], ['pe_trailing', 'P/E'],
    ['roic', 'ROIC'], ['fcf_yield', 'FCF Yld'], ['revenue_growth_yoy', 'Rev Grw'], ['earnings_growth_yoy', 'Earn Grw']]

  if (!data) return <div style={{ color: C.muted, textAlign: 'center', padding: 60 }}>Run an analysis first.</div>

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 16, lineHeight: 1.7 }}>
        Full <strong style={{ color: C.text }}>5-dimension fundamental scoring</strong> for your holdings —
        valuation, profitability, health, growth, quality → composite, grade, verdict. Click a row for the radar,
        metric grid, and per-signal breakdown.
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: C.text, fontWeight: 700, marginRight: 4 }}>Sort:</span>
        {SORT_BTNS.map(([k, l]) => (
          <button key={k} onClick={() => sortBy(k)} style={{ padding: '4px 11px', borderRadius: 6, fontSize: 10,
            fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums',
            background: sort.k === k ? `${C.cyan}18` : 'transparent',
            border: `1px solid ${sort.k === k ? C.cyan : C.border2}`,
            color: sort.k === k ? C.cyan : C.muted }}>
            {l}{sort.k === k ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10, marginBottom: 16 }}>
        {summary.map(([l, v, c, sub]) => <MBox key={l} label={l} value={v} color={c} sub={sub} />)}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        {loading && <span style={{ fontSize: 10, color: C.cyan, fontVariantNumeric: 'tabular-nums' }}>Scoring… {progress}%</span>}
        <button onClick={runScoring} disabled={loading || !runId} style={{ background: loading ? C.dim : 'transparent',
          color: C.cyan, border: `1px solid ${C.cyan}`, borderRadius: 7, padding: '6px 14px', fontSize: 10,
          fontWeight: 700, cursor: loading ? 'wait' : 'pointer', fontVariantNumeric: 'tabular-nums' }}>
          {loading ? 'Working…' : '↻ Re-score holdings'}
        </button>
      </div>
      {loading && <div style={{ height: 4, background: C.dim, borderRadius: 2, overflow: 'hidden', marginBottom: 16 }}>
        <div style={{ width: `${progress}%`, height: '100%', background: C.cyan, borderRadius: 2, transition: 'width 0.3s' }} /></div>}

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
              <TH>Ticker</TH><TH>Theme</TH>
              {COLS.map(([k, l]) => <TH key={k} onClick={() => sortBy(k)} active={sort.k === k}>{l}{sort.k === k ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}</TH>)}
              {activeDim && <TH active>{DIM_LABEL[activeDim]} Grade</TH>}
              <TH /></tr></thead>
            <tbody>
              {sorted.map((r, i) => {
                const sc = r.sc, isOpen = expanded === r.ticker, bad = sc && (sc.error || sc.composite_score == null)
                return [
                  <tr key={r.ticker} style={{ borderBottom: `1px solid ${isOpen ? C.cyan + '28' : C.border}`,
                    background: isOpen ? `${C.cyan}06` : i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent' }}>
                    <TD style={{ fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(r.theme), fontSize: 12 }}>{r.ticker}</TD>
                    <TD><Chip label={r.theme} color={tc(r.theme)} /></TD>
                    {!sc ? <TD style={{ color: C.muted, fontSize: 10 }}>{loading ? 'queued…' : '—'}</TD>
                      : bad ? <td colSpan={COLS.length + (activeDim ? 1 : 0)} style={{ padding: '9px 10px' }}>
                          <Chip label={sc.insufficient_data ? 'Insufficient data' : 'No data'} color={C.amber} />
                          <span style={{ fontSize: 9, color: C.muted, marginLeft: 8 }}>
                            {sc.insufficient_data
                              ? `${sc.coverage}/${sc.coverage_total} key fields — not scored rather than scored on partials`
                              : (sc.error || 'thin yfinance coverage')}
                          </span></td>
                      : <>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 800, color: GCOL[sc.composite_grade] || C.muted }}>{sc.composite_score} {sc.composite_grade}</TD>
                          <TD><Chip label={sc.verdict} color={VCOL[sc.verdict] || C.muted} /></TD>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{fX(sc.pe_trailing)}</TD>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{fP(sc.roic)}</TD>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{fP(sc.fcf_yield)}</TD>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{fP(sc.revenue_growth_yoy)}</TD>
                          <TD style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{fP(sc.earnings_growth_yoy)}</TD>
                          {activeDim && <TD style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 800, color: GCOL[(sc[activeDim] || {}).grade] || C.muted }}>{safe((sc[activeDim] || {}).score)} {(sc[activeDim] || {}).grade || ''}</TD>}
                        </>}
                    <TD>{sc && !bad && <button onClick={() => setExpanded(isOpen ? null : r.ticker)} style={{ background: 'transparent', color: C.muted, border: `1px solid ${C.border2}`, borderRadius: 6, padding: '4px 10px', fontSize: 9, fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }}>{isOpen ? 'Hide' : 'Details'}</button>}</TD>
                  </tr>,
                  isOpen && sc && !bad ? (
                    <tr key={r.ticker + '-d'}><td colSpan={COLS.length + 3 + (activeDim ? 1 : 0)} style={{ padding: '0 16px 18px', background: `${C.cyan}04`, borderBottom: `1px solid ${C.border}` }}>
                      <FundDetail sc={sc} />
                    </td></tr>
                  ) : null
                ]
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function FundDetail({ sc }) {
  const dims = [sc.valuation, sc.profitability, sc.health, sc.growth, sc.quality].filter(Boolean)
  const radar = dims.map(d => ({ dim: d.dimension.split(' ')[0], score: safe(d.score) }))
  const metrics = [
    ['P/E', fX(sc.pe_trailing)], ['Fwd P/E', fX(sc.pe_forward)], ['EV/EBITDA', fX(sc.ev_ebitda)], ['P/B', fX(sc.pb)],
    ['PEG', fR(sc.peg)], ['Gross Mgn', fP(sc.gross_margin)], ['Op Mgn', fP(sc.operating_margin)], ['Net Mgn', fP(sc.net_margin)],
    ['ROE', fP(sc.roe)], ['ROIC', fP(sc.roic)], ['FCF Yield', fP(sc.fcf_yield)], ['Div Yield', fP(sc.dividend_yield)],
    ['Rev Grw', fP(sc.revenue_growth_yoy)], ['Earn Grw', fP(sc.earnings_growth_yoy)], ['Rev CAGR 3Y', fP(sc.revenue_cagr_3y)], ['Analyst', fP(sc.analyst_upside)],
    ['D/E', fR(sc.debt_to_equity)], ['Current', fR(sc.current_ratio)], ['Int Cov', fX(sc.interest_coverage)], ['Price', sc.current_price != null ? `$${sc.current_price}` : '—'],
  ]
  return (
    <div style={{ paddingTop: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 16 }}>
        <div>
          <SL text="Fundamental Radar" />
          <ResponsiveContainer width="100%" height={160}>
            <RadarChart data={radar}>
              <PolarGrid stroke={C.border2} />
              <PolarAngleAxis dataKey="dim" tick={{ fill: C.muted, fontSize: 9 }} />
              <Radar dataKey="score" stroke={C.cyan} fill={C.cyan} fillOpacity={0.12} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <SL text="Key Metrics" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
            {metrics.map(([l, v]) => (
              <div key={l} style={{ background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 8, padding: '7px 9px' }}>
                <div style={{ fontSize: 8, color: C.muted, textTransform: 'uppercase', marginBottom: 2 }}>{l}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: v === '—' ? C.muted : C.text, fontVariantNumeric: 'tabular-nums' }}>{v}</div>
              </div>
            ))}
          </div>
          {sc.dcf && (
            <div style={{ marginTop: 12, background: `${C.green}0a`, border: `1px solid ${C.green}25`, borderRadius: 8, padding: '10px 14px' }}>
              <span style={{ fontSize: 10, color: C.muted }}>DCF Fair Value </span>
              <span style={{ fontSize: 12, fontWeight: 800, color: sc.dcf.margin_of_safety > 0 ? C.green : C.red, fontVariantNumeric: 'tabular-nums' }}>
                ${sc.dcf.fair_value} ({sc.dcf.margin_of_safety > 0 ? '+' : ''}{sc.dcf.margin_of_safety}% vs price) — {sc.dcf.upside_downside}
              </span>
            </div>
          )}
          {sc.valuation_analysis && (
            <div style={{ marginTop: 12 }}>
              <ValuationCard val={sc.valuation_analysis} />
            </div>
          )}
        </div>
      </div>
      <div style={{ marginTop: 18 }}>
        <SL text="Score Breakdown by Dimension" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12, marginTop: 8 }}>
          {dims.map(d => (
            <div key={d.dimension} style={{ background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 10, padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 10, fontWeight: 800, color: C.text }}>{d.dimension}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: sCol(d.score) }}>{d.score}/100</span>
                  {d.grade && <Chip label={d.grade} color={GCOL[d.grade] || C.muted} />}
                </span>
              </div>
              {(d.signals || []).map((sig, si) => (
                <div key={si} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, marginBottom: 2 }}>
                    <span style={{ color: C.muted }}>{sig.flag} {sig.label}</span>
                    <span style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{sig.value}</span>
                  </div>
                  <div style={{ height: 3, background: C.bg, borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ width: `${Math.max(0, Math.min(100, safe(sig.score)))}%`, height: '100%', background: sCol(safe(sig.score)), borderRadius: 2 }} />
                  </div>
                  {sig.interpretation && <div style={{ fontSize: 8.5, color: C.muted, marginTop: 2 }}>{sig.interpretation}</div>}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
