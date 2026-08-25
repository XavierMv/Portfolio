// ui.jsx — design tokens + shared primitives
//
// Visual language: a light, ~95% achromatic editorial system. Structure and
// chrome are neutral; colour is functional punctuation, never decoration.
// Depth comes from surface contrast — there are no shadows anywhere.
//
// Every export name here is unchanged from the previous dark theme, so this is
// purely a repaint: no component logic or data flow was altered.

// ── Palette ──────────────────────────────────────────────────────────────────
// Legacy key names (green/red/amber/cyan/purple/pink/blue) are kept so existing
// conditional styling keeps working untouched — only the values they resolve to
// have changed. `cyan` was the app's primary-accent slot, so it maps to Ember.
export const C = {
  // surfaces
  bg:     '#ffffff',   // Canvas White
  card:   '#efefef',   // Ash — dominant card/section background
  card2:  '#f5f5f5',   // Fog — nested containers
  dim:    '#e8e8e8',   // Mist — bar tracks, wells
  ivory:  '#ebe6dd',   // warm wash for featured blocks

  // rules
  border:  '#e8e8e8',  // Mist hairline
  border2: '#dcdcdc',  // stronger rule

  // ink
  text:   '#202020',   // Graphite
  body:   '#4d4d4d',   // Steel
  muted:  '#828282',   // Slate

  // accent — functional punctuation only
  cyan:   '#ff682c',   // Ember (primary accent / active state)
  amber:  '#816729',   // Brass (warn / secondary accent)

  // muted data semantics
  green:  '#3d7a4f',   // Moss  — gain
  red:    '#b3402f',   // Brick — loss
  purple: '#5b4a86',
  pink:   '#8a3d63',
  blue:   '#2f5d8a',

  // named aliases, for new code that wants to read as the reference does
  canvas: '#ffffff', ash: '#efefef', fog: '#f5f5f5',
  graphite: '#202020', steel: '#4d4d4d', slate: '#828282', mist: '#e8e8e8',
  ember: '#ff682c', brass: '#816729', moss: '#3d7a4f', brick: '#b3402f',
}

// Desaturated theme marks — distinguishable, but none competes with Ember.
export const THEMES = {
  AI:'#2f5d8a', Robotics:'#a35a2b', Quantum:'#5b4a86',
  Space:'#3d7a4f', Nuclear:'#816729', LNG:'#8a3d63',
  AR:'#2f7a75', Custom:'#4d4d4d',
}

export const HCOL = { Short:C.brick, Medium:C.brass, Long:C.moss }
export const SCOL = { Optimized:C.blue, Factor:C.purple, Thematic:C.brass,
                      Balanced:C.moss, Conservative:C.steel, Baseline:C.slate,
                      Aggressive:C.brick, Actual:C.ember, Recommended:C.moss }

// Medals: metal tones, muted to sit inside an achromatic page.
export const RANK = ['#a8862c','#8c8c8c','#9c6b42',C.slate,C.slate,C.slate,
                     C.slate,C.slate,C.slate,C.slate]
export const rankColor = i =>
  (i===0?'#a8862c':i===1?'#8c8c8c':i===2?'#9c6b42':C.slate)

// ── Legacy-colour remap ──────────────────────────────────────────────────────
// The backend ships presentation hex in agent reports, strategy flags, exit
// triggers, verdicts and valuation triggers. Rather than edit those payloads
// (which would mean touching backend logic), translate them here at the point
// of display. Anything unrecognised passes through unchanged.
const REMAP = {
  '#1ddb82': C.moss,  '#12e87a': C.moss,  '#4ade80': '#5c9670',
  '#a3e635': C.moss,
  '#ff3558': C.brick, '#ff2d55': C.brick, '#f43f5e': C.brick,
  '#ff7043': '#c2703f', '#ff6020': C.ember, '#ff6b35': '#a35a2b',
  '#ffaa18': C.brass, '#ffb020': C.brass,
  '#00ccf5': C.blue,  '#3388ff': C.blue,
  '#9933ff': C.purple, '#ff1a88': C.pink,
  '#4a6080': C.slate, '#8aa0c2': C.slate, '#e2ecf7': C.text,
  '#ffd700': '#a8862c', '#c0c0c0': '#8c8c8c', '#cd7f32': '#9c6b42',
}
export const remap = c =>
  (typeof c === 'string' && REMAP[c.toLowerCase()]) || c || C.slate

// ── Helpers (unchanged behaviour) ────────────────────────────────────────────
export const tc  = t => THEMES[t] || C.steel
export const grc = v => (typeof v==='number' && v>=0) ? C.moss : C.brick
export const safe = v => (typeof v==='number' && isFinite(v)) ? v : 0
export const pct  = (v,d=1) => { const n=safe(v); return `${n>=0?'+':''}${(n*100).toFixed(d)}%` }
export const f2   = v => safe(v).toFixed(2)
export const f1   = v => safe(v).toFixed(1)

// Shared type ramp
export const FONT_DISPLAY = "'Schibsted Grotesk', 'Inter', sans-serif"
export const FONT_UI      = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
// Figures use Inter's tabular numerals rather than a monospace face — columns
// still align, but the page keeps its editorial voice.
export const NUM = { fontVariantNumeric:'tabular-nums', fontFeatureSettings:"'tnum' 1" }
// Zebra striping: a whisper of graphite. The old rgba(255,255,255,…) was
// invisible against a white canvas.
export const STRIPE = 'rgba(32,32,32,0.022)'

// ── Primitives ───────────────────────────────────────────────────────────────

// Tags are fully rounded (20px) per the reference, and quiet by default.
export function Chip({ label, color }) {
  if (!label) return null
  const c = remap(color)
  return (
    <span style={{ fontSize:9.5, fontWeight:500, letterSpacing:'0.02em',
      color:c, border:`1px solid ${c}33`, borderRadius:20, padding:'2px 9px',
      background:`${c}12`, whiteSpace:'nowrap', display:'inline-block',
      lineHeight:1.5, fontFamily:FONT_UI }}>
      {String(label)}
    </span>
  )
}

// Metric tile — flat Ash surface, no border, no shadow. The label is the
// smallest thing on the page; the figure carries the weight.
export function MBox({ label, value, color, sub }) {
  return (
    <div style={{ background:C.ash, borderRadius:8, padding:'14px 16px' }}>
      <div style={{ fontSize:9, color:C.slate, letterSpacing:'0.08em',
        textTransform:'uppercase', marginBottom:6, fontWeight:500 }}>{label}</div>
      <div style={{ fontSize:22, fontWeight:400, color:color||C.text,
        fontFamily:FONT_DISPLAY, letterSpacing:'-0.02em', lineHeight:1.1, ...NUM }}>
        {String(value??'—')}
      </div>
      {sub ? <div style={{ fontSize:9.5, color:C.slate, marginTop:5 }}>{String(sub)}</div> : null}
    </div>
  )
}

// `ratio` renders the value as a plain number (Sharpe 1.85) instead of a
// percentage — without it, every ratio below 2 was mislabelled as a percent.
export function HBar({ label, value, max, color, ratio = false }) {
  const w = Math.min(Math.abs(safe(value))/Math.max(safe(max),0.001)*100, 100)
  const c = remap(color)
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:7 }}>
      <div style={{ width:54, fontSize:9.5, color:C.slate, textAlign:'right', flexShrink:0 }}>{label}</div>
      <div style={{ flex:1, height:3, background:C.mist, overflow:'hidden' }}>
        <div style={{ width:`${w}%`, height:'100%', background:c }} />
      </div>
      <div style={{ width:46, fontSize:10, color:C.text, textAlign:'right',
        flexShrink:0, fontWeight:500, ...NUM }}>
        {ratio ? f2(value) : pct(value)}
      </div>
    </div>
  )
}

// Section label — the editorial device that replaces heavy headings.
export function SL({ text }) {
  return (
    <div style={{ fontSize:9, color:C.slate, letterSpacing:'0.1em',
      textTransform:'uppercase', fontWeight:500,
      marginBottom:14, paddingBottom:9, borderBottom:`1px solid ${C.mist}` }}>{text}</div>
  )
}

// Cards: 8px radius, flat Ash, hairline rule instead of a heavy border.
export function Card({ children, style }) {
  return (
    <div style={{ background:C.ash, border:`1px solid ${C.mist}`, borderRadius:8,
                  padding:24, marginBottom:16, ...style }}>
      {children}
    </div>
  )
}

export function TH({ children, onClick, active }) {
  return (
    <th onClick={onClick} style={{ padding:'9px 10px', textAlign:'left',
      cursor:onClick?'pointer':'default', userSelect:'none', whiteSpace:'nowrap',
      color:active?C.ember:C.slate, fontSize:9, fontWeight:500,
      letterSpacing:'0.08em', textTransform:'uppercase',
      borderBottom:`1px solid ${C.rule||C.border2}` }}>
      {children}
    </th>
  )
}

export function TD({ children, style }) {
  return <td style={{ padding:'10px', fontSize:11.5, color:C.body, ...NUM, ...style }}>{children}</td>
}
