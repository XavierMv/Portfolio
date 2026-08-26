"""
analytics.py  –  Portfolio Analytics Engine
All metric computation. Pure math, no I/O.
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Optional

TRADING_DAYS = 252
RF = 0.043          # risk-free rate (~4.3 % T-bill)


# ── returns ────────────────────────────────────────────────────────────────────
def calc_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def total_return(prices: pd.Series) -> float:
    return float((prices.iloc[-1] / prices.iloc[0]) - 1)


def annualized_return(prices: pd.Series) -> float:
    tot  = total_return(prices)
    # n prices span n-1 periods of growth: a 2-bar series is one day, not two.
    yrs  = (len(prices) - 1) / TRADING_DAYS
    return float((1 + tot) ** (1 / max(yrs, 0.01)) - 1)


# ── volatility ─────────────────────────────────────────────────────────────────
def ann_vol(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(TRADING_DAYS))


def downside_dev(returns: pd.Series, mar: float = RF) -> float:
    daily_mar = mar / TRADING_DAYS
    neg = returns[returns < daily_mar] - daily_mar
    return float(np.sqrt((neg ** 2).sum() / max(len(returns), 1)) * np.sqrt(TRADING_DAYS))


# ── ratios ─────────────────────────────────────────────────────────────────────
def _geom_annual(returns: pd.Series) -> float:
    """Annualized geometric (compound) return of a daily-returns series.

    Compounding the arithmetic daily mean — (1+mean)^252 − 1 — ignores
    volatility drag and ran several points above the CAGR shown in the UI
    (8pp on a 33%-vol series). Every ratio here now uses the same geometric
    figure as annualized_return()/calmar(), and matches how
    combinations._real_metrics already builds strategy Sharpe."""
    n = max(len(returns), 1)
    return float((1 + returns).prod() ** (TRADING_DAYS / n) - 1)


def sharpe(returns: pd.Series) -> float:
    ar  = _geom_annual(returns)
    vol = ann_vol(returns)
    return float((ar - RF) / vol) if vol > 0 else float("nan")


def sortino(returns: pd.Series) -> float:
    ar = _geom_annual(returns)
    dd = downside_dev(returns)
    return float((ar - RF) / dd) if dd > 0 else float("nan")


def calmar(prices: pd.Series) -> float:
    mdd = max_drawdown(prices)
    ar  = annualized_return(prices)
    return float(ar / abs(mdd)) if mdd != 0 else float("nan")


def treynor(returns: pd.Series, bm_returns: pd.Series) -> float:
    b   = beta(returns, bm_returns)
    ar  = _geom_annual(returns)
    return float((ar - RF) / b) if b and b != 0 else float("nan")


def information_ratio(returns: pd.Series, bm_returns: pd.Series) -> float:
    r, b  = returns.align(bm_returns, join="inner")
    exc   = r - b
    te    = exc.std() * np.sqrt(TRADING_DAYS)
    return float((exc.mean() * TRADING_DAYS) / te) if te > 0 else float("nan")


# ── factor ─────────────────────────────────────────────────────────────────────
def beta(returns: pd.Series, bm_returns: pd.Series) -> float:
    r, b = returns.align(bm_returns, join="inner")
    if len(r) < 5:
        return float("nan")
    cov = np.cov(r, b)
    return float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else float("nan")


def alpha(returns: pd.Series, bm_returns: pd.Series) -> float:
    b_val = beta(returns, bm_returns)
    if np.isnan(b_val):
        return float("nan")
    r, bm  = returns.align(bm_returns, join="inner")
    ar     = float((1 + r.mean()) ** TRADING_DAYS - 1)
    bm_ar  = float((1 + bm.mean()) ** TRADING_DAYS - 1)
    return float(ar - (RF + b_val * (bm_ar - RF)))


def r_squared(returns: pd.Series, bm_returns: pd.Series) -> float:
    r, b = returns.align(bm_returns, join="inner")
    if len(r) < 5:
        return float("nan")
    corr, _ = stats.pearsonr(r, b)
    return float(corr ** 2)


# ── drawdown ───────────────────────────────────────────────────────────────────
def max_drawdown(prices: pd.Series) -> float:
    peak = prices.cummax()
    dd   = (prices - peak) / peak
    return float(dd.min())


def drawdown_series(prices: pd.Series) -> pd.Series:
    return (prices - prices.cummax()) / prices.cummax()


def ulcer_index(prices: pd.Series) -> float:
    dd = drawdown_series(prices) * 100
    return float(np.sqrt((dd ** 2).mean()))


def recovery_factor(prices: pd.Series) -> float:
    mdd = abs(max_drawdown(prices))
    return float(total_return(prices) / mdd) if mdd > 0 else float("nan")


# ── VaR ────────────────────────────────────────────────────────────────────────
def var_hist(returns: pd.Series, conf: float = 0.95) -> float:
    return float(-np.percentile(returns, (1 - conf) * 100))


def cvar_hist(returns: pd.Series, conf: float = 0.95) -> float:
    v   = var_hist(returns, conf)
    bad = returns[returns <= -v]
    return float(-bad.mean()) if len(bad) > 0 else float("nan")


def var_param(returns: pd.Series, conf: float = 0.95) -> float:
    mu, sig = returns.mean(), returns.std()
    z = stats.norm.ppf(1 - conf)
    return float(-(mu + z * sig))


# ── capture ────────────────────────────────────────────────────────────────────
def upside_capture(returns: pd.Series, bm_returns: pd.Series) -> float:
    r, b = returns.align(bm_returns, join="inner")
    up   = b > 0
    if up.sum() == 0:
        return float("nan")
    # Ratio of AVERAGE up-day returns. Both the previous annualized form
    # ((1+g)^252-1 each side) and a cumulative-product ratio explode at daily
    # frequency over multi-year windows — a 2x-daily-beta fund shows ~10x and
    # ~26x respectively, when every consumer of this number (horizon_score at
    # 1.30, the watchlist at 1.20, timeline entry checks at 1.15) treats it as
    # O(1). The mean ratio is horizon-independent: self-capture is exactly 1.0
    # and a 2x-beta fund is exactly 2.0.
    br = float(b[up].mean())
    return float(r[up].mean() / br) if br != 0 else float("nan")


def downside_capture(returns: pd.Series, bm_returns: pd.Series) -> float:
    r, b = returns.align(bm_returns, join="inner")
    dn   = b < 0
    if dn.sum() == 0:
        return float("nan")
    br = float(b[dn].mean())
    return float(r[dn].mean() / br) if br != 0 else float("nan")


# ── diversification ────────────────────────────────────────────────────────────
def hhi(weights: np.ndarray) -> float:
    return float(np.sum(weights ** 2))


def div_ratio(weights: np.ndarray, vols: np.ndarray, port_vol: float) -> float:
    return float(np.dot(weights, vols) / port_vol) if port_vol > 0 else float("nan")


def effective_n(weights: np.ndarray) -> float:
    h = hhi(weights)
    return float(1 / h) if h > 0 else float("nan")


# ── horizon scoring ────────────────────────────────────────────────────────────
def horizon_score(m: dict) -> dict:
    """Return short/medium/long scores 0-100 for a stock metrics dict."""
    vol_v   = m.get("annualized_volatility", 0.30) or 0.30
    beta_v  = m.get("beta",     1.0)  or 1.0
    sharpe_v= m.get("sharpe",   0.0)  or 0.0
    sortino_v=m.get("sortino",  0.0)  or 0.0
    mdd_v   = abs(m.get("max_drawdown", 0.30) or 0.30)
    alpha_v = m.get("alpha",    0.0)  or 0.0
    ret_v   = m.get("annualized_return", 0.0) or 0.0
    calmar_v= m.get("calmar",   0.0)  or 0.0
    ulcer_v = m.get("ulcer_index", 10.0) or 10.0
    up_cap  = m.get("upside_capture", 1.0) or 1.0

    s_short  = 50.0
    s_medium = 50.0
    s_long   = 50.0

    # Short signals
    if ret_v   > 0.35:          s_short += 20
    elif ret_v < -0.10:         s_short -= 15
    if beta_v  > 1.40:          s_short += 15
    elif beta_v < 0.70:         s_short -= 10
    if vol_v   > 0.50:          s_short += 12
    elif vol_v < 0.20:          s_short -= 8
    if up_cap  > 1.30:          s_short += 8
    if mdd_v   > 0.60:          s_short -= 12

    # Medium signals
    if 0.5 <= sharpe_v < 2.0:   s_medium += 18
    elif sharpe_v < 0:          s_medium -= 15
    if 0.20 <= vol_v <= 0.50:   s_medium += 12
    if 0.80 <= beta_v <= 1.40:  s_medium += 10
    if alpha_v > 0:              s_medium += 12
    else:                        s_medium -= 8
    if mdd_v > 0.45:             s_medium -= 10

    # Long signals
    if sharpe_v >= 1.0:          s_long += 22
    elif sharpe_v < 0.5:         s_long -= 18
    if vol_v < 0.20:             s_long += 15
    elif vol_v > 0.50:           s_long -= 12
    if alpha_v > 0.05:           s_long += 18
    elif alpha_v < 0:            s_long -= 15
    if mdd_v < 0.20:             s_long += 12
    elif mdd_v > 0.45:           s_long -= 15
    if calmar_v > 1.0:           s_long += 10
    if ulcer_v < 8:              s_long += 8
    elif ulcer_v > 20:           s_long -= 10
    if sortino_v > 1.5:          s_long += 8

    s_short  = float(np.clip(s_short,  0, 100))
    s_medium = float(np.clip(s_medium, 0, 100))
    s_long   = float(np.clip(s_long,   0, 100))

    best = max([("Short", s_short), ("Medium", s_medium), ("Long", s_long)],
               key=lambda x: x[1])[0]

    return {"short": s_short, "medium": s_medium, "long": s_long, "best": best}


# ── per-stock metrics ──────────────────────────────────────────────────────────
def compute_stock_metrics(ticker: str, prices: pd.Series,
                           bm_returns: pd.Series, theme: str = "Custom") -> dict:
    if prices is None or len(prices) < 20:
        return {"ticker": ticker, "theme": theme, "error": "Insufficient data"}

    returns = calc_returns(prices)
    m = {
        "ticker":               ticker,
        "theme":                theme,
        "total_return":         total_return(prices),
        "annualized_return":    annualized_return(prices),
        "annualized_volatility":ann_vol(returns),
        "sharpe":               sharpe(returns),
        "sortino":              sortino(returns),
        "calmar":               calmar(prices),
        "treynor":              treynor(returns, bm_returns),
        "information_ratio":    information_ratio(returns, bm_returns),
        "beta":                 beta(returns, bm_returns),
        "alpha":                alpha(returns, bm_returns),
        "r_squared":            r_squared(returns, bm_returns),
        "max_drawdown":         max_drawdown(prices),
        "ulcer_index":          ulcer_index(prices),
        "recovery_factor":      recovery_factor(prices),
        "var_95":               var_hist(returns, 0.95),
        "cvar_95":              cvar_hist(returns, 0.95),
        "var_99":               var_hist(returns, 0.99),
        "upside_capture":       upside_capture(returns, bm_returns),
        "downside_capture":     downside_capture(returns, bm_returns),
        "_prices":              prices,
        "_returns":             returns,
    }
    m["horizon"] = horizon_score(m)
    return m


# ── portfolio-level metrics ────────────────────────────────────────────────────
def compute_portfolio_metrics(stock_metrics: list, bm_returns: pd.Series,
                               weights: dict | None = None) -> dict:
    """
    Portfolio-level metrics.

    `weights` maps ticker -> relative size (dollars, shares, or percent — it is
    normalized either way). Omit it for the equal-weight default. Without real
    weights, HHI is always 1/n and Effective N is always n, so those two metrics
    cannot say anything about the actual book.
    """
    valid = [m for m in stock_metrics if "error" not in m]
    if not valid:
        return {}

    n = len(valid)
    if weights:
        w = np.array([max(float(weights.get(m["ticker"], 0.0) or 0.0), 0.0)
                      for m in valid], dtype=float)
        w = np.array([1 / n] * n) if w.sum() <= 0 else w / w.sum()
        weighting = "custom"
    else:
        w = np.array([1 / n] * n)
        weighting = "equal"

    # A single short-history holding (a recent IPO such as OKLO or LUNR) must not
    # decide the window for everything else. `dropna()` keeps only dates where
    # EVERY holding traded, which silently throws away years of history for the
    # rest of the book and rewrites every portfolio-level metric.
    #
    # Instead, keep the full union of dates and rebalance across whichever names
    # are actually trading on each date: a stock joins the portfolio the day its
    # history starts. Weights are renormalized per-date so they always sum to 1.
    raw_df = pd.DataFrame({m["ticker"]: m["_returns"] for m in valid}).sort_index()

    present = raw_df.notna().values.astype(float)          # (T, n) availability mask
    wmat    = present * w                                   # zero-out absent names
    wsum    = wmat.sum(axis=1, keepdims=True)
    active  = wsum[:, 0] > 0
    wmat    = np.divide(wmat, np.where(wsum == 0, 1.0, wsum))

    port_vals = np.nansum(np.nan_to_num(raw_df.values, nan=0.0) * wmat, axis=1)
    port_returns = pd.Series(port_vals[active], index=raw_df.index[active])

    # `returns_df` still drives the covariance-based tools (efficient frontier,
    # strategy backtests), which need a complete rectangular matrix. Use the
    # longest window that keeps every holding, and report the coverage gap.
    returns_df   = raw_df.dropna()
    full_span    = int(len(port_returns))
    common_span  = int(len(returns_df))

    if port_returns.empty:
        return {}
    # Anchor the series at 100 one bar before the first return. Starting it at
    # 100*(1+r0) silently dropped day 0 from total_return / max_drawdown —
    # combinations._real_metrics compounds the same returns and never did.
    _anchor = port_returns.index[0] - pd.offsets.BDay(1)
    port_prices  = pd.concat([pd.Series([1.0], index=[_anchor]),
                              (1.0 + port_returns).cumprod()]) * 100

    vols     = np.array([m["annualized_volatility"] for m in valid])
    port_vol = ann_vol(port_returns)
    # pairwise-complete — a short-history name shouldn't blank the whole matrix
    corr_mat = raw_df.corr(min_periods=20)

    return {
        "total_return":         total_return(port_prices),
        "annualized_return":    annualized_return(port_prices),
        "annualized_volatility":port_vol,
        "sharpe":               sharpe(port_returns),
        "sortino":              sortino(port_returns),
        "calmar":               calmar(port_prices),
        "treynor":              treynor(port_returns, bm_returns),
        "information_ratio":    information_ratio(port_returns, bm_returns),
        "beta":                 beta(port_returns, bm_returns),
        "alpha":                alpha(port_returns, bm_returns),
        "r_squared":            r_squared(port_returns, bm_returns),
        "max_drawdown":         max_drawdown(port_prices),
        "ulcer_index":          ulcer_index(port_prices),
        "var_95":               var_hist(port_returns, 0.95),
        "cvar_95":              cvar_hist(port_returns, 0.95),
        "var_99":               var_hist(port_returns, 0.99),
        "upside_capture":       upside_capture(port_returns, bm_returns),
        "downside_capture":     downside_capture(port_returns, bm_returns),
        "hhi":                  hhi(w),
        "div_ratio":            div_ratio(w, vols, port_vol),
        "effective_n":          effective_n(w),
        # How much history each view rests on. `common_days` < `history_days`
        # means at least one holding is younger than the lookback, so the
        # covariance-based views (frontier, strategy backtests) see less data
        # than the portfolio curve does.
        "history_days":         full_span,
        "common_days":          common_span,
        # "equal" = no sizes supplied, so HHI/effective_n are structural
        # constants; "custom" = derived from the real allocation.
        "weighting":            weighting,
        "weights_map":          {m["ticker"]: float(wi) for m, wi in zip(valid, w)},
        "_port_prices":         port_prices,
        "_port_returns":        port_returns,
        "_corr_matrix":         corr_mat,
        "_returns_df":          returns_df,
        "_weights":             w,
        "_tickers":             [m["ticker"] for m in valid],
    }
