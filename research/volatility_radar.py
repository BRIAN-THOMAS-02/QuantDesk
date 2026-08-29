"""Volatility Radar: rank tradable instruments by live volatility & regime,
attach expiry calendar + strategy playbook + social/news buzz."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis import indicators as ta
from data.providers.yfinance_provider import YFinanceProvider
from quant.volatility import yang_zhang, atr_percentile, vol_cone
from research.expiries import RADAR_INSTRUMENTS, next_expiries
from utils.helpers import logger


class VolatilityRadar:

    def __init__(self):
        self.yf = YFinanceProvider()

    @staticmethod
    def _playbook(vol_pctile: float, ret1w: float) -> dict:
        """Strategy fit from vol regime - honest heuristics, not advice."""
        if vol_pctile < 25:
            return {"stance": "VOL CHEAP",
                    "play": "debit strategies: long straddle/strangle into catalysts; "
                            "long options benefit if vol expands"}
        if vol_pctile > 75:
            return {"stance": "VOL RICH",
                    "play": "credit strategies: iron condors/covered calls; "
                            "size DOWN on directional trades (wide stops needed)"}
        stance = "VOL FAIR"
        play = ("directional swings with ATR stops; "
                "sell premium only with trend confirmation")
        if abs(ret1w) > 6:
            stance += " | TRENDING FAST"
            play = ("ride momentum with trailing stops (supertrend/chandelier); "
                    "avoid fresh selling of premium against the move")
        return {"stance": stance, "play": play}

    def scan(self) -> list[dict]:
        rows = []
        for key, meta in RADAR_INSTRUMENTS.items():
            try:
                df = self.yf.history(meta["yf"], period="1y")
                if len(df) < 80:
                    continue
                yz = yang_zhang(df.high, df.low, df.open, df.close, 21)
                vol_now = float(yz.iloc[-1]) * 100
                pctile = float((yz.dropna() <= yz.iloc[-1]).mean()) * 100
                atrp = float(ta.atr(df).iloc[-1] / df.close.iloc[-1] * 100)
                rng = float(((df.high - df.low) / df.close).tail(21).mean() * 100)
                ret1w = float(df.close.pct_change(5).iloc[-1] * 100)
                ret1m = float(df.close.pct_change(21).iloc[-1] * 100)
                vz = ta.volume_zscore(df.volume).iloc[-1]
                exps = next_expiries(key, n=2)
                pb = self._playbook(pctile, ret1w)
                rows.append({
                    "instrument": key, "label": meta["label"], "kind": meta["kind"],
                    "ltp": round(float(df.close.iloc[-1]), 2),
                    "ann_vol_yz_pct": round(vol_now, 1),
                    "vol_percentile_1y": round(pctile, 0),
                    "atr_pct": round(atrp, 2),
                    "avg_daily_range_pct": round(rng, 2),
                    "ret_1w_pct": round(ret1w, 1),
                    "ret_1m_pct": round(ret1m, 1),
                    "volume_z": round(float(np.nan_to_num(vz)), 2),
                    "next_expiries": [{"date": e.date, "kind": e.kind,
                                       "rule": e.rule} for e in exps],
                    **pb,
                    "_rank": vol_now,
                })
            except Exception as e:
                logger.debug("radar skip %s: %s", key, e)
        rows.sort(key=lambda r: -r.pop("_rank"))
        return rows

    def study(self, instrument: str) -> dict:
        meta = RADAR_INSTRUMENTS.get(instrument.upper())
        if not meta:
            raise KeyError(f"unknown radar instrument {instrument}")
        df = self.yf.history(meta["yf"], period="2y")
        cone = vol_cone(df.close)
        yz = yang_zhang(df.high, df.low, df.open, df.close, 21)
        study = {
            "instrument": instrument.upper(), "label": meta["label"],
            "kind": meta["kind"],
            "current_vol_pct": round(float(yz.iloc[-1]) * 100, 2),
            "percentile_2y": round(float((yz.dropna() <= yz.iloc[-1]).mean()) * 100, 1),
            "cone": cone.to_dict("records"),
            "expiries": [e.__dict__ for e in next_expiries(instrument.upper(), n=4)],
            "session_notes": {
                 "index": "09:15 open auction volatility; expiry-day gamma pinning near max-OI strikes; post-14:30 trend continuation stats strongest.",
                 "equity": "watch opening 15m range; SME-style smallcaps gap on news; avoid first-minute market orders.",
                 "commodity": "evening session (17:00-23:30) carries US data shocks; MCX gold tracks COMEX overnight.",
                 "currency": "RBI intervention zones blunt trends; best moves around Fed/RBI events.",
                 "vol": "read the level itself: rich vol favors premium-selling (credit) & wide stops; cheap vol favors premium-buying & tight stops.",
                 "fund": "fund/ETF vol tracks underlying index; treat like index with lower idiosyncratic noise.",
             }.get(meta["kind"], "use regime + percentile_2y for sizing; wide stops when vol percentile is elevated."),
            }
        return study
