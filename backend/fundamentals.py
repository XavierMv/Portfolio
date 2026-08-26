"""
fundamentals.py  –  Fundamental Analysis Engine

Fetches and scores stocks across 5 dimensions:
  1. Valuation      — is the stock cheap or expensive?
  2. Profitability  — how well does it generate returns?
  3. Financial Health — how strong is the balance sheet?
  4. Growth         — revenue/earnings trajectory
  5. Quality        — earnings consistency, FCF conversion

Each dimension returns a score 0-100 and a letter grade.
A composite "fundamental score" combines all five.
"""

import math
import yfinance as yf
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
from valuation import compute_valuation, dcf_value

CACHE_DIR = Path.home() / ".portfolio_v3_cache" / "fundamentals"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 24   # hours — fundamentals change slowly


# ── Cache helpers ──────────────────────────────────────────────────────────────
def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=CACHE_TTL)


def _save(ticker: str, data: dict):
    try:
        with open(_cache_path(ticker), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _load(ticker: str) -> dict | None:
    try:
        if _is_fresh(_cache_path(ticker)):
            with open(_cache_path(ticker)) as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ── Safe math ──────────────────────────────────────────────────────────────────
def _s(v, default=None):
    """Return v if it's a finite number, else default."""
    if v is None:
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _pct(v, default=None):
    """Return v*100 if finite."""
    r = _s(v)
    return round(r * 100, 2) if r is not None else default


# ── Grade helpers ──────────────────────────────────────────────────────────────
def _grade(score: float) -> str:
    if score >= 85: return "A+"
    if score >= 75: return "A"
    if score >= 65: return "B+"
    if score >= 55: return "B"
    if score >= 45: return "C+"
    if score >= 35: return "C"
    if score >= 25: return "D"
    return "F"


def _clamp(v: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, v))


# ── Data-completeness guard ───────────────────────────────────────────────────
# Every dimension scorer falls back to 50/100 when it has nothing to score, so a
# ticker with NO fundamental data at all still comes out as "50.0, C+, HOLD" —
# indistinguishable from a genuinely mediocre business. Small caps, foreign
# listings and pre-revenue names routinely have thin yfinance coverage, so check
# for a minimum spine of fields before scoring at all.
KEY_FIELDS = [
    "market_cap", "pe_trailing", "gross_margin",
    "revenue_growth_yoy", "total_debt", "fcf", "roe",
]
REQUIRED_MIN = 4


def _coverage(raw: dict) -> tuple[int, list[str]]:
    """Return (count of KEY_FIELDS present, list of the missing ones)."""
    present, missing = 0, []
    for f in KEY_FIELDS:
        if _s(raw.get(f)) is not None:
            present += 1
        else:
            missing.append(f)
    return present, missing


# ── Sector benchmarks ─────────────────────────────────────────────────────────
# Median "fair" P/E by sector — used to score relative cheapness
SECTOR_PE = {
    "Technology":           28,
    "Communication Services":22,
    "Industrials":          20,
    "Healthcare":           24,
    "Consumer Cyclical":    20,
    "Consumer Defensive":   18,
    "Energy":               14,
    "Utilities":            17,
    "Financial Services":   14,
    "Basic Materials":      15,
    "Real Estate":          35,
    "Unknown":              22,
}

SECTOR_EV_EBITDA = {
    "Technology":           22,
    "Communication Services":16,
    "Industrials":          14,
    "Healthcare":           18,
    "Consumer Cyclical":    15,
    "Consumer Defensive":   14,
    "Energy":               8,
    "Utilities":            12,
    "Financial Services":   10,
    "Basic Materials":      10,
    "Real Estate":          20,
    "Unknown":              15,
}


# ── Fetch raw fundamentals from yfinance ──────────────────────────────────────
def fetch_fundamentals_raw(ticker: str) -> dict:
    """Pull all fundamental data from yfinance .info dict."""
    cached = _load(ticker)
    if cached:
        return cached

    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}

        # Income statement (annual)
        fin  = t.financials        # columns = fiscal year ends
        qfin = t.quarterly_financials

        # Balance sheet
        bs   = t.balance_sheet
        qbs  = t.quarterly_balance_sheet

        # Cash flow
        cf   = t.cashflow
        qcf  = t.quarterly_cashflow

        def row(df, *names):
            """Get the most recent annual value for a row by trying multiple names."""
            if df is None or df.empty:
                return None
            for name in names:
                if name in df.index:
                    vals = df.loc[name].dropna()
                    if len(vals):
                        return float(vals.iloc[0])
            return None

        def row_hist(df, *names, n=4):
            """Get last n annual values for a row."""
            if df is None or df.empty:
                return []
            for name in names:
                if name in df.index:
                    vals = df.loc[name].dropna().head(n)
                    return [float(v) for v in vals]
            return []

        raw = {
            "ticker": ticker,

            # Valuation multiples (from .info — already calculated by Yahoo)
            "pe_trailing":      _s(info.get("trailingPE")),
            "pe_forward":       _s(info.get("forwardPE")),
            "pb":               _s(info.get("priceToBook")),
            "ps_trailing":      _s(info.get("priceToSalesTrailing12Months")),
            "peg":              _s(info.get("pegRatio")),
            "ev_ebitda":        _s(info.get("enterpriseToEbitda")),
            "ev_revenue":       _s(info.get("enterpriseToRevenue")),
            "market_cap":       _s(info.get("marketCap")),
            "enterprise_value": _s(info.get("enterpriseValue")),

            # Per-share
            "eps_trailing":     _s(info.get("trailingEps")),
            "eps_forward":      _s(info.get("forwardEps")),
            "book_value":       _s(info.get("bookValue")),
            "current_price":    _s(info.get("currentPrice") or info.get("regularMarketPrice")),

            # Profitability
            "gross_margin":     _pct(info.get("grossMargins")),
            "operating_margin": _pct(info.get("operatingMargins")),
            "net_margin":       _pct(info.get("profitMargins")),
            "roe":              _pct(info.get("returnOnEquity")),
            "roa":              _pct(info.get("returnOnAssets")),
            "roic":             None,   # computed below

            # Growth
            "revenue_growth_yoy":  _pct(info.get("revenueGrowth")),
            "earnings_growth_yoy": _pct(info.get("earningsGrowth")),
            "earnings_quarterly_growth": _pct(info.get("earningsQuarterlyGrowth")),

            # Health
            "total_debt":       _s(info.get("totalDebt")),
            "total_cash":       _s(info.get("totalCash")),
            "debt_to_equity":   _s(info.get("debtToEquity")),
            "current_ratio":    _s(info.get("currentRatio")),
            "quick_ratio":      _s(info.get("quickRatio")),
            "interest_coverage": None,  # computed below

            # Cash flow
            "fcf":              _s(info.get("freeCashflow")),
            "operating_cf":     _s(info.get("operatingCashflow")),
            "fcf_yield":        None,   # computed below

            # Dividends
            # Yahoo moved `dividendYield` to percent form (3.1, not 0.031) in
            # early 2025 and yfinance passes it through unscaled — so no *100.
            # Same convention dividends.py declares. CONFIRMED live 2026-08-26:
            # yf.Ticker("KO").info["dividendYield"] returned 2.31 (percent).
            "dividend_yield":   _s(info.get("dividendYield")),
            "payout_ratio":     _pct(info.get("payoutRatio")),

            # Analyst
            "analyst_target":   _s(info.get("targetMeanPrice")),
            "analyst_low":      _s(info.get("targetLowPrice")),
            "analyst_high":     _s(info.get("targetHighPrice")),
            "recommendation":   info.get("recommendationKey", ""),
            "num_analysts":     _s(info.get("numberOfAnalystOpinions")),

            # Meta
            "sector":           info.get("sector", "Unknown"),
            "industry":         info.get("industry", "Unknown"),
            "name":             info.get("shortName", ticker),
            "employees":        _s(info.get("fullTimeEmployees")),

            # Historical revenue for growth trend
            "revenue_history":  row_hist(fin, "Total Revenue", "Revenue", n=4),
            "ebitda_history":   row_hist(fin, "EBITDA", "Normalized EBITDA", n=4),
            "net_income_history": row_hist(fin, "Net Income", "Net Income From Continuing Operations", n=4),
            "fcf_history":      row_hist(cf,  "Free Cash Flow", n=4),

            # For ROIC / interest coverage
            "_ebit":            row(fin, "EBIT", "Operating Income"),
            "_interest_exp":    row(fin, "Interest Expense"),
            "_invested_cap":    None,
        }

        # ── Derived metrics ────────────────────────────────────────────────────
        # ROIC = EBIT*(1-tax) / Invested Capital
        equity = _s(info.get("bookValue"), 0) * _s(info.get("sharesOutstanding"), 1)
        debt   = raw["total_debt"] or 0
        cash   = raw["total_cash"] or 0
        inv_cap = equity + debt - cash
        if raw["_ebit"] and inv_cap and inv_cap > 0:
            tax_rate = 0.21
            raw["roic"] = round(raw["_ebit"] * (1 - tax_rate) / inv_cap * 100, 2)
            raw["_invested_cap"] = inv_cap

        # Interest coverage = EBIT / Interest Expense
        if raw["_ebit"] and raw["_interest_exp"] and raw["_interest_exp"] != 0:
            raw["interest_coverage"] = round(abs(raw["_ebit"] / raw["_interest_exp"]), 2)

        # FCF yield = FCF / Market Cap
        if raw["fcf"] and raw["market_cap"] and raw["market_cap"] > 0:
            raw["fcf_yield"] = round(raw["fcf"] / raw["market_cap"] * 100, 2)

        # Upside to analyst target
        if raw["analyst_target"] and raw["current_price"] and raw["current_price"] > 0:
            raw["analyst_upside"] = round((raw["analyst_target"] / raw["current_price"] - 1) * 100, 2)
        else:
            raw["analyst_upside"] = None

        # Revenue CAGR (3Y)
        rev = raw["revenue_history"]
        if len(rev) >= 3 and rev[-1] and rev[-1] > 0 and rev[0] and rev[0] > 0:
            raw["revenue_cagr_3y"] = round(((rev[0] / rev[-1]) ** (1/3) - 1) * 100, 2)
        else:
            raw["revenue_cagr_3y"] = None

        # Net income CAGR (3Y)
        ni = raw["net_income_history"]
        if len(ni) >= 3 and ni[-1] and ni[-1] > 0 and ni[0] and ni[0] > 0:
            raw["earnings_cagr_3y"] = round(((ni[0] / ni[-1]) ** (1/3) - 1) * 100, 2)
        else:
            raw["earnings_cagr_3y"] = None

        # Remove private keys before caching
        for k in list(raw.keys()):
            if k.startswith("_"):
                raw.pop(k)

        _save(ticker, raw)
        return raw

    except Exception as e:
        print(f"  [!] Fundamentals error {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


# ── Scoring functions ─────────────────────────────────────────────────────────

def score_valuation(raw: dict) -> dict:
    """
    Score cheapness vs sector benchmarks and intrinsic value.
    Returns score 0-100 (100 = very cheap / undervalued).
    """
    sector   = raw.get("sector", "Unknown")
    pe_bench = SECTOR_PE.get(sector, 22)
    ev_bench = SECTOR_EV_EBITDA.get(sector, 15)

    signals = []
    total   = 0.0
    count   = 0

    def add(val, bench, weight, invert=False, label=""):
        nonlocal total, count
        if val is None:
            return
        if val <= 0:
            # A negative multiple (negative earnings, EBITDA or book value) is
            # not "maximally expensive" — it is meaningless. Scoring it 0 made
            # a loss-maker indistinguishable from a wildly overpriced profitable
            # company, and double-punished losses the profitability dimension
            # already captures. Skip it; P/S, PEG and analyst upside still
            # anchor the dimension for pre-profit names.
            return
        ratio = val / bench if bench else 1.0
        # ratio < 1 = cheaper than benchmark = good
        raw_score = (1 / ratio) * 50 if not invert else ratio * 50
        s = _clamp(raw_score, 0, 100)
        total  += s * weight
        count  += weight
        flag = "✅" if s >= 55 else "⚠️" if s >= 35 else "🔴"
        signals.append({
            "label": label,
            "value": round(val, 2),
            "benchmark": bench,
            "score": round(s, 1),
            "flag":  flag,
            "interpretation": (
                "Below sector median — attractive" if ratio < 0.85 else
                "Near sector median — fairly valued" if ratio < 1.20 else
                "Premium to sector — expensive"
            )
        })

    # Trailing P/E
    add(raw.get("pe_trailing"), pe_bench, 2.0, label=f"Trailing P/E (sector median {pe_bench}x)")
    # Forward P/E
    add(raw.get("pe_forward"),  pe_bench * 0.9, 1.5, label=f"Forward P/E (sector median {pe_bench*0.9:.0f}x)")
    # EV/EBITDA
    add(raw.get("ev_ebitda"),   ev_bench, 2.0, label=f"EV/EBITDA (sector median {ev_bench}x)")
    # P/B
    add(raw.get("pb"), 3.5, 0.8, label="Price/Book (fair value ~3.5x)")
    # P/S
    add(raw.get("ps_trailing"), 5.0, 0.8, label="Price/Sales (fair value ~5x)")
    # PEG — below 1 is undervalued relative to growth
    peg = raw.get("peg")
    if peg and peg > 0:
        s = _clamp((1 / peg) * 50, 0, 100) if peg < 5 else 10
        signals.append({
            "label": "PEG Ratio (< 1.0 = undervalued relative to growth)",
            "value": round(peg, 2), "benchmark": 1.0, "score": round(s, 1),
            "flag": "✅" if peg < 1.0 else "⚠️" if peg < 2.0 else "🔴",
            "interpretation": "Undervalued vs growth" if peg < 1.0 else
                              "Fairly valued vs growth" if peg < 2.0 else "Expensive vs growth"
        })
        total += s * 1.5; count += 1.5

    # Analyst upside
    upside = raw.get("analyst_upside")
    if upside is not None:
        s = _clamp(50 + upside, 0, 100)
        signals.append({
            "label": f"Analyst consensus upside ({raw.get('num_analysts',0)} analysts)",
            "value": round(upside, 1), "benchmark": 0, "score": round(s,1),
            "flag": "✅" if upside > 15 else "⚠️" if upside > 0 else "🔴",
            "interpretation": f"Target: ${raw.get('analyst_target','N/A')} | Rec: {raw.get('recommendation','N/A')}"
        })
        total += s * 1.0; count += 1.0

    score = round(total / count if count > 0 else 50, 1)
    return {"score": score, "grade": _grade(score), "signals": signals, "dimension": "Valuation"}


def score_profitability(raw: dict) -> dict:
    """
    Score how well the company generates returns.
    Returns score 0-100 (100 = highly profitable).
    """
    signals = []
    total = 0.0; count = 0.0

    def add(val, good_thresh, bad_thresh, weight, label, unit="%"):
        nonlocal total, count
        if val is None: return
        if good_thresh > bad_thresh:  # higher is better
            s = _clamp(50 + (val - bad_thresh) / (good_thresh - bad_thresh) * 50, 0, 100)
            flag = "✅" if val >= good_thresh else "⚠️" if val >= bad_thresh else "🔴"
        else:  # lower is better
            s = _clamp(50 + (bad_thresh - val) / (bad_thresh - good_thresh) * 50, 0, 100)
            flag = "✅" if val <= good_thresh else "⚠️" if val <= bad_thresh else "🔴"
        total += s * weight; count += weight
        signals.append({"label":label,"value":round(val,1),"unit":unit,"score":round(s,1),"flag":flag})

    add(raw.get("gross_margin"),    60,   20,  2.0, "Gross Margin (excellent >60%)")
    add(raw.get("operating_margin"),20,   -5,  2.0, "Operating Margin (excellent >20%)")
    add(raw.get("net_margin"),      15,   -5,  2.0, "Net Profit Margin (excellent >15%)")
    add(raw.get("roe"),             20,    0,  2.5, "ROE — Return on Equity (excellent >20%)")
    add(raw.get("roa"),             10,    0,  1.5, "ROA — Return on Assets (excellent >10%)")
    add(raw.get("roic"),            15,    0,  2.5, "ROIC — Return on Invested Capital (excellent >15%)")
    add(raw.get("fcf_yield"),       6,   -2,  1.5, "Free Cash Flow Yield (excellent >6%)")

    score = round(total / count if count > 0 else 50, 1)
    return {"score": score, "grade": _grade(score), "signals": signals, "dimension": "Profitability"}


def score_health(raw: dict) -> dict:
    """
    Score balance sheet strength and financial resilience.
    Returns score 0-100 (100 = rock-solid balance sheet).
    """
    signals = []
    total = 0.0; count = 0.0

    # Debt/Equity — lower is better.
    # yfinance reports `debtToEquity` in PERCENT form (74.0 means 0.74x), so it
    # always needs dividing by 100. The old `if de > 5` guard tried to sniff the
    # format instead and inverted the score for genuinely low-debt names:
    # 4.9 (0.049x, superb) scored 0/100 while 5.1 (0.051x) scored 98.7/100.
    de = raw.get("debt_to_equity")
    if de is not None:
        de = de / 100.0
        s = _clamp(100 - de * 25, 0, 100)
        signals.append({
            "label": "Debt/Equity (lower is better; <1.0 is healthy)",
            "value": round(de, 2),            # ratio form, e.g. 0.74
            "score": round(s,1),
            "flag": "✅" if de < 1.0 else "⚠️" if de < 2.0 else "🔴"
        })
        total += s * 2.5; count += 2.5

    # Current Ratio — higher is better (>1.5 is healthy)
    cr = raw.get("current_ratio")
    if cr is not None:
        s = _clamp((cr - 0.5) / 2.0 * 100, 0, 100)
        signals.append({
            "label": "Current Ratio (>1.5 healthy; >2.0 excellent)",
            "value": round(cr, 2), "score": round(s,1),
            "flag": "✅" if cr > 2.0 else "⚠️" if cr > 1.0 else "🔴"
        })
        total += s * 2.0; count += 2.0

    # Interest Coverage — higher is better (>5x is healthy)
    ic = raw.get("interest_coverage")
    if ic is not None:
        s = _clamp(ic / 10 * 80, 0, 100)
        signals.append({
            "label": "Interest Coverage (>5x healthy; >10x excellent)",
            "value": round(ic, 1), "score": round(s,1),
            "flag": "✅" if ic > 10 else "⚠️" if ic > 4 else "🔴"
        })
        total += s * 2.0; count += 2.0

    # Cash vs Debt
    cash = raw.get("total_cash", 0) or 0
    debt = raw.get("total_debt", 0) or 0
    if debt > 0 and cash is not None:
        net_cash_ratio = cash / debt
        s = _clamp(net_cash_ratio * 80, 0, 100)
        signals.append({
            "label": "Cash / Total Debt ratio (>1.0 = net cash positive)",
            "value": round(net_cash_ratio, 2), "score": round(s,1),
            "flag": "✅" if net_cash_ratio > 1.0 else "⚠️" if net_cash_ratio > 0.5 else "🔴"
        })
        total += s * 1.5; count += 1.5
    elif cash > 0 and debt == 0:
        signals.append({"label":"Cash / Total Debt","value":"Debt-free","score":100,"flag":"✅"})
        total += 100 * 1.5; count += 1.5

    # Quick Ratio
    qr = raw.get("quick_ratio")
    if qr is not None:
        s = _clamp((qr - 0.3) / 1.7 * 100, 0, 100)
        signals.append({
            "label": "Quick Ratio (>1.0 healthy — can meet short-term obligations)",
            "value": round(qr, 2), "score": round(s,1),
            "flag": "✅" if qr > 1.5 else "⚠️" if qr > 0.8 else "🔴"
        })
        total += s * 1.5; count += 1.5

    # Operating Cash Flow vs Net Income — quality check
    ocf = raw.get("operating_cf")
    ni_hist = raw.get("net_income_history", [])
    ni = ni_hist[0] if ni_hist else None
    if ocf and ni and ni > 0:
        ocf_ratio = ocf / ni
        s = _clamp(ocf_ratio * 50, 0, 100)
        signals.append({
            "label": "Operating CF / Net Income (>1.0 = high earnings quality)",
            "value": round(ocf_ratio, 2), "score": round(s,1),
            "flag": "✅" if ocf_ratio > 1.2 else "⚠️" if ocf_ratio > 0.7 else "🔴"
        })
        total += s * 1.5; count += 1.5

    score = round(total / count if count > 0 else 50, 1)
    return {"score": score, "grade": _grade(score), "signals": signals, "dimension": "Financial Health"}


def score_growth(raw: dict) -> dict:
    """
    Score revenue and earnings growth trajectory.
    Returns score 0-100 (100 = strong, accelerating growth).
    """
    signals = []
    total = 0.0; count = 0.0

    # YoY revenue growth
    rg = raw.get("revenue_growth_yoy")
    if rg is not None:
        s = _clamp(50 + rg * 2.5, 0, 100)
        signals.append({
            "label": "Revenue Growth YoY (excellent >20%)",
            "value": round(rg, 1), "score": round(s,1),
            "flag": "✅" if rg > 20 else "⚠️" if rg > 5 else "🔴"
        })
        total += s * 2.0; count += 2.0

    # Revenue CAGR 3Y
    cagr = raw.get("revenue_cagr_3y")
    if cagr is not None:
        s = _clamp(50 + cagr * 2.5, 0, 100)
        signals.append({
            "label": "Revenue CAGR 3Y (excellent >15%)",
            "value": round(cagr, 1), "score": round(s,1),
            "flag": "✅" if cagr > 15 else "⚠️" if cagr > 5 else "🔴"
        })
        total += s * 2.0; count += 2.0

    # YoY earnings growth
    eg = raw.get("earnings_growth_yoy")
    if eg is not None:
        s = _clamp(50 + eg * 2.0, 0, 100)
        signals.append({
            "label": "Earnings Growth YoY (excellent >15%)",
            "value": round(eg, 1), "score": round(s,1),
            "flag": "✅" if eg > 15 else "⚠️" if eg > 0 else "🔴"
        })
        total += s * 2.5; count += 2.5

    # Earnings CAGR 3Y
    ecagr = raw.get("earnings_cagr_3y")
    if ecagr is not None:
        s = _clamp(50 + ecagr * 2.0, 0, 100)
        signals.append({
            "label": "EPS CAGR 3Y (excellent >15%)",
            "value": round(ecagr, 1), "score": round(s,1),
            "flag": "✅" if ecagr > 15 else "⚠️" if ecagr > 5 else "🔴"
        })
        total += s * 2.0; count += 2.0

    # Quarterly earnings growth momentum
    qeg = raw.get("earnings_quarterly_growth")
    if qeg is not None:
        s = _clamp(50 + qeg * 2.0, 0, 100)
        signals.append({
            "label": "Quarterly Earnings Growth (momentum signal)",
            "value": round(qeg, 1), "score": round(s,1),
            "flag": "✅" if qeg > 10 else "⚠️" if qeg > 0 else "🔴"
        })
        total += s * 1.5; count += 1.5

    # Revenue trend (is it accelerating or decelerating?)
    rev_h = raw.get("revenue_history", [])
    if len(rev_h) >= 3:
        # Simple: compare last 2 annual changes
        g1 = (rev_h[0] - rev_h[1]) / abs(rev_h[1]) * 100 if rev_h[1] else 0
        g2 = (rev_h[1] - rev_h[2]) / abs(rev_h[2]) * 100 if rev_h[2] else 0
        trend = g1 - g2
        s = _clamp(50 + trend * 2, 0, 100)
        signals.append({
            "label": "Revenue acceleration trend (YoY growth is: accelerating / decelerating)",
            "value": round(trend, 1), "score": round(s,1),
            "flag": "✅" if trend > 5 else "⚠️" if trend > -5 else "🔴",
            "interpretation": "Accelerating" if trend > 5 else "Stable" if trend > -5 else "Decelerating"
        })
        total += s * 1.0; count += 1.0

    score = round(total / count if count > 0 else 50, 1)
    return {"score": score, "grade": _grade(score), "signals": signals, "dimension": "Growth"}


def score_quality(raw: dict) -> dict:
    """
    Score earnings quality, FCF conversion, and capital allocation.
    Returns score 0-100 (100 = exceptional quality).
    """
    signals = []
    total = 0.0; count = 0.0

    # FCF / Net income conversion
    fcf = raw.get("fcf")
    ni_hist = raw.get("net_income_history", [])
    ni = ni_hist[0] if ni_hist else None
    if fcf and ni and abs(ni) > 0:
        fcf_conv = fcf / ni
        s = _clamp(fcf_conv * 60, 0, 100)
        signals.append({
            "label": "FCF / Net Income (>1.0 = earnings are real cash)",
            "value": round(fcf_conv, 2), "score": round(s,1),
            "flag": "✅" if fcf_conv > 1.0 else "⚠️" if fcf_conv > 0.5 else "🔴"
        })
        total += s * 2.5; count += 2.5

    # Earnings consistency (std dev of net income growth)
    ni_h = raw.get("net_income_history", [])
    if len(ni_h) >= 3:
        growths = []
        for i in range(len(ni_h)-1):
            if ni_h[i+1] and ni_h[i+1] != 0:
                growths.append((ni_h[i] - ni_h[i+1]) / abs(ni_h[i+1]) * 100)
        if growths:
            consistency = 100 - min(np.std(growths), 100)
            s = _clamp(consistency, 0, 100)
            signals.append({
                "label": "Earnings Consistency (stability of annual net income growth)",
                "value": round(float(np.std(growths)), 1), "score": round(s,1),
                "flag": "✅" if np.std(growths) < 20 else "⚠️" if np.std(growths) < 50 else "🔴",
                "interpretation": "Stable" if np.std(growths) < 20 else "Volatile"
            })
            total += s * 2.0; count += 2.0

    # Gross margin stability
    gm = raw.get("gross_margin")
    if gm is not None:
        # High gross margin = pricing power = quality
        s = _clamp(gm * 1.4, 0, 100)
        signals.append({
            "label": "Gross Margin (pricing power indicator)",
            "value": round(gm, 1), "score": round(s,1),
            "flag": "✅" if gm > 50 else "⚠️" if gm > 25 else "🔴"
        })
        total += s * 1.5; count += 1.5

    # Payout discipline — high payout can signal maturity, low can mean growth reinvestment
    payout = raw.get("payout_ratio")
    if payout is not None and payout > 0:
        # 20-60% is the sweet spot — too high risks the dividend, too low = nothing returned
        s = _clamp(100 - abs(payout - 40) * 2, 0, 100)
        signals.append({
            "label": "Payout Ratio (20-60% is sustainable discipline)",
            "value": round(payout, 1), "score": round(s,1),
            "flag": "✅" if 20 < payout < 60 else "⚠️" if payout < 80 else "🔴"
        })
        total += s * 1.0; count += 1.0

    # ROIC vs Cost of Capital proxy (ROIC > 10% typically exceeds WACC)
    roic = raw.get("roic")
    if roic is not None:
        s = _clamp(50 + (roic - 10) * 3, 0, 100)
        signals.append({
            "label": "ROIC vs WACC proxy (>10% = likely creating shareholder value)",
            "value": round(roic, 1), "score": round(s,1),
            "flag": "✅" if roic > 15 else "⚠️" if roic > 8 else "🔴"
        })
        total += s * 2.5; count += 2.5

    # Operating leverage: if operating margin > gross margin * 0.3 = good
    om = raw.get("operating_margin")
    gm = raw.get("gross_margin")
    if om is not None and gm and gm > 0:
        op_lev = om / gm
        s = _clamp(op_lev * 120, 0, 100)
        signals.append({
            "label": "Operating Leverage (operating vs gross margin ratio)",
            "value": round(op_lev, 2), "score": round(s,1),
            "flag": "✅" if op_lev > 0.4 else "⚠️" if op_lev > 0.15 else "🔴"
        })
        total += s * 1.0; count += 1.0

    score = round(total / count if count > 0 else 50, 1)
    return {"score": score, "grade": _grade(score), "signals": signals, "dimension": "Quality"}


# ── DCF Fair Value estimate ───────────────────────────────────────────────────
def estimate_fair_value(raw: dict) -> dict | None:
    """
    Thin wrapper over valuation.dcf_value — the single DCF implementation.

    This module used to carry its own copy, which diverged from valuation.py by
    9–19% whenever data was incomplete and, worse, had no `fcf <= 0` guard: a
    cash-burning name produced a NEGATIVE fair value (-$96.57, margin of safety
    -341%) that was rendered as a real estimate and fed into the timeline entry
    checklist. It also read `(revenue_cagr_3y or 10)`, so a *missing* revenue
    CAGR silently became +10% growth — inventing optimism from absent data.

    valuation.dcf_value guards both cases, so it is the one source of truth.
    This wrapper only reshapes its output into the {fair_value, margin_of_safety,
    …} contract that the Fundamentals/Discovery cards and timeline.py expect.
    """
    try:
        fair = dcf_value(raw)          # None when FCF <= 0 or data is too thin
        price = _s(raw.get("current_price"))
        if fair is None or not price or price <= 0:
            return None

        margin_of_safety = (fair - price) / price * 100

        # Report the same growth rate valuation.dcf_value actually used, rather
        # than recomputing it here and drifting apart again.
        g = 0.08
        fcf_h = raw.get("fcf_history") or []
        if len(fcf_h) >= 3 and fcf_h[-1] and fcf_h[0] and fcf_h[-1] > 0 and fcf_h[0] > 0:
            g = (fcf_h[0] / fcf_h[-1]) ** (1 / (len(fcf_h) - 1)) - 1
        rev_cagr = _s(raw.get("revenue_cagr_3y"))
        if rev_cagr is not None:
            g = (g + rev_cagr / 100) / 2
        g = max(-0.10, min(0.35, g))

        return {
            "fair_value":        round(fair, 2),
            "current_price":     round(price, 2),
            "margin_of_safety":  round(margin_of_safety, 1),
            "growth_assumption": round(g * 100, 1),
            "wacc":              10.0,
            "upside_downside":   "Undervalued"   if margin_of_safety > 15  else
                                 "Fairly Valued" if margin_of_safety > -15 else "Overvalued",
        }
    except Exception:
        return None


# ── Master function ───────────────────────────────────────────────────────────
def compute_fundamentals(ticker: str) -> dict:
    """
    Fetch all fundamental data and compute all 5 dimension scores
    plus a composite score and DCF fair value estimate.
    """
    raw = fetch_fundamentals_raw(ticker)
    if "error" in raw:
        return {"ticker": ticker, "error": raw["error"]}

    # Refuse to score on partial data rather than emitting a confident-looking
    # 50/100 HOLD built out of defaults.
    n_present, missing = _coverage(raw)
    if n_present < REQUIRED_MIN:
        return {
            "ticker":            ticker,
            "name":              raw.get("name", ticker),
            "sector":            raw.get("sector", "Unknown"),
            "industry":          raw.get("industry", "Unknown"),
            "insufficient_data": True,
            "coverage":          n_present,
            "coverage_required": REQUIRED_MIN,
            "coverage_total":    len(KEY_FIELDS),
            "missing_fields":    missing,
            "reason": (
                f"Only {n_present} of {len(KEY_FIELDS)} key fundamental fields "
                f"available (need {REQUIRED_MIN}). Missing: {', '.join(missing)}. "
                f"Typical for pre-revenue, small-cap or thinly-covered listings — "
                f"scoring these on partial data would be misleading."
            ),
            "composite_score":   None,
            "composite_grade":   None,
            "verdict":           "INSUFFICIENT DATA",
            "current_price":     raw.get("current_price"),
        }

    val   = score_valuation(raw)
    prof  = score_profitability(raw)
    hlth  = score_health(raw)
    grw   = score_growth(raw)
    qlty  = score_quality(raw)

    # Composite score — weighted average
    weights = {"valuation": 0.25, "profitability": 0.25,
               "health": 0.20, "growth": 0.20, "quality": 0.10}

    composite = round(
        val["score"]  * weights["valuation"] +
        prof["score"] * weights["profitability"] +
        hlth["score"] * weights["health"] +
        grw["score"]  * weights["growth"] +
        qlty["score"] * weights["quality"],
        1
    )

    dcf = estimate_fair_value(raw)

    # Overall fundamental verdict
    if composite >= 75:   verdict = "STRONG BUY"
    elif composite >= 62: verdict = "BUY"
    elif composite >= 48: verdict = "HOLD"
    elif composite >= 35: verdict = "WEAK"
    else:                 verdict = "AVOID"

    return {
        "ticker":       ticker,
        "name":         raw.get("name", ticker),
        "sector":       raw.get("sector", "Unknown"),
        "industry":     raw.get("industry", "Unknown"),

        # Quick-look metrics for the table
        "pe_trailing":      raw.get("pe_trailing"),
        "pe_forward":       raw.get("pe_forward"),
        "pb":               raw.get("pb"),
        "peg":              raw.get("peg"),
        "ev_ebitda":        raw.get("ev_ebitda"),
        "gross_margin":     raw.get("gross_margin"),
        "operating_margin": raw.get("operating_margin"),
        "net_margin":       raw.get("net_margin"),
        "roe":              raw.get("roe"),
        "roic":             raw.get("roic"),
        "revenue_growth_yoy": raw.get("revenue_growth_yoy"),
        "earnings_growth_yoy": raw.get("earnings_growth_yoy"),
        "revenue_cagr_3y":  raw.get("revenue_cagr_3y"),
        "debt_to_equity":   raw.get("debt_to_equity"),
        "current_ratio":    raw.get("current_ratio"),
        "interest_coverage":raw.get("interest_coverage"),
        "fcf_yield":        raw.get("fcf_yield"),
        "dividend_yield":   raw.get("dividend_yield"),
        "analyst_target":   raw.get("analyst_target"),
        "analyst_upside":   raw.get("analyst_upside"),
        "recommendation":   raw.get("recommendation"),
        "current_price":    raw.get("current_price"),

        # Scores
        "insufficient_data": False,
        "coverage":        n_present,
        "coverage_total":  len(KEY_FIELDS),
        "missing_fields":  missing,
        "composite_score": composite,
        "composite_grade": _grade(composite),
        "verdict":         verdict,
        "valuation":       val,
        "profitability":   prof,
        "health":          hlth,
        "growth":          grw,
        "quality":         qlty,

        # DCF
        "dcf": dcf,

        # Multi-method valuation trigger (add-on)
        "valuation_analysis": compute_valuation(raw),
    }