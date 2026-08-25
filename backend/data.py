"""
data.py  –  Yahoo Finance data fetcher with local cache
"""
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

CACHE_DIR = Path.home() / ".portfolio_v3_cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL  = 4   # hours


def _cache_path(ticker: str, period: str) -> Path:
    return CACHE_DIR / f"{ticker}_{period}.parquet"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=CACHE_TTL)


def _cache_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    return (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds() / 3600.0


# Records which tickers were served from an out-of-date cache on the last run,
# so the API can tell the user their numbers aren't live. {ticker: age_hours}
LAST_STALE: dict[str, float] = {}


def _read_cache(path: Path) -> pd.Series | None:
    try:
        s = pd.read_parquet(path)["price"]
        return s if len(s) >= 20 else None
    except Exception:
        return None


def fetch_prices(ticker: str, period: str = "5y") -> pd.Series | None:
    """
    Fresh cache → live fetch → STALE cache.

    That last step matters: Yahoo rate-limits aggressively (HTTP 429), and
    without a fallback a single throttled request turns a complete local price
    history into a hard failure. Day-old daily bars are entirely usable for a
    multi-year analysis — far better than refusing to run at all. Callers can
    read LAST_STALE to see what wasn't live.
    """
    cache = _cache_path(ticker, period)
    if _is_fresh(cache):
        s = _read_cache(cache)
        if s is not None:
            return s

    err = None
    try:
        data = yf.download(ticker, period=period, auto_adjust=True,
                            progress=False, threads=False)
        if not data.empty and len(data) >= 20:
            prices = (data["Close"].squeeze() if isinstance(data.columns, pd.MultiIndex)
                      else data["Close"]).dropna()
            if len(prices) >= 20:
                try:
                    pd.DataFrame({"price": prices}).to_parquet(cache)
                except Exception:
                    pass          # a read-only cache dir must not fail the fetch
                LAST_STALE.pop(ticker, None)
                return prices
    except Exception as e:
        err = e

    # Live fetch failed or came back empty — fall back to whatever we have.
    s = _read_cache(cache)
    if s is not None:
        age = _cache_age_hours(cache) or 0.0
        LAST_STALE[ticker] = round(age, 1)
        print(f"  [~] {ticker}: live fetch unavailable, using cache from "
              f"{age:.0f}h ago{f' ({type(err).__name__})' if err else ''}")
        return s

    print(f"  [!] {ticker}: no live data and no cache{f' — {err}' if err else ''}")
    return None


def fetch_all(tickers: list[str], period: str = "5y",
              benchmark: str = "SPY") -> dict[str, pd.Series]:
    result = {}
    all_t  = list(dict.fromkeys(list(tickers) + [benchmark]))
    held   = set(tickers)
    LAST_STALE.clear()
    for t in all_t:
        prices = fetch_prices(t, period)
        if prices is None:
            continue
        # A ticker can be both a holding and the benchmark (e.g. holding SPY while
        # benchmarking against SPY). Store it under both keys — filing it only
        # under "__benchmark" used to drop it from the portfolio entirely and
        # report it as "No data from Yahoo Finance".
        if t in held:
            result[t] = prices
        if t == benchmark:
            result["__benchmark"] = prices
    return result


def clear_cache():
    for f in CACHE_DIR.glob("*.parquet"):
        f.unlink()
