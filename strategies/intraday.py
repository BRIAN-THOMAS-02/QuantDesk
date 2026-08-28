"""Intraday strategies (square-off same day). NSE session aware."""
from __future__ import annotations

import pandas as pd

from strategies.base import Signal, StrategyBase
from analysis import indicators as ta


class OpeningRangeBreakout(StrategyBase):
    """ORB: trade break of first 15-min range with VWAP filter.
    df must be INTRADAY bars (5m/15m) covering multiple sessions."""
    name = "opening_range_breakout"
    holding_period = "intraday"
    description = "15-min range break + VWAP side filter, square off EOD"

    def generate(self, df: pd.DataFrame) -> Signal:
        day = df.index[-1].date()
        today = df[df.index.date == day]
        if len(today) < 3:
            return self._mk(self.symbol, 0)
        first = today.iloc[:2]                      # 2 x 15m bars = OR
        or_high, or_low = float(first.high.max()), float(first.low.min())
        vwap = ta.vwap_intraday(today)
        last = today.iloc[-1]
        if last.close > or_high and last.close > vwap.iloc[-1]:
            stop = or_low
            risk = last.close - stop
            return self._mk(self.symbol, 1, entry=last.close, stop=round(stop, 2),
                            t1=round(last.close + risk, 2),
                            t2=round(last.close + 2 * risk, 2),
                            conf=70, or_high=or_high, or_low=or_low,
                            above_vwap=True)
        if last.close < or_low and last.close < vwap.iloc[-1]:
            stop = or_high
            risk = stop - last.close
            return self._mk(self.symbol, -1, entry=last.close, stop=round(stop, 2),
                            t1=round(last.close - risk, 2),
                            t2=round(last.close - 2 * risk, 2),
                            conf=65, or_high=or_high, or_low=or_low)
        return self._mk(self.symbol, 0, or_high=or_high, or_low=or_low)


class CPRTrendDay(StrategyBase):
    """Central Pivot Range strategy: narrow CPR + price breaking above TC
    = trend-day long below BC short (see formulas/pivot_points_cpr)."""
    name = "cpr_trend_day"
    holding_period = "intraday"
    description = "Narrow CPR directional break"

    def generate(self, df: pd.DataFrame, prev_day=None) -> Signal:
        days = sorted(set(df.index.date))
        if prev_day is None:
            if len(days) < 2:
                return self._mk(self.symbol, 0)
            prev_day = df[df.index.date == days[-2]].iloc[-1]
        piv = ta.pivot_points(prev_day)
        today = df[df.index.date == days[-1]]
        last = today.iloc[-1]
        narrow = piv["cpr_width"] / piv["pivot"] * 100 < 0.25
        if not narrow:
            return self._mk(self.symbol, 0, note="wide CPR - range day expected")
        if last.close > piv["cpr_top"]:
            return self._mk(self.symbol, 1, entry=last.close,
                            stop=round(piv["pivot"], 2),
                            t1=round(piv["r1"], 2), t2=round(piv["r2"], 2),
                            conf=68, **piv)
        if last.close < piv["cpr_bottom"]:
            return self._mk(self.symbol, -1, entry=last.close,
                            stop=round(piv["pivot"], 2),
                            t1=round(piv["s1"], 2), t2=round(piv["s2"], 2),
                            conf=68, **piv)
        return self._mk(self.symbol, 0, **piv)


INTRADAY_STRATEGIES: dict[str, type[StrategyBase]] = {
    s.name: s for s in [OpeningRangeBreakout, CPRTrendDay]}
