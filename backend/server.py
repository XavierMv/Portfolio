"""
server.py  –  FastAPI backend
Serves all data to the React frontend via REST + SSE.
Run: uvicorn server:app --reload --port 8000
"""
import os
import math
import json
import asyncio
from pathlib import Path
from typing import Any

# ── TLS trust store ───────────────────────────────────────────────────────────
# Must run BEFORE httpx / requests / yfinance / anthropic are imported.
#
# Security suites (Norton, Kaspersky, ESET, Zscaler…) and corporate proxies
# intercept HTTPS and re-sign every certificate with their own root CA. Windows
# trusts that CA, but `certifi` — the fixed public-CA bundle httpx and requests
# default to — does not. The result is that every outbound call fails TLS before
# it reaches the network: the Anthropic SDK raises APIConnectionError, and
# yfinance silently reports "possibly delisted / no price data".
#
# truststore makes Python verify against the OS trust store instead, which
# already trusts whatever is doing the interception. Certificates are still
# fully verified — this does NOT disable verification.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as _e:                     # optional dependency
    print(f"[tls] truststore unavailable ({_e}); using certifi. "
          f"If HTTPS calls fail with SSL/connection errors, run: pip install truststore")


def _build_ca_bundle() -> str | None:
    """
    Write a CA bundle of certifi + the OS root store, and point libcurl at it.

    truststore only patches Python's `ssl` module. yfinance 1.x does its HTTP
    through curl_cffi (libcurl), which never consults `ssl` — it reads its own
    bundle, so an intercepted connection still fails there with
    "curl: (60) SSL certificate problem: unable to get local issuer certificate"
    and yfinance reports it as "possibly delisted / no price data".

    Combining certifi with the Windows/macOS root store covers both the public
    CAs and whatever local CA is doing the interception. Verification stays ON.
    """
    import ssl as _ssl
    try:
        import certifi as _certifi
    except Exception:
        return None

    pems = []
    for _store in ("ROOT", "CA"):
        try:
            for _der, _enc, _trust in _ssl.enum_certificates(_store):
                try:
                    pems.append(_ssl.DER_cert_to_PEM_cert(_der))
                except Exception:
                    pass
        except Exception:
            pass                       # enum_certificates is Windows-only
    if not pems:
        return None

    try:
        _dir = Path.home() / ".portfolio_v3_cache"
        _dir.mkdir(parents=True, exist_ok=True)
        _path = _dir / "ca_bundle.pem"
        _body = open(_certifi.where(), encoding="utf-8").read() + "\n" + "\n".join(pems)
        # only rewrite when the store changed, so startup stays cheap
        if not _path.exists() or _path.read_text(encoding="utf-8") != _body:
            _path.write_text(_body, encoding="utf-8")
        return str(_path)
    except Exception:
        return None


_CA = _build_ca_bundle()
if _CA:
    # libcurl (curl_cffi/yfinance), requests, and stdlib all honour one of these.
    for _var in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        os.environ.setdefault(_var, _CA)
    print(f"[tls] CA bundle: certifi + OS root store -> {_CA}")

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from pathlib import Path as _Path
_BASE = _Path(__file__).resolve().parent
load_dotenv(_BASE / ".env")            # backend/.env  (recommended location)
load_dotenv(_BASE.parent / ".env")     # project-root/.env  (fallback, no override)
load_dotenv()                          # default cwd search (no override)

from analytics  import (calc_returns, compute_stock_metrics,
                         compute_portfolio_metrics, horizon_score)
from data       import fetch_all, clear_cache, LAST_STALE
from montecarlo import simulate_portfolio, simulate_stock
from combinations import (generate_combinations, generate_combinations_with_fundamentals,
                          generate_watchlist, efficient_frontier, build_named_portfolio)
from agents     import run_agent, get_agent_list, run_scout, SCOUT_STEP_LABELS
from fundamentals import compute_fundamentals
from timeline import build_stock_timeline, build_portfolio_timeline

app = FastAPI(title="Portfolio Analyzer API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Serve the built React frontend
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


# ── helpers ────────────────────────────────────────────────────────────────────
def _safe(v):
    """Convert numpy / nan / inf → JSON-safe Python types."""
    if isinstance(v, (np.integer,)):       return int(v)
    if isinstance(v, (np.floating,)):      return None if math.isnan(v) or math.isinf(v) else float(v)
    if isinstance(v, float):               return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, np.ndarray):          return v.tolist()
    if isinstance(v, pd.Series):           return v.tolist()
    if isinstance(v, pd.DataFrame):        return v.to_dict("list")
    if isinstance(v, dict):                return {k: _safe(vv) for k, vv in v.items()}
    if isinstance(v, list):                return [_safe(x) for x in v]
    return v


def _clean(m: dict) -> dict:
    """Remove private keys and make safe."""
    return _safe({k: v for k, v in m.items() if not k.startswith("_")})


# ── in-memory cache ───────────────────────────────────────────────────────────
_analysis_cache: dict[str, Any] = {}   # key = run_id


# ── request models ─────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    tickers:   dict[str, str]   # {ticker: theme}
    period:    str = "5y"
    benchmark: str = "SPY"
    # Optional real position sizes: {ticker: dollars | shares | percent}.
    # Normalized server-side, so any consistent unit works. Omit for equal weight.
    weights:   dict[str, float] | None = None


class AgentRequest(BaseModel):
    agent_id:  str
    run_id:    str


# ── endpoints ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    from agents import _clean_key
    k = _clean_key()
    return {"status": "ok", "version": "3.0", "has_api_key": bool(k and k != "your-key-here")}


# Candidate models probed by /api/diag — first one that works is recommended.
_DIAG_MODELS = [
    "claude-sonnet-4-5",
    "claude-sonnet-4-20250514",
    "claude-opus-4-1-20250805",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
]

@app.get("/api/diag")
def diag():
    """Live API diagnostic — probes several models and reports which ones your key can call."""
    from agents import _clean_key, MODEL
    import anthropic
    key = _clean_key()
    if not key or key == "your-key-here":
        return {"has_api_key": False, "current_model": MODEL, "ok": False,
                "error": "No ANTHROPIC_API_KEY loaded. Put it in backend/.env (no quotes) and restart."}
    c = anthropic.Anthropic(api_key=key)
    results, working = {}, []
    for m in dict.fromkeys([MODEL] + _DIAG_MODELS):
        try:
            c.messages.create(model=m, max_tokens=8, messages=[{"role": "user", "content": "ping"}])
            results[m] = "ok"; working.append(m)
        except Exception as e:
            results[m] = f"{type(e).__name__}: {str(e)[:120]}"
    return {
        "has_api_key": True,
        "key_prefix": key[:14] + "…",
        "current_model": MODEL,
        "current_model_ok": results.get(MODEL) == "ok",
        "working_models": working,
        "recommended": working[0] if working else None,
        "hint": (f"Set ANTHROPIC_MODEL={working[0]} in backend/.env and restart."
                 if working and results.get(MODEL) != "ok"
                 else "Current model works — agents will use live calls." if working
                 else "No tested model is available to this key — check your Console plan/credits."),
        "probe": results,
    }


@app.get("/api/agents")
def list_agents():
    return get_agent_list()


@app.post("/api/run")
def run_analysis(req: RunRequest):
    """
    Fetch data + compute all metrics for the given tickers.
    Returns the full analysis as JSON.
    """
    ticker_map = req.tickers          # {NVDA: "AI", ...}
    tickers    = list(ticker_map.keys())

    # 1. Fetch prices
    price_data = fetch_all(tickers, period=req.period, benchmark=req.benchmark)
    if "__benchmark" not in price_data:
        raise HTTPException(400,
            f"Could not fetch benchmark ({req.benchmark}) — no live data and nothing "
            f"cached for it. Yahoo Finance rate-limits heavily (HTTP 429); wait a few "
            f"minutes and retry, or pick a benchmark you have already analysed before.")

    bm_prices  = price_data.pop("__benchmark")
    bm_returns = calc_returns(bm_prices)

    # 2. Per-stock metrics
    stock_metrics = []
    for ticker in tickers:
        if ticker not in price_data:
            stock_metrics.append({"ticker": ticker, "theme": ticker_map[ticker],
                                   "error": "No data from Yahoo Finance"})
            continue
        m = compute_stock_metrics(ticker, price_data[ticker], bm_returns,
                                  theme=ticker_map.get(ticker, "Custom"))
        stock_metrics.append(m)

    # 3. Portfolio metrics — honour real position sizes when supplied
    user_weights = {k.upper(): v for k, v in (req.weights or {}).items() if v and v > 0}
    port = compute_portfolio_metrics(stock_metrics, bm_returns, weights=user_weights or None)

    # 4. Combinations — ranked on real backtested risk stats, not weighted
    #    per-stock averages, so the table agrees with the equity curves.
    valid = [m for m in stock_metrics if "error" not in m]
    returns_df = port.get("_returns_df")
    combos = generate_combinations(valid, returns_df=returns_df, bm_returns=bm_returns)

    # 4b. Reference books, ranked alongside the generated strategies so the
    #     medals answer a real question: how does what you ACTUALLY hold, and
    #     what this app RECOMMENDS you hold, compare to the ten alternatives?
    timelines     = [build_stock_timeline(m) for m in valid]
    port_timeline = build_portfolio_timeline(timelines)

    # "Conviction Weighted" — built from timeline.py's own per-stock sizing,
    # which already blends price conviction with fundamentals and trims for
    # volatility, drawdown and negative alpha. This is the app's recommendation
    # expressed as a portfolio instead of 30 separate suggestions.
    conviction_w = {t["ticker"]: t.get("target_size_pct", 0) or 0 for t in timelines}
    conviction = build_named_portfolio(
        valid, conviction_w, "Conviction Weighted", "Recommended", "Long",
        "Sizes each holding by its RELATIVE conviction tier (price 55% + fundamentals "
        "45%), trimmed for volatility, drawdown and negative alpha, then normalized to "
        "100% under a position cap. The sizing this app recommends, scored as one book.",
        # Deliberately UNCAPPED. timeline.py's base_size already applies position
        # limits per stock; capping again distorts the thing this row exists to
        # show. Capping redistributes the excess proportionally, which pushes
        # weight into the LOWEST-conviction names (a 2.5% target ballooned to
        # 13.3%), inverting the ordering. The row expresses relative conviction
        # normalized to 100% — absolute sizing stays on the Timeline tab.
        returns_df=returns_df, bm_returns=bm_returns, cap=None,
        is_reference=True)
    if conviction:
        combos.append(conviction)

    # "Your Portfolio" — the real allocation, uncapped and reported as held.
    if user_weights:
        actual = build_named_portfolio(
            valid, user_weights, "Your Portfolio", "Actual", "Long",
            "Your current allocation as entered in the sidebar, scored on exactly "
            "the same basis as every strategy above.",
            returns_df=returns_df, bm_returns=bm_returns, cap=None,
            is_actual=True, is_reference=True)
        if actual:
            combos.append(actual)

    combos = sorted(combos, key=lambda x: -x["score"])

    # 5. Watchlist
    watchlist = generate_watchlist(valid)

    # 6. Efficient frontier
    frontier   = efficient_frontier(returns_df) if returns_df is not None else []

    # 6b. Real per-strategy backtests — weight each strategy's FULL weight vector
    #     against the historical daily-returns matrix and compound to an equity curve.
    combo_curve_dates, benchmark_curve = [], []
    if returns_df is not None and not returns_df.empty and combos:
        cols = list(returns_df.columns)
        idx  = returns_df.index
        N = 90
        step = max(1, len(idx) // N)
        sel = list(range(0, len(idx), step))
        if sel and sel[-1] != len(idx) - 1:
            sel.append(len(idx) - 1)
        combo_curve_dates = [str(idx[j])[:10] for j in sel]
        rmat = returns_df.values  # (T, n) aligned to cols
        for combo in combos:
            w  = combo.get("weights") or []
            ct = combo.get("tickers") or []
            if len(w) != len(cols):                 # realign by ticker if needed
                wmap = dict(zip(ct, w))
                w = [wmap.get(c, 0.0) for c in cols]
            wv = np.array(w, dtype=float)
            tot = wv.sum()
            if tot > 0:
                wv = wv / tot
            pr  = rmat.dot(wv)                       # daily portfolio returns
            eqc = (1.0 + pr).cumprod() * 100.0
            combo["curve"] = [round(float(eqc[j]), 2) for j in sel]
            combo.pop("weights", None); combo.pop("tickers", None)
        bench_aligned = bm_returns.reindex(idx).fillna(0.0)
        beq = (1.0 + bench_aligned.values).cumprod() * 100.0
        benchmark_curve = [round(float(beq[j]), 2) for j in sel]
    else:
        for combo in combos:
            combo.pop("weights", None); combo.pop("tickers", None)

    # 7. Equity curve (port + benchmark, normalized)
    port_prices = port.get("_port_prices")
    eq_curve = []
    if port_prices is not None:
        norm_port = (port_prices / port_prices.iloc[0] * 100).round(2)
        norm_bm   = (bm_prices / bm_prices.iloc[0] * 100).round(2)
        bm_aligned = norm_bm.reindex(norm_port.index, method="nearest")
        for dt, pv in norm_port.items():
            eq_curve.append({
                "date": str(dt)[:10],
                "portfolio": round(float(pv), 2),
                "benchmark": round(float(bm_aligned.get(dt, 100)), 2),
            })

    # 8. Correlation matrix
    corr = port.get("_corr_matrix")
    corr_data = None
    if corr is not None:
        corr_data = {"labels": list(corr.columns),
                     "values": [[round(float(v), 3) for v in row]
                                 for row in corr.values]}

    # 9. Build portfolio summary for agents
    port_stats = _clean(port)
    port_summary = {
        "tickers": tickers,
        "themes": ticker_map,
        "portfolio_stats": {
            "sharpe":               port_stats.get("sharpe"),
            "annualized_return":    port_stats.get("annualized_return"),
            "annualized_volatility":port_stats.get("annualized_volatility"),
            "beta":                 port_stats.get("beta"),
            "max_drawdown":         port_stats.get("max_drawdown"),
            "alpha":                port_stats.get("alpha"),
        }
    }

    # 10. Build run_id and cache
    import hashlib, time
    run_id = hashlib.md5(f"{tickers}{req.period}{time.time()}".encode()).hexdigest()[:12]
    # Cache port_summary + simplified stock metrics (for fundamental-enriched re-ranking)
    # Carry every metric the timeline and combination engines read. Dropping any
    # of them makes the enriched re-run silently fall back to defaults, so the
    # entry checklists would change for reasons unrelated to fundamentals.
    def _f(m, k, d=0.0):
        v = m.get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return d
        return v if math.isfinite(v) else d

    simple_stocks = [{
        "ticker": m["ticker"],
        "theme":  m.get("theme", "Custom"),
        "annualized_return":     _f(m, "annualized_return"),
        "annualized_volatility": _f(m, "annualized_volatility"),
        "sharpe":       _f(m, "sharpe"),
        "sortino":      _f(m, "sortino"),
        "alpha":        _f(m, "alpha"),
        "beta":         _f(m, "beta", 1.0),
        "max_drawdown": _f(m, "max_drawdown"),
        "calmar":       _f(m, "calmar"),
        "ulcer_index":       _f(m, "ulcer_index", 10.0),
        "information_ratio": _f(m, "information_ratio"),
        "upside_capture":    _f(m, "upside_capture",   1.0),
        "downside_capture":  _f(m, "downside_capture", 1.0),
        "recovery_factor":   _f(m, "recovery_factor"),
        "horizon":      m.get("horizon", {}),
    } for m in stock_metrics if "error" not in m]
    _analysis_cache[run_id] = {
        "port_summary":       port_summary,
        "stock_metrics_simple": simple_stocks,
        # full aligned price DataFrame for the Monte Carlo add-on
        "price_df": pd.DataFrame({t: s for t, s in price_data.items()}).dropna(how="all"),
        # kept so the fundamental re-rank can reuse the same real backtest
        "returns_df": returns_df,
        "bm_returns": bm_returns,
        "user_weights": user_weights,
        "conviction_weights": conviction_w,
    }

    # 11. Serialize stocks
    clean_stocks = []
    for m in stock_metrics:
        cm = _clean(m)
        # add price / date arrays for sparklines
        if "_prices" in m and m["_prices"] is not None:
            prices = m["_prices"]
            cm["price_dates"]  = [str(d)[:10] for d in prices.index]
            cm["price_values"] = [round(float(v), 4) for v in prices.values]
        clean_stocks.append(cm)

    return {
        "run_id":    run_id,
        "stocks":    clean_stocks,
        "portfolio": port_stats,
        "combinations": combos,
        "combo_curve_dates": combo_curve_dates,
        "benchmark_curve": benchmark_curve,
        "watchlist": watchlist,
        "frontier":  frontier,
        "equity_curve": eq_curve,
        "corr":      corr_data,
        "benchmark": req.benchmark,
        "period":    req.period,
        # Tickers served from an out-of-date cache because the live fetch was
        # unavailable (usually Yahoo rate-limiting). {ticker: age_in_hours}
        "stale_data": dict(LAST_STALE),
        "n_loaded":  sum(1 for m in stock_metrics if "error" not in m),
        "n_failed":  sum(1 for m in stock_metrics if "error" in m),
        "timelines": _safe(timelines),
        "portfolio_timeline": _safe(port_timeline),
    }


@app.post("/api/agent")
def call_agent(req: AgentRequest):
    """Run a single AI agent synchronously and return its report."""
    cached = _analysis_cache.get(req.run_id, {})
    port_summary = cached.get("port_summary", {"tickers":[], "themes":{}, "portfolio_stats":{}})
    return run_agent(req.agent_id, port_summary)


@app.get("/api/agent/stream/{run_id}/{agent_id}")
async def stream_agent(run_id: str, agent_id: str):
    """
    SSE endpoint — streams agent thinking steps then the final report.
    """
    cached = _analysis_cache.get(run_id, {})
    port_summary = cached.get("port_summary", {"tickers":[], "themes":{}, "portfolio_stats":{}})

    thinking_steps = {
        "macro":  ["Fetching latest Fed statements…","Analyzing yield curve data…","Correlating with portfolio beta…","Generating macro assessment…"],
        "sector": ["Scanning sector rotation signals…","Fetching institutional flow data…","Analyzing theme momentum…","Generating sector report…"],
        "risk":   ["Running Monte Carlo simulations…","Computing correlation stress tests…","Analyzing tail risk scenarios…","Generating risk report…"],
        "news":   ["Scanning Bloomberg & Reuters feeds…","Processing earnings transcripts…","Identifying catalyst events…","Generating news report…"],
        "quant":  ["Running factor decomposition…","Backtesting momentum signals…","Computing optimal weights…","Generating quant report…"],
    }
    steps = thinking_steps.get(agent_id, ["Analyzing…","Processing…","Generating report…"])

    async def event_gen():
        for i, step in enumerate(steps):
            data = json.dumps({"type": "thinking", "step": step, "progress": int((i+1)/len(steps)*80)})
            yield f"data: {data}\n\n"
            await asyncio.sleep(0.7)

        # Run the actual agent in a thread
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_agent, agent_id, port_summary)
        data = json.dumps({"type": "done", "progress": 100, "result": result})
        yield f"data: {data}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



@app.post("/api/combinations/with-fundamentals")
async def combinations_with_fundamentals(body: dict):
    """
    Recompute portfolio combinations after fundamentals are loaded.
    Body: { "run_id": "...", "fund_data": { "NVDA": {...}, ... } }
    Merges fundamental scores into stock metrics and re-ranks strategies.
    """
    run_id = body.get("run_id", "")
    fund_data = body.get("fund_data", {})

    cached = _analysis_cache.get(run_id, {})
    port_summary = cached.get("port_summary", {})
    tickers = port_summary.get("tickers", [])
    ticker_map = port_summary.get("themes", {})

    if not tickers:
        raise HTTPException(404, "Run ID not found. Run /api/run first.")

    # Re-fetch stock metrics from cache or rebuild minimal version
    # We store a simplified stock list in the cache
    stock_metrics = cached.get("stock_metrics_simple", [])
    if not stock_metrics:
        raise HTTPException(404, "Stock metrics not cached. Re-run analysis.")

    rdf, bmr = cached.get("returns_df"), cached.get("bm_returns")
    combos = generate_combinations_with_fundamentals(
        stock_metrics, fund_data, returns_df=rdf, bm_returns=bmr,
    )

    # Re-attach the reference books, now carrying fundamental scores so they are
    # compared on the same blended basis as the generated strategies.
    enriched = []
    for m in stock_metrics:
        fd = fund_data.get(m["ticker"], {}) or {}
        e = dict(m)
        e["fundamental_score"]   = fd.get("composite_score") or 0
        e["fundamental_grade"]   = fd.get("composite_grade") or ""
        e["fundamental_verdict"] = fd.get("verdict") or ""
        enriched.append(e)

    conv_w = cached.get("conviction_weights") or {}
    if conv_w:
        c = build_named_portfolio(
            enriched, conv_w, "Conviction Weighted", "Recommended", "Long",
            "Sizes each holding by its RELATIVE conviction tier (price 55% + fundamentals "
            "45%), trimmed for volatility, drawdown and negative alpha, then normalized to "
            "100% under a position cap. The sizing this app recommends, scored as one book.",
            returns_df=rdf, bm_returns=bmr, cap=None, is_reference=True)
        if c:
            combos.append(c)

    uw = cached.get("user_weights") or {}
    if uw:
        a = build_named_portfolio(
            enriched, uw, "Your Portfolio", "Actual", "Long",
            "Your current allocation as entered in the sidebar, scored on exactly "
            "the same basis as every strategy above.",
            returns_df=rdf, bm_returns=bmr, cap=None,
            is_actual=True, is_reference=True)
        if a:
            combos.append(a)

    combos = sorted(combos, key=lambda x: -x["score"])

    # Attach the same sampled backtest curves the initial /api/run produced, so
    # the Compare tab keeps working after the fundamental re-rank.
    returns_df = cached.get("returns_df")
    curve_dates, bench_curve = [], []
    if returns_df is not None and not returns_df.empty and combos:
        cols, idx = list(returns_df.columns), returns_df.index
        step = max(1, len(idx) // 90)
        sel = list(range(0, len(idx), step))
        if sel and sel[-1] != len(idx) - 1:
            sel.append(len(idx) - 1)
        curve_dates = [str(idx[j])[:10] for j in sel]
        rmat = returns_df.values
        for combo in combos:
            w  = combo.get("weights") or []
            ct = combo.get("tickers") or []
            if len(w) != len(cols):
                wmap = dict(zip(ct, w))
                w = [wmap.get(c, 0.0) for c in cols]
            wv = np.array(w, dtype=float)
            if wv.sum() > 0:
                wv = wv / wv.sum()
            eqc = (1.0 + rmat.dot(wv)).cumprod() * 100.0
            combo["curve"] = [round(float(eqc[j]), 2) for j in sel]
        bm = cached.get("bm_returns")
        if bm is not None:
            beq = (1.0 + bm.reindex(idx).fillna(0.0).values).cumprod() * 100.0
            bench_curve = [round(float(beq[j]), 2) for j in sel]
    for combo in combos:
        combo.pop("weights", None); combo.pop("tickers", None)

    return _safe({"combinations": combos,
                  "combo_curve_dates": curve_dates,
                  "benchmark_curve": bench_curve})



@app.post("/api/timeline/enrich")
async def enrich_timelines(body: dict):
    """
    Re-run timeline assessments after fundamentals are loaded,
    merging fundamental data into each stock's timeline.
    Body: { "run_id": "...", "fund_data": { "NVDA": {...}, ... } }
    """
    run_id   = body.get("run_id", "")
    fund_data = body.get("fund_data", {})

    cached = _analysis_cache.get(run_id, {})
    stock_metrics = cached.get("stock_metrics_simple", [])
    if not stock_metrics:
        raise HTTPException(404, "Run ID not found. Re-run /api/run first.")

    loop = asyncio.get_event_loop()

    def enrich_one(m):
        fd = fund_data.get(m["ticker"])
        return build_stock_timeline(m, fd)

    tasks = [loop.run_in_executor(None, enrich_one, m) for m in stock_metrics]
    import asyncio as aio
    timelines = await aio.gather(*tasks)
    port_timeline = build_portfolio_timeline(list(timelines))
    return _safe({"timelines": list(timelines), "portfolio_timeline": port_timeline})

@app.delete("/api/cache")
def delete_cache():
    clear_cache()
    return {"status": "cache cleared"}


# ── Fundamentals endpoints ─────────────────────────────────────────────────────

@app.get("/api/fundamentals/{ticker}")
def get_fundamentals(ticker: str):
    """Fetch and score all fundamental data for a single ticker."""
    result = compute_fundamentals(ticker.upper())
    return _safe(result)


@app.post("/api/fundamentals/batch")
async def get_fundamentals_batch(body: dict):
    """
    Fetch fundamentals for a list of tickers in parallel.
    Body: { "tickers": ["NVDA", "AAPL", ...] }
    Returns list of fundamental reports.
    """
    tickers = body.get("tickers", [])
    if not tickers:
        return []

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, compute_fundamentals, t.upper())
        for t in tickers
    ]
    import asyncio as aio
    results = await aio.gather(*tasks, return_exceptions=True)

    cleaned = []
    for r in results:
        if isinstance(r, Exception):
            cleaned.append({"error": str(r)})
        else:
            cleaned.append(_safe(r))
    return cleaned


@app.get("/api/fundamentals/stream/{run_id}")
async def stream_fundamentals(run_id: str):
    """
    SSE stream — fetches fundamentals one by one and streams results.
    Frontend shows a live progress bar as each stock completes.
    """
    cached = _analysis_cache.get(run_id, {})
    tickers = list(cached.get("port_summary", {}).get("tickers", []))
    if not tickers:
        raise HTTPException(404, "Run ID not found or no tickers")

    async def gen():
        loop = asyncio.get_event_loop()
        total = len(tickers)
        for i, ticker in enumerate(tickers):
            result = await loop.run_in_executor(None, compute_fundamentals, ticker)
            payload = json.dumps({
                "type":    "result",
                "ticker":  ticker,
                "index":   i,
                "total":   total,
                "progress": round((i + 1) / total * 100),
                "data":    _safe(result),
            })
            yield f"data: {payload}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── Scout / Discovery endpoints ─────────────────────────────────────────────────

@app.get("/api/scout/stream")
async def scout_stream(theme: str, owned: str = ""):
    """SSE — stream Scout thinking steps then the discovered candidate list."""
    owned_tickers = [t.strip().upper() for t in owned.split(",") if t.strip()]
    steps = SCOUT_STEP_LABELS

    async def gen():
        loop = asyncio.get_event_loop()
        total = len(steps)
        for i, step in enumerate(steps):
            yield f"data: {json.dumps({'type':'thinking','step':step,'progress':round((i+1)/total*85)})}\n\n"
            await asyncio.sleep(0.6)
        result = await loop.run_in_executor(None, lambda: run_scout(theme, owned_tickers))
        yield f"data: {json.dumps({'type':'done','progress':100,'result':_safe(result)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/score")
async def score_tickers(body: dict):
    """Fundamentals handoff — score a list of (discovered) tickers in parallel."""
    tickers = [t.strip().upper() for t in body.get("tickers", []) if t.strip()]
    if not tickers:
        return []
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, compute_fundamentals, t) for t in tickers]
    import asyncio as aio
    results = await aio.gather(*tasks, return_exceptions=True)
    out = []
    for t, r in zip(tickers, results):
        out.append({"ticker": t, "error": str(r)} if isinstance(r, Exception) else _safe(r))
    return out


# Serve React app for all non-API routes
@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not built yet. Run: cd frontend && npm install && npm run build"}

# ── Monte Carlo add-on ────────────────────────────────────────────────────────
class MonteCarloRequest(BaseModel):
    run_id: str
    horizon_years: float = 5.0
    drift_mode: str = "dampened"      # dampened | raw | market
    target_return: float = 0.5        # 0.5 = +50% over the horizon

@app.post("/api/montecarlo")
def run_montecarlo(req: MonteCarloRequest):
    """Portfolio + per-stock GBM simulation using the cached price history."""
    cached = _analysis_cache.get(req.run_id, {})
    price_df = cached.get("price_df")
    if price_df is None or getattr(price_df, "empty", True):
        raise HTTPException(404, "Run an analysis first (price data not cached).")
    # Simulate the real allocation when sizes were supplied — an equal-weight
    # assumption understates concentration risk for a book that isn't equal weight.
    mc_weights = cached.get("user_weights") or None
    port = simulate_portfolio(price_df, weights=mc_weights,
                              horizon_years=req.horizon_years,
                              drift_mode=req.drift_mode,
                              target_return=req.target_return)
    stocks = [{"ticker": t,
               "sim": simulate_stock(price_df[t].dropna().values,
                                     horizon_years=req.horizon_years,
                                     drift_mode=req.drift_mode,
                                     target_return=req.target_return)}
              for t in price_df.columns]
    return _safe({"portfolio": port, "stocks": stocks,
                  "weighting": "custom" if mc_weights else "equal"})