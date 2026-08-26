"""
combinations.py  –  Portfolio Combination Engine
Generates multiple weighted strategies and ranks them by composite score.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from analytics import TRADING_DAYS, RF


def _norm(arr: list | np.ndarray, cap: float = 0.40) -> np.ndarray:
    """Normalize to weights summing to 1 with no weight above `cap`.

    The cap must survive renormalization: clipping once and dividing by the new
    sum can push the clipped entries straight back above the cap. Iterate —
    freeze the capped names and redistribute the remainder across the rest.
    """
    a = np.array(arr, dtype=float)
    a = np.clip(a, 0, None)
    s = a.sum()
    if s == 0:
        a = np.ones(len(a))
        s = float(len(a))
    a = a / s
    n = len(a)
    if cap * n <= 1.0:          # cap can't be satisfied — equal weight is the closest
        return np.ones(n) / n
    for _ in range(100):
        over = a > cap + 1e-12
        if not over.any():
            break
        excess = float((a[over] - cap).sum())
        a[over] = cap
        room = ~over
        if not room.any():
            break
        under_sum = float(a[room].sum())
        if under_sum > 0:
            a[room] += excess * a[room] / under_sum
        else:
            a[room] += excess / room.sum()
    return a / a.sum()


def _real_metrics(w: np.ndarray, tickers: list[str],
                  returns_df: pd.DataFrame | None,
                  bm_returns: pd.Series | None) -> dict | None:
    """
    Backtest this weight vector against the actual daily-returns matrix.

    Returns the same risk stats the UI displays, computed from the compounded
    portfolio series rather than from weighted averages of per-stock stats.
    Weighted averages cannot see correlation: they overstate the volatility and
    drawdown of a diversified book and understate a concentrated one, which is
    exactly the comparison the strategy ranking is trying to make.
    """
    if returns_df is None or returns_df.empty:
        return None
    cols = list(returns_df.columns)
    wmap = dict(zip(tickers, w))
    wv = np.array([wmap.get(c, 0.0) for c in cols], dtype=float)
    tot = wv.sum()
    if tot <= 0:
        return None
    wv = wv / tot

    pr = pd.Series(returns_df.values.dot(wv), index=returns_df.index)
    if len(pr) < 20:
        return None

    eq   = (1.0 + pr).cumprod()
    yrs  = len(pr) / TRADING_DAYS
    ret  = float(eq.iloc[-1] ** (1.0 / max(yrs, 0.01)) - 1.0)
    vol  = float(pr.std(ddof=1) * np.sqrt(TRADING_DAYS))
    peak = eq.cummax()
    mdd  = float(((eq - peak) / peak).min())

    out = {
        "ret": ret,
        "vol": vol,
        "mdd": mdd,
        "sharpe": (ret - RF) / vol if vol > 0 else 0.0,
        "calmar": ret / abs(mdd) if mdd != 0 else 0.0,
    }

    # Beta / alpha against the benchmark over the overlapping window.
    if bm_returns is not None and len(bm_returns) > 0:
        r, b = pr.align(bm_returns, join="inner")
        if len(r) >= 20:
            cov = np.cov(r.values, b.values)
            if cov[1, 1] != 0:
                beta_v = float(cov[0, 1] / cov[1, 1])
                bm_ar  = float((1 + b.mean()) ** TRADING_DAYS - 1)
                r_ar   = float((1 + r.mean()) ** TRADING_DAYS - 1)
                out["beta"]  = beta_v
                out["alpha"] = float(r_ar - (RF + beta_v * (bm_ar - RF)))
    return out


def _build(stocks: list[dict], weights: np.ndarray,
           name: str, style: str, horizon: str, desc: str,
           returns_df: pd.DataFrame | None = None,
           bm_returns: pd.Series | None = None) -> dict:
    w = weights / weights.sum()
    tickers = [s["ticker"] for s in stocks]

    # Weighted-average fallbacks — used only when no return history is available.
    # The 0.82 on vol is a diversification GUESS standing in for the correlation
    # a real covariance matrix would supply; there is no correct constant. Kept
    # deliberately: any change is a different guess, not a fix. This path is
    # flagged to the UI via exact_metrics=False and the Combinations tab labels
    # it as approximate.
    ret   = float(np.dot(w, [s.get("annualized_return",    0) or 0 for s in stocks]))
    vol   = float(np.dot(w, [s.get("annualized_volatility", 0) or 0 for s in stocks]) * 0.82)
    beta  = float(np.dot(w, [s.get("beta",  1.0) or 1.0 for s in stocks]))
    alpha = float(np.dot(w, [s.get("alpha", 0.0) or 0.0 for s in stocks]))
    mdd   = float(np.dot(w, [s.get("max_drawdown", -0.30) or -0.30 for s in stocks]))
    sharpe= (ret - RF) / max(vol, 0.001)
    calmar= ret / max(abs(mdd), 0.001)
    hhi   = float(np.dot(w, w))

    # Prefer the real backtest whenever the returns matrix is available, so the
    # table numbers and the equity curve on the Compare tab describe the same
    # portfolio.
    real = _real_metrics(w, tickers, returns_df, bm_returns)
    exact = real is not None
    if exact:
        ret    = real["ret"]
        vol    = real["vol"]
        mdd    = real["mdd"]
        sharpe = real["sharpe"]
        calmar = real["calmar"]
        beta   = real.get("beta",  beta)
        alpha  = real.get("alpha", alpha)

    # Fundamental composite — a weighted average over the stocks that actually
    # HAVE a score. Names flagged insufficient_data must not be folded in as 0,
    # which would read as "worst possible business" and penalise any strategy
    # holding a thinly-covered name.
    fund_scores = [s.get("fundamental_score") or s.get("composite_score") or 0 for s in stocks]
    scored_mask = np.array([fs > 0 for fs in fund_scores], dtype=float)
    scored_w    = w * scored_mask
    scored_wsum = float(scored_w.sum())
    has_fund    = scored_wsum > 0
    fund_composite = (float(np.dot(scored_w, fund_scores)) / scored_wsum) if has_fund else 0.0
    fund_coverage  = round(scored_wsum * 100, 1)   # % of portfolio weight scored

    flags = []
    if beta   > 1.60:  flags.append({"label": f"High Beta {beta:.2f}",           "color": "#ffaa18"})
    if abs(mdd)>0.55:  flags.append({"label": f"Deep MDD {mdd*100:.0f}%",        "color": "#ff3558"})
    neg_a = sum(1 for s, wi in zip(stocks, w) if (s.get("alpha") or 0) < 0 and wi > 0.03)
    if neg_a > 2:      flags.append({"label": f"{neg_a} neg-alpha positions",    "color": "#ff3558"})
    if hhi   > 0.12:   flags.append({"label": "Concentrated (HHI>0.12)",          "color": "#ffaa18"})
    if sharpe > 1.5:   flags.append({"label": "Excellent Sharpe ✓",              "color": "#1ddb82"})
    if alpha  > 0.25:  flags.append({"label": f"Strong alpha {alpha*100:.0f}% ✓","color": "#1ddb82"})
    if has_fund:
        if fund_composite < 45:
            flags.append({"label": f"Weak fundamentals avg {fund_composite:.0f}/100", "color": "#ff3558"})
        elif fund_composite > 70:
            flags.append({"label": f"Strong fundamentals avg {fund_composite:.0f}/100 ✓", "color": "#1ddb82"})

    # Score blends price + fundamental quality when available
    fund_bonus = fund_composite * 0.30 if has_fund else 0
    score = sharpe*35 + calmar*12 + alpha*18 + fund_bonus - abs(mdd)*10 - hhi*25 + \
            (5 if horizon == "Long" else 2 if horizon == "Medium" else 0)

    top_w = sorted([{
        "ticker":            s["ticker"],
        "theme":             s.get("theme", "Custom"),
        "weight":            float(wi),
        "fundamental_grade": s.get("fundamental_grade") or s.get("grade") or "",
        "fundamental_score": s.get("fundamental_score") or s.get("composite_score") or 0,
        "verdict":           s.get("fundamental_verdict") or s.get("verdict") or "",
    } for s, wi in zip(stocks, w)], key=lambda x: -x["weight"])[:7]

    return {"name": name, "style": style, "horizon": horizon, "desc": desc,
            "ret": ret, "vol": vol, "beta": beta, "alpha": alpha, "mdd": mdd,
            "sharpe": sharpe, "calmar": calmar, "hhi": hhi,
            "fund_composite": round(fund_composite, 1),
            "has_fundamentals": has_fund,
            "fund_coverage": fund_coverage,
            # True when ret/vol/mdd/sharpe came from a real backtest of these
            # weights; False when they fall back to weighted per-stock averages.
            "exact_metrics": exact,
            "score": round(score, 2), "flags": flags, "top_weights": top_w,
            # full weight vector aligned to the input `stocks` order — used for
            # the real per-strategy backtest in server.py /api/run.
            "weights": [float(x) for x in w],
            "tickers": [s["ticker"] for s in stocks]}


def build_named_portfolio(stocks: list[dict],
                          weight_map: dict[str, float],
                          name: str, style: str, horizon: str, desc: str,
                          returns_df: pd.DataFrame | None = None,
                          bm_returns: pd.Series | None = None,
                          cap: float | None = None,
                          **extra) -> dict | None:
    """
    Score an explicitly-weighted book with the same engine as the generated
    strategies, so it can be ranked alongside them.

    Used for "Your Portfolio" (the user's real allocation) and "Conviction
    Weighted" (the sizing timeline.py already recommends). `cap=None` means no
    position cap — a real book is reported as held, not clipped to look tidier.
    """
    if len(stocks) < 2:
        return None
    raw = np.array([max(float(weight_map.get(s["ticker"], 0.0) or 0.0), 0.0)
                    for s in stocks], dtype=float)
    if raw.sum() <= 0:
        return None
    w = _norm(raw, cap=cap) if cap else raw / raw.sum()
    combo = _build(stocks, w, name, style, horizon, desc,
                   returns_df=returns_df, bm_returns=bm_returns)
    combo.update(extra)
    return combo


def generate_combinations(stocks: list[dict],
                          returns_df: pd.DataFrame | None = None,
                          bm_returns: pd.Series | None = None) -> list[dict]:
    """Generate 10 distinct portfolio strategies and rank best→worst.

    Pass `returns_df` (daily returns, columns = tickers) and `bm_returns` to get
    real backtested risk stats instead of weighted per-stock averages.
    """
    if len(stocks) < 2:
        return []
    n = len(stocks)

    def mk(fn):
        return _norm([max(fn(s), 1e-6) for s in stocks])

    def _B(*a):
        return _build(*a, returns_df=returns_df, bm_returns=bm_returns)

    combos = [
        _B(stocks, mk(lambda s: max(s.get("sharpe",0),0.001)/max(s.get("annualized_volatility",0.3),0.01)),
               "Max Sharpe",       "Optimized",    "Long",
               "Weights by Sharpe/vol ratio — tangency portfolio on the efficient frontier."),

        _B(stocks, mk(lambda s: max(s.get("sharpe",0),0.001)),
               "Quality Focus",    "Optimized",    "Long",
               "Overweights high-Sharpe stocks. Favors proven risk/reward over raw return."),

        _B(stocks, mk(lambda s: max(s.get("alpha",0),0.001)),
               "Alpha Hunters",    "Factor",       "Long",
               "Concentrated on stocks with the highest Jensen's Alpha."),

        _B(stocks, _norm([3.5/n if s.get("theme") in ("Nuclear","LNG") else 0.4/n for s in stocks]),
               "Energy Overweight","Thematic",     "Long",
               "3.5× tilt into Nuclear + LNG. Energy transition + LNG export tailwinds."),

        _B(stocks, mk(lambda s: 1/max(s.get("annualized_volatility",0.3),0.01)),
               "Risk Parity",      "Balanced",     "Long",
               "Inverse-vol weights — each stock contributes equally to portfolio risk."),

        _B(stocks, mk(lambda s: 1/max(s.get("annualized_volatility",0.3)*s.get("beta",1),0.01)),
               "Defensive",        "Conservative", "Long",
               "Inverse vol×beta. Capital preservation, reduced drawdown exposure."),

        _B(stocks, np.array([1/n]*n),
               "Equal Weight",     "Baseline",     "Medium",
               "1/N allocation — the naive benchmark. Surprisingly hard to beat."),

        _B(stocks, _norm([4/n if s.get("theme")=="AI" else 0.4/n for s in stocks]),
               "AI Overweight",    "Thematic",     "Medium",
               "4× tilt into AI (NVDA, ASML, AVGO, GOOGL). High growth, elevated vol."),

        _B(stocks, mk(lambda s: max(s.get("annualized_return",0),0.001)),
               "Momentum Tilt",    "Aggressive",   "Short",
               "Overweights highest recent returners. Needs active monitoring."),

        _B(stocks, mk(lambda s: max(s.get("annualized_return",0)*s.get("annualized_volatility",0.3),0.001)),
               "Speculation",      "Aggressive",   "Short",
               "Maximizes return × vol exposure. Extreme upside and drawdown risk."),
    ]
    return sorted(combos, key=lambda x: -x["score"])


# ── Watchlist signals ──────────────────────────────────────────────────────────
def generate_watchlist(stocks: list[dict]) -> list[dict]:
    signals = []
    for s in stocks:
        if "error" in s:
            continue
        t    = s["ticker"]
        th   = s.get("theme", "Custom")
        ret  = s.get("annualized_return",   0) or 0
        vol  = s.get("annualized_volatility",0.3) or 0.3
        sh   = s.get("sharpe",  0) or 0
        al   = s.get("alpha",   0) or 0
        bv   = s.get("beta",  1.0) or 1.0
        mdd  = abs(s.get("max_drawdown", 0.3) or 0.3)
        cal  = s.get("calmar",  0) or 0
        ir   = s.get("information_ratio", 0) or 0
        uc   = s.get("upside_capture",  1.0) or 1.0
        dc   = s.get("downside_capture",1.0) or 1.0

        if al > 0.08 and sh < 0.8:
            signals.append({"ticker":t,"theme":th,"type":"BUY_WATCH","priority":"HIGH",
                "title":"High Alpha, Inefficient Risk",
                "desc":f"Alpha {al*100:.1f}% but Sharpe only {sh:.2f}. Strong potential not yet reflected in risk-adjusted returns.",
                "action":f"Watch for volatility compression. If vol drops below {vol*100:.0f}%, risk-adjusted case strengthens."})

        if ret > 0.35 and sh > 1.0:
            signals.append({"ticker":t,"theme":th,"type":"MOMENTUM","priority":"HIGH",
                "title":"Momentum Leader",
                "desc":f"{ret*100:.0f}% annualized return with Sharpe {sh:.2f}. Upside capture {uc*100:.0f}%.",
                "action":"Consider overweighting. Set trailing stop at max-drawdown level to protect gains."})

        hs = s.get("horizon", {})
        if isinstance(hs, dict) and hs.get("long", 0) > 78 and sh > 1.0 and al > 0.05:
            signals.append({"ticker":t,"theme":th,"type":"BUY_WATCH","priority":"HIGH",
                "title":"Long-Term Compounder",
                "desc":f"Horizon score {hs['long']:.0f}/100. Sharpe {sh:.2f}, Alpha {al*100:.1f}%, Calmar {cal:.2f}.",
                "action":"Core holding candidate. Add on dips. Target 5-8% allocation."})

        if al > 0.06 and bv < 0.70 and sh > 0.7:
            signals.append({"ticker":t,"theme":th,"type":"UNDERVALUED","priority":"MEDIUM",
                "title":"Low-Beta Alpha Generator",
                "desc":f"Beta {bv:.2f} with alpha {al*100:.1f}%. Returns largely independent of market.",
                "action":"Excellent diversifier. Increases portfolio Sharpe. Consider raising weight."})

        if vol > 0.55 and al < 0 and sh < 0.3:
            signals.append({"ticker":t,"theme":th,"type":"RISK_FLAG","priority":"HIGH",
                "title":"High Risk, Negative Alpha",
                "desc":f"Vol {vol*100:.0f}%, Alpha {al*100:.1f}%, Sharpe {sh:.2f}. Taking risk without reward.",
                "action":"Reduce position. Only hold with specific near-term catalyst."})

        if sh < 0 and ret < 0:
            signals.append({"ticker":t,"theme":th,"type":"DRAG","priority":"HIGH",
                "title":"Portfolio Drag",
                "desc":f"Negative return ({ret*100:.1f}%) and Sharpe ({sh:.2f}). Reduces portfolio efficiency.",
                "action":"Re-evaluate thesis. Rotate capital into higher-Sharpe alternatives."})

        if mdd > 0.60 and cal < 0.4:
            signals.append({"ticker":t,"theme":th,"type":"RISK_FLAG","priority":"HIGH",
                "title":"Extreme Drawdown Risk",
                "desc":f"Max drawdown {mdd*100:.0f}%, Calmar {cal:.2f}. Return doesn't justify historical pain.",
                "action":"Keep position <2%. Only hold if speculative upside justifies exposure."})

        if uc > 1.20 and dc < 0.90:
            signals.append({"ticker":t,"theme":th,"type":"MOMENTUM","priority":"MEDIUM",
                "title":"Asymmetric Capture",
                "desc":f"Upside {uc*100:.0f}% vs downside {dc*100:.0f}%. Outperforms in bull, limits bear losses.",
                "action":"Ideal profile. Increase weight during market uptrends."})

        if ir > 0.8:
            signals.append({"ticker":t,"theme":th,"type":"UNDERVALUED","priority":"MEDIUM",
                "title":"High Information Ratio",
                "desc":f"IR {ir:.2f} — consistent alpha vs tracking error. Structural edge.",
                "action":"Strong signal of structural outperformance. Consider as core holding."})

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(signals, key=lambda x: order[x["priority"]])


# ── Efficient frontier ─────────────────────────────────────────────────────────
def efficient_frontier(returns_df: pd.DataFrame, n_points: int = 50) -> list[dict]:
    if returns_df.empty or len(returns_df.columns) < 2:
        return []
    mu  = returns_df.mean().values * TRADING_DAYS
    cov = returns_df.cov().values  * TRADING_DAYS
    n   = len(mu)
    w0  = np.array([1/n]*n)
    bounds = [(0.005, 0.40)] * n

    min_ret = float(np.min(mu)) * 0.5
    max_ret = float(np.max(mu)) * 0.95
    targets = np.linspace(min_ret, max_ret, n_points)

    frontier = []
    for target in targets:
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1},
                {"type": "eq", "fun": lambda w, t=target: float(w @ mu) - t}]
        res = minimize(lambda w: float(np.sqrt(w @ cov @ w)),
                       w0, method="SLSQP", bounds=bounds, constraints=cons,
                       options={"maxiter": 400, "ftol": 1e-8})
        if res.success:
            v  = float(np.sqrt(res.x @ cov @ res.x))
            sh = (target - RF) / max(v, 1e-8)
            frontier.append({"ret": round(target, 4), "vol": round(v, 4),
                              "sharpe": round(sh, 4)})
    return frontier


# ── Fundamental-aware strategy builders ──────────────────────────────────────
def generate_combinations_with_fundamentals(
    stocks: list[dict],
    fund_data: dict,
    returns_df: pd.DataFrame | None = None,
    bm_returns: pd.Series | None = None,
) -> list[dict]:
    """
    Like generate_combinations() but merges in fundamental scores first,
    enabling fundamental-weighted strategies and blended scoring.

    fund_data: {ticker: fundamental_dict} from fundamentals.compute_fundamentals()
    """
    # Merge fundamental data into each stock dict (non-destructive copy)
    enriched = []
    for s in stocks:
        ticker = s["ticker"]
        fd = fund_data.get(ticker, {})
        merged = dict(s)
        merged["fundamental_score"]   = fd.get("composite_score", 0) or 0
        merged["fundamental_grade"]   = fd.get("composite_grade", "") or ""
        merged["fundamental_verdict"] = fd.get("verdict", "") or ""
        # Individual dimension scores
        merged["val_score"]  = (fd.get("valuation")    or {}).get("score", 0) or 0
        merged["prof_score"] = (fd.get("profitability") or {}).get("score", 0) or 0
        merged["hlth_score"] = (fd.get("health")        or {}).get("score", 0) or 0
        merged["grw_score"]  = (fd.get("growth")        or {}).get("score", 0) or 0
        merged["qlty_score"] = (fd.get("quality")       or {}).get("score", 0) or 0
        enriched.append(merged)

    if len(enriched) < 2:
        return []
    n = len(enriched)

    def mk(fn):
        return _norm([max(fn(s), 1e-6) for s in enriched])

    def _B(*a):
        return _build(*a, returns_df=returns_df, bm_returns=bm_returns)

    combos = [
        _B(enriched, mk(lambda s: max(s.get("sharpe",0),0.001)/max(s.get("annualized_volatility",0.3),0.01)),
               "Max Sharpe",           "Optimized",    "Long",
               "Weights by Sharpe/vol ratio — tangency portfolio on the efficient frontier."),

        _B(enriched, mk(lambda s: max(s.get("fundamental_score",0),1)/100),
               "Fundamental Leaders",  "Factor",       "Long",
               "Overweights stocks with strongest composite fundamental scores (valuation + profitability + health + growth + quality). Eliminates loss-makers."),

        _B(enriched, mk(lambda s: max(s.get("prof_score",0),1)/100),
               "Profitability Focus",  "Factor",       "Long",
               "Weights by profitability score. Favors high-margin, high-ROIC compounders."),

        _B(enriched, mk(lambda s: max(s.get("val_score",0),1)/100),
               "Value Play",           "Factor",       "Long",
               "Overweights most undervalued stocks by P/E, EV/EBITDA, and DCF margin of safety."),

        _B(enriched, mk(lambda s: max(s.get("grw_score",0),1)/100),
               "Growth Tilt",          "Factor",       "Medium",
               "Weights by growth score — revenue and earnings momentum leaders."),

        _B(enriched, mk(lambda s: 1/max(s.get("annualized_volatility",0.3),0.01)),
               "Risk Parity",          "Balanced",     "Long",
               "Inverse-vol weights — each stock contributes equally to portfolio risk."),

        _B(enriched, mk(lambda s: max(s.get("hlth_score",0),1)/100),
               "Fortress Balance Sheet","Conservative", "Long",
               "Overweights stocks with strongest financial health — lowest debt, highest coverage ratios."),

        _B(enriched, np.array([1/n]*n),
               "Equal Weight",         "Baseline",     "Medium",
               "1/N allocation — the naive benchmark. Surprisingly hard to beat consistently."),

        _B(enriched, _norm([4/n if s.get("theme")=="AI" else 0.4/n for s in enriched]),
               "AI Overweight",        "Thematic",     "Medium",
               "4× tilt into AI theme. High growth but elevated volatility."),

        _B(enriched, mk(lambda s: max(s.get("annualized_return",0),0.001)),
               "Momentum Tilt",        "Aggressive",   "Short",
               "Overweights highest recent returners. Needs active monitoring."),
    ]
    return sorted(combos, key=lambda x: -x["score"])
