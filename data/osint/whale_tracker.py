"""Whale radar: detect institutional/HNI footprints from OSINT data.

Signals combined into a 0-100 whale score per symbol:
1. Bulk deals   (>=0.5% of shares) - big single-session prints
2. Block deals  (negotiated window) - pure institution-to-institution transfers
3. Delivery %   spikes - real accumulation vs speculative churn
4. Volume z-score anomaly on price data
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.providers.nse_provider import NSEProvider
from utils.helpers import logger

# Substring classifiers for client names seen in NSE bulk/block deal reports
INSTITUTIONAL_PATTERNS = [
    "MUTUAL FUND", "MF/", "TRUSTEE", "INSURANCE", "LIFE INS", "PENSION",
    "GOLDMAN", "MORGAN", "CITIGROUP", "JPMORGAN", "JP MORGAN", "SOCIETE",
    "BNP PARIBAS", "DEUTSCHE", "UBS", "BARCLAYS", "CREDIT SUISSE",
    "NOMURA", "MERRILL", "MACQUARIE", "ABU DHABI", "GOVERNMENT",
    "SBI ", "HDFC MF", "ICICI PRU", "NIPPON", "AXIS MF", "KOTAK MAH",
    "SMALLCAP WORLD", "FIDELITY", "VANGUARD", "BLACKROCK", "SCHRODER",
]
HNI_DESK_PATTERNS = ["PLUTUS", "GRASIM", "FDI", "NRI", "HUF", "PROPRIETOR",
                     "INVESTMENT PVT", "CAPITAL PVT", "HOLDINGS", "FAMILY"]


class WhaleTracker:

    def __init__(self, provider: NSEProvider | None = None):
        self.nse = provider or NSEProvider()

    # ------------------------------------------------------------------ #
    def fetch_deals(self, days: int = 5) -> pd.DataFrame:
        frames = []
        try:
            bulk = self.nse.bulk_deals(days=days)
            if not bulk.empty:
                bulk["deal_type"] = "BULK"
                frames.append(bulk)
        except Exception as e:
            logger.warning("bulk deals unavailable: %s", e)
        try:
            block = self.nse.block_deals()
            if not block.empty:
                block["deal_type"] = "BLOCK"
                frames.append(block)
        except Exception as e:
            logger.warning("block deals unavailable: %s", e)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # ------------------------------------------------------------------ #
    @staticmethod
    def classify(client: str) -> str:
        c = (client or "").upper()
        if any(p in c for p in INSTITUTIONAL_PATTERNS):
            return "INSTITUTION"
        if any(p in c for p in HNI_DESK_PATTERNS):
            return "HNI/DESK"
        return "OTHER"

    def whale_table(self, days: int = 5, min_value_cr: float = 10.0) -> pd.DataFrame:
        """Aggregated recent whale prints with side, class and value."""
        df = self.fetch_deals(days=days)
        if df.empty or "qty" not in df:
            return pd.DataFrame(columns=[
                "date", "symbol", "client", "class", "side", "qty",
                "avg_price", "value_cr", "deal_type"])
        df = df.copy()
        df["class"] = df["client"].apply(self.classify)
        df["value_cr"] = (df.get("qty", 0).fillna(0) *
                          df.get("avg_price", 0).fillna(0)) / 1e7
        df = df[df.value_cr >= min_value_cr]
        order = {"BLOCK": 0, "BULK": 1}
        df["ord"] = df.deal_type.map(order)
        return (df.sort_values(["ord", "value_cr"], ascending=[True, False])
                  .drop(columns="ord").reset_index(drop=True))

    def symbol_summary(self, days: int = 5) -> pd.DataFrame:
        """Net institutional interest per symbol from deal prints."""
        wt = self.whale_table(days=days)
        if wt.empty:
            return wt
        agg = (wt.groupby("symbol")
                 .agg(prints=("value_cr", "size"),
                      total_value_cr=("value_cr", "sum"),
                      institutions=("class", lambda s: (s == "INSTITUTION").sum()))
                 .reset_index())
        buy_side = wt[wt.side.str.upper().str.startswith(("B", "ACQ"))] \
            .groupby("symbol").value_cr.sum()
        sell_side = wt[wt.side.str.upper().str.startswith(("S", "DIS"))] \
            .groupby("symbol").value_cr.sum()
        agg["buy_cr"] = agg.symbol.map(buy_side).fillna(0)
        agg["sell_cr"] = agg.symbol.map(sell_side).fillna(0)
        agg["net_bias"] = np.where(agg.buy_cr > agg.sell_cr, "ACCUMULATION",
                                   np.where(agg.sell_cr > agg.buy_cr, "DISTRIBUTION", "-"))
        return agg.sort_values("total_value_cr", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------ #
    @staticmethod
    def volume_anomaly(hist: pd.DataFrame, lookback: int = 20) -> dict:
        """z-score of latest volume + delivery-style read."""
        v = hist["volume"].astype(float)
        if len(v) < lookback + 1 or v.iloc[-1] <= 0:
            return {"vol_z": 0.0, "vol_ratio": 1.0}
        mu, sd = v.iloc[-lookback - 1:-1].mean(), v.iloc[-lookback - 1:-1].std() or 1
        z = float((v.iloc[-1] - mu) / sd)
        return {"vol_z": round(z, 2), "vol_ratio": round(float(v.iloc[-1] / max(mu, 1)), 2)}

    @staticmethod
    def delivery_spike(delivery_df: pd.DataFrame, baseline_n: int = 20) -> dict | None:
        if delivery_df is None or delivery_df.empty or "delivery_pct" not in delivery_df:
            return None
        d = delivery_df.sort_values("date")
        base = d.delivery_pct.iloc[:-baseline_n].mean() if len(d) > baseline_n else d.delivery_pct.mean()
        latest = float(d.delivery_pct.iloc[-1])
        return {
            "latest_delivery_pct": round(latest, 2),
            "baseline_delivery_pct": round(float(base), 2),
            "spike_x": round(latest / base, 2) if base else None,
        }

    def score_symbol(self, symbol: str, hist: pd.DataFrame,
                     delivery_df: pd.DataFrame | None = None,
                     deals: pd.DataFrame | None = None) -> dict:
        """Composite 0-100 whale accumulation score for one symbol."""
        score, parts = 0.0, {}
        anom = self.volume_anomaly(hist)
        parts["volume"] = min(max(anom["vol_z"], -3), 6)
        score += max(parts["volume"], 0) * 8          # up to ~48 pts

        if delivery_df is not None and not delivery_df.empty:
            sp = self.delivery_spike(delivery_df)
            if sp and sp["spike_x"]:
                parts["delivery"] = sp["spike_x"]
                score += min(sp["spike_x"], 2.0) * 15  # up to 30

        if deals is not None and not deals.empty and "symbol" in deals:
            sym = deals[deals.symbol.str.upper() == symbol.upper()]
            if not sym.empty:
                inst_buy = sym[(sym["class"] == "INSTITUTION") &
                               sym.side.str.upper().str.startswith(("B", "ACQ"))].value_cr.sum()
                inst_sell = sym[(sym["class"] == "INSTITUTION") &
                                sym.side.str.upper().str.startswith(("S", "DIS"))].value_cr.sum()
                net = float(inst_buy - inst_sell)
                parts["deals_net_cr"] = round(net, 1)
                score += np.clip(net, -200, 200) / 200 * 22   # up to 22

        score = float(np.clip(score, 0, 100))
        label = ("STRONG ACCUMULATION" if score >= 65 else
                 "ACCUMULATION" if score >= 45 else
                 "DISTRIBUTION" if score <= 20 else "NEUTRAL")
        return {"symbol": symbol.upper(), "whale_score": round(score, 1),
                "label": label, "components": parts}
