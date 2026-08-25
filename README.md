# Portfolio Analyzer Discovery — May 2026

A thematic growth-portfolio analysis platform with an AI **Scout / Discovery agent**
that finds *net-new* tickers within a theme, then scores them with the same
5-dimension fundamental engine used for your existing holdings.

## What's new in the Discovery edition

- **🔭 Scout agent (6th agent).** Give it a theme (Space, Nuclear, AI/Semis, LNG,
  Quantum, Robotics, AR) or a free-text sub-theme. It uses web search to surface
  peers, challengers, and supply-chain / picks-and-shovels names you *don't* already
  own — then applies hard filters (no Taiwan/OTC/China/crypto; prefer NASDAQ/NYSE/TSX;
  EWY proxy for Korea) and flags uncertain Wealthsimple availability.
- **Fundamentals handoff.** Every discovered candidate can be scored on demand
  (Valuation / Profitability / Health / Growth / Quality + DCF). A
  **data-completeness guard** marks thin-coverage names "insufficient data" instead
  of scoring them on partial data.
- **Discovery tab** with theme picker, live SSE "thinking" animation, candidate
  table, and per-row + bulk "Run fundamentals" actions.

Architecture: **web search discovers → yfinance + fundamentals scores.**

## Requirements

- Python 3.10+
- Node.js 18+ (only needed once, to build the frontend)

## Quick start (Windows)

1. Extract this folder somewhere simple, e.g. `C:\Stonks\Portfolio_Analyzer_Discovery_May_2026`
   (avoid OneDrive-synced paths — they sometimes lock files mid-build).
2. Double-click **`start.bat`**. On first run it builds the frontend, installs Python
   deps, and starts the server.
3. Open **http://localhost:8000** in your browser.

### Manual start (if you prefer)

```bat
cd frontend
npm install
npm run build
cd ..\backend
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Watch the prompt path: run `npm` commands from `...\frontend>` and `uvicorn` from `...\backend>`.

## Enabling the AI agents (optional)

The five analysis agents and the Scout agent work **without** an API key using
curated static reports / seed candidates. For **live** web-search discovery and
reasoning:

1. Copy `.env.example` to `.env` **inside the `backend` folder**.
2. Put your key in it: `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart the server.

> The `.env` must sit where you launch uvicorn from (the `backend` folder), because
> it's loaded from the current working directory. If the key isn't picked up, that's
> the usual cause.

Get a key at console.anthropic.com (billed separately from any Claude subscription;
a few dollars of prepaid credit lasts a long time at per-run costs of fractions of a cent).

## Optional future upgrade

The Scout's prompt methodology mirrors Anthropic's Claude for Financial Services
equity-research skills (idea-generation / sector-overview / competitive-analysis).
You can later swap in their MCP connectors (MT Newswires, Aiera for news;
Daloopa, Morningstar for fundamentals) as richer data sources — see the comments
at the top of `backend/agents.py`. The default stays web search + yfinance, no extra
dependencies required.

## Entering your holdings

The sidebar takes one ticker per line:

```
NVDA:AI:9000
ASML:AI:7000
IONQ:Quantum
```

`TICKER:Theme:Amount` — the **amount is optional** and can be dollars, shares, or percent
(it gets normalized, so use whatever is easiest to read off your brokerage). Supply it and
the app measures your *actual* book — HHI, Effective N, diversification ratio and the Monte
Carlo simulation all use your real sizes, and **"Your Portfolio" is ranked against all ten
strategies** so you can see where you actually stand. Leave amounts off and everything runs
equal-weight as before (in which case HHI and Effective N are just 1/n and n, so they tell
you nothing).

## Tabs

- **Overview** — portfolio metrics, equity curve vs benchmark, strategy scores
- **Combinations** — 10 weighting strategies ranked by price + fundamentals, plus two
  reference rows: **Your Portfolio** (your real allocation) and **Conviction Weighted**
  (the sizing this app recommends). All metrics are real backtests of each weight vector.
- **Compare** — up to 5 strategies side by side, with backtested growth curves
- **Stocks** — per-holding risk/return table with horizon tags
- **📖 Fundamentals** — 5-dimension scoring per holding; finishing a scoring run
  automatically re-ranks Combinations and enriches the Timeline
- **👀 Watchlist** — generated signals (BUY_WATCH, MOMENTUM, UNDERVALUED, RISK_FLAG, DRAG)
- **⏱ Timeline** — holding periods, conviction tiers, entry checklists, exit triggers
- **🔭 Discovery** — the Scout agent (works without running an analysis first)
- **🤖 AI Agents** — Macro / Sector / Risk / News / Quant analysis of your holdings
- **🎲 Monte Carlo** — correlated GBM simulation of outcome ranges and goal probabilities
