"""Direct NSE India public API client (OSINT - no key required).

Covers what yfinance cannot: option chains, bulk/block deals (whale prints),
delivery %, FII/DII daily flows, live quotes.

NSE blocks non-browser clients -> we emulate a browser session with cookie
handshake. Endpoints occasionally change; keep this file the single place to fix.
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import requests

from data.providers.base import DataProvider
from utils.helpers import logger

BASE = "https://www.nseindia.com"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


class NSEProvider(DataProvider):
    name = "nse"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(BROWSER_HEADERS)
        self._cookie_ts = 0.0

    # ------------------------------------------------------------------ #
    def _ensure_cookies(self, max_age: int = 300):
        if time.time() - self._cookie_ts > max_age:
            try:
                self._session.get(BASE, timeout=10)
                self._cookie_ts = time.time()
            except requests.RequestException as e:
                logger.warning("NSE cookie handshake failed: %s", e)

    def _get_json(self, path: str, params: dict | None = None, retries: int = 3) -> dict:
        for attempt in range(1, retries + 1):
            self._ensure_cookies()
            try:
                r = self._session.get(f"{BASE}{path}", params=params, timeout=15)
                if r.status_code == 200:
                    return r.json()
                logger.debug("NSE %s -> HTTP %s (attempt %d)", path, r.status_code, attempt)
            except (requests.RequestException, ValueError) as e:
                logger.debug("NSE %s failed (attempt %d): %s", path, attempt, e)
            time.sleep(1.2 * attempt)
        raise ConnectionError(f"NSE endpoint unreachable: {path}")

    # ------------------------------------------------------------------ #
    # OHLCV fallback via quote API (use YFinanceProvider for long history)
    # ------------------------------------------------------------------ #
    def history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        from data.providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider().history(symbol, period, interval)

    def quote(self, symbol: str) -> dict:
        d = self._get_json("/api/quote-equity", {"symbol": symbol.upper()})
        price = d.get("priceInfo", {})
        return {
            "symbol": d.get("info", {}).get("symbol", symbol.upper()),
            "ltp": price.get("lastPrice"),
            "prev_close": price.get("previousClose"),
            "change_pct": price.get("pChange"),
            "day_high": price.get("intraDayHighLow", {}).get("max"),
            "day_low": price.get("intraDayHighLow", {}).get("min"),
            "open": price.get("open"),
            "volume": d.get("securityWiseDP", {}).get("lastQty"),
            "total_traded_value_cr": (d.get("priceInfo", {}).get("totalTradedValue") or 0) / 1e7,
        }

    # ------------------------------------------------------------------ #
    # OPTION CHAIN  (indices + equities)
    # ------------------------------------------------------------------ #
    def expiries(self, underlying: str) -> list[str]:
        u = underlying.upper()
        path = "/api/option-chain-indices" if u in {"NIFTY", "BANKNIFTY", "FINNIFTY",
                                                    "MIDCPNIFTY", "NIFTYNXT50"} \
               else "/api/option-chain-equities"
        d = self._get_json(path, {"symbol": u})
        return list(d.get("records", {}).get("expiryDates", []))

    def option_chain(self, underlying: str, expiry: str | None = None) -> pd.DataFrame:
        """Returns per-strike rows with CE/PE OI, IV, LTP, greeks-ready fields."""
        u = underlying.upper()
        path = "/api/option-chain-indices" if u in {"NIFTY", "BANKNIFTY", "FINNIFTY",
                                                    "MIDCPNIFTY", "NIFTYNXT50"} \
               else "/api/option-chain-equities"
        d = self._get_json(path, {"symbol": u})
        rec = d.get("records", {})
        expiry = expiry or rec.get("expiryDates", [None])[0]
        rows = []
        for item in rec.get("data", []):
            if item.get("expiryDate") != expiry:
                continue
            ce, pe = item.get("CE") or {}, item.get("PE") or {}
            rows.append({
                "expiry": expiry,
                "strike": item.get("strikePrice"),
                "spot": rec.get("underlyingValue"),
                "ce_oi": ce.get("openInterest"), "ce_chg_oi": ce.get("changeinOpenInterest"),
                "ce_iv": ce.get("impliedVolatility"), "ce_ltp": ce.get("lastPrice"),
                "ce_volume": ce.get("totalTradedVolume"),
                "pe_oi": pe.get("openInterest"), "pe_chg_oi": pe.get("changeinOpenInterest"),
                "pe_iv": pe.get("impliedVolatility"), "pe_ltp": pe.get("lastPrice"),
                "pe_volume": pe.get("totalTradedVolume"),
                "pcr_strike": ((pe.get("openInterest") or 0) /
                               (ce.get("openInterest") or 1)),
            })
        df = pd.DataFrame(rows).dropna(subset=["strike"]).sort_values("strike")
        return df.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # WHALE PRINTS: bulk & block deals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _deals_to_df(records: list[dict]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        rename = {
            "symbol": "symbol", "date": "date", "clientName": "client",
            "transactionType": "side", "quantityTraded": "qty",
            "shareholding": "post_pct_holding",
            "priceAtWhichTraded": "avg_price", "remarks": "remarks",
            "secType": "sec_type",
        }
        df = df.rename(columns=rename)
        for c in ("qty", "avg_price"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        return df

    def bulk_deals(self, days: int = 5) -> pd.DataFrame:
        out = []
        end = datetime.now()
        for i in range(days):
            day = end.replace(hour=12, minute=0)
            day = day.__class__.fromtimestamp(day.timestamp() - i * 86400)
            try:
                d = self._get_json(
                    "/api/report/bulk-deals",
                    {"index": "equities", "from": day.strftime("%d-%m-%Y"),
                     "to": day.strftime("%d-%m-%Y")},
                )
                out.extend(d.get("bulk Deals") or d.get("bulkDeals") or d.get("data") or [])
            except ConnectionError:
                continue
        return self._deals_to_df(out)

    def block_deals(self, days: int = 5) -> pd.DataFrame:
        try:
            d = self._get_json("/api/report/block-deals", {"index": "equities"})
            return self._deals_to_df(d.get("block Deals") or d.get("blockDeals") or [])
        except ConnectionError:
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # FII / DII daily cash-market activity
    # ------------------------------------------------------------------ #
    def fii_dii(self) -> pd.DataFrame:
        d = self._get_json("/api/fiidiiTradeReact")
        rows = []
        for item in d:
            rows.append({
                "date": item.get("date"),
                "category": (item.get("category") or "").upper(),
                "buy_cr": float(item.get("buyValue") or 0),
                "sell_cr": float(item.get("sellValue") or 0),
                "net_cr": float(item.get("netValue") or 0),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    # DELIVERY %  (accumulation/distribution signal)
    # ------------------------------------------------------------------ #
    def delivery_data(self, symbol: str) -> pd.DataFrame:
        d = self._get_json("/api/report/delivery-data", {"symbol": symbol.upper()})
        recs = d.get("delivery") or []
        df = pd.DataFrame(recs).rename(columns={
            "date": "date", "quantityTraded": "traded_qty",
            "deliverableQuantity": "deliverable_qty",
            "deliveryToTradedQuantity": "delivery_pct",
            "series": "series"})
        if not df.empty:
            for c in ("traded_qty", "deliverable_qty", "delivery_pct"):
                if c in df:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
