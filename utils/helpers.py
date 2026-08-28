"""Shared helpers."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, time as dtime
from functools import lru_cache

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("trading")

NSE_YF_SUFFIX = ".NS"


def to_yf_symbol(symbol: str) -> str:
    """RELIANCE -> RELIANCE.NS. Indices (^NSEI), BSE (.BO), futures (GC=F)
    and FX (USDINR=X) pass through untouched."""
    s = symbol.strip().upper()
    if s.startswith("^") or "." in s or "=" in s:
        return s
    return f"{s}{NSE_YF_SUFFIX}"


@lru_cache(maxsize=1)
def nse_holidays(year: int | None = None) -> set[pd.Timestamp]:
    """Best-effort static NSE holiday list (OSINT). Extend yearly."""
    year = year or datetime.now().year
    static = {
        2024: ["2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29",
               "2024-04-11", "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17",
               "2024-07-17", "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15",
               "2024-11-20", "2024-12-25"],
        2025: ["2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14",
               "2025-04-18", "2025-05-01", "2025-08-15", "2025-08-27", "2025-10-02",
               "2025-10-21", "2025-10-22", "2025-11-05", "2025-12-25"],
        2026: ["2026-01-26", "2026-03-03", "2026-03-04", "2026-03-21", "2026-04-01",
               "2026-04-03", "2026-04-14", "2026-05-01", "2026-08-15", "2026-10-02",
               "2026-11-09", "2026-11-24", "2026-12-25"],
    }
    return {pd.Timestamp(d) for d in static.get(year, [])}


def is_trading_day(ts: pd.Timestamp) -> bool:
    if ts.weekday() >= 5:
        return False
    return ts.normalize() not in nse_holidays(ts.year)


def market_phase(now: datetime | None = None) -> str:
    """NSE session phases in IST. Caller should pass IST time if possible."""
    now = now or datetime.now()
    t = now.time()
    pre = dtime(9, 0)
    open_t = dtime(9, 15)
    close_t = dtime(15, 30)
    if not is_trading_day(pd.Timestamp(now)):
        return "CLOSED_HOLIDAY"
    if t < pre:
        return "PRE_OPEN_PENDING"
    if pre <= t < open_t:
        return "PRE_OPEN_AUCTION"
    if open_t <= t <= close_t:
        return "OPEN"
    return "POST_CLOSE"


def annualized_return(series: pd.Series, periods_per_year: int = 252) -> float:
    total = series.iloc[-1] / series.iloc[0]
    years = len(series) / periods_per_year
    return float(total ** (1 / years) - 1) if years > 0 else 0.0


def pretty_table(df: pd.DataFrame) -> str:
    try:
        from tabulate import tabulate
        return tabulate(df, headers="keys", tablefmt="github", showindex=False, floatfmt=".2f")
    except ImportError:
        return df.to_string(index=False)
