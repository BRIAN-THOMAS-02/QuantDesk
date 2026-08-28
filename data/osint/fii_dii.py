"""FII / DII flow intelligence (OSINT via NSE public API).

Institutional flows are the single most-followed "smart money" signal in India:
- FII net buying  -> bullish regime tailwind
- FII net selling -> rallies tend to fade; reduce long bias / tighten stops
- DII             -> often contrarian cushion when FIIs sell

Strategy hook: `regime_bias()` converts recent flows into a -1..+1 score.
"""
from __future__ import annotations

import pandas as pd

from data.providers.nse_provider import NSEProvider
from utils.helpers import logger


class FiiDiiTracker:

    def __init__(self, provider: NSEProvider | None = None):
        self.nse = provider or NSEProvider()

    def latest(self) -> pd.DataFrame:
        try:
            return self.nse.fii_dii()
        except ConnectionError as e:
            logger.warning("FII/DII fetch failed (%s); returning empty frame.", e)
            return pd.DataFrame(columns=["date", "category", "buy_cr", "sell_cr", "net_cr"])

    def summary_text(self) -> str:
        df = self.latest()
        if df.empty:
            return "FII/DII data unavailable right now."
        lines = ["=== FII / DII Cash Market Activity ==="]
        for _, r in df.iterrows():
            emoji = "+" if r.net_cr >= 0 else ""
            lines.append(f"{r.date} | {r.category:<4} | Buy ₹{r.buy_cr:>9,.0f}cr | "
                         f"Sell ₹{r.sell_cr:>9,.0f}cr | Net {emoji}{r.net_cr:>8,.0f}cr")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    def regime_bias(self, lookback_days: int = 5) -> dict:
        """-1 (strong FII outflow) .. +1 (strong FII inflow). Weight recent more."""
        df = self.latest()
        if df.empty:
            return {"score": 0.0, "label": "NEUTRAL", "detail": "no data"}
        df = df.tail(lookback_days * 2)
        fii = df[df.category.str.contains("FII|FPI", na=False)]
        dii = df[df.category.str.contains("DII", na=False)]
        if fii.empty:
            return {"score": 0.0, "label": "NEUTRAL", "detail": "no FII rows"}

        nets = fii.sort_values("date").tail(lookback_days).net_cr.astype(float)
        weights = [i + 1 for i in range(len(nets))]          # recency weighted
        fii_score = float((nets.values * weights).__truediv__(sum(weights)).sum())

        # normalise: ±5000cr daily is an extreme session in Indian mkts
        fii_norm = max(-1.0, min(1.0, fii_score / 5000))
        label = ("BULLISH" if fii_norm > 0.25 else
                 "BEARISH" if fii_norm < -0.25 else "NEUTRAL")

        detail = {
            "fii_net_5d_cr": round(float(nets.sum()), 1),
            "dii_net_5d_cr": round(float(dii.tail(lookback_days).net_cr.sum()), 1)
                             if not dii.empty else None,
        }
        return {"score": round(fii_norm, 3), "label": label, "detail": detail}
