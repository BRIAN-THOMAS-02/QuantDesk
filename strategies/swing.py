"""Swing trading strategies (multi-day holds, 5-30 sessions typical).

Each returns a Signal for the LATEST bar with entry/stop/targets sized by ATR.
Backtest-friendly: every strategy also exposes `entries(df) -> bool Series`
marking historical entry bars so the backtester can simulate honestly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import Signal, StrategyBase
from analysis import indicators as ta


class SupertrendRSI(StrategyBase):
    """Trend-following workhorse popular on Indian timeframes (daily).
    Long when ST flips green + RSI confirms >50 + ADX trending."""
    name = "supertrend_rsi"
    description = "Supertrend flip + RSI>50 + ADX>20 trend continuation"

    def generate(self, df: pd.DataFrame) -> Signal:
        st = ta.supertrend(df); df = df.assign(st_dir=st.direction)
        df["rsi"] = ta.rsi(df.close)
        df["adx"] = ta.adx(df).adx
        last, prev = df.iloc[-1], df.iloc[-2]
        a = ta.atr(df).iloc[-1]
        flip_up = prev.st_dir == -1 and last.st_dir == 1
        holding = last.st_dir == 1 and prev.rsi < 50 <= last.rsi
        if not ((flip_up or holding) and last.adx > 20):
            return self._mk(self.symbol, 0, rsi=last.rsi, adx=last.adx)
        conf = min(40 + last.rsi * 0.3 + last.adx, 95)
        return self._mk(self.symbol, 1, entry=last.close,
                        stop=round(last.close - 2 * a, 2),
                        t1=round(last.close + 2 * a, 2),
                        t2=round(last.close + 4 * a, 2),
                        conf=conf, rsi=last.rsi, adx=last.adx)

    def entries(self, df: pd.DataFrame) -> pd.Series:
        st = ta.supertrend(df)
        r = ta.rsi(df.close); ad = ta.adx(df).adx
        flip = (st.direction.shift(1) == -1) & (st.direction == 1)
        cont = (st.direction == 1) & (r.shift(1) < 50) & (r >= 50)
        return (flip | cont) & (ad > 20)


class BollingerMeanReversion(StrategyBase):
    """Buy the fear: close below lower BB + RSI<30, exit at mid-band.
    Works in range-bound large caps; avoid in strong downtrends."""
    name = "bb_mean_reversion"
    description = "Lower-band touch + RSI oversold, target mid-band"

    def generate(self, df: pd.DataFrame) -> Signal:
        bb = ta.bollinger(df.close)
        r = ta.rsi(df.close)
        last = df.iloc[-1]
        if not (last.close <= bb.lower.iloc[-1] and r.iloc[-1] < 32):
            return self._mk(self.symbol, 0, rsi=r.iloc[-1])
        mid = bb.mid.iloc[-1]
        stop = round(min(last.low, bb.lower.iloc[-1] * 0.99), 2)
        return self._mk(self.symbol, 1, entry=last.close, stop=stop,
                        t1=round(mid, 2), t2=round(mid + (mid - last.close), 2),
                        conf=min(70 + (32 - r.iloc[-1]) * 2, 90), rsi=r.iloc[-1])

    def entries(self, df: pd.DataFrame) -> pd.Series:
        bb = ta.bollinger(df.close)
        r = ta.rsi(df.close)
        return (df.close <= bb.lower) & (r < 32)


class BreakoutPullback(StrategyBase):
    """Darvas-style: breakout of 20d high on volume, then buy the shallow
    pullback that holds above the breakout level. High win-rate swing setup."""
    name = "breakout_pullback"
    description = "20d-high breakout w/ volume then pullback retest"

    def generate(self, df: pd.DataFrame) -> Signal:
        d = donchian_state(df)
        last, prev = d.iloc[-1], d.iloc[-2]
        vz = float(np.nan_to_num(ta.volume_zscore(df.volume).iloc[-1]))
        # pullback day: yesterday broke out, today dips but closes above level
        pulled_back = prev.brokeout and last.close >= prev.level and last.close < prev.high
        if not (pulled_back or d.iloc[-1].brokeout):
            return self._mk(self.symbol, 0)
        lvl = float(prev.level if pulled_back else prev.level)
        a = ta.atr(df).iloc[-1]
        conf = min(55 + max(vz, 0) * 10, 92)
        return self._mk(self.symbol, 1, entry=last.close,
                        stop=round(lvl - a, 2),
                        t1=round(last.close + 1.5 * a, 2),
                        t2=round(last.close + 3 * a, 2),
                        conf=conf, volz=vz, level=lvl)

    def entries(self, df: pd.DataFrame) -> pd.Series:
        d = donchian_state(df)
        vz = ta.volume_zscore(df.volume)
        return d.brokeout & (vz > 0.5)


def donchian_state(df: pd.DataFrame) -> pd.DataFrame:
    upper = df.high.rolling(20).max().shift(1)     # exclude today
    out = pd.DataFrame({"level": upper}, index=df.index)
    out["brokeout"] = (df.close > upper) & (df.close.shift(1) <= upper.shift(1))
    out["high"] = df.high
    return out


class EMACrossADX(StrategyBase):
    """Classic 20/50 EMA cross filtered by ADX - positional swing."""
    name = "ema_cross_adx"
    description = "EMA20 x EMA50 golden cross with ADX strength filter"

    def generate(self, df: pd.DataFrame) -> Signal:
        e20, e50 = ta.ema(df.close, 20), ta.ema(df.close, 50)
        ad = ta.adx(df).adx.iloc[-1]
        cross = e20.iloc[-2] <= e50.iloc[-2] and e20.iloc[-1] > e50.iloc[-1]
        above = e20.iloc[-1] > e50.iloc[-1] and df.close.iloc[-1] > e20.iloc[-1]
        if not ((cross or above) and ad > 18):
            return self._mk(self.symbol, 0, adx=ad)
        a = ta.atr(df).iloc[-1]
        return self._mk(self.symbol, 1, entry=df.close.iloc[-1],
                        stop=round(df.close.iloc[-1] - 2 * a, 2),
                        t1=round(df.close.iloc[-1] + 2 * a, 2),
                        t2=round(df.close.iloc[-1] + 4 * a, 2),
                        conf=min(45 + ad, 90), adx=ad)

    def entries(self, df: pd.DataFrame) -> pd.Series:
        e20, e50 = ta.ema(df.close, 20), ta.ema(df.close, 50)
        cross = (e20.shift(1) <= e50.shift(1)) & (e20 > e50)
        return cross & (ta.adx(df).adx > 18)


class WeeklyMomentum(StrategyBase):
    """Cross-sectional style momentum held 4-8 weeks: rank by 6m return
    skipping last 2 weeks; enter when stock is top-decile AND above EMA100."""
    name = "weekly_momentum"
    description = "6-2 month momentum + trend filter, multi-week hold"

    def generate(self, df: pd.DataFrame) -> Signal:
        m = ta.momentum_rank(df.close, months=6, skip=10)
        e100 = ta.ema(df.close, 100).iloc[-1]
        last = df.close.iloc[-1]
        if not (np.isfinite(m) and m > 0 and last > e100):
            return self._mk(self.symbol, 0, mom_6_2=m)
        a = ta.atr(df).iloc[-1]
        return self._mk(self.symbol, 1, entry=last,
                        stop=round(last - 2.5 * a, 2),
                        t2=round(last + 5 * a, 2),
                        conf=min(60 + m * 200, 92),
                        mom_6_2=round(m, 3))

    def entries(self, df: pd.DataFrame) -> pd.Series:
        m_series = df.close.pct_change(126 - 10)
        return (m_series > 0.08) & (df.close > ta.ema(df.close, 100))


SWING_STRATEGIES: dict[str, type[StrategyBase]] = {
    s.name: s for s in [SupertrendRSI, BollingerMeanReversion,
                        BreakoutPullback, EMACrossADX, WeeklyMomentum]}
