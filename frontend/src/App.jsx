import { useState, useCallback } from 'react'
import Sidebar from './components/Sidebar.jsx'
import OverviewTab from './components/tabs/OverviewTab.jsx'
import CombinationsTab from './components/tabs/CombinationsTab.jsx'
import CompareTab from './components/tabs/CompareTab.jsx'
import StocksTab from './components/tabs/StocksTab.jsx'
import WatchlistTab from './components/tabs/WatchlistTab.jsx'
import AgentsTab from './components/tabs/AgentsTab.jsx'
import FundamentalsTab from './components/tabs/FundamentalsTab.jsx'
import TimelineTab from './components/tabs/TimelineTab.jsx'
import DiscoveryTab from './components/tabs/DiscoveryTab.jsx'
import MonteCarloView from './components/MonteCarloView.jsx'

const TABS = [
  { id:'overview',      label:'Overview' },
  { id:'combinations',  label:'Combinations' },
  { id:'compare',       label:'Compare' },
  { id:'stocks',        label:'Stocks' },
  { id:'fundamentals',  label:'📖 Fundamentals' },
  { id:'watchlist',     label:'👀 Watchlist' },
  { id:'timeline',       label:'⏱ Timeline' },
  { id:'discovery',     label:'🔭 Discovery' },
  { id:'agents',        label:'🤖 AI Agents' },
  // was an array literal — t.id/t.label came back undefined, so this rendered a
  // blank button that set the active tab to undefined and showed nothing.
  { id:'montecarlo',    label:'🎲 Monte Carlo' },
]

const C = {
  bg:'#ffffff', card:'#efefef', border:'#e8e8e8', rule:'#dcdcdc',
  text:'#202020', body:'#4d4d4d', muted:'#828282', ember:'#ff682c',
  cyan:'#ff682c',            // primary-accent slot, now Ember
}
const FONT_DISPLAY = "'Schibsted Grotesk', 'Inter', sans-serif"
const FONT_UI = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"

export default function App() {
  const [tab, setTab]         = useState('overview')
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [runId, setRunId]     = useState(null)
  const [enriching, setEnriching] = useState(false)

  // Fundamentals handoff. The Fundamentals tab scores every holding, but nothing
  // ever fed those scores back — so /api/combinations/with-fundamentals and
  // /api/timeline/enrich were dead endpoints, the Fund column stayed "—", and the
  // fundamental strategies (Fundamental Leaders, Value Play, Fortress Balance
  // Sheet…) never appeared despite the UI promising "price + fundamentals".
  const applyFundamentals = useCallback(async (scores) => {
    const fund_data = Object.fromEntries(
      Object.entries(scores || {}).filter(([, v]) => v && !v.error && !v.insufficient_data)
    )
    if (!runId || !Object.keys(fund_data).length) return
    setEnriching(true)
    try {
      const [cRes, tRes] = await Promise.allSettled([
        fetch('/api/combinations/with-fundamentals', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: runId, fund_data }),
        }),
        fetch('/api/timeline/enrich', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: runId, fund_data }),
        }),
      ])
      const patch = {}
      if (cRes.status === 'fulfilled' && cRes.value.ok) {
        const j = await cRes.value.json()
        if (j?.combinations?.length) {
          patch.combinations = j.combinations
          if (j.combo_curve_dates?.length) patch.combo_curve_dates = j.combo_curve_dates
          if (j.benchmark_curve?.length)   patch.benchmark_curve   = j.benchmark_curve
        }
      }
      if (tRes.status === 'fulfilled' && tRes.value.ok) {
        const j = await tRes.value.json()
        if (j?.timelines?.length) {
          patch.timelines = j.timelines
          patch.portfolio_timeline = j.portfolio_timeline
        }
      }
      if (Object.keys(patch).length) setData(d => (d ? { ...d, ...patch } : d))
    } catch { /* keep the price-only view rather than blanking the tabs */ }
    finally { setEnriching(false) }
  }, [runId])

  const runAnalysis = useCallback(async (tickerMap, period, benchmark, weights = null) => {
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: tickerMap, period, benchmark, weights }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Server error')
      }
      const json = await res.json()
      setData(json)
      setRunId(json.run_id)
      setTab('overview')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div style={{ background:C.bg, color:C.text, height:'100vh',
                  fontFamily:FONT_UI,
                  display:'flex', flexDirection:'column', overflow:'hidden' }}>

      {/* Header */}
      <div style={{ padding:'18px 32px', borderBottom:`1px solid ${C.border}`,
                    background:C.bg,
                    display:'flex', justifyContent:'space-between', alignItems:'center',
                    flexShrink:0 }}>
        <div>
          <div style={{ fontSize:23, fontWeight:400, letterSpacing:'-0.025em',
                        fontFamily:FONT_DISPLAY, lineHeight:1.1 }}>
            Portfolio Analyzer
            <span style={{ fontSize:11, color:C.muted, marginLeft:10,
                           fontFamily:FONT_UI, letterSpacing:0 }}>
              Discovery
            </span>
          </div>
          <div style={{ fontSize:10.5, color:C.muted, marginTop:5, fontVariantNumeric:'tabular-nums' }}>
            {data
              ? `${data.n_loaded} tickers loaded · ${data.period} · vs ${data.benchmark} · ${data.combinations?.length || 0} strategies`
              : 'Enter tickers and click Run Analysis'}
          </div>
        </div>
        {(loading || enriching) && (
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <div style={{ width:140, height:2, background:C.border, overflow:'hidden' }}>
              <div style={{ width:'60%', height:'100%', background:C.ember,
                            animation:'loading-bar 1.5s ease-in-out infinite' }} />
            </div>
            <span style={{ fontSize:10.5, color:C.muted }}>{enriching ? 'Re-ranking with fundamentals…' : 'Fetching data…'}</span>
          </div>
        )}
      </div>

      <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
        <Sidebar onRun={runAnalysis} loading={loading} error={error} data={data} />

        {/* Main content */}
        <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
          {/* Tabs */}
          <div style={{ display:'flex', gap:2, borderBottom:`1px solid ${C.border}`,
                        padding:'10px 30px', flexShrink:0, overflowX:'auto' }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                background: tab===t.id ? C.text : 'transparent',
                border:'none', cursor:'pointer', borderRadius:200,
                padding:'7px 15px', fontSize:11.5, fontWeight:500, whiteSpace:'nowrap',
                color: tab===t.id ? C.bg : C.muted,
                transition:'background 0.15s, color 0.15s',
              }}>{t.label}</button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex:1, overflowY:'auto', padding:'30px 32px 80px' }}>
            {!data && !loading && (
              <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
                            justifyContent:'center', height:'50vh', gap:12 }}>
                <div style={{ fontSize:34, fontFamily:FONT_DISPLAY, fontWeight:400,
                              letterSpacing:'-0.025em', color:C.text, lineHeight:1.15,
                              maxWidth:520, textAlign:'center' }}>
                  Enter your tickers and run an analysis
                </div>
                <div style={{ fontSize:12, color:C.muted, maxWidth:430, textAlign:'center',
                              lineHeight:1.65 }}>
                  Any Yahoo Finance ticker — stocks, ETFs, indices. Format{' '}
                  <span style={{ color:C.ember }}>TICKER:Theme</span>, with an optional{' '}
                  <span style={{ color:C.ember }}>:Amount</span> to measure your real book.
                </div>
              </div>
            )}

            {loading && (
              <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:12 }}>
                {Array(18).fill(0).map((_,i) => (
                  <div key={i} style={{ background:C.card, borderRadius:8, height:78,
                                        opacity:0.55 }} />
                ))}
              </div>
            )}

            {data && !loading && (
              <>
                {tab==='overview'      && <OverviewTab data={data} />}
                {tab==='combinations'  && <CombinationsTab data={data} />}
                {tab==='compare'       && <CompareTab data={data} />}
                {tab==='stocks'        && <StocksTab data={data} />}
                {tab==='fundamentals'  && <FundamentalsTab data={data} onScores={applyFundamentals} />}
                {tab==='watchlist'     && <WatchlistTab data={data} />}
                {tab==='timeline'      && <TimelineTab data={data} runId={runId} />}
                {tab==='agents'        && <AgentsTab data={data} runId={runId} />}
                {tab==='discovery'     && <DiscoveryTab data={data} runId={runId} />}
                {tab === "montecarlo" && <MonteCarloView runId={runId} />}
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes loading-bar {
          0%   { width: 0%; margin-left: 0%; }
          50%  { width: 60%; margin-left: 20%; }
          100% { width: 0%; margin-left: 100%; }
        }
      `}</style>
    </div>
  )
}
