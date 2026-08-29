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
        try:
            fi = tk.fast_info
            prev = float(fi.get("previousClose") or 0)
            last = float(fi.get("lastPrice") or 0)
            data = {
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
            if data["ltp"] or data["prev_close"]:
                return data
        except Exception:
            pass
         # Fallback: some yfinance versions make fast_info.lastPrice trigger a
         # 1y history fetch that raises; derive the snapshot from recent bars.
        hist = self.history(symbol, "5d")
        if hist.empty:
            return {"symbol": symbol.upper(), "ltp": 0.0, "prev_close": 0.0,
                     "change_pct": 0.0, "day_high": 0.0, "day_low": 0.0,
                     "volume": 0, "market_cap_cr": 0.0, "currency": "INR"}
        last = float(hist["close"].iloc[-1])
        prev = float(hist["close"].iloc[-2]) if len(hist) > 1 else last
        return {
             "symbol": symbol.upper(),
             "ltp": last,
             "prev_close": prev,
             "change_pct": ((last - prev) / prev * 100) if prev else 0.0,
             "day_high": float(hist["high"].iloc[-1]),
             "day_low": float(hist["low"].iloc[-1]),
             "volume": int(hist["volume"].iloc[-1]) if "volume" in hist else 0,
             "market_cap_cr": 0.0,
             "currency": "INR",
          }

    def fundamentals(self, symbol: str) -> dict:
        """Lightweight fundamentals snapshot (OSINT)."""
        tk = yf.Ticker(to_yf_symbol(symbol))
        i = tk.info
        keys = ["trailingPE", "forwardPE", "priceToBook", "dividendYield",
                "returnOnEquity", "debtToEquity", "profitMargins",
                "revenueGrowth", "earningsGrowth", "beta", "sector"]
        return {k: i.get(k) for k in keys if i.get(k) is not None}
