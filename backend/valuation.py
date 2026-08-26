"""
valuation.py — Multi-method fair-value triangulation + valuation trigger.
Portfolio Analyzer Discovery (May 2026).

Answers: "what is the stock worth, vs what it trades at?" — then turns the gap
into an actionable trigger (STRONG BUY / BUY / HOLD / TRIM / AVOID on valuation).

WHY MULTIPLE METHODS: a single DCF is fragile — tiny changes to the growth or
discount rate swing fair value wildly. Triangulating four independent methods and
weighting them by how much data supports each gives a far more robust estimate.
The four methods:
  1. DCF              — discounted free cash flow (intrinsic).
  2. Peer multiples   — apply sector-median P/E & EV/EBITDA to this company's metrics.
  3. Historical mult. — apply the company's own normal P/E to forward earnings.
  4. Analyst target   — consensus Wall Street target (sentiment anchor).

Each method returns a fair value (or None if data is missing). We blend the
available ones by weight, derive a margin of safety vs the live price, and map
that to a discrete trigger. We also report a fair-value RANGE (low/high across
methods) so the user sees how tight or wide the estimate is.
"""
import math


# Weights for blending methods when all are present (renormalized if some missing).
METHOD_WEIGHTS = {
    "dcf": 0.32,
    "peer_multiple": 0.23,
    "historical_multiple": 0.18,
    "analyst_target": 0.17,
    "sales_multiple": 0.10,
}

# Valuation trigger bands, by margin of safety (fair/price − 1).
#   MOS = +30% means fair value is 30% above price → undervalued → buy signal.
TRIGGER_BANDS = [
    (0.30, "STRONG BUY",  "Deeply undervalued — fair value well above price"),
    (0.12, "BUY",         "Undervalued — meaningful upside to fair value"),
    (-0.12, "HOLD",       "Fairly valued — price near intrinsic worth"),
    (-0.30, "TRIM",       "Overvalued — price above fair value, consider trimming"),
    (-9.99, "AVOID",      "Significantly overvalued — price well above fair value"),
]


def _finite(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── Method 1: DCF (intrinsic) ────────────────────────────────────────────────
def dcf_value(raw):
    """5-yr discounted FCF + terminal value. Returns per-share fair value or None."""
    fcf = _finite(raw.get("fcf"))
    mc = _finite(raw.get("market_cap"))
    price = _finite(raw.get("current_price"))
    if not fcf or not mc or not price or mc <= 0 or price <= 0 or fcf <= 0:
        return None
    shares = mc / price
    # growth: blend recent FCF growth history with revenue CAGR, clamped sane
    g = 0.08
    fcf_h = raw.get("fcf_history") or []
    if len(fcf_h) >= 3 and fcf_h[-1] and fcf_h[0] and fcf_h[-1] > 0 and fcf_h[0] > 0:
        cagr = (fcf_h[0] / fcf_h[-1]) ** (1 / (len(fcf_h) - 1)) - 1
        g = cagr
    rev_cagr = _finite(raw.get("revenue_cagr_3y"))
    if rev_cagr is not None:
        g = (g + rev_cagr / 100) / 2
    g = max(-0.10, min(0.35, g))
    wacc, term_g, n = 0.10, 0.03, 5
    pv, f = 0.0, fcf
    for yr in range(1, n + 1):
        f *= (1 + g)
        pv += f / (1 + wacc) ** yr
    tv = f * (1 + term_g) / (wacc - term_g)
    pv += tv / (1 + wacc) ** n
    return round(pv / shares, 2) if shares > 0 else None


# ── Method 2: Peer / sector multiples ────────────────────────────────────────
SECTOR_PE = {
    "Technology": 28, "Communication Services": 22, "Industrials": 20,
    "Healthcare": 24, "Consumer Cyclical": 20, "Consumer Defensive": 18,
    "Energy": 14, "Utilities": 17, "Financial Services": 14,
    "Basic Materials": 15, "Real Estate": 35, "Unknown": 22,
}

def peer_multiple_value(raw):
    """Apply sector-median P/E to this company's EPS. Returns fair value or None."""
    sector = raw.get("sector", "Unknown")
    pe_bench = SECTOR_PE.get(sector, 22)
    price = _finite(raw.get("current_price"))
    # Derive EPS from the TRAILING multiple: the sector benchmark is a trailing
    # median, and forward-EPS x trailing-median mixed two bases, inflating fair
    # value for anything with expected growth. Forward P/E only as fallback.
    pe = _finite(raw.get("pe_trailing")) or _finite(raw.get("pe_forward"))
    if not price or not pe or pe <= 0:
        return None
    eps = price / pe                       # implied EPS
    return round(eps * pe_bench, 2)


# ── Method 3: Company's own historical multiple ──────────────────────────────
def historical_multiple_value(raw):
    """
    Apply a 'normal' P/E to forward EPS. Without a stored P/E history, we proxy
    the normal multiple as a modest discount to the current trailing P/E when
    elevated (mean-reversion), bounded by sector norms.
    """
    price = _finite(raw.get("current_price"))
    pe_t = _finite(raw.get("pe_trailing"))
    pe_f = _finite(raw.get("pe_forward"))
    if not price or not pe_t or pe_t <= 0:
        return None
    eps_ttm = price / pe_t
    sector = raw.get("sector", "Unknown")
    sector_pe = SECTOR_PE.get(sector, 22)
    # 'normal' multiple = midpoint of forward P/E and sector P/E, capped vs trailing
    normal_pe = pe_f if pe_f and pe_f > 0 else pe_t
    normal_pe = (normal_pe + sector_pe) / 2
    normal_pe = min(normal_pe, pe_t * 1.1)   # don't assume expansion above current
    return round(eps_ttm * normal_pe, 2)


# ── Method 4: Analyst consensus ──────────────────────────────────────────────
def analyst_value(raw):
    t = _finite(raw.get("analyst_target"))
    n = _finite(raw.get("num_analysts"))
    if not t or t <= 0:
        return None
    # ignore ultra-thin coverage (1 analyst) as unreliable
    if n is not None and n < 2:
        return None
    return round(t, 2)


# ── Method 5: Price/Sales (for pre-earnings / cash-burning growth names) ──────
# Sector-median P/S multiples — lets us value companies with no earnings or FCF.
SECTOR_PS = {
    "Technology": 6.0, "Communication Services": 4.0, "Industrials": 2.5,
    "Healthcare": 5.0, "Consumer Cyclical": 1.8, "Consumer Defensive": 1.5,
    "Energy": 1.5, "Utilities": 2.0, "Financial Services": 3.0,
    "Basic Materials": 1.8, "Real Estate": 6.0, "Unknown": 3.0,
}

def sales_multiple_value(raw):
    """Apply sector-median P/S to this company's revenue/share. For pre-profit names."""
    price = _finite(raw.get("current_price"))
    ps = _finite(raw.get("ps_trailing"))
    if not price or not ps or ps <= 0:
        return None
    sector = raw.get("sector", "Unknown")
    ps_bench = SECTOR_PS.get(sector, 3.0)
    sales_per_share = price / ps          # implied revenue/share
    return round(sales_per_share * ps_bench, 2)


# ── Blend + trigger ──────────────────────────────────────────────────────────
def compute_valuation(raw):
    """
    Triangulate fair value across methods and produce a valuation trigger.
    Returns a dict with per-method values, blended fair value, range, margin of
    safety, and the discrete trigger — or {available: False} if too little data.
    """
    price = _finite(raw.get("current_price"))
    if not price or price <= 0:
        return {"available": False, "reason": "no current price"}

    methods = {
        "dcf": dcf_value(raw),
        "peer_multiple": peer_multiple_value(raw),
        "historical_multiple": historical_multiple_value(raw),
        "analyst_target": analyst_value(raw),
        "sales_multiple": sales_multiple_value(raw),
    }
    present = {k: v for k, v in methods.items() if v is not None and v > 0}

    # Speculative fallback: if intrinsic methods can't run (no earnings/FCF) but we
    # have at least a P/S or analyst anchor, still produce a signal — flagged as
    # low-confidence and 'speculative basis'. This is the SPCX-style case.
    speculative_basis = False
    if len(present) < 2:
        # try with whatever single anchor exists (P/S or analyst)
        anchor = present.get("sales_multiple") or present.get("analyst_target")
        if anchor:
            speculative_basis = True
            fair_value = round(anchor, 2)
            mos = (fair_value - price) / price
            trigger, trigger_desc = "HOLD", ""
            for thresh, label, desc in TRIGGER_BANDS:
                if mos >= thresh:
                    trigger, trigger_desc = label, desc
                    break
            return {
                "available": True, "speculative_basis": True,
                "current_price": price, "fair_value": fair_value,
                "fair_value_low": fair_value, "fair_value_high": fair_value,
                "margin_of_safety": round(mos * 100, 1),
                "upside_to_fair": round((fair_value / price - 1) * 100, 1),
                "trigger": trigger, "trigger_desc": trigger_desc + " (speculative basis — no earnings/FCF to value intrinsically)",
                "methods": methods, "methods_used": list(present.keys()),
                "method_count": len(present), "dispersion": None, "confidence": "Low",
            }
        return {
            "available": False,
            "reason": f"Only {len(present)} valuation method(s) had data — need ≥2 to triangulate. "
                      f"Likely a pre-revenue or no-earnings name where intrinsic value can't be computed.",
            "methods": methods, "current_price": price,
        }

    # weighted blend over available methods (renormalize weights)
    wsum = sum(METHOD_WEIGHTS[k] for k in present)
    fair_value = sum(present[k] * METHOD_WEIGHTS[k] for k in present) / wsum
    fair_value = round(fair_value, 2)

    vals = list(present.values())
    fv_low, fv_high = round(min(vals), 2), round(max(vals), 2)

    # margin of safety: positive = undervalued (fair above price)
    mos = (fair_value - price) / price

    trigger, trigger_desc = "HOLD", ""
    for thresh, label, desc in TRIGGER_BANDS:
        if mos >= thresh:
            trigger, trigger_desc = label, desc
            break

    # dispersion: how much the methods disagree (relative spread). High = low confidence.
    dispersion = (fv_high - fv_low) / fair_value if fair_value > 0 else 0
    confidence = ("High" if dispersion < 0.20 and len(present) >= 3
                  else "Low" if dispersion > 0.45 or len(present) < 3
                  else "Medium")

    return {
        "available": True,
        "speculative_basis": False,
        "current_price": price,
        "fair_value": fair_value,
        "fair_value_low": fv_low,
        "fair_value_high": fv_high,
        "margin_of_safety": round(mos * 100, 1),     # percent
        "upside_to_fair": round((fair_value / price - 1) * 100, 1),
        "trigger": trigger,
        "trigger_desc": trigger_desc,
        "methods": {k: methods[k] for k in methods},  # include None ones for transparency
        "methods_used": list(present.keys()),
        "method_count": len(present),
        "dispersion": round(dispersion * 100, 1),
        "confidence": confidence,
    }


# trigger → display color (used by frontend via API)
TRIGGER_COLORS = {
    "STRONG BUY": "#12e87a", "BUY": "#4ade80", "HOLD": "#ffb020",
    "TRIM": "#ff7043", "AVOID": "#ff2d55",
}
