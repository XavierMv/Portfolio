// ScoreDetail.jsx — expandable fundamentals panel for a scored ticker.
// Radar + key-metric grid + DCF + valuation card + per-dimension signal bars.
//
// This is the same panel DiscoveryTab and FundamentalsTab render inline. It was
// extracted here so DividendsTab could reuse it rather than add a third copy;
// those two still carry their own local versions and can be migrated onto this
// component whenever they're next touched.
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { C, Chip, SL, safe } from '../ui.jsx'
import ValuationCard from './ValuationCard.jsx'

const GCOL = { 'A+': C.green, A: C.green, 'B+': '#5c9670', B: '#5c9670', 'C+': C.amber, C: C.amber, D: '#c2703f', F: C.red }
const fX = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}x` : '—'
const fP = v => v != null && isFinite(Number(v)) ? `${Number(v).toFixed(1)}%` : '—'
const sCol = s => s >= 55 ? C.green : s >= 35 ? C.amber : C.red

export default function ScoreDetail({ sc }) {
  if (!sc) return null
  const dims = [sc.valuation, sc.profitability, sc.health, sc.growth, sc.quality].filter(Boolean)
  const radar = dims.map(d => ({ dim: d.dimension.split(' ')[0], score: safe(d.score) }))
  const metrics = [
    ['P/E', fX(sc.pe_trailing)], ['EV/EBITDA', fX(sc.ev_ebitda)], ['Gross Mgn', fP(sc.gross_margin)],
    ['Op Mgn', fP(sc.operating_margin)], ['ROE', fP(sc.roe)], ['ROIC', fP(sc.roic)],
    ['Rev Grw', fP(sc.revenue_growth_yoy)], ['FCF Yield', fP(sc.fcf_yield)],
    ['Div Yield', fP(sc.dividend_yield)], ['D/E', sc.debt_to_equity != null ? Number(sc.debt_to_equity).toFixed(2) : '—'],
    ['Current', sc.current_ratio != null ? Number(sc.current_ratio).toFixed(2) : '—'],
    ['Int Cov', fX(sc.interest_coverage)],
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
                ${sc.dcf.fair_value} ({sc.dcf.margin_of_safety > 0 ? '+' : ''}{sc.dcf.margin_of_safety}% vs price) — {sc.dcf.upside_downside}
              </span>
            </div>
          )}
          {sc.valuation_analysis && (
            <div style={{ marginTop: 12 }}><ValuationCard val={sc.valuation_analysis} /></div>
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
                <div key={si} style={{ marginBottom: 7 }}>
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
