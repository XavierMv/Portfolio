import { useState, useRef, useEffect, useCallback } from 'react'
import { C, SL, Card } from '../../ui.jsx'

const AGENTS = [
  { id: 'macro', icon: '🌐', name: 'Macro Agent', role: 'Macro & Rate', color: '#2f5d8a' },
  { id: 'sector', icon: '🏭', name: 'Sector Agent', role: 'Thematic Rotation', color: '#3d7a4f' },
  { id: 'risk', icon: '🛡️', name: 'Risk Agent', role: 'Portfolio Risk', color: '#b3402f' },
  { id: 'news', icon: '📰', name: 'News Agent', role: 'Catalyst Scanner', color: '#5b4a86' },
  { id: 'quant', icon: '🤖', name: 'Quant Agent', role: 'Factor Model', color: '#816729' },
]

export default function AgentsTab({ data, runId }) {
  const [active, setActive] = useState(null)
  const [loading, setLoading] = useState({})
  const [done, setDone] = useState({})
  const [results, setResults] = useState({})
  const [steps, setSteps] = useState({})
  const evtRef = useRef(null)

  const run = useCallback(id => {
    if (done[id]) { setActive(a => a === id ? null : id); return }
    setActive(id); setLoading(l => ({ ...l, [id]: 0 })); setSteps(s => ({ ...s, [id]: [] }))
    const es = new EventSource(`/api/agent/stream/${runId || 'none'}/${id}`)
    evtRef.current = es
    es.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'thinking') { setLoading(l => ({ ...l, [id]: msg.progress })); setSteps(s => ({ ...s, [id]: [...(s[id] || []), msg.step] })) }
      else if (msg.type === 'done') { es.close(); setLoading(l => ({ ...l, [id]: 100 })); setDone(d => ({ ...d, [id]: true })); setResults(r => ({ ...r, [id]: msg.result })) }
    }
    es.onerror = () => { es.close(); setDone(d => ({ ...d, [id]: true })) }
  }, [done, runId])

  useEffect(() => () => evtRef.current?.close(), [])

  const rep = active ? results[active]?.report : null
  const live = active ? results[active]?.live : null
  const def = active ? AGENTS.find(a => a.id === active) : null

  return (
    <div>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 18, lineHeight: 1.7 }}>
        5 agents analyze your <strong style={{ color: C.text }}>holdings</strong> with live web search + reasoning (API key), or expert static reports otherwise.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10, marginBottom: 24 }}>
        {AGENTS.map(a => {
          const act = active === a.id, ld = loading[a.id] != null && !done[a.id], dn = done[a.id]
          return (
            <button key={a.id} onClick={() => run(a.id)} style={{ background: act ? `${a.color}12` : C.card,
              border: `1px solid ${act ? a.color : C.mist}`, borderRadius: 8, padding: '20px 14px', cursor: 'pointer', textAlign: 'center' }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>{a.icon}</div>
              <div style={{ fontSize: 11, fontWeight: 800, color: act ? a.color : C.text, marginBottom: 3 }}>{a.name}</div>
              <div style={{ fontSize: 9, color: C.muted }}>{a.role}</div>
              {ld && <div style={{ marginTop: 10 }}><div style={{ height: 3, background: C.dim, borderRadius: 2 }}>
                <div style={{ width: `${loading[a.id]}%`, height: '100%', background: a.color, borderRadius: 2 }} /></div>
                <div style={{ fontSize: 8, color: a.color, marginTop: 3 }}>{loading[a.id]}%</div></div>}
              {dn && <div style={{ fontSize: 9, color: C.green, marginTop: 8 }}>✓ Complete</div>}
            </button>
          )
        })}
      </div>
      {active && def && (
        <Card style={{ border: `1px solid ${def.color}30` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div style={{ fontSize: 28 }}>{def.icon}</div>
            <div><div style={{ fontSize: 15, fontWeight: 800, color: def.color }}>{def.name}</div>
              <div style={{ fontSize: 10, color: C.muted }}>{def.role}</div></div>
          </div>
          {!done[active] && (steps[active] || []).map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
              background: `${def.color}0a`, borderRadius: 8, padding: '8px 14px' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: def.color }} />
              <span style={{ fontSize: 11, color: C.text }}>{s}</span>
            </div>
          ))}
          {done[active] && rep && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 9, fontWeight: 800, padding: '4px 10px', borderRadius: 6,
                    color: live ? C.green : C.amber, border: `1px solid ${(live ? C.green : C.amber)}55`,
                    background: `${(live ? C.green : C.amber)}14` }}>{live ? '● LIVE API + WEB SEARCH' : '● STATIC FALLBACK'}</span>
                  {rep._error && <span style={{ fontSize: 9, color: C.red }}>{rep._error}</span>}
                </div>
                <div style={{ background: `${rep.sentiment_color || C.amber}18`, border: `1px solid ${rep.sentiment_color || C.amber}44`, borderRadius: 8, padding: '6px 14px' }}>
                  <div style={{ fontSize: 9, color: C.muted, textTransform: 'uppercase' }}>Sentiment</div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: rep.sentiment_color || C.amber }}>{rep.sentiment}</div>
                </div>
              </div>
              <div style={{ background: `${def.color}0a`, borderLeft: `3px solid ${def.color}`, borderRadius: '0 8px 8px 0', padding: '12px 16px', marginBottom: 18, fontSize: 11, color: C.text, lineHeight: 1.7 }}>{rep.summary}</div>
              <SL text="Key Findings" />
              <div style={{ marginBottom: 18 }}>
                {(rep.bullets || []).map((b, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10, background: `${b.color}0c`, borderRadius: 8, padding: '8px 12px', borderLeft: `2px solid ${b.color}` }}>
                    <span style={{ fontSize: 14 }}>{b.icon}</span>
                    <span style={{ fontSize: 11, color: C.text, lineHeight: 1.5 }}>{b.text}</span>
                  </div>
                ))}
              </div>
              <div style={{ background: `${C.green}10`, border: `1px solid ${C.green}30`, borderRadius: 10, padding: '12px 16px' }}>
                <div style={{ fontSize: 9, color: C.green, textTransform: 'uppercase', marginBottom: 6, fontWeight: 800 }}>→ Recommendation</div>
                <div style={{ fontSize: 11, color: C.text, lineHeight: 1.6 }}>{rep.recommendation}</div>
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  )
}
