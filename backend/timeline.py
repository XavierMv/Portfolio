"""
timeline.py  —  Holding Timeline & Entry/Exit Guidance Engine

Extends horizon scoring with:
  • Specific holding period ranges (e.g. "6–18 months")
  • Entry condition checklist (when to add / initiate)
  • Exit trigger list (when to reduce / sell)
  • Catalyst calendar (upcoming events that matter)
  • Position sizing guidance based on conviction + risk
  • Portfolio-level timeline mix analysis
  • Rebalancing schedule recommendation
"""

import math
from datetime import date, timedelta
from typing import Optional

def _today() -> date:
    """Evaluated per call — a module-level constant would freeze the date at
    import time and drift on a server left running for days."""
    return date.today()


# ── Constants ──────────────────────────────────────────────────────────────────
HORIZON_RANGES = {
    # (min_months, max_months, label)
    "Short":  (1,   12, "1–12 months"),
    "Medium": (12,  36, "1–3 years"),
    "Long":   (36, 120, "3–10 years"),
}

HORIZON_COLORS = {
    "Short":  "#ff2d55",
    "Medium": "#ffb020",
    "Long":   "#12e87a",
}

REBAL_SCHEDULE = {
    "Short":  "Monthly review — momentum can reverse quickly",
    "Medium": "Quarterly review — track earnings and macro shifts",
    "Long":   "Semi-annual review — focus on fundamental changes, not price noise",
}


# ── Utility ────────────────────────────────────────────────────────────────────
def _months_from_today(months: int) -> str:
    target = _today() + timedelta(days=int(months * 30.44))
    return target.strftime("%b %Y")


def _safe(v, default=0.0) -> float:
    if v is None:
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ── Per-stock holding timeline ────────────────────────────────────────────────
def build_stock_timeline(m: dict, fund: Optional[dict] = None) -> dict:
    """
    Build a complete holding timeline assessment for one stock.

    Parameters
    ----------
    m    : stock metrics dict (from compute_stock_metrics)
    fund : optional fundamental dict (from compute_fundamentals)
    """
    ticker   = m.get("ticker", "")
    theme    = m.get("theme", "Custom")
    hs       = m.get("horizon", {})

    s_short  = _safe(hs.get("short",  50))
    s_medium = _safe(hs.get("medium", 50))
    s_long   = _safe(hs.get("long",   50))
    best     = hs.get("best", "Medium")

    vol      = _safe(m.get("annualized_volatility", 0.30), 0.30)
    beta_v   = _safe(m.get("beta",    1.0), 1.0)
    sharpe_v = _safe(m.get("sharpe",  0.0))
    sortino_v= _safe(m.get("sortino", 0.0))
    alpha_v  = _safe(m.get("alpha",   0.0))
    mdd_v    = abs(_safe(m.get("max_drawdown", 0.30), 0.30))
    ret_v    = _safe(m.get("annualized_return", 0.0))
    calmar_v = _safe(m.get("calmar",  0.0))
    ulcer_v  = _safe(m.get("ulcer_index", 10.0), 10.0)
    up_cap   = _safe(m.get("upside_capture",   1.0), 1.0)
    dn_cap   = _safe(m.get("downside_capture", 1.0), 1.0)
    ir       = _safe(m.get("information_ratio", 0.0))

    # Fundamental data (optional)
    f_score  = 0
    f_grade  = ""
    f_verdict= ""
    f_pe     = None
    f_dcf_mos= None
    f_rev_g  = None
    f_roic   = None
    f_gm     = None
    if fund and "error" not in fund:
        f_score   = _safe(fund.get("composite_score", 0))
        f_grade   = fund.get("composite_grade", "")
        f_verdict = fund.get("verdict", "")
        f_pe      = fund.get("pe_forward") or fund.get("pe_trailing")
        dcf       = fund.get("dcf") or {}
        f_dcf_mos = dcf.get("margin_of_safety")
        f_rev_g   = fund.get("revenue_growth_yoy")
        f_roic    = fund.get("roic")
        f_gm      = fund.get("gross_margin")

    has_fund = f_score > 0

    # ── Specific holding period ────────────────────────────────────────────────
    min_m, max_m, label = HORIZON_RANGES[best]

    # Narrow the window based on volatility + conviction
    if best == "Short":
        if vol > 0.80 or mdd_v > 0.60:      min_m, max_m = 1, 6    # very speculative
        elif sharpe_v > 1.0:                  min_m, max_m = 3, 12
        else:                                 min_m, max_m = 2, 9
    elif best == "Medium":
        if sharpe_v > 1.5:                    min_m, max_m = 12, 24
        elif sharpe_v > 0.8:                  min_m, max_m = 12, 36
        else:                                 min_m, max_m = 6, 24
    else:  # Long
        if sharpe_v > 1.5 and alpha_v > 0.10: min_m, max_m = 36, 120
        elif sharpe_v > 1.0:                   min_m, max_m = 24, 84
        else:                                   min_m, max_m = 18, 60

    hold_from  = _months_from_today(min_m)
    hold_until = _months_from_today(max_m)
    hold_range = f"{min_m}–{max_m} months"
    hold_label = f"{hold_from} → {hold_until}"

    # ── Conviction tier ────────────────────────────────────────────────────────
    # Combines price score + fundamental score
    price_conviction = (
        min(s_long if best == "Long" else s_medium if best == "Medium" else s_short, 100)
    )
    if has_fund:
        conviction_score = price_conviction * 0.55 + f_score * 0.45
    else:
        conviction_score = price_conviction

    if conviction_score >= 80:   conviction = "Very High"
    elif conviction_score >= 65: conviction = "High"
    elif conviction_score >= 50: conviction = "Moderate"
    elif conviction_score >= 35: conviction = "Low"
    else:                         conviction = "Speculative"

    # ── Recommended position size (% of portfolio) ────────────────────────────
    # Scale with conviction, reduce for high vol and mdd
    base_size = {
        "Very High": 8.0, "High": 6.0, "Moderate": 4.0,
        "Low": 2.0, "Speculative": 1.0,
    }[conviction]

    # Penalise extreme risk
    if vol > 0.80 or mdd_v > 0.70:
        base_size = min(base_size, 2.0)
    elif vol > 0.50 or mdd_v > 0.50:
        base_size = min(base_size, 4.0)

    # Penalise negative alpha / negative Sharpe
    if alpha_v < -0.05 or sharpe_v < -0.1:
        base_size = min(base_size, 1.5)

    size_range = f"{base_size:.0f}–{base_size * 1.5:.0f}%"

    # ── Entry conditions ───────────────────────────────────────────────────────
    entry_signals = []

    if best == "Short":
        entry_signals.append({
            "met":  ret_v > 0.20,
            "label":"Price momentum above 20% annualized — trend is in your favour",
        })
        entry_signals.append({
            "met":  up_cap > 1.15,
            "label":"Upside capture > 115% — stock outperforms in bull phases",
        })
        entry_signals.append({
            "met":  vol > 0.30,
            "label":"Sufficient volatility (>30%) to generate short-term trading opportunities",
        })
        entry_signals.append({
            "met":  mdd_v < 0.60,
            "label":"Max drawdown < 60% — risk is within acceptable short-term bounds",
        })
        if has_fund and f_rev_g is not None:
            entry_signals.append({
                "met":  _safe(f_rev_g) > 15,
                "label":f"Revenue growth {_safe(f_rev_g):.0f}% YoY supports near-term momentum",
            })
    elif best == "Medium":
        entry_signals.append({
            "met":  sharpe_v > 0.5,
            "label":f"Sharpe ratio {sharpe_v:.2f} — reasonable risk-adjusted return profile",
        })
        entry_signals.append({
            "met":  alpha_v > 0,
            "label":f"Positive alpha {alpha_v * 100:.1f}% — outperforming CAPM expectations",
        })
        entry_signals.append({
            "met":  0.20 <= vol <= 0.55,
            "label":f"Volatility {vol * 100:.0f}% in healthy medium-term range (20–55%)",
        })
        entry_signals.append({
            "met":  mdd_v < 0.50,
            "label":f"Max drawdown {mdd_v * 100:.0f}% — manageable over 1–3Y holding horizon",
        })
        if has_fund and f_pe is not None:
            entry_signals.append({
                "met":  _safe(f_pe) < 40,
                "label":f"Forward P/E {_safe(f_pe):.1f}x — valuation supports medium-term entry",
            })
        if has_fund and f_dcf_mos is not None:
            entry_signals.append({
                "met":  _safe(f_dcf_mos) > 0,
                "label":f"DCF margin of safety {_safe(f_dcf_mos):.1f}% — not meaningfully overvalued",
            })
    else:  # Long
        entry_signals.append({
            "met":  sharpe_v >= 1.0,
            "label":f"Sharpe {sharpe_v:.2f} ≥ 1.0 — strong compounding potential over multi-year horizon",
        })
        entry_signals.append({
            "met":  alpha_v > 0.05,
            "label":f"Alpha {alpha_v * 100:.1f}% — consistent CAPM outperformance",
        })
        entry_signals.append({
            "met":  calmar_v > 0.8,
            "label":f"Calmar ratio {calmar_v:.2f} — return justifies drawdown risk",
        })
        entry_signals.append({
            "met":  ulcer_v < 15,
            "label":f"Ulcer index {ulcer_v:.1f} — drawdown pain is manageable long-term",
        })
        if has_fund:
            entry_signals.append({
                "met":  f_score >= 60,
                "label":f"Fundamental score {f_score:.0f}/100 ({f_grade}) — strong business quality",
            })
            if f_roic is not None:
                entry_signals.append({
                    "met":  _safe(f_roic) > 12,
                    "label":f"ROIC {_safe(f_roic):.1f}% > estimated WACC — value creation confirmed",
                })
            if f_dcf_mos is not None:
                entry_signals.append({
                    "met":  _safe(f_dcf_mos) > 10,
                    "label":f"DCF margin of safety {_safe(f_dcf_mos):.1f}% — buying below intrinsic value",
                })

    entry_met   = sum(1 for e in entry_signals if e["met"])
    entry_total = len(entry_signals)
    entry_pct   = round(entry_met / max(entry_total, 1) * 100)
    ready_to_enter = entry_pct >= 60

    # ── Exit triggers ──────────────────────────────────────────────────────────
    exit_triggers = []

    # Universal triggers (apply to all horizons)
    exit_triggers.append({
        "type":  "stop_loss",
        "label": f"Stop-loss: price falls {min(int(mdd_v * 100 * 0.5), 25)}% from your entry point",
        "color": "#ff2d55",
    })

    if best == "Short":
        exit_triggers.append({
            "type":  "momentum_fade",
            "label": "Momentum reversal: 3-month return goes negative while SPY is positive",
            "color": "#ffb020",
        })
        exit_triggers.append({
            "type":  "time_stop",
            "label": f"Time stop: reassess position at {_months_from_today(max_m)} if thesis hasn't played out",
            "color": "#ffb020",
        })
        exit_triggers.append({
            "type":  "beta_spike",
            "label": "Beta spikes above 2.5 or stock becomes uncorrelated with original thesis",
            "color": "#ff2d55",
        })
    elif best == "Medium":
        exit_triggers.append({
            "type":  "thesis_break",
            "label": "Two consecutive earnings misses with downward guidance revision",
            "color": "#ff2d55",
        })
        exit_triggers.append({
            "type":  "valuation",
            "label": f"Stock becomes overvalued: P/E exceeds {int(_safe(f_pe, 25) * 2.0):.0f}x (2× entry multiple)" if f_pe else "P/E exceeds 2× sector median",
            "color": "#ffb020",
        })
        exit_triggers.append({
            "type":  "alpha_fade",
            "label": "Alpha turns negative for two consecutive quarters — structural edge may be lost",
            "color": "#ffb020",
        })
        exit_triggers.append({
            "type":  "time_stop",
            "label": f"Time stop: full review at {_months_from_today(max_m)} — reassess thesis vs market",
            "color": "#ffb020",
        })
    else:  # Long
        exit_triggers.append({
            "type":  "fundamental_deterioration",
            "label": "ROIC drops below cost of capital for 2 consecutive years — moat erosion",
            "color": "#ff2d55",
        })
        exit_triggers.append({
            "type":  "overvaluation",
            "label": f"DCF margin of safety turns to -{20}% or worse — materially overvalued",
            "color": "#ff2d55",
        })
        exit_triggers.append({
            "type":  "thesis_break",
            "label": "Core thesis changes: regulatory reversal, technology disruption, or major management failure",
            "color": "#ff2d55",
        })
        exit_triggers.append({
            "type":  "rebalance",
            "label": f"Position drifts above {base_size * 2.5:.0f}% of portfolio — trim to maintain diversification",
            "color": "#ffb020",
        })
        exit_triggers.append({
            "type":  "better_opportunity",
            "label": "A higher-conviction stock in the same theme offers meaningfully better risk/reward",
            "color": "#4a6080",
        })

    # ── Catalyst calendar ──────────────────────────────────────────────────────
    # Theme-based upcoming catalysts
    THEME_CATALYSTS = {
        "AI": [
            {"event": "Hyperscaler Q-results (MSFT, GOOGL, AMZN, META)", "timing": "Quarterly", "impact": "High"},
            {"event": "NVDA earnings — datacenter capex signal",           "timing": "Quarterly", "impact": "High"},
            {"event": "AI chip export control updates",                     "timing": "Ongoing",   "impact": "Medium"},
            {"event": "AI regulation developments (EU AI Act milestones)", "timing": "Ongoing",   "impact": "Medium"},
        ],
        "Nuclear": [
            {"event": "NRC licensing decisions for SMR applications",       "timing": "Quarterly", "impact": "High"},
            {"event": "Utility PPA announcements (data centre contracts)",  "timing": "Ongoing",   "impact": "High"},
            {"event": "Uranium spot price movements",                        "timing": "Monthly",   "impact": "Medium"},
            {"event": "Government energy policy updates (IRA, ADVANCE Act)","timing": "Ongoing",   "impact": "Medium"},
        ],
        "Space": [
            {"event": "DoD/NASA contract awards",                           "timing": "Quarterly", "impact": "High"},
            {"event": "Launch success/failure events",                       "timing": "Per launch","impact": "High"},
            {"event": "Defence budget announcements",                        "timing": "Annual",    "impact": "Medium"},
            {"event": "Commercial satellite backlog updates",                "timing": "Quarterly", "impact": "Medium"},
        ],
        "LNG": [
            {"event": "FERC export terminal permitting decisions",          "timing": "Ongoing",   "impact": "High"},
            {"event": "European LNG import contract renewals",              "timing": "Annual",    "impact": "High"},
            {"event": "Henry Hub / TTF natural gas price trends",           "timing": "Monthly",   "impact": "Medium"},
            {"event": "US DOE export authorization updates",                "timing": "Ongoing",   "impact": "Medium"},
        ],
        "Robotics": [
            {"event": "Enterprise IT capex cycle updates",                  "timing": "Quarterly", "impact": "High"},
            {"event": "Manufacturing PMI data — automation demand proxy",   "timing": "Monthly",   "impact": "Medium"},
            {"event": "Earnings RPO (remaining performance obligation) growth","timing": "Quarterly","impact": "High"},
            {"event": "AI-robotics integration milestones",                 "timing": "Ongoing",   "impact": "Medium"},
        ],
        "Quantum": [
            {"event": "IBM / Google quantum milestone announcements",       "timing": "Ongoing",   "impact": "High"},
            {"event": "Government quantum computing funding rounds",         "timing": "Annual",    "impact": "Medium"},
            {"event": "Commercial quantum advantage demonstrations",         "timing": "Ongoing",   "impact": "High"},
            {"event": "Error rate / qubit count progress updates",          "timing": "Quarterly", "impact": "Medium"},
        ],
        "AR": [
            {"event": "Consumer headset / smart-glasses launch cycles (AAPL, META)", "timing": "Annual",    "impact": "High"},
            {"event": "Waveguide & microdisplay supply agreements",                   "timing": "Quarterly", "impact": "High"},
            {"event": "Enterprise AR deployment wins (field service, logistics)",     "timing": "Quarterly", "impact": "Medium"},
            {"event": "Display panel pricing and OLED microdisplay yields",           "timing": "Monthly",   "impact": "Medium"},
        ],
        "Custom": [
            {"event": "Quarterly earnings and guidance",                    "timing": "Quarterly", "impact": "High"},
            {"event": "Macro: Fed rate decisions and CPI data",             "timing": "Monthly",   "impact": "Medium"},
            {"event": "Analyst rating changes and price target updates",    "timing": "Ongoing",   "impact": "Low"},
        ],
    }
    catalysts = THEME_CATALYSTS.get(theme, THEME_CATALYSTS["Custom"])

    # ── Risk-adjusted return target ────────────────────────────────────────────
    # What return you need to justify the risk over the holding period
    years = (min_m + max_m) / 2 / 12
    required_return_pct = round(
        (1 + max(mdd_v * 0.5, 0.05)) ** (1 / max(years, 0.5)) - 1,
        3
    ) * 100  # annualised hurdle rate

    expected_return_pct = round(ret_v * 100, 1)
    return_vs_hurdle    = expected_return_pct - required_return_pct
    meets_hurdle        = return_vs_hurdle > 0

    # ── Summary narrative ──────────────────────────────────────────────────────
    narrative_parts = []
    narrative_parts.append(
        f"{ticker} is best suited for a {best.lower()}-term hold "
        f"({hold_range} — from {hold_from} to {hold_until})."
    )
    if conviction in ("Very High", "High"):
        narrative_parts.append(
            f"Conviction is {conviction.lower()} (score {conviction_score:.0f}/100), "
            f"supporting a position of {size_range} of portfolio."
        )
    else:
        narrative_parts.append(
            f"Conviction is {conviction.lower()} — keep position small at {size_range}."
        )
    if meets_hurdle:
        narrative_parts.append(
            f"Expected return {expected_return_pct:.1f}% annualized beats the "
            f"risk-adjusted hurdle rate of {required_return_pct:.1f}%."
        )
    else:
        narrative_parts.append(
            f"Expected return {expected_return_pct:.1f}% falls short of the "
            f"risk-adjusted hurdle {required_return_pct:.1f}% — thin margin of safety."
        )
    if has_fund and f_verdict:
        narrative_parts.append(
            f"Fundamental verdict: {f_verdict} (score {f_score:.0f}/100, grade {f_grade})."
        )
    if best == "Long" and sharpe_v >= 1.0:
        narrative_parts.append(
            "Strong compounding candidate — prioritise holding through volatility rather than trading around it."
        )
    elif best == "Short":
        narrative_parts.append(
            "Active monitoring required — set alerts at key price levels and review monthly."
        )

    narrative = " ".join(narrative_parts)

    return {
        "ticker":            ticker,
        "theme":             theme,
        "best_horizon":      best,
        "short_score":       round(s_short, 1),
        "medium_score":      round(s_medium, 1),
        "long_score":        round(s_long, 1),
        "hold_range":        hold_range,
        "hold_from":         hold_from,
        "hold_until":        hold_until,
        "hold_label":        hold_label,
        "min_months":        min_m,
        "max_months":        max_m,
        "conviction":        conviction,
        "conviction_score":  round(conviction_score, 1),
        "size_range":        size_range,
        # Numeric mid-point of size_range, as a % of portfolio. Exposed so the
        # combination engine can build a "Conviction Weighted" book out of the
        # sizing this engine already recommends per stock.
        "target_size_pct":   round(base_size * 1.25, 2),
        "entry_signals":     entry_signals,
        "entry_met":         entry_met,
        "entry_total":       entry_total,
        "entry_pct":         entry_pct,
        "ready_to_enter":    ready_to_enter,
        "exit_triggers":     exit_triggers,
        "catalysts":         catalysts,
        "required_return":   round(required_return_pct, 1),
        "expected_return":   expected_return_pct,
        "meets_hurdle":      meets_hurdle,
        "rebal_schedule":    REBAL_SCHEDULE[best],
        "narrative":         narrative,
        # pass-through for UI
        "fundamental_score": f_score,
        "fundamental_grade": f_grade,
        "verdict":           f_verdict,
    }


# ── Portfolio-level timeline analysis ────────────────────────────────────────
def build_portfolio_timeline(timelines: list[dict]) -> dict:
    """
    Aggregate individual stock timelines into portfolio-level insights.
    """
    if not timelines:
        return {}

    n = len(timelines)

    # Horizon mix
    by_horizon = {"Short": [], "Medium": [], "Long": []}
    for t in timelines:
        by_horizon[t["best_horizon"]].append(t)

    horizon_mix = {
        h: {
            "count":   len(stocks),
            "pct":     round(len(stocks) / n * 100, 1),
            "tickers": [s["ticker"] for s in stocks],
            "avg_conviction": round(
                sum(s["conviction_score"] for s in stocks) / max(len(stocks), 1), 1
            ) if stocks else 0,
        }
        for h, stocks in by_horizon.items()
    }

    # Conviction distribution
    conviction_counts = {}
    for t in timelines:
        c = t["conviction"]
        conviction_counts[c] = conviction_counts.get(c, 0) + 1

    # Entry readiness
    ready     = [t for t in timelines if t["ready_to_enter"]]
    not_ready = [t for t in timelines if not t["ready_to_enter"]]

    # Hurdle rate pass
    meets = [t for t in timelines if t["meets_hurdle"]]

    # Average holding window (months)
    avg_min = sum(t["min_months"] for t in timelines) / n
    avg_max = sum(t["max_months"] for t in timelines) / n

    # Next significant catalyst window — earliest theme catalyst
    next_review_date = _months_from_today(round(avg_min))

    # Portfolio-level rebalancing recommendation
    short_pct = horizon_mix["Short"]["pct"]
    long_pct  = horizon_mix["Long"]["pct"]
    if short_pct > 40:
        rebal_rec = "High short-term exposure — review monthly. Consider reducing speculative names."
    elif long_pct > 70:
        rebal_rec = "Long-term portfolio — semi-annual reviews are sufficient. Focus on fundamentals."
    else:
        rebal_rec = "Balanced horizon mix — quarterly reviews recommended."

    # Risk-return verdict for full portfolio
    avg_expected = sum(t["expected_return"] for t in timelines) / n
    avg_hurdle   = sum(t["required_return"]  for t in timelines) / n
    port_return_vs_hurdle = avg_expected - avg_hurdle

    # Theme catalyst summary (deduplicated)
    theme_catalysts = {}
    for t in timelines:
        theme = t["theme"]
        if theme not in theme_catalysts and t.get("catalysts"):
            theme_catalysts[theme] = t["catalysts"]

    return {
        "horizon_mix":         horizon_mix,
        "conviction_counts":   conviction_counts,
        "ready_count":         len(ready),
        "not_ready_count":     len(not_ready),
        "ready_tickers":       [t["ticker"] for t in ready],
        "not_ready_tickers":   [t["ticker"] for t in not_ready],
        "hurdle_pass_count":   len(meets),
        "hurdle_pass_tickers": [t["ticker"] for t in meets],
        "avg_min_months":      round(avg_min, 1),
        "avg_max_months":      round(avg_max, 1),
        "next_review_date":    next_review_date,
        "rebal_recommendation":rebal_rec,
        "avg_expected_return": round(avg_expected, 1),
        "avg_hurdle_return":   round(avg_hurdle, 1),
        "port_vs_hurdle":      round(port_return_vs_hurdle, 1),
        "theme_catalysts":     theme_catalysts,
        "total_stocks":        n,
    }
