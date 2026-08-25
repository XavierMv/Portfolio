import { useState, useEffect } from 'react'
import { C } from '../ui.jsx'

const DEFAULT = `NVDA:AI
ASML:AI
AVGO:AI
EWY:AI
GOOGL:AI
ISRG:Robotics
SYM:Robotics
TER:Robotics
ROK:Robotics
PATH:Robotics
MSFT:Quantum
IBM:Quantum
IONQ:Quantum
QBTS:Quantum
LMT:Space
RKLB:Space
PL:Space
NOC:Space
LUNR:Space
CEG:Nuclear
CCJ:Nuclear
BWXT:Nuclear
VST:Nuclear
OKLO:Nuclear
DNN:Nuclear
LNG:LNG
KMI:LNG
XOM:LNG
GLNG:LNG
TTE:LNG`

const PERIODS = ['1y', '2y', '5y', '10y', 'max']

export default function Sidebar({ onRun, loading, error, data }) {
  const [text, setText]           = useState(DEFAULT)
  const [period, setPeriod]       = useState('5y')
  const [benchmark, setBenchmark] = useState('SPY')
  // /api/health reports whether an ANTHROPIC_API_KEY was loaded. Nothing called
  // it before, so there was no way to tell live agent runs from the silent
  // static-fallback mode — agents swallow API errors and fall back quietly.
  const [health, setHealth] = useState(null)
  useEffect(() => {
    let alive = true
    fetch('/api/health').then(r => r.json())
      .then(j => { if (alive) setHealth(j) })
      .catch(() => { if (alive) setHealth({ error: true }) })
    return () => { alive = false }
  }, [])

  // TICKER:Theme:Amount — the third field is optional. Amount can be dollars,
  // shares or percent; it is normalized server-side, so any consistent unit works.
  // Omit it everywhere and the portfolio stays equal-weight as before.
  const parse = () => {
    const map = {}, weights = {}
    text.split('\n').map(l => l.trim()).filter(Boolean).forEach(line => {
      const [t, th, amt] = line.split(':')
      if (!t || !t.trim()) return
      const tk = t.trim().toUpperCase()
      map[tk] = (th || 'Custom').trim() || 'Custom'
      const v = parseFloat(String(amt || '').replace(/[$,\s]/g, ''))
      if (isFinite(v) && v > 0) weights[tk] = v
    })
    return { map, weights }
  }

  const run = () => {
    const { map, weights } = parse()
    if (Object.keys(map).length) {
      onRun(map, period, benchmark, Object.keys(weights).length ? weights : null)
    }
  }

  const { map: pMap, weights: pW } = parse()
  const n = Object.keys(pMap).length
  const nW = Object.keys(pW).length
  const totalW = Object.values(pW).reduce((a, b) => a + b, 0)

  return (
    <div style={{ width: 288, flexShrink: 0, borderRight: `1px solid ${C.border}`,
      background: C.bg, padding: '24px 22px', overflowY: 'auto', display: 'flex',
      flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 9, color: C.slate, letterSpacing: '0.1em',
          textTransform: 'uppercase', marginBottom: 8, fontWeight: 500,
          paddingBottom: 8, borderBottom: `1px solid ${C.mist}` }}>
          Holdings · {n}
          <span style={{ color: C.slate, opacity: 0.7, letterSpacing: 0, textTransform: 'none' }}>
            {'  '}TICKER:Theme:Amount
          </span>
        </div>
        <textarea value={text} onChange={e => setText(e.target.value)} spellCheck={false}
          style={{ width: '100%', height: 290, background: C.fog, color: C.text,
            border: `1px solid ${C.mist}`, borderRadius: 8, padding: 12, fontSize: 11.5,
            lineHeight: 1.75, resize: 'vertical', outline: 'none', boxSizing: 'border-box',
            fontVariantNumeric: 'tabular-nums' }} />
      </div>

      <div style={{ fontSize: 9.5, lineHeight: 1.65, marginTop: -10,
        color: nW ? C.moss : C.slate }}>
        {nW === 0
          ? '○ No sizes given — equal weight assumed (HHI / Effective N are structural).'
          : nW < n
            ? `⚠ ${nW}/${n} sized (total ${totalW.toLocaleString()}). Unsized names are excluded from "Your Portfolio".`
            : `● All ${n} sized · total ${totalW.toLocaleString()} — "Your Portfolio" ranked against every strategy.`}
      </div>

      <div>
        <div style={{ fontSize: 9, color: C.slate, letterSpacing: '0.1em',
          textTransform: 'uppercase', marginBottom: 9, fontWeight: 500,
          paddingBottom: 8, borderBottom: `1px solid ${C.mist}` }}>Period</div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{
              padding: '6px 13px', borderRadius: 200, fontSize: 10.5, fontWeight: 500,
              cursor: 'pointer',
              background: period === p ? C.text : 'transparent',
              border: `1px solid ${period === p ? C.text : C.rule || C.border2}`,
              color: period === p ? C.bg : C.muted }}>{p}</button>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 9, color: C.slate, letterSpacing: '0.1em',
          textTransform: 'uppercase', marginBottom: 9, fontWeight: 500,
          paddingBottom: 8, borderBottom: `1px solid ${C.mist}` }}>Benchmark</div>
        <input value={benchmark} onChange={e => setBenchmark(e.target.value.toUpperCase())}
          style={{ width: '100%', background: C.fog, color: C.text, border: `1px solid ${C.mist}`,
            borderRadius: 8, padding: '9px 12px', fontSize: 11.5,
            outline: 'none', boxSizing: 'border-box', fontVariantNumeric: 'tabular-nums' }} />
      </div>

      <button onClick={run} disabled={loading} style={{
        background: loading ? C.mist : C.text, color: loading ? C.slate : C.bg,
        border: 'none', borderRadius: 0, padding: '13px', fontWeight: 500, fontSize: 12,
        letterSpacing: '0.02em',
        cursor: loading ? 'not-allowed' : 'pointer' }}>
        {loading ? 'Running…' : 'Run Analysis'}
      </button>

      {error && (
        <div style={{ background: `${C.red}0d`, borderLeft: `2px solid ${C.red}`, borderRadius: 0,
          padding: '10px 12px', fontSize: 10.5, color: C.red, lineHeight: 1.55 }}>{error}</div>
      )}

      {health && !health.error && (
        <div style={{ fontSize: 9.5, lineHeight: 1.7, borderTop: `1px solid ${C.mist}`, paddingTop: 14,
          color: C.slate }}>
          <span style={{ color: health.has_api_key ? C.moss : C.brass, fontWeight: 500 }}>
            {health.has_api_key ? '● API key active' : '○ Static mode'}
          </span><br />
          <span style={{ fontSize: 8.5 }}>
            {health.has_api_key
              ? 'Agents & Scout use live web search.'
              : 'Agents use canned reports; Scout uses curated seeds. Add ANTHROPIC_API_KEY to backend/.env.'}
          </span>
        </div>
      )}

      {data && (
        <div style={{ fontSize: 9.5, color: C.slate, lineHeight: 1.7,
          borderTop: `1px solid ${C.mist}`, paddingTop: 14, fontVariantNumeric: 'tabular-nums' }}>
          {data.n_loaded} loaded · {data.n_failed} failed<br />
          vs {data.benchmark} · {data.period}
          {(() => {
            // Yahoo rate-limits hard (HTTP 429). When a live fetch fails we fall
            // back to cached prices rather than refusing to run — but the figures
            // are then only as current as that cache, so say so plainly.
            const st = data.stale_data || {}
            const n = Object.keys(st).length
            if (!n) return null
            const hrs = Math.max(...Object.values(st))
            const age = hrs < 48 ? `${Math.round(hrs)}h` : `${Math.round(hrs / 24)}d`
            return (
              <div style={{ marginTop: 8, color: C.brass, lineHeight: 1.6 }}>
                ○ Cached prices — {n} ticker{n > 1 ? 's' : ''} up to {age} old.
                <span style={{ color: C.slate }}> Yahoo was unreachable (rate limit); retry later for live data.</span>
              </div>
            )
          })()}
        </div>
      )}
    </div>
  )
}
