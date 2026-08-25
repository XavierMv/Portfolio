# Portfolio Analyzer Discovery — May 2026
## Full Context Prompt

Copy everything below the line into a new conversation to bring an assistant fully up to speed on this project, its constraints, its architecture, and how to work on it.

> Note: this document was redacted before publishing. Personal details — local
> filesystem paths, holdings the author actually owns, and billing specifics —
> were removed. Everything describing the software itself is unchanged.

---

## DESIGN CONTEXT

This app is built for a retail investor running a thematic growth portfolio of
roughly 30 stocks on a brokerage that supports fractional shares and real share
ownership (not CFDs). Development happens on Windows; the project should be
extracted to a simple path such as `C:\Stonks\` rather than a cloud-synced
folder, which can lock files mid-build.

The portfolio spans seven themes: **Space, Nuclear, AI/Semiconductors,
LNG/Energy, Quantum Computing, Robotics, and Augmented Reality (AR)**. The
default holdings set baked into the sidebar (ticker:theme):

```
NVDA:AI, ASML:AI, AVGO:AI, EWY:AI, GOOGL:AI
ISRG:Robotics, SYM:Robotics, TER:Robotics, ROK:Robotics, PATH:Robotics
MSFT:Quantum, IBM:Quantum, IONQ:Quantum, QBTS:Quantum
LMT:Space, RKLB:Space, PL:Space, NOC:Space, LUNR:Space
CEG:Nuclear, CCJ:Nuclear, BWXT:Nuclear, VST:Nuclear, OKLO:Nuclear, DNN:Nuclear
LNG:LNG, KMI:LNG, XOM:LNG, GLNG:LNG, TTE:LNG
```

## HARD INVESTMENT CONSTRAINTS (non-negotiable filters)

These are platform/risk constraints the Scout agent applies BEFORE any
valuation analysis:

- **No Taiwan-listed stocks** (geopolitical risk).
- **No OTC / pink-sheet securities** (unavailable on the target brokerage).
- **No mainland-China-domiciled names** (sanctions/opacity).
- **No crypto-adjacent holdings** (volatility; miners, exchanges, treasury-coin proxies).
- **Prefer NASDAQ / NYSE / TSX** primary listings. TSX avoids FX conversion (e.g. MDA.TO).
- **Korean exposure via ETF proxy** (EWY) instead of KRX listings.
- **Flag uncertain brokerage availability** rather than asserting a name is available.

## DESIGN PRINCIPLES

- **Valuation discipline**: overvalued momentum names are removed even when they
  fit a theme. Thematic fit is never sufficient on its own.
- **Royalty/platform preference**: favour "picks and shovels" plays that win
  regardless of who leads a sector.
- **Iterative, constraint-driven workflow**: start broad (full sector research),
  then progressively apply constraints to narrow to a valid, actionable set.
- **Time-horizon framework**: positions are categorized from annual
  "lottery ticket" reviews to permanent core holdings.
- **Sync discipline**: stress-test whether frontend previews and backend logic are
  truly synchronized. Direct gap analysis is preferred over uncritical affirmation.

---

## THE SOFTWARE: "Portfolio Analyzer Discovery May 2026"

A full-stack desktop app (runs locally, served at http://localhost:8000) that analyzes holdings AND discovers net-new candidates. It's the evolution of an earlier "Portfolio Analyzer v3." Architecture principle for discovery: **web search discovers tickers → yfinance + fundamentals scores them** (Yahoo Finance can only verify a known ticker, never discover one).

### Tech stack
- **Backend**: Python + FastAPI, served via `uvicorn server:app --host 0.0.0.0 --port 8000`. Data from Yahoo Finance (`yfinance`) with a 4-hour local disk cache (parquet, at `~/.portfolio_v3_cache/`; fundamentals cached 24h as JSON under `~/.portfolio_v3_cache/fundamentals/`).
- **Frontend**: React + Vite + recharts, built with `npm run build` into `frontend/dist`, which FastAPI serves.
- **AI**: Anthropic API with the `web_search_20250305` tool. Graceful static fallback when no API key is present.

### Backend modules (in `backend/`)
- `data.py` — yfinance fetch + 4hr disk cache; `fetch_prices()`, `fetch_benchmark()`, `clear_cache()`.
- `analytics.py` — all price metrics (TRADING_DAYS=252, risk-free RF=0.043): total/annualized return, volatility, downside deviation, Sharpe, Sortino, Calmar, Treynor, beta/alpha/R², max drawdown, Ulcer index, VaR/CVaR (95/99), information ratio, up/down capture, HHI, diversification ratio, effective N. Plus `horizon_score()` → {short, medium, long, best}.
  `compute_portfolio_metrics(stock_metrics, bm_returns, weights=None)` accepts real
  position sizes (`{ticker: dollars|shares|percent}`, normalized); omit for equal weight.
  It reports `weighting` ("equal"|"custom"), `weights_map`, and `history_days` vs
  `common_days` — a holding younger than the lookback no longer truncates the whole
  portfolio series, but it does shrink the window the covariance tools can use.
- `fundamentals.py` — 5-dimension scoring (Valuation 25%, Profitability 25%, Financial Health 20%, Growth 20%, Quality 10%) → composite 0–100, letter grade A+–F, verdict STRONG BUY/BUY/HOLD/WEAK/AVOID. DCF fair value (WACC ~10%, terminal growth 3%, 5-year projection) with margin of safety. Sector P/E and EV/EBITDA benchmark tables. **KEY FEATURE — data-completeness guard**: KEY_FIELDS = [market_cap, pe_trailing, gross_margin, revenue_growth_yoy, total_debt, fcf, roe]; if fewer than REQUIRED_MIN=4 are present, returns `{insufficient_data: True, reason: ...}` instead of scoring on partial data (small/foreign/pre-revenue names often have thin yfinance coverage). Scored results also carry `coverage`/`missing_fields`.
  There is exactly ONE DCF: `estimate_fair_value()` is a thin wrapper over
  `valuation.dcf_value()`. Do not reintroduce a second copy — the previous duplicate
  diverged 9–19% on incomplete data and, lacking an `fcf <= 0` guard, returned a
  NEGATIVE fair value for cash-burning names.
  Note `debt_to_equity` from yfinance is in PERCENT form (74.0 = 0.74x) and is always
  divided by 100; do not add a magnitude-sniffing heuristic.
- `combinations.py` — generates 10 weighting strategies blending price + fundamentals. Combination score = `Sharpe×35 + Calmar×12 + Alpha×18 + (FundComposite×0.30) − |MaxDD|×10 − HHI×25 + horizon_bonus`.
  **Every ranking input is a REAL backtest**: `_real_metrics()` applies each weight
  vector to the actual daily-returns matrix and compounds it, so ret/vol/mdd/sharpe/
  calmar/beta/alpha describe the same portfolio as the equity curve on the Compare tab.
  (These were previously weighted per-stock averages with a flat `×0.82` volatility
  fudge, which ignored correlation and produced a wrong medal order.) Falls back to the
  averages only when no return history is available — flagged via `exact_metrics: false`.
  `build_named_portfolio()` scores an explicitly-weighted book on the same basis; it
  backs the two reference rows below. Strategies: Max Sharpe, Fundamental Leaders, Profitability Focus, Value Play, Growth Tilt, Risk Parity, Fortress Balance Sheet, Equal Weight, Momentum Tilt, Alpha Hunters. Plus `generate_watchlist()` (signals: BUY_WATCH, MOMENTUM, UNDERVALUED, RISK_FLAG, DRAG).
  Two REFERENCE rows are ranked alongside the ten strategies so the medals answer a real
  question: **"Your Portfolio"** (`is_actual`) — the real allocation, uncapped, shown only
  when position sizes are supplied — and **"Conviction Weighted"** (`is_reference`) — built
  from `timeline.py`'s own per-stock `target_size_pct`, deliberately UNCAPPED because
  capping redistributes excess into the lowest-conviction names and inverts the ordering.
- `timeline.py` — holding-period engine: per-stock hold ranges, conviction tiers (Very High→Speculative, weighted price 55% + fundamental 45%), position sizing, entry checklists, exit triggers, theme catalyst calendars, hurdle rate vs expected return. Plus portfolio-level horizon mix and conviction aggregation.
- `agents.py` — **the core of this app: 6 AI agents.** Five "analyze" agents take a portfolio summary as input: Macro 🌐, Sector 🏭, Risk 🛡️, News 📰 (uses web search), Quant 🤖. The sixth is the **Scout / Discovery agent 🔭** (mode="discover") — see below. Includes `run_agent()` dispatch, STEP_LABELS for SSE thinking animation, robust `_parse_json()`, and static fallbacks (`_static_analyze()` canned reports, `_static_scout()` curated seed candidates per theme).
- `server.py` — FastAPI endpoints: `GET /api/health` (reports has_api_key), `GET /api/agents`, `POST /api/run` (full analysis → stocks/portfolio/combinations/watchlist/equity_curve/timelines), `GET /api/agent/stream/{run_id}/{agent_id}` (SSE for analyze agents), `GET /api/scout/stream?theme=&owned=` (SSE for discovery), `POST /api/score` (fundamentals handoff — scores a list of tickers, including discovered ones), `GET /api/fundamentals/{ticker}`, `GET /api/fundamentals/stream/{run_id}`, `DELETE /api/cache`, and a SPA catch-all. Has a `_safe()` numpy/nan/inf JSON guard. Calls `load_dotenv()` at top.

### Frontend (in `frontend/src/`)
- `ui.jsx` — shared design tokens (color map C, THEMES color-by-theme, helpers safe/pct/f2/f1/grc) and primitives (Chip, SL, Card, HBar).
- `components/Sidebar.jsx` — ticker textarea, period buttons, benchmark input, Run button,
  status box (calls `/api/health` for live-vs-static key state).
  **Input format: `TICKER:Theme:Amount`.** The third field is OPTIONAL — dollars, shares or
  percent (normalized server-side). Supply it and the app measures the real book (HHI,
  Effective N, diversification ratio, Monte Carlo) and ranks "Your Portfolio" against every
  strategy. Omit it everywhere and behaviour is equal-weight, exactly as before.
- `components/tabs/` — one file per tab: OverviewTab, CombinationsTab, CompareTab, StocksTab,
  FundamentalsTab, WatchlistTab, TimelineTab, DiscoveryTab, AgentsTab, plus
  `components/MonteCarloView.jsx`. (A legacy combined `Tabs.jsx` was retired — it was dead
  code that had diverged from the live per-tab files.)
- `components/tabs/DiscoveryTab.jsx` — **the Scout UI** (see below).
- `App.jsx` — wires sidebar + tab bar: Overview, Combinations, Compare, Stocks,
  📖 Fundamentals, 👀 Watchlist, ⏱ Timeline, 🔭 Discovery, 🤖 AI Agents, 🎲 Monte Carlo.
  Default ~30-ticker list baked in. Also owns the **fundamentals handoff**: when the
  Fundamentals tab finishes streaming it calls `applyFundamentals()`, which POSTs the scores
  to `/api/combinations/with-fundamentals` and `/api/timeline/enrich` and merges the results.
  Without that call those endpoints are dead and the "price + fundamentals" blend never
  happens — which was the case until Aug 2026.

### THE SCOUT / DISCOVERY AGENT (the defining feature)

The Scout is a 6th agent that DISCOVERS net-new tickers rather than analyzing held ones. Its design:
1. **Inverted input**: receives a theme string (one of the 7 themes or a free-text sub-theme like "AI memory / HBM supply chain"), NOT a portfolio summary.
2. **Web-search discovery**: uses the same web_search tool the News agent uses; the system prompt directs it to map the theme's value chain and surface peers, challengers, and supply-chain / picks-and-shovels names beyond the obvious large caps already held.
3. **Hard-constraint pre-filter baked into the system prompt**: all the constraints above (no Taiwan/OTC/China/crypto; prefer NASDAQ/NYSE/TSX; EWY for Korea; flag uncertain brokerage availability). The already-owned tickers in the theme are passed in so it returns net-new names.
4. **Parseable JSON output contract** (no preamble, no markdown fences): each candidate has `ticker, name, exchange, theme, one_line_thesis, model_type` (royalty/platform | pure-play | supply-chain | diversified), and `wealthsimple_uncertain`.
5. **Fundamentals handoff**: discovered tickers flow into the same yfinance + fundamentals.py 5-dimension scoring, with the data-completeness guard marking thin-coverage names "insufficient data."
6. **Discovery frontend tab**: theme picker, SSE-streamed thinking animation, candidate table (ticker/name/exchange/model_type/thesis/fundamentals/action), per-row and bulk "Run fundamentals" actions, expandable detail with radar + key metrics + DCF, and the ⚠ availability-uncertain flag.

The Scout's prompt methodology mirrors Anthropic's Claude for Financial Services equity-research vertical (github.com/anthropics/financial-services): the idea-generation (/screen), sector-overview (/sector), and competitive-analysis skills. Their MCP connectors (MT Newswires, Aiera for news; Daloopa, Morningstar for fundamentals) are noted as an OPTIONAL future upgrade path in agents.py comments — but the default is web search + yfinance, with no extra dependencies required.

### DYNAMIC THEME MANAGEMENT (latest enhancement)

The Discovery tab lets themes be added/deleted/renamed/recolored directly from the UI — no code editing, no rebuild. Custom themes are persisted in the browser via `localStorage` (key `pad_custom_themes_v1`), so they survive refreshes per-device. A "⚙ Manage themes" button opens a panel with a name field, a color palette picker, and add/delete/rename controls. Built-in themes stay fixed; only custom ones are editable. The free-text box also still accepts any one-off theme. (Note: this is a desktop-app feature because localStorage doesn't work in Claude's artifact preview sandbox.)

### THE STANDALONE PREVIEW

There's also `portfolio-preview.jsx` — a single-file React artifact with dummy data that demonstrates all tabs including a 🔭 Discovery tab with representative demo candidates. It's the visual/UX mockup (no backend, no real data, no localStorage), used to validate the design. The real discovery/scoring happens in the desktop app.

---

## WINDOWS LAUNCH / WORKFLOW NOTES

- Extract to a simple path (e.g. `C:\Stonks\`), not a cloud-synced folder (avoids file locks mid-build).
- The included `start.bat` builds the frontend on first run, installs Python deps, and starts the server.
- Manual: `cd frontend` → `npm install` → `npm run build`, then `cd ..\backend` → `python -m uvicorn server:app --host 0.0.0.0 --port 8000`. Watch the prompt path — npm commands run from `...\frontend>`, uvicorn from `...\backend>`.
- Editing workflow: edit the EXTRACTED folder (not the zip). Backend Python edits take effect on server restart; frontend edits under `frontend/src/` require `npm run build` then refresh (the browser serves built `dist`, not raw source).

## API KEY NOTES

- The agents work WITHOUT a key (static canned reports / curated seed candidates). WITH a key they make real API calls + live web search.
- A Claude Max/Pro subscription does NOT provide API access — they're separate products, and as of early 2026 Anthropic blocks third-party tools from using subscription auth. Use a Console API key (console.anthropic.com) with prepaid credits, billed per token.
- The `.env` file must sit in the `backend` folder (where uvicorn is launched from), because `load_dotenv()` reads the current working directory. Format: `ANTHROPIC_API_KEY=sk-ant-...` — no quotes, no spaces around `=`. Restart the server after editing. If the key isn't picked up, the most common cause is `.env` in the wrong folder or named `.env.txt`. Diagnostic: agents swallow API errors and fall back silently, so watch the uvicorn terminal for `[Agent ...] API error:` lines.

## HOW TO WORK ON THIS PROJECT

- Confirm exact code signatures before implementing against existing code — don't guess; ask for the current files if they aren't available. (Note: sandboxes reset between sessions, so previously generated files won't be on disk.)
- Verify builds actually compile before packaging (run `npm run build` and a Python syntax/smoke test).
- Be direct and honest about valuation, tradeoffs, and any limitations — gap analysis is preferred over affirmation.
- Reasonably concise.

---

## WHAT YOU MIGHT BE ASKED TO DO

Examples: add new discovery themes; refine the Scout prompt or constraints; adjust fundamental scoring weights or the combination-score formula; add MCP connectors as a data upgrade; build new tabs or analytics; debug the Windows launch or API key; package an updated zip; or sync the preview mockup with the real backend. When packaging, deliver an updated zip and walk through exactly which files changed and the launch steps.
