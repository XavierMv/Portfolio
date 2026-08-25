// DiscoveryTab.jsx — Scout/Discovery agent UI
// theme picker → SSE thinking animation → candidate table → fundamentals handoff
import { useState, useRef, useEffect } from 'react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { C, Chip, SL, safe, tc } from '../../ui.jsx'
import ValuationCard from '../ValuationCard.jsx'

const BUILTIN_THEMES = ['AI', 'Nuclear', 'Space', 'LNG', 'Quantum', 'Robotics', 'AR']
const STORAGE_KEY = 'pad_custom_themes_v1'
const PALETTE = [C.cyan, C.green, C.amber, C.purple, C.pink, C.blue, '#ff682c', '#5c9670', '#b3402f', '#3d7a4f']

function loadCustomThemes() {
  try { const raw = localStorage.getItem(STORAGE_KEY); if (!raw) return []
    const arr = JSON.parse(raw); return Array.isArray(arr) ? arr.filter(t => t && t.name) : [] } catch { return [] }
}
function saveCustomThemes(arr) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(arr)) } catch {} }

const MODEL_COLORS = { 'royalty/platform': C.purple, 'pure-play': C.cyan, 'supply-chain': C.green, diversified: C.amber }
const VCOL = { 'STRONG BUY': C.green, BUY: '#5c9670', HOLD: C.amber, WEAK: '#c2703f', AVOID: C.red }
const GCOL = { 'A+': C.green, A: C.green, 'B+': '#5c9670', B: '#5c9670', 'C+': C.amber, C: C.amber, D: '#c2703f', F: C.red }
const fX = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}x` : '—'
const fP = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}%` : '—'
const sCol = s => s >= 55 ? C.green : s >= 35 ? C.amber : C.red

export default function DiscoveryTab({ data }) {
  const [theme, setTheme] = useState('Nuclear')
  const [freeText, setFreeText] = useState('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [steps, setSteps] = useState([])
  const [result, setResult] = useState(null)
  const [live, setLive] = useState(null)
  const [scores, setScores] = useState({})
  const [scoring, setScoring] = useState({})
  const [expanded, setExpanded] = useState(null)
  const [customThemes, setCustomThemes] = useState(loadCustomThemes)
  const [managing, setManaging] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [draftColor, setDraftColor] = useState(PALETTE[0])
  const [editingIdx, setEditingIdx] = useState(null)
  const evtRef = useRef(null)

  const allThemes = [...BUILTIN_THEMES, ...customThemes.map(t => t.name)]
  const themeColor = name => { const c = customThemes.find(t => t.name === name); return c ? c.color : tc(name) }
  useEffect(() => { saveCustomThemes(customThemes) }, [customThemes])

  const addTheme = () => {
    const name = draftName.trim(); if (!name) return
    if (allThemes.some(t => t.toLowerCase() === name.toLowerCase())) { setDraftName(''); return }
    setCustomThemes(arr => [...arr, { name, color: draftColor }]); setDraftName(''); setDraftColor(PALETTE[0])
  }
  const deleteTheme = idx => { const removed = customThemes[idx]?.name
    setCustomThemes(arr => arr.filter((_, i) => i !== idx)); if (theme === removed) setTheme('Nuclear'); if (editingIdx === idx) setEditingIdx(null) }
  const saveEdit = (idx, name, color) => { const nm = name.trim(); if (!nm) return
    setCustomThemes(arr => arr.map((t, i) => i === idx ? { name: nm, color } : t)); setEditingIdx(null) }

  const ownedInTheme = (data?.stocks || []).filter(s => !s.error && s.theme === theme).map(s => s.ticker)
  const activeTheme = freeText.trim() || theme

  const runScout = () => {
    if (loading) return
    setLoading(true); setProgress(0); setSteps([]); setResult(null); setScores({}); setExpanded(null)
    const owned = encodeURIComponent(ownedInTheme.join(','))
    const q = encodeURIComponent(activeTheme)
    const es = new EventSource(`/api/scout/stream?theme=${q}&owned=${owned}`)
    evtRef.current = es
    es.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'thinking') { setProgress(msg.progress); setSteps(s => [...s, msg.step]) }
      else if (msg.type === 'done') { es.close(); setLoading(false); setProgress(100)
        setResult(msg.result?.report || null); setLive(msg.result?.live ?? null) }
    }
    es.onerror = () => { es.close(); setLoading(false) }
  }
  useEffect(() => () => evtRef.current?.close(), [])

  const runFundamentals = async ticker => {
    setScoring(s => ({ ...s, [ticker]: true }))
    try {
      const res = await fetch('/api/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tickers: [ticker] }) })
      const arr = await res.json()
      setScores(s => ({ ...s, [ticker]: arr[0] })); setExpanded(ticker)
    } catch { setScores(s => ({ ...s, [ticker]: { ticker, error: 'request failed' } })) }
    finally { setScoring(s => ({ ...s, [ticker]: false })) }
  }
  const scoreAll = async () => { for (const c of (result?.candidates || [])) if (!scores[c.ticker]) await runFundamentals(c.ticker) }

  const candidates = result?.candidates || []

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 16, lineHeight: 1.7 }}>
        The <span style={{ color: C.pink, fontWeight: 700 }}>🔭 Scout agent</span> discovers <em>net-new</em> tickers
        in a theme — peers, challengers, and supply-chain / picks-and-shovels names beyond what you own. It applies
        your hard filters (no Taiwan/OTC/China/crypto; prefer NASDAQ/NYSE/TSX; EWY for Korea) and flags uncertain
        Wealthsimple availability. Discovered names hand off to the same fundamentals scoring as your holdings.
        <span> Web-search powered (API key for live results; static seeds otherwise).</span>
      </div>

      <div style={{ background: C.card, border: `1px solid ${C.border2}`, borderRadius: 12, padding: 18, marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <SL text="Pick a theme to screen" />
          <button onClick={() => setManaging(m => !m)} style={{ background: 'transparent', color: managing ? C.pink : C.muted,
            border: `1px solid ${managing ? C.pink : C.border2}`, borderRadius: 6, padding: '3px 10px', fontSize: 9,
            fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums', marginBottom: 10 }}>{managing ? '✓ Done' : '⚙ Manage themes'}</button>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {allThemes.map(t => { const col = themeColor(t)
            return <button key={t} onClick={() => { setTheme(t); setFreeText('') }} style={{ padding: '6px 14px',
              borderRadius: 7, fontSize: 11, fontWeight: 700, cursor: 'pointer',
              background: (!freeText && theme === t) ? `${col}18` : 'transparent',
              border: `1px solid ${(!freeText && theme === t) ? col : C.border2}`,
              color: (!freeText && theme === t) ? col : C.muted }}>{t}</button> })}
        </div>

        {managing && (
          <div style={{ background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 10, padding: 14, marginBottom: 12 }}>
            <div style={{ fontSize: 9, color: C.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>
              Custom themes <span>· saved in this browser</span></div>
            {customThemes.length === 0 && <div style={{ fontSize: 10, color: C.muted, marginBottom: 12 }}>No custom themes yet. Add one below.</div>}
            {customThemes.map((t, idx) => (
              <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                {editingIdx === idx ? <EditRow theme={t} palette={PALETTE} onSave={(n, c) => saveEdit(idx, n, c)} onCancel={() => setEditingIdx(null)} />
                  : <>
                      <span style={{ width: 12, height: 12, borderRadius: 3, background: t.color, flexShrink: 0 }} />
                      <span style={{ fontSize: 11, color: C.text, fontWeight: 700, flex: 1 }}>{t.name}</span>
                      <button onClick={() => setEditingIdx(idx)} style={miniBtn(C.cyan)}>Rename / recolor</button>
                      <button onClick={() => deleteTheme(idx)} style={miniBtn(C.red)}>Delete</button>
                    </>}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border2}` }}>
              <input value={draftName} onChange={e => setDraftName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') addTheme() }}
                placeholder="New theme, e.g. Defense / Drones" style={{ flex: 1, background: C.bg, color: C.text,
                border: `1px solid ${C.border2}`, borderRadius: 6, padding: '7px 10px', fontSize: 11, fontVariantNumeric: 'tabular-nums', outline: 'none' }} />
              <div style={{ display: 'flex', gap: 4 }}>
                {PALETTE.map(col => <button key={col} onClick={() => setDraftColor(col)} title={col} style={{ width: 18, height: 18,
                  borderRadius: 4, background: col, cursor: 'pointer', border: `2px solid ${draftColor === col ? C.text : 'transparent'}`, outline: `1px solid ${C.mist}` }} />)}
              </div>
              <button onClick={addTheme} style={{ background: C.text, color: C.bg, border: 'none', borderRadius: 0,
                padding: '7px 14px', fontSize: 10, fontWeight: 800, cursor: 'pointer', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>+ Add</button>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: C.muted }}>or free-text sub-theme:</span>
          <input value={freeText} onChange={e => setFreeText(e.target.value)} placeholder='e.g. "AI memory / HBM supply chain"'
            style={{ flex: 1, background: C.dim, color: C.text, border: `1px solid ${C.border2}`, borderRadius: 6, padding: '7px 10px', fontSize: 11, fontVariantNumeric: 'tabular-nums', outline: 'none' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, flexWrap: 'wrap', gap: 10 }}>
          <div style={{ fontSize: 10, color: C.muted }}>
            Screening: <span style={{ color: themeColor(theme), fontWeight: 700 }}>{activeTheme}</span>
            {ownedInTheme.length > 0 && <span> · excluding {ownedInTheme.length} owned: {ownedInTheme.join(', ')}</span>}
          </div>
          <button onClick={runScout} disabled={loading} style={{ background: loading ? C.mist : C.text, color: loading ? C.slate : C.bg,
            border: 'none', borderRadius: 9, padding: '9px 20px', fontWeight: 800, fontSize: 12,
            cursor: loading ? 'not-allowed' : 'pointer', fontVariantNumeric: 'tabular-nums' }}>{loading ? '🔭 Scouting…' : '🔭 Discover Candidates'}</button>
        </div>
      </div>

      {loading && (
        <div style={{ background: C.card, border: `1px solid ${C.pink}30`, borderRadius: 12, padding: 18, marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: C.pink, fontWeight: 700 }}>Scout agent working…</span>
            <span style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums', color: C.pink }}>{progress}%</span>
          </div>
          <div style={{ height: 4, background: C.dim, borderRadius: 2, overflow: 'hidden', marginBottom: 14 }}>
            <div style={{ width: `${progress}%`, height: '100%', background: C.pink, borderRadius: 2, transition: 'width 0.4s' }} />
          </div>
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, background: `${C.pink}0a`, borderRadius: 8, padding: '8px 14px' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: C.pink, flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: C.text }}>{s}</span>
            </div>
          ))}
        </div>
      )}

      {result && candidates.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '4px 0 12px', flexWrap: 'wrap', gap: 10 }}>
            <div style={{ fontSize: 12, color: C.text, fontWeight: 700 }}>
              {candidates.length} candidates discovered
              {live === false && <span style={{ fontSize: 10, color: C.amber, marginLeft: 8 }}>· static seeds (add API key for live search)</span>}
              {live === true && <span style={{ fontSize: 10, color: C.green, marginLeft: 8 }}>· live web search</span>}
            </div>
            <button onClick={scoreAll} style={{ background: 'transparent', color: C.cyan, border: `1px solid ${C.cyan}`,
              borderRadius: 7, padding: '6px 14px', fontSize: 10, fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }}>Run fundamentals on all</button>
          </div>

          {result.note && (
            <div style={{ fontSize: 10, color: C.amber, marginBottom: 12, background: `${C.amber}0c`, borderRadius: 8, padding: '8px 12px', borderLeft: `2px solid ${C.amber}` }}>{result.note}</div>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead><tr style={{ borderBottom: `1px solid ${C.border2}` }}>
                {['Ticker', 'Name', 'Exchange', 'Model Type', 'Thesis', 'Fundamentals', ''].map(h =>
                  <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: C.muted, fontSize: 9, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase' }}>{h}</th>)}
              </tr></thead>
              <tbody>
                {candidates.map((c, i) => {
                  const sc = scores[c.ticker]; const isOpen = expanded === c.ticker; const mc = MODEL_COLORS[c.model_type] || C.muted
                  const bad = sc && (sc.error || sc.composite_score == null)
                  return [
                    <tr key={c.ticker} style={{ borderBottom: `1px solid ${isOpen ? C.cyan + '28' : C.border}`, background: isOpen ? `${C.cyan}06` : i % 2 === 0 ? 'rgba(32,32,32,0.022)' : 'transparent' }}>
                      <td style={{ padding: '10px', fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: tc(c.theme), fontSize: 12 }}>
                        {c.ticker}{c.wealthsimple_uncertain && <span title="Wealthsimple availability uncertain" style={{ marginLeft: 5, fontSize: 9, color: C.amber }}>⚠</span>}</td>
                      <td style={{ padding: '10px', color: C.text }}>{c.name}</td>
                      <td style={{ padding: '10px' }}><Chip label={c.exchange || '—'} color={c.exchange ? C.muted : C.amber} /></td>
                      <td style={{ padding: '10px' }}><Chip label={c.model_type} color={mc} /></td>
                      <td style={{ padding: '10px', color: C.muted, fontSize: 10, maxWidth: 260 }}>{c.one_line_thesis}</td>
                      <td style={{ padding: '10px' }}>
                        {!sc ? <span style={{ color: C.muted, fontSize: 10 }}>—</span>
                          : bad ? <Chip label="No data" color={C.amber} />
                          : <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ fontSize: 10, fontVariantNumeric: 'tabular-nums', color: GCOL[sc.composite_grade] || C.muted, fontWeight: 700 }}>{sc.composite_score}/100 {sc.composite_grade}</span>
                              <Chip label={sc.verdict} color={VCOL[sc.verdict] || C.muted} />
                            </div>}
                      </td>
                      <td style={{ padding: '10px' }}>
                        {!sc ? <button onClick={() => runFundamentals(c.ticker)} disabled={scoring[c.ticker]} style={{ background: 'transparent', color: C.cyan, border: `1px solid ${C.cyan}55`, borderRadius: 6, padding: '4px 10px', fontSize: 9, fontWeight: 700, cursor: scoring[c.ticker] ? 'wait' : 'pointer', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{scoring[c.ticker] ? 'Scoring…' : 'Run fundamentals'}</button>
                          : !bad ? <button onClick={() => setExpanded(isOpen ? null : c.ticker)} style={{ background: 'transparent', color: C.muted, border: `1px solid ${C.border2}`, borderRadius: 6, padding: '4px 10px', fontSize: 9, fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums' }}>{isOpen ? 'Hide' : 'Details'}</button>
                          : null}
                      </td>
                    </tr>,
                    isOpen && sc && !bad ? (
                      <tr key={c.ticker + '-d'}><td colSpan={7} style={{ padding: '0 16px 18px', background: `${C.cyan}04`, borderBottom: `1px solid ${C.border}` }}><CandidateDetail sc={sc} /></td></tr>
                    ) : null
                  ]
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {result && candidates.length === 0 && !loading && (
        <div style={{ color: C.muted, textAlign: 'center', padding: 30 }}>No candidates returned. Try a different theme or free-text sub-theme.</div>
      )}
    </div>
  )
}

function CandidateDetail({ sc }) {
  const dims = [sc.valuation, sc.profitability, sc.health, sc.growth, sc.quality].filter(Boolean)
  const radar = dims.map(d => ({ dim: d.dimension.split(' ')[0], score: safe(d.score) }))
  const metrics = [['P/E', fX(sc.pe_trailing)], ['EV/EBITDA', fX(sc.ev_ebitda)], ['Gross Mgn', fP(sc.gross_margin)],
    ['Op Mgn', fP(sc.operating_margin)], ['ROE', fP(sc.roe)], ['ROIC', fP(sc.roic)], ['Rev Grw', fP(sc.revenue_growth_yoy)], ['FCF Yield', fP(sc.fcf_yield)]]
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
              <div key={l} style={{ background: C.dim, border: `1px solid ${C.border2}`, borderRadius: 8, padding: '8px 10px' }}>
                <div style={{ fontSize: 8, color: C.muted, textTransform: 'uppercase', marginBottom: 2 }}>{l}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: v === '—' ? C.muted : C.text, fontVariantNumeric: 'tabular-nums' }}>{v}</div>
              </div>
            ))}
          </div>
          {sc.dcf && (
            <div style={{ marginTop: 12, background: `${C.green}0a`, border: `1px solid ${C.green}25`, borderRadius: 8, padding: '10px 14px' }}>
              <span style={{ fontSize: 10, color: C.muted }}>DCF Fair Value </span>
              <span style={{ fontSize: 12, fontWeight: 800, color: sc.dcf.margin_of_safety > 0 ? C.green : C.red, fontVariantNumeric: 'tabular-nums' }}>
                ${sc.dcf.fair_value} ({sc.dcf.margin_of_safety > 0 ? '+' : ''}{sc.dcf.margin_of_safety}% vs price) — {sc.dcf.upside_downside}</span>
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
                <span style={{ fontSize: 11, fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: sCol(d.score) }}>{d.score}/100</span>
              </div>
              {(d.signals || []).map((sig, si) => (
                <div key={si} style={{ marginBottom: 7 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, marginBottom: 2 }}>
                    <span style={{ color: C.muted }}>{sig.flag} {sig.label}</span>
                    <span style={{ fontVariantNumeric: 'tabular-nums', color: C.text }}>{sig.value}</span>
                  </div>
                  <div style={{ height: 3, background: C.bg, borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ width: `${Math.max(0, Math.min(100, safe(sig.score)))}%`, height: '100%', background: sCol(safe(sig.score)), borderRadius: 2 }} />
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function miniBtn(color) {
  return { background: 'transparent', color, border: `1px solid ${color}55`, borderRadius: 6,
    padding: '3px 9px', fontSize: 9, fontWeight: 700, cursor: 'pointer', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
}

function EditRow({ theme, palette, onSave, onCancel }) {
  const [name, setName] = useState(theme.name)
  const [color, setColor] = useState(theme.color)
  return (
    <>
      <input value={name} onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') onSave(name, color); if (e.key === 'Escape') onCancel() }}
        autoFocus style={{ flex: 1, background: C.bg, color: C.text, border: `1px solid ${C.cyan}`, borderRadius: 6, padding: '6px 9px', fontSize: 11, fontVariantNumeric: 'tabular-nums', outline: 'none' }} />
      <div style={{ display: 'flex', gap: 4 }}>
        {palette.map(col => <button key={col} onClick={() => setColor(col)} title={col} style={{ width: 16, height: 16, borderRadius: 4, background: col, cursor: 'pointer', border: `2px solid ${color === col ? C.text : 'transparent'}`, outline: `1px solid ${C.mist}` }} />)}
      </div>
      <button onClick={() => onSave(name, color)} style={miniBtn(C.green)}>Save</button>
      <button onClick={onCancel} style={miniBtn(C.muted)}>Cancel</button>
    </>
  )
}
