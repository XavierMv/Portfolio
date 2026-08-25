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
pip install -r ..\requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Watch the prompt path: run `npm` commands from `...\frontend>` and `uvicorn` from `...\backend>`.

## Running on GitHub Codespaces (no local install)

You can run the whole app on GitHub instead of your own machine. This is the
recommended way to keep the API key off both the repo and your disk.

1. On the repo page: **Code → Codespaces → Create codespace**.
2. The devcontainer installs Python + Node deps and builds the frontend
   automatically (first run takes a few minutes).
3. In the terminal:

   ```bash
   cd backend && python -m uvicorn server:app --host 0.0.0.0 --port 8000
   ```

4. Codespaces forwards port 8000 and opens it in your browser — same
   `localhost:8000` experience, running on GitHub.

### Starting it from a phone

The codespace starts the server **automatically** when it opens, so there is
nothing to type. Open the codespace, wait for setup, then tap the forwarded
**port 8000** URL (a "port forwarded" toast appears, or find it under the
**Ports** tab).

If you need to start or restart it by hand, the whole command is:

```bash
./start.sh
```

That builds the frontend if needed, stops any previous instance, and starts the
server. Safe to run repeatedly.

### The API key as a Codespaces secret

Set the key **once** as a secret, and every codespace you create gets it
injected as an environment variable. It is never written to the repo, never
written to a file, and is not visible to anyone who can read the repo:

- **github.com → Settings → Codespaces → Secrets → New secret**
- Name: `ANTHROPIC_API_KEY`, value: your key
- Grant it access to this repository

The app reads `ANTHROPIC_API_KEY` straight from the environment, so nothing
else is needed. An injected environment variable takes precedence over any
`.env` file, so the secret always wins.

Verify it loaded at `/api/diag` — or check the sidebar, which shows
"● API key active" instead of "○ Static mode".

## Enabling the AI agents when running locally

The five analysis agents and the Scout agent work **without** an API key using
curated static reports / seed candidates. For **live** web-search discovery and
reasoning on a local install:

1. Copy `.env.example` to `.env` **inside the `backend` folder**.
2. Put your key in it: `ANTHROPIC_API_KEY=sk-ant-...` — no quotes, no spaces around `=`.
3. Restart the server.

> `backend/.env` is gitignored and must never be committed. The server looks for
> it next to `server.py` first, then the project root, then the working
> directory — so it is found regardless of where you launch uvicorn from.

Get a key at console.anthropic.com (billed separately from any Claude subscription;
a few dollars of prepaid credit lasts a long time at per-run costs of fractions of a cent).

> **Never paste a key into a source file, a script, or `start.bat`.** If a key is
> ever exposed — committed, zipped, emailed, or uploaded — revoke it at
> console.anthropic.com and issue a new one. Rotating is free and instant.

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
