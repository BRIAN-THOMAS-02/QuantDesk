"""Free OSINT data via Yahoo Finance (NSE/BSE symbols). No API key needed.

Good for: daily/hourly OHLCV for equities + indices, fundamentals-ish info.
Limitations: no F&O chain, no delivery %, delayed intraday. The NSEProvider
and KiteProvider cover those gaps.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from utils.helpers import to_yf_symbol
from data.providers.base import DataProvider


class YFinanceProvider(DataProvider):
    name = "yfinance"

    def history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        tk = yf.Ticker(to_yf_symbol(symbol))
        df = tk.history(period=period, interval=interval, auto_adjust=False)
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.index).tz_localize(None)
        cols = {c.lower(): c for c in df.columns}
        out = pd.DataFrame({
            "open": df[cols["open"]], "high": df[cols["high"]],
            "low": df[cols["low"]], "close": df[cols["close"]],
            "volume": df[cols["volume"]] if "volume" in cols else 0,
        })
        return self._validate(out)

    def quote(self, symbol: str) -> dict:
        tk = yf.Ticker(to_yf_symbol(symbol))
        fi = tk.fast_info
        prev = float(fi.get("previousClose") or 0)
        last = float(fi.get("lastPrice") or 0)
        return {
            "symbol": symbol.upper(),
            "ltp": last,
            "prev_close": prev,
            "change_pct": ((last - prev) / prev * 100) if prev else 0.0,
            "day_high": float(fi.get("dayHigh") or 0),
            "day_low": float(fi.get("dayLow") or 0),
            "volume": int(fi.get("lastVolume") or 0),
            "market_cap_cr": (float(fi.get("marketCap") or 0)) / 1e7,
            "currency": fi.get("currency", "INR"),
        }

    def fundamentals(self, symbol: str) -> dict:
        """Lightweight fundamentals snapshot (OSINT)."""
        tk = yf.Ticker(to_yf_symbol(symbol))
        i = tk.info
        keys = ["trailingPE", "forwardPE", "priceToBook", "dividendYield",
                "returnOnEquity", "debtToEquity", "profitMargins",
                "revenueGrowth", "earningsGrowth", "beta", "sector"]
        return {k: i.get(k) for k in keys if i.get(k) is not None}
