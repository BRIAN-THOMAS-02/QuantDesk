"""F&O expiry calendar rules engine.

Rules encoded as of SEBI's Oct-2025 rationalization (verify against latest
exchange circulars - each result carries a `rule` string so the UI shows
exactly which assumption produced the date).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

WEEKLY_INDEX_EXPIRY = {          # post-Sep-2025 regime
    "NIFTY": "TUE", "SENSEX": "THU",
}
MONTHLY_LAST_WEEKDAY = "last"     # monthly contracts expire last expiry-weekday


@dataclass
class ExpiryInfo:
    symbol: str
    kind: str                     # weekly|monthly|commodity|currency
    date: str                     # ISO
    rule: str


def _next_weekday(d: date, weekday: int) -> date:
    days_ahead = (weekday - d.weekday()) % 7
    return d + timedelta(days=days_ahead)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


WD = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}


def next_expiries(symbol: str, n: int = 4, today: date | None = None) -> list[ExpiryInfo]:
    today = today or date.today()
    s = symbol.upper()
    out: list[ExpiryInfo] = []

    if s in WEEKLY_INDEX_EXPIRY:                       # weekly index options
        wd = WD[WEEKLY_INDEX_EXPIRY[s]]
        d = _next_weekday(today, wd)
        rule = f"NSE weekly index option expires every {WEEKLY_INDEX_EXPIRY[s]} (post Sep-2025)"
        for _ in range(n):
            out.append(ExpiryInfo(s, "weekly", d.isoformat(), rule))
            d += timedelta(days=7)

    elif s.endswith("_STOCK"):                          # stock options: monthly
        base = s.replace("_STOCK", "")
        y, m = today.year, today.month
        rule = "Stock options expire on the monthly index-expiry weekday of expiry month"
        guard = 0
        while len(out) < n and guard < 48:
            guard += 1
            d = _last_weekday_of_month(y, m, WD[WEEKLY_INDEX_EXPIRY.get("NIFTY", "TUE")])
            if d > today:
                out.append(ExpiryInfo(base, "monthly", d.isoformat(), rule))
            m += 1
            if m > 12:
                m, y = 1, y + 1

    elif s in {"GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC"}:
        d = today
        rule = "MCX contracts: ~19th of prior month (approximate - verify MCX circular)"
        for _ in range(n):
            if d.day >= 19:
                nm, ny = (d.month % 12) + 1, d.year + (d.month == 12)
                d = date(ny, nm, 19)
            else:
                d = date(d.year, d.month, 19)
            out.append(ExpiryInfo(s, "commodity", d.isoformat(), rule))

    elif s in {"USDINR", "EURINR", "GBPINR", "JPYINR"}:
        y, m = today.year, today.month
        rule = "Currency futures: 2 business days before last business day of month"
        for _ in range(n):
            if m == 12:
                last = date(y, 12, 31)
            else:
                last = date(y, m + 1, 1) - timedelta(days=1)
            while last.weekday() >= 5:
                last -= timedelta(days=1)
            exp = last - timedelta(days=2)
            while exp.weekday() >= 5:
                exp -= timedelta(days=1)
            if exp >= today:
                out.append(ExpiryInfo(s, "currency", exp.isoformat(), rule))
            m += 1
            if m > 12:
                m, y = 1, y + 1
            if len(out) >= n:
                break
    else:
        # treat as equity with monthly stock-option style expiry
        return next_expiries(s + "_STOCK", n, today)
    return out[:n]


RADAR_INSTRUMENTS: dict[str, dict] = {
    # key -> {label, source, kind, buzz_query}
    "NIFTY":       {"label": "Nifty 50 Index Options", "yf": "^NSEI", "kind": "index"},
    "BANKNIFTY":   {"label": "Bank Nifty Options", "yf": "^NSEBANK", "kind": "index"},
    "INDIAVIX":    {"label": "India VIX", "yf": "^INDIAVIX", "kind": "vol"},
    "TATAMOTORS":  {"label": "Tata Motors (high-beta auto)", "yf": "TATAMOTORS.NS", "kind": "equity"},
    "ADANIENT":    {"label": "Adani Enterprises (event beta)", "yf": "ADANIENT.NS", "kind": "equity"},
    "ETERNAL":     {"label": "Eternal/Zomato (new-age retail favourite)", "yf": "ETERNAL.NS", "kind": "equity"},
    "IRFC":        {"label": "IRFC (retail momentum favourite)", "yf": "IRFC.NS", "kind": "equity"},
    "RVNL":        {"label": "RVNL (rail capex theme)", "yf": "RVNL.NS", "kind": "equity"},
    "IEX":         {"label": "IEX (policy event beta)", "yf": "IEX.NS", "kind": "equity"},
    "SUZLON":      {"label": "Suzlon (green theme retail heavy)", "yf": "SUZLON.NS", "kind": "equity"},
    "YESBANK":     {"label": "Yes Bank (turnaround/speculative)", "yf": "YESBANK.NS", "kind": "equity"},
    "TATASTEEL":   {"label": "Tata Steel (global beta)", "yf": "TATASTEEL.NS", "kind": "equity"},
    "GOLD":        {"label": "Gold MCX proxy", "yf": "GC=F", "kind": "commodity"},
    "SILVER":      {"label": "Silver MCX proxy", "yf": "SI=F", "kind": "commodity"},
    "CRUDEOIL":    {"label": "Crude Oil MCX proxy", "yf": "CL=F", "kind": "commodity"},
    "NATURALGAS":  {"label": "Natural Gas (extreme vol)", "yf": "NG=F", "kind": "commodity"},
    "USDINR":      {"label": "USD-INR currency futures", "yf": "USDINR=X", "kind": "currency"},
}
