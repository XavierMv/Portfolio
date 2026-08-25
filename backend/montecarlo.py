"""
montecarlo.py — Monte Carlo simulation for portfolio & per-stock outcomes.
Portfolio Analyzer Discovery (May 2026).

Simulates thousands of future price paths using Geometric Brownian Motion (GBM)
calibrated to each holding's historical drift and volatility, with a correlated
multivariate model at the portfolio level so diversification is captured honestly.

Produces, over a chosen horizon:
  • outcome RANGES — percentile bands (P5/P25/P50/P75/P95) of ending value
  • goal/risk PROBABILITIES — P(reaching a target return), P(loss), P(deep drawdown),
    expected CAGR, value-at-risk, and a risk/return verdict that can feed the
    investment decision trigger.

This is EQUITY portfolio logic — not options. It models where your holdings
(and discovered candidates) could realistically end up, so position decisions
rest on a distribution of outcomes rather than a single point estimate.

Honest limits (stated plainly in the UI too):
  - GBM assumes lognormal returns with constant drift/vol — real markets have fat
    tails and regime shifts, so extreme outcomes are understated.
  - Drift estimated from history is a weak predictor of the future; the module
    therefore offers a 'dampened drift' option that shrinks historical drift toward
    a conservative market assumption.
  - It is a probabilistic model, not a forecast. Educational, not advice.
"""
import math
import numpy as np

TRADING_DAYS = 252
DEFAULT_PATHS = 10000


def _annualize_from_prices(prices: np.ndarray):
    """Return (annual drift mu, annual vol sigma) from a daily price series."""
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    if len(prices) < 30:
        return None, None
    log_ret = np.diff(np.log(prices))
    mu_d = np.mean(log_ret)
    sd_d = np.std(log_ret, ddof=1)
    mu = mu_d * TRADING_DAYS
    sigma = sd_d * math.sqrt(TRADING_DAYS)
    return float(mu), float(sigma)


def _dampen_drift(mu, sigma, mode="dampened"):
    """
    Drift handling. Historical drift is a noisy predictor; offer three modes:
      raw       — use historical mu as-is (most optimistic for past winners)
      dampened  — shrink historical mu halfway toward a conservative market drift
      market    — ignore history, use a flat market-like drift
    A risk premium of ~5% over the modeled vol is a reasonable conservative anchor.
    """
    market_mu = 0.07  # conservative long-run nominal equity drift
    if mode == "raw":
        return mu
    if mode == "market":
        return market_mu
    # dampened (default): halfway between history and market, capped so a single
    # hot stock doesn't imply implausible compounding
    blended = 0.5 * mu + 0.5 * market_mu
    return float(max(-0.10, min(blended, 0.30)))


def simulate_stock(prices, horizon_years=5.0, n_paths=DEFAULT_PATHS,
                   drift_mode="dampened", target_return=None, seed=None):
    """
    Simulate a single stock's ending multiple over the horizon via GBM.
    Returns percentile bands + goal/risk probabilities.
    target_return: e.g. 1.0 means "doubled" (100% gain). If None, uses 0.5 & 1.0 defaults.
    """
    mu_hist, sigma = _annualize_from_prices(prices)
    if mu_hist is None or sigma is None or sigma <= 0:
        return {"available": False, "reason": "insufficient price history for simulation"}

    mu = _dampen_drift(mu_hist, sigma, drift_mode)
    rng = np.random.default_rng(seed)
    T = max(0.1, float(horizon_years))
    steps = max(1, int(round(T * TRADING_DAYS)))
    dt = T / steps

    # GBM: simulate terminal multiple via sum of log-returns (vectorized over paths)
    drift_term = (mu - 0.5 * sigma ** 2) * dt
    vol_term = sigma * math.sqrt(dt)
    z = rng.standard_normal((n_paths, steps))
    log_paths = np.cumsum(drift_term + vol_term * z, axis=1)
    terminal_mult = np.exp(log_paths[:, -1])          # ending value / start
    # path min for drawdown analysis (relative to start)
    running_min = np.exp(np.minimum.accumulate(log_paths, axis=1)[:, -1])

    pctl = np.percentile(terminal_mult, [5, 25, 50, 75, 95])
    ann_cagr = terminal_mult ** (1.0 / T) - 1.0

    # goal/risk probabilities
    tgt = target_return if target_return is not None else 1.0
    prob_target = float(np.mean(terminal_mult - 1.0 >= tgt))
    prob_50 = float(np.mean(terminal_mult - 1.0 >= 0.5))
    prob_double = float(np.mean(terminal_mult >= 2.0))
    prob_loss = float(np.mean(terminal_mult < 1.0))
    prob_dd30 = float(np.mean(running_min <= 0.70))    # touched −30% at some point
    prob_dd50 = float(np.mean(running_min <= 0.50))
    var5_mult = float(np.percentile(terminal_mult, 5))  # 5th-pctile ending multiple

    return {
        "available": True,
        "drift_mode": drift_mode,
        "horizon_years": T,
        "n_paths": n_paths,
        "mu_historical": round(mu_hist, 4),
        "mu_used": round(mu, 4),
        "sigma": round(sigma, 4),
        "bands": {
            "p5": round(float(pctl[0]), 3), "p25": round(float(pctl[1]), 3),
            "p50": round(float(pctl[2]), 3), "p75": round(float(pctl[3]), 3),
            "p95": round(float(pctl[4]), 3),
        },
        "cagr": {
            "p5": round(float(np.percentile(ann_cagr, 5)) * 100, 1),
            "p50": round(float(np.percentile(ann_cagr, 50)) * 100, 1),
            "p95": round(float(np.percentile(ann_cagr, 95)) * 100, 1),
            "mean": round(float(np.mean(ann_cagr)) * 100, 1),
        },
        "prob_target": round(prob_target, 3),
        "target_return": tgt,
        "prob_50pct": round(prob_50, 3),
        "prob_double": round(prob_double, 3),
        "prob_loss": round(prob_loss, 3),
        "prob_drawdown_30": round(prob_dd30, 3),
        "prob_drawdown_50": round(prob_dd50, 3),
        "var5_ending_multiple": round(var5_mult, 3),
    }


def simulate_portfolio(price_df, weights=None, horizon_years=5.0,
                       n_paths=DEFAULT_PATHS, drift_mode="dampened",
                       target_return=0.5, seed=None):
    """
    Correlated multivariate GBM across all holdings. Captures diversification by
    using the empirical covariance of log-returns (Cholesky factorization).

    price_df: pandas DataFrame, columns = tickers, rows = dates (aligned closes).
    weights: dict ticker->weight or None (equal weight).
    Returns portfolio-level bands + goal/risk probabilities.
    """
    import pandas as pd
    df = price_df.dropna(how="any")
    tickers = list(df.columns)
    if len(tickers) < 1 or len(df) < 40:
        return {"available": False, "reason": "insufficient aligned price history"}

    log_ret = np.diff(np.log(df.values), axis=0)        # (days, assets)
    mu_d = log_ret.mean(axis=0)
    cov_d = np.cov(log_ret, rowvar=False)
    if cov_d.ndim == 0:                                  # single asset edge case
        cov_d = np.array([[float(cov_d)]])
        mu_d = np.array([float(mu_d)])

    # annualize drift, then dampen per-asset
    mu_ann = mu_d * TRADING_DAYS
    sigma_ann = np.sqrt(np.diag(cov_d) * TRADING_DAYS)
    mu_used = np.array([_dampen_drift(mu_ann[i], sigma_ann[i], drift_mode)
                        for i in range(len(tickers))])

    # weights
    if weights is None:
        w = np.array([1.0 / len(tickers)] * len(tickers))
    else:
        w = np.array([weights.get(t, 0.0) for t in tickers], dtype=float)
        if w.sum() == 0:
            w = np.array([1.0 / len(tickers)] * len(tickers))
        w = w / w.sum()

    rng = np.random.default_rng(seed)
    T = max(0.1, float(horizon_years))
    steps = max(1, int(round(T * TRADING_DAYS)))

    # One simulation step = one trading day. Use the empirical DAILY covariance
    # directly for correlated daily shocks (Cholesky factor L). Drift per day uses
    # the dampened annual drift divided by trading days, minus the Itô correction.
    cov_step = cov_d
    try:
        L = np.linalg.cholesky(cov_step + np.eye(len(tickers)) * 1e-12)
    except np.linalg.LinAlgError:
        # fallback: ignore correlation if covariance isn't positive-definite
        L = np.diag(np.sqrt(np.maximum(np.diag(cov_step), 1e-12)))

    drift_step = (mu_used / TRADING_DAYS) - 0.5 * np.diag(cov_step)

    # simulate path-by-path in chunks to control memory
    n_assets = len(tickers)
    port_terminal = np.empty(n_paths)
    port_runmin = np.empty(n_paths)
    chunk = 2000
    done = 0
    while done < n_paths:
        m = min(chunk, n_paths - done)
        # shocks: (m, steps, assets)
        z = rng.standard_normal((m, steps, n_assets))
        correlated = z @ L.T                              # apply correlation
        log_incr = drift_step + correlated                # broadcast drift
        cum = np.cumsum(log_incr, axis=1)                 # (m, steps, assets)
        asset_mult = np.exp(cum)                          # multiples through time
        # portfolio value through time = weighted sum of asset multiples (rebalanced-at-0)
        port_path = asset_mult @ w                        # (m, steps)
        port_terminal[done:done + m] = port_path[:, -1]
        port_runmin[done:done + m] = port_path.min(axis=1)
        done += m

    pctl = np.percentile(port_terminal, [5, 25, 50, 75, 95])
    ann_cagr = port_terminal ** (1.0 / T) - 1.0

    prob_target = float(np.mean(port_terminal - 1.0 >= target_return))
    prob_loss = float(np.mean(port_terminal < 1.0))
    prob_dd20 = float(np.mean(port_runmin <= 0.80))
    prob_dd30 = float(np.mean(port_runmin <= 0.70))
    var5 = float(np.percentile(port_terminal, 5))

    # risk/return verdict for the decision trigger
    median_cagr = float(np.percentile(ann_cagr, 50)) * 100
    downside = prob_loss
    verdict, vcolor = _portfolio_verdict(median_cagr, prob_target, prob_loss, prob_dd30)

    return {
        "available": True,
        "tickers": tickers, "n_paths": n_paths, "horizon_years": T,
        "drift_mode": drift_mode, "target_return": target_return,
        "bands": {
            "p5": round(float(pctl[0]), 3), "p25": round(float(pctl[1]), 3),
            "p50": round(float(pctl[2]), 3), "p75": round(float(pctl[3]), 3),
            "p95": round(float(pctl[4]), 3),
        },
        "cagr": {
            "p5": round(float(np.percentile(ann_cagr, 5)) * 100, 1),
            "p50": round(median_cagr, 1),
            "p95": round(float(np.percentile(ann_cagr, 95)) * 100, 1),
            "mean": round(float(np.mean(ann_cagr)) * 100, 1),
        },
        "prob_target": round(prob_target, 3),
        "prob_loss": round(prob_loss, 3),
        "prob_drawdown_20": round(prob_dd20, 3),
        "prob_drawdown_30": round(prob_dd30, 3),
        "var5_ending_multiple": round(var5, 3),
        "verdict": verdict, "verdict_color": vcolor,
    }


def _portfolio_verdict(median_cagr, prob_target, prob_loss, prob_dd30):
    """Map simulation outcomes to a risk/return verdict for the decision trigger."""
    # favorable: solid median CAGR, good odds of hitting target, low ruin risk
    score = 0
    score += min(median_cagr, 25) * 2          # up to 50
    score += prob_target * 30                  # up to 30
    score -= prob_loss * 25                     # penalize loss odds
    score -= prob_dd30 * 20                     # penalize deep-drawdown odds
    if score >= 55:
        return "FAVORABLE", "#12e87a"
    if score >= 35:
        return "BALANCED", "#ffb020"
    if score >= 18:
        return "RISKY", "#ff7043"
    return "UNFAVORABLE", "#ff2d55"


# simple verdict colors for frontend reuse
VERDICT_COLORS = {
    "FAVORABLE": "#12e87a", "BALANCED": "#ffb020",
    "RISKY": "#ff7043", "UNFAVORABLE": "#ff2d55",
}
