"""
dividends.py — High dividend-yield screener built on yfinance's screener API.

Ranks US-listed equities by dividend yield using `yf.screen` + `yf.EquityQuery`,
then hands the results to the same fundamentals engine the rest of this app uses.

READ THIS BEFORE TRUSTING THE RANKING
-------------------------------------
Sorting by raw dividend yield surfaces **yield traps**. A yield is just
dividend / price, so the fastest way to the top of this list is for the price to
collapse — which is usually the market pricing in a cut that has not been
announced yet. The highest-yielding name in any screen is more often a business
in trouble than a bargain.

The filters here are *partial* mitigations, not a solution:

  * **Market cap floor** removes micro-caps, where thin coverage and stale data
    make the reported yield least reliable.
  * **Payout ratio ceiling** removes companies paying out more than they earn, a
    dividend that arithmetic alone says cannot continue. NOTE: Yahoo's screener
    exposes no payout field (see `discover_fields`), so this filter is normally
    applied *after* the screen, from per-ticker `.info`, or skipped entirely.

Neither catches a cyclical peak, a pending cut, a one-off special dividend
inflating a trailing figure, or a REIT/BDC/MLP whose payout ratio is not
comparable to an ordinary corporation's. Treat the output as a candidate list to
research, never as a buy list. Run the fundamentals scoring on anything you take
seriously — coverage, leverage and free cash flow are what tell you whether the
dividend is actually funded.

CLI
---
    python dividends.py --min-yield 4 --min-market-cap 2e9 --limit 100
    python dividends.py --show-fields
    python dividends.py --fallback AAPL MSFT KO PG T VZ
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Final, Iterable, Sequence

import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — the ONLY place Yahoo/yfinance field-name strings appear.
#
# Nothing below this dict hardcodes a schema string. When Yahoo renames a field,
# this is the single file location to edit.
# ─────────────────────────────────────────────────────────────────────────────
CONFIG: Final[dict[str, Any]] = {
    # ── Screener operands ────────────────────────────────────────────────────
    "operands": {
        "region": "region",
        "exchange": "exchange",
    },
    # Discovery rules: logical name -> tokens that must ALL appear (lowercased)
    # in a valid field name. We never assume the field is literally called this.
    "discover": {
        "dividend_yield": ("dividend", "yield"),
        "payout_ratio": ("payout",),
        "market_cap": ("marketcap",),
    },
    # When several fields match a rule, prefer these exact names in order.
    # `dividendyield` is the trailing figure; `forward_dividend_yield` is the
    # forward estimate. Trailing is the honest default — forward is a projection.
    "prefer": {
        "dividend_yield": ("dividendyield", "forward_dividend_yield"),
        "market_cap": ("intradaymarketcap", "lastclosemarketcap.lasttwelvemonths"),
        "payout_ratio": (),
    },
    # Rules we refuse to run without. Anything not listed is optional.
    "required": ("dividend_yield", "market_cap"),
    # ── Screener response shape ──────────────────────────────────────────────
    "response": {
        "rows": ("quotes", "records"),
        "total": ("total", "count"),
    },
    # Output column -> candidate response keys, first present key wins.
    "columns": {
        "ticker": ("symbol",),
        "name": ("shortName", "longName", "displayName"),
        "sector": ("sector", "sectorDisp"),
        "price": ("regularMarketPrice", "intradayprice", "previousClose"),
        "dividend_yield": ("dividendYield", "trailingAnnualDividendYield"),
        # Annual dividend per share in DOLLARS. Trailing preferred (matches the
        # trailing yield the table ranks by); forward rate as fallback. When
        # Yahoo omits both, it is derived as price * yield.
        "dividend_rate": ("trailingAnnualDividendRate", "dividendRate"),
        "payout_ratio": ("payoutRatio",),
        "market_cap": ("marketCap",),
        "five_year_avg_yield": ("fiveYearAvgDividendYield",),
    },
    # ── Per-ticker .info keys, used by --fallback and payout enrichment ──────
    "info": {
        "dividend_yield": ("dividendYield", "trailingAnnualDividendYield"),
        "dividend_rate": ("trailingAnnualDividendRate", "dividendRate"),
        "payout_ratio": ("payoutRatio",),
        "five_year_avg_yield": ("fiveYearAvgDividendYield",),
        "price": ("currentPrice", "regularMarketPrice", "previousClose"),
        "name": ("shortName", "longName"),
        "sector": ("sector",),
        "market_cap": ("marketCap",),
    },
    # ── Units ────────────────────────────────────────────────────────────────
    # Yahoo is inconsistent here and yfinance does NOT normalise it, so the
    # assumption is declared rather than sniffed at runtime. This codebase
    # deliberately avoids magnitude-sniffing heuristics (see the debt_to_equity
    # note in fundamentals.py) — they silently invert on edge values. Override
    # with --yield-units if a future Yahoo change flips one of these.
    "units": {
        "screener_yield": "percent",  # screener returns 4.2 for 4.2%
        "info_yield": "percent",      # confirmed live 2026-08-26: KO -> 2.31
        # Per-key exceptions to the defaults above. trailingAnnualDividendYield
        # stayed in fraction form when dividendYield moved to percent, so one
        # flag cannot cover a fallback chain spanning both keys. CONFIRMED live
        # 2026-08-26 on KO: dividendYield -> 2.31 (percent) while
        # trailingAnnualDividendYield -> 0.0227 (fraction), same dividend.
        # fiveYearAvgDividendYield has always been percent and is never scaled.
        "by_key": {
            "trailingAnnualDividendYield": "fraction",
        },
    },
    # ── Pagination / networking ──────────────────────────────────────────────
    "paging": {
        "max_page_size": 250,  # Yahoo's hard per-request cap
        "max_pages": 40,       # backstop against a non-advancing cursor
    },
    "retry": {
        "attempts": 4,
        "base_delay": 1.5,
        "max_delay": 30.0,
    },
}

DEFAULTS: Final[dict[str, Any]] = {
    "region": "us",
    "exchanges": ("NMS", "NYQ"),
    "min_market_cap": 2_000_000_000.0,
    "min_yield": 4.0,
    "max_payout": 0.7,
    "limit": 100,
    "output": "dividend_screen.csv",
}


class ScreenerError(RuntimeError):
    """Raised when Yahoo's response does not match the shape we expect.

    Exists so a schema change reads as a sentence instead of surfacing as a bare
    KeyError/IndexError from somewhere deep in a dict walk.
    """


@dataclass(frozen=True)
class FieldMap:
    """Screener field names resolved against the installed yfinance version."""

    resolved: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()

    def __getitem__(self, logical: str) -> str:
        try:
            return self.resolved[logical]
        except KeyError:
            raise ScreenerError(
                f"Field '{logical}' was not resolved for this yfinance version. "
                f"Resolved: {sorted(self.resolved)}; missing: {list(self.missing)}."
            ) from None

    def has(self, logical: str) -> bool:
        return logical in self.resolved


# ─────────────────────────────────────────────────────────────────────────────
# Field discovery
# ─────────────────────────────────────────────────────────────────────────────
def valid_fields() -> dict[str, list[str]]:
    """Return yfinance's valid screener operands, grouped by category.

    `valid_fields` is a *property*, so it only yields data on an instance — a
    bare `yf.EquityQuery.valid_fields` returns the property object itself. We
    build a throwaway instance to read it. No network call is involved.
    """
    try:
        probe = yf.EquityQuery("eq", [CONFIG["operands"]["region"], DEFAULTS["region"]])
        fields = probe.valid_fields
    except Exception as exc:  # construction or property access changed shape
        raise ScreenerError(
            f"Could not read EquityQuery.valid_fields from yfinance "
            f"{getattr(yf, '__version__', '?')}: {type(exc).__name__}: {exc}. "
            "The screener API has likely changed shape."
        ) from exc

    if not isinstance(fields, dict) or not fields:
        raise ScreenerError(
            f"EquityQuery.valid_fields returned {type(fields).__name__}, expected a "
            "non-empty dict of category -> field names."
        )
    return {str(k): [str(f) for f in v] for k, v in fields.items()}


def discover_fields(verbose: bool = False) -> FieldMap:
    """Resolve logical names to real screener fields by token matching.

    Deliberately never assumes a literal field name: each rule in
    CONFIG["discover"] is a set of tokens that must all appear. Where several
    fields match, CONFIG["prefer"] breaks the tie deterministically — without
    it, `dividend_yield` is ambiguous, since yfinance exposes both a trailing
    and a forward yield (and lists the forward one under two categories).
    """
    catalogue = valid_fields()
    # Re-check the shape here too. `valid_fields()` validates its own output, but
    # this function must not assume that: it is the seam a Yahoo/yfinance schema
    # change arrives through, and the contract is a readable error, never an
    # AttributeError/KeyError from a dict walk two lines down.
    if not isinstance(catalogue, dict):
        raise ScreenerError(
            f"Field catalogue is {type(catalogue).__name__}, expected dict of "
            "category -> field names. The screener API has changed shape."
        )
    # de-duplicate but keep first-seen order; a field can appear in >1 category
    seen: dict[str, None] = {}
    for category, names in catalogue.items():
        if not isinstance(names, (list, tuple, set)):
            raise ScreenerError(
                f"Field catalogue entry {category!r} is {type(names).__name__}, "
                "expected a sequence of field names."
            )
        for name in names:
            seen.setdefault(str(name), None)
    flat = list(seen)

    if verbose:
        print(f"yfinance {getattr(yf, '__version__', '?')} — "
              f"{len(flat)} screener fields across {len(catalogue)} categories")
        for category, names in catalogue.items():
            print(f"  [{category}] {', '.join(sorted(names))}")
        print()

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for logical, tokens in CONFIG["discover"].items():
        matches = [f for f in flat if all(t in f.lower() for t in tokens)]
        if not matches:
            missing.append(logical)
            continue
        chosen = next((p for p in CONFIG["prefer"].get(logical, ()) if p in matches),
                      matches[0])
        resolved[logical] = chosen
        if verbose:
            others = [m for m in matches if m != chosen]
            extra = f"  (also matched: {', '.join(others)})" if others else ""
            print(f"  {logical:16} -> {chosen}{extra}")

    for logical in CONFIG["required"]:
        if logical not in resolved:
            raise ScreenerError(
                f"No screener field matches {logical!r} "
                f"(tokens {CONFIG['discover'][logical]}) in yfinance "
                f"{getattr(yf, '__version__', '?')}. Searched {len(flat)} fields. "
                "Run with --show-fields to inspect the catalogue, then update "
                "CONFIG['discover'] / CONFIG['prefer']."
            )
    if verbose and missing:
        print(f"  not available in this version (filters skipped): {', '.join(missing)}")
        print()
    return FieldMap(resolved=resolved, missing=tuple(missing))


# ─────────────────────────────────────────────────────────────────────────────
# Query construction + paginated screening
# ─────────────────────────────────────────────────────────────────────────────
def build_query(
    fields: FieldMap,
    region: str,
    exchanges: Sequence[str],
    min_market_cap: float,
    min_yield: float,
    max_payout: float | None,
) -> yf.EquityQuery:
    """Assemble the EquityQuery. Filters for unavailable fields are omitted."""
    ops = CONFIG["operands"]
    clauses: list[yf.EquityQuery] = [
        yf.EquityQuery("eq", [ops["region"], region]),
        yf.EquityQuery("gt", [fields["market_cap"], float(min_market_cap)]),
        yf.EquityQuery("gt", [fields["dividend_yield"], float(min_yield)]),
    ]
    if exchanges:
        clauses.append(yf.EquityQuery("is-in", [ops["exchange"], *exchanges]))
    # Only ever added when the installed version actually exposes the field —
    # EquityQuery validates operands at construction and raises on an unknown
    # one, so an optimistic clause here would hard-fail the whole screen.
    if max_payout is not None and fields.has("payout_ratio"):
        clauses.append(yf.EquityQuery("lt", [fields["payout_ratio"], float(max_payout)]))

    try:
        return yf.EquityQuery("and", clauses)
    except Exception as exc:
        raise ScreenerError(
            f"Rejected by yfinance while building the query: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _pluck(row: dict[str, Any], keys: Iterable[str]) -> Any:
    """First present, non-null value among `keys`; None if none are present."""
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _yield_pct(row: dict[str, Any], keys: Iterable[str],
               default_units: str) -> float | None:
    """Dividend yield in PERCENT, honouring per-key unit exceptions.

    The fallback keys do not share units (dividendYield is percent,
    trailingAnnualDividendYield is a fraction), so the scaling decision has to
    know WHICH key supplied the value — a single flag applied after a blind
    _pluck was wrong by 100x whenever the fallback key fired.
    """
    for key in keys:
        if key in row and row[key] is not None:
            value = _num(row[key])
            if value is None:
                continue
            units = CONFIG["units"]["by_key"].get(key, default_units)
            return round(value * 100.0, 3) if units == "fraction" else round(value, 3)
    return None


def _rows_from(payload: Any) -> list[dict[str, Any]]:
    """Extract the result rows, tolerating a renamed container key."""
    if not isinstance(payload, dict):
        raise ScreenerError(
            f"Screener returned {type(payload).__name__}, expected a dict. "
            "Yahoo's response envelope has changed."
        )
    for key in CONFIG["response"]["rows"]:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    raise ScreenerError(
        f"No result rows in the screener response. Looked for "
        f"{list(CONFIG['response']['rows'])}, found keys: {sorted(payload)}."
    )


def _with_retry(call, what: str):
    """Run `call`, retrying with exponential backoff + jitter on failure.

    Yahoo rate-limits aggressively (HTTP 429) and intermittently 5xxs. Retrying
    is the difference between a usable screen and a stack trace.
    """
    cfg = CONFIG["retry"]
    last: Exception | None = None
    for attempt in range(cfg["attempts"]):
        try:
            return call()
        except Exception as exc:
            last = exc
            if attempt == cfg["attempts"] - 1:
                break
            delay = min(cfg["base_delay"] * (2 ** attempt), cfg["max_delay"])
            delay += random.uniform(0, delay * 0.25)
            print(f"  [~] {what}: {type(exc).__name__} — retrying in {delay:.1f}s "
                  f"({attempt + 1}/{cfg['attempts'] - 1})", file=sys.stderr)
            time.sleep(delay)
    raise ScreenerError(
        f"{what} failed after {cfg['attempts']} attempts: "
        f"{type(last).__name__}: {last}"
    ) from last


def screen_dividends(
    fields: FieldMap,
    *,
    region: str = DEFAULTS["region"],
    exchanges: Sequence[str] = DEFAULTS["exchanges"],
    min_market_cap: float = DEFAULTS["min_market_cap"],
    min_yield: float = DEFAULTS["min_yield"],
    max_payout: float | None = DEFAULTS["max_payout"],
    limit: int = DEFAULTS["limit"],
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Run the screen, paginating past Yahoo's 250-row-per-request cap."""
    query = build_query(fields, region, exchanges, min_market_cap, min_yield, max_payout)
    sort_field = fields["dividend_yield"]
    page_size = min(CONFIG["paging"]["max_page_size"], max(int(limit), 1))

    collected: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    offset = 0

    for page in range(CONFIG["paging"]["max_pages"]):
        payload = _with_retry(
            lambda: yf.screen(query, offset=offset, size=page_size,
                              sortField=sort_field, sortAsc=False),
            f"screen page {page + 1} (offset {offset})",
        )
        rows = _rows_from(payload)
        if not rows:
            break

        # Yahoo sometimes ignores a large offset and replays page 1. Dedupe by
        # ticker so a non-advancing cursor terminates instead of looping.
        fresh = 0
        for row in rows:
            ticker = _pluck(row, CONFIG["columns"]["ticker"])
            if not ticker or ticker in seen_tickers:
                continue
            seen_tickers.add(str(ticker))
            collected.append(row)
            fresh += 1
            if len(collected) >= limit:
                break

        if verbose:
            print(f"  page {page + 1}: {len(rows)} rows, {fresh} new "
                  f"({len(collected)}/{limit} collected)")

        if len(collected) >= limit or fresh == 0 or len(rows) < page_size:
            break
        offset += page_size

    return collected[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Shaping
# ─────────────────────────────────────────────────────────────────────────────
def _num(value: Any) -> float | None:
    """Coerce to a finite float, or None. Never raises."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def to_dataframe(rows: list[dict[str, Any]], *, yield_units: str) -> pd.DataFrame:
    """Shape raw screener rows into the documented output columns."""
    columns = CONFIG["columns"]

    records: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = {}
        for name, candidates in columns.items():
            if name == "dividend_yield":
                record[name] = _yield_pct(row, candidates, yield_units)
                continue
            value = _pluck(row, candidates)
            record[name] = value if name in ("ticker", "name", "sector") else _num(value)
        # fiveYearAvgDividendYield is always percent — never rescaled.
        if record.get("five_year_avg_yield") is not None:
            record["five_year_avg_yield"] = round(record["five_year_avg_yield"], 3)
        # Dollar amount: derive from price * yield when Yahoo omits the field.
        if record.get("dividend_rate") is None and \
                record.get("price") is not None and record.get("dividend_yield") is not None:
            record["dividend_rate"] = round(record["price"] * record["dividend_yield"] / 100.0, 2)
        records.append(record)

    frame = pd.DataFrame(records, columns=list(columns))
    if not frame.empty:
        frame = frame.sort_values("dividend_yield", ascending=False, na_position="last")
        frame = frame.reset_index(drop=True)
    return frame


def enrich_payout(frame: pd.DataFrame, *, verbose: bool = True) -> pd.DataFrame:
    """Fill missing payout ratios from per-ticker `.info`.

    The screener has no payout field, so when the ceiling matters it has to be
    applied here — one request per ticker, which is why it is opt-in.
    """
    if frame.empty or "payout_ratio" not in frame:
        return frame
    need = frame["payout_ratio"].isna()
    if not need.any():
        return frame
    if verbose:
        print(f"  fetching payout ratio for {int(need.sum())} tickers…")
    for idx in frame.index[need]:
        ticker = frame.at[idx, "ticker"]
        info = _safe_info(str(ticker))
        if info:
            frame.at[idx, "payout_ratio"] = _num(
                _pluck(info, CONFIG["info"]["payout_ratio"])
            )
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: per-ticker .info, no screener
# ─────────────────────────────────────────────────────────────────────────────
def _safe_info(ticker: str) -> dict[str, Any] | None:
    """Fetch `.info` with retry. Returns None rather than raising."""
    try:
        info = _with_retry(lambda: yf.Ticker(ticker).info, f"{ticker} .info")
    except ScreenerError:
        return None
    return info if isinstance(info, dict) and info else None


def fallback_yields(
    tickers: Sequence[str], *, yield_units: str, verbose: bool = True
) -> pd.DataFrame:
    """Build the same table from per-ticker `.info`, skipping the screener.

    Tickers with no dividend data are reported and excluded rather than being
    emitted as a 0% yield, which would rank them as if they were real results.
    """
    keys = CONFIG["info"]
    records: list[dict[str, Any]] = []
    skipped: list[str] = []

    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        info = _safe_info(ticker)
        if info is None:
            skipped.append(f"{ticker} (no data)")
            continue
        dy = _yield_pct(info, keys["dividend_yield"], yield_units)
        if dy is None:
            skipped.append(f"{ticker} (pays no dividend)")
            continue
        price = _num(_pluck(info, keys["price"]))
        rate = _num(_pluck(info, keys["dividend_rate"]))
        if rate is None and price is not None:
            rate = round(price * dy / 100.0, 2)
        records.append({
            "ticker": ticker,
            "name": _pluck(info, keys["name"]),
            "sector": _pluck(info, keys["sector"]),
            "price": price,
            "dividend_yield": dy,
            "dividend_rate": rate,
            "payout_ratio": _num(_pluck(info, keys["payout_ratio"])),
            "market_cap": _num(_pluck(info, keys["market_cap"])),
            "five_year_avg_yield": _num(_pluck(info, keys["five_year_avg_yield"])),
        })
        if verbose:
            print(f"  {ticker}: {records[-1]['dividend_yield']}%")

    if verbose and skipped:
        print(f"  skipped {len(skipped)}: {', '.join(skipped)}")

    frame = pd.DataFrame(records, columns=list(CONFIG["columns"]))
    if not frame.empty:
        frame = frame.sort_values("dividend_yield", ascending=False).reset_index(drop=True)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("CLI")[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--region", default=DEFAULTS["region"])
    parser.add_argument("--exchanges", nargs="*", default=list(DEFAULTS["exchanges"]))
    parser.add_argument("--min-market-cap", type=float, default=DEFAULTS["min_market_cap"])
    parser.add_argument("--min-yield", type=float, default=DEFAULTS["min_yield"],
                        help="in percent, e.g. 4 for 4%%")
    parser.add_argument("--max-payout", type=float, default=DEFAULTS["max_payout"],
                        help="skipped automatically if the field is unavailable")
    parser.add_argument("--no-payout-filter", action="store_true",
                        help="never apply the payout ceiling")
    parser.add_argument("--enrich-payout", action="store_true",
                        help="fill missing payout ratios from per-ticker .info "
                             "(one request per ticker) and apply the ceiling")
    parser.add_argument("--limit", type=int, default=DEFAULTS["limit"])
    parser.add_argument("--output", default=DEFAULTS["output"])
    parser.add_argument("--yield-units", choices=("percent", "fraction"),
                        default=CONFIG["units"]["screener_yield"],
                        help="how to interpret Yahoo's yield values")
    parser.add_argument("--show-fields", action="store_true",
                        help="print the screener field catalogue and exit")
    parser.add_argument("--fallback", nargs="*", metavar="TICKER",
                        help="skip the screener; read .info for these tickers")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    verbose = not args.quiet

    try:
        if args.show_fields:
            discover_fields(verbose=True)
            return 0

        if args.fallback is not None:
            if not args.fallback:
                print("--fallback needs at least one ticker.", file=sys.stderr)
                return 2
            if verbose:
                print(f"Fallback mode — {len(args.fallback)} tickers, screener skipped")
            frame = fallback_yields(args.fallback,
                                    yield_units=CONFIG["units"]["info_yield"],
                                    verbose=verbose)
        else:
            fields = discover_fields(verbose=verbose)
            max_payout = None if args.no_payout_filter else args.max_payout
            if verbose and max_payout is not None and not fields.has("payout_ratio"):
                print("  note: no payout field in this yfinance version — "
                      "ceiling not applied in the screen "
                      "(use --enrich-payout to apply it afterwards)")
            rows = screen_dividends(
                fields,
                region=args.region,
                exchanges=args.exchanges,
                min_market_cap=args.min_market_cap,
                min_yield=args.min_yield,
                max_payout=max_payout,
                limit=args.limit,
                verbose=verbose,
            )
            frame = to_dataframe(rows, yield_units=args.yield_units)
            if args.enrich_payout and max_payout is not None:
                frame = enrich_payout(frame, verbose=verbose)
                before = len(frame)
                frame = frame[
                    frame["payout_ratio"].isna() | (frame["payout_ratio"] < max_payout)
                ].reset_index(drop=True)
                if verbose:
                    print(f"  payout ceiling removed {before - len(frame)} rows")
    except ScreenerError as exc:
        print(f"\nScreener error: {exc}", file=sys.stderr)
        return 1

    if frame.empty:
        print("No results.", file=sys.stderr)
        return 1

    if verbose:
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print(f"\n{len(frame)} results\n")
            print(frame.head(25).to_string(index=False))
        print("\nReminder: a high raw yield is as often a distress signal as a "
              "bargain. Check coverage and free cash flow before acting.")

    frame.to_csv(args.output, index=False)
    print(f"\nWrote {len(frame)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
