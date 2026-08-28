"""Volatility estimators - the edge in options & stop placement.

Includes: close-to-close, EWMA (RiskMetrics), Parkinson, Garman-Klass,
Rogers-Satchell, Yang-Zhang + annualization utilities.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def close_to_close(close: pd.Series, window: int = 20) -> pd.Series:
    lr = np.log(close / close.shift(1))
    return lr.rolling(window).std() * math.sqrt(TRADING_DAYS)


def ewma_vol(close: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics EWMA daily vol -> annualized."""
    lr = np.log(close / close.shift(1))
    return lr.ewm(alpha=1 - lam).std() * math.sqrt(TRADING_DAYS)


def parkinson(high: pd.Series, low: pd.Series, window: int = 20) -> pd.Series:
    hl = (np.log(high / low)) ** 2
    return np.sqrt(hl.rolling(window).mean() / (4 * math.log(2)) * TRADING_DAYS)


def garman_klass(high, low, open_, close, window: int = 20) -> pd.Series:
    log_hl = np.log(high / low) ** 2
    log_co = np.log(close / open_) ** 2
    var = (0.5 * log_hl - (2 * math.log(2) - 1) * log_co).rolling(window).mean()
    return np.sqrt(var * TRADING_DAYS)


def rogers_satchell(high, low, open_, close, window: int = 20) -> pd.Series:
    o, h, l, c = (np.log(x) for x in (open_, high, low, close))
    rs = (h - o) * (h - c) + (l - o) * (l - c)
    return np.sqrt(rs.rolling(window).mean() * TRADING_DAYS)


def yang_zhang(high, low, open_, close, window: int = 20) -> pd.Series:
    """Best unbiased estimator using overnight + intraday components."""
    o, h, l, c = (np.log(x) for x in (open_, high, low, close))
    co = c - o
    oc = o - c.shift(1)
    cc = c - c.shift(1)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    v_os = co.rolling(window).var(ddof=1)
    v_rs = ((h - o) * (h - c) + (l - o) * (l - c)).rolling(window).mean()
    v_on = oc.rolling(window).var(ddof=1)
    return np.sqrt((v_on + k * v_os + (1 - k) * v_rs) * TRADING_DAYS)


def vol_cone(close: pd.Series, windows=(5, 10, 21, 42, 63)) -> pd.DataFrame:
    """Current vs historical distribution of realized vol per horizon."""
    rows = []
    for w in windows:
        v = close_to_calc(close, w)
        rows.append({
            "window_days": w,
            "current": round(float(v.iloc[-1]) * 100, 2),
            "p25": round(float(v.quantile(0.25)) * 100, 2),
            "median": round(float(v.median()) * 100, 2),
            "p75": round(float(v.quantile(0.75)) * 100, 2),
        })
    return pd.DataFrame(rows)


def close_to_calc(close: pd.Series, w: int) -> pd.Series:
    return close_to_close(close, w)


def atr_percentile(high, low, close, window: int = 14, lookback: int = 252) -> float:
    from analysis.indicators import atr
    a = atr(high, low, close, window)
    hist = a.iloc[-lookback:]
    return round(float((hist.iloc[-1] > hist).mean() * 100), 1)   # percentile 0-100


def forecast_ewma_next(close: pd.Series, lam: float = 0.94) -> float:
    """Next-day vol forecast (annualized %) via RiskMetrics recursion."""
    lr = np.log(close / close.shift(1)).dropna()
    var = lr.var(ddof=1)
    for r in lr.iloc[-250:]:
        var = lam * var + (1 - lam) * r ** 2
    return round(math.sqrt(var * TRADING_DAYS) * 100, 2)
