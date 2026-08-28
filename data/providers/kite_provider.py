"""Zerodha Kite Connect provider - plug in your API key in .env to activate.

Until then every call raises a clear error; the system runs on OSINT providers.
Once keys are set this becomes the primary source (real-time ticks, F&O chain,
order placement via execution.kite_orders).
"""
from __future__ import annotations

import pandas as pd

from config import settings
from data.providers.base import DataProvider
from utils.helpers import logger

INTERVAL_MAP = {
    "minute": "minute", "3minute": "3minute", "5minute": "5minute",
    "10minute": "10minute", "15minute": "15minute", "30minute": "30minute",
    "60minute": "60minute", "1d": "day",
}


class KiteProvider(DataProvider):
    name = "kite"

    def __init__(self, api_key: str | None = None, access_token: str | None = None):
        self.api_key = api_key or settings.KITE_API_KEY
        self.access_token = access_token or settings.KITE_ACCESS_TOKEN
        self._kite = None
        self._instruments: pd.DataFrame | None = None

    # ------------------------------------------------------------------ #
    @property
    def kite(self):
        if self._kite is not None:
            return self._kite
        if not self.api_key:
            raise RuntimeError(
                "Kite API key missing. Add KITE_API_KEY / KITE_ACCESS_TOKEN to .env "
                "(see README 'Connecting Zerodha'). Meanwhile use NSEProvider/YFinanceProvider.")
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:
            raise RuntimeError("pip install kiteconnect") from e
        k = KiteConnect(api_key=self.api_key)
        if not self.access_token:
            logger.info("Login URL: %s", k.login_url())
            raise RuntimeError("Set KITE_ACCESS_TOKEN from the login flow in README.")
        k.set_access_token(self.access_token)
        self._kite = k
        return k

    # ------------------------------------------------------------------ #
    def instrument_master(self) -> pd.DataFrame:
        """Full tradable universe incl. F&O tokens. Cached per process."""
        if self._instruments is None:
            self._instruments = pd.DataFrame(self.kite.instruments())
        return self._instruments

    def resolve(self, symbol: str, exchange: str = "NSE") -> int:
        m = self.instrument_master()
        row = m[(m.tradingsymbol == symbol.upper()) & (m.exchange == exchange)]
        if row.empty:
            raise KeyError(f"{symbol} on {exchange} not found")
        return int(row.iloc[0].instrument_token)

    # ------------------------------------------------------------------ #
    def history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        from datetime import datetime, timedelta
        end = datetime.now()
        days = {"5d": 5, "1mo": 30, "6mo": 182, "2y": 730}.get(period, 730)
        data = self.kite.historical_data(
            self.resolve(symbol),
            from_=end - timedelta(days=days), to=end,
            interval=INTERVAL_MAP.get(interval, "day"))
        df = pd.DataFrame(data).rename(columns={
            "date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume"})
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            df = df.set_index("date")
        return self._validate(df)

    def quote(self, symbol: str) -> dict:
        q = self.kite.quote(f"NSE:{symbol.upper()}")[f"NSE:{symbol.upper()}"]
        return {
            "symbol": symbol.upper(),
            "ltp": q.get("last_price"),
            "prev_close": q.get("ohlc", {}).get("close"),
            "change_pct": ((q["last_price"] / q["ohlc"]["close"]) - 1) * 100
                          if q.get("ohlc", {}).get("close") else 0,
            "volume": q.get("volume"),
            "oi": q.get("oi"),
            "depth_buy": q.get("depth", {}).get("buy", [])[:3],
            "depth_sell": q.get("depth", {}).get("sell", [])[:3],
        }

    def option_chain(self, underlying: str, expiry: str | None = None) -> pd.DataFrame:
        m = self.instrument_master()
        u = underlying.upper()
        opts = m[(m.name == u) & (m.instrument_type.isin(["CE", "PE"]))]
        if expiry:
            opts = opts[opts.expiry.astype(str).str[:10] == str(expiry)[:10]]
        tokens = opts.instrument_token.tolist()
        quotes = self.kite.quote([int(t) for t in tokens])
        rows = []
        for tok, q in quotes.items():
            r = opts[opts.instrument_token == tok].iloc[0]
            rows.append({
                "strike": float(r.strike), "type": r.instrument_type,
                "expiry": r.expiry, "ltp": q.get("last_price"),
                "oi": q.get("oi"), "chg_oi": q.get("oi_day_high") and 0,
                "volume": q.get("volume"),
                "bid": (q.get("depth", {}).get("buy") or [{}])[0].get("price"),
                "ask": (q.get("depth", {}).get("sell") or [{}])[0].get("price"),
            })
        return pd.DataFrame(rows)

    def margins(self) -> dict:
        return self.kite.margins()
