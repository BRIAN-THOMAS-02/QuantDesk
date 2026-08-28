"""Technical indicator library (pure pandas/numpy - no TA-Lib dependency).

All functions take aligned pd.Series/DataFrame and return Series aligned to input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ #
# MOVING AVERAGES
# ------------------------------------------------------------------ #
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def hma(s: pd.Series, n: int) -> pd.Series:
    """Hull MA - fast & smooth for swing entries."""
    half = ema(s, max(n // 2, 1)); full = ema(s, n)
    return ema(2 * half - full, int(np.sqrt(n)))


# ------------------------------------------------------------------ #
# MOMENTUM OSCILLATORS
# ------------------------------------------------------------------ #
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50)


def macd(close: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def stochastic(df: pd.DataFrame, k_n=14, d_n=3, smooth_k=3) -> pd.DataFrame:
    hh = df["high"].rolling(k_n).max()
    ll = df["low"].rolling(k_n).min()
    raw_k = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    k = raw_k.rolling(smooth_k).mean()
    return pd.DataFrame({"k": k, "d": k.rolling(d_n).mean()})


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hh = df["high"].rolling(n).max(); ll = df["low"].rolling(n).min()
    return -100 * (hh - df["close"]) / (hh - ll).replace(0, np.nan)


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return close.pct_change(n) * 100


def momentum_rank(close: pd.Series, months: int = 6, skip: int = 14) -> float:
    """Academic cross-sectional momentum: 12-1 style (skip recent 2 weeks)."""
    if len(close) < months * 21 + skip + 1:
        return np.nan
    past = close.iloc[-(months * 21 + skip)]
    recent = close.iloc[-skip]
    return float(past / recent - 1)


# ------------------------------------------------------------------ #
# TREND / VOLATILITY
# ------------------------------------------------------------------ #
def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr_s = true_range(df).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr_s
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": dx.ewm(alpha=1 / n, adjust=False).mean(),
                         "plus_di": plus_di, "minus_di": minus_di})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    m = sma(close, n); sd = close.rolling(n).std()
    upper, lower = m + k * sd, m - k * sd
    width = (upper - lower) / m * 100
    pctb = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({"mid": m, "upper": upper, "lower": lower,
                         "width_pct": width, "%b": pctb})


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """Popular Indian swing-trading overlay. direction: +1 long / -1 short."""
    hl2 = (df["high"] + df["low"]) / 2
    a = atr(df, period)
    ub = (hl2 + mult * a).values
    lb = (hl2 - mult * a).values
    close = df["close"].values
    st = np.full(len(df), np.nan)
    dirn = np.ones(len(df), dtype=int)
    fub, flb = ub.copy(), lb.copy()
    for i in range(1, len(df)):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or close[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or close[i - 1] < flb[i - 1]) else flb[i - 1]
        prev_d = dirn[i - 1]
        if prev_d == 1:
            dirn[i] = -1 if close[i] < flb[i] else 1
        else:
            dirn[i] = 1 if close[i] > fub[i] else -1
        st[i] = flb[i] if dirn[i] == 1 else fub[i]
    return pd.DataFrame({"supertrend": st, "direction": dirn}, index=df.index)


def donchian(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return pd.DataFrame({
        "upper": df["high"].rolling(n).max(),
        "lower": df["low"].rolling(n).min(),
        "mid": (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2,
    })


def ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    conv = (df.high.rolling(9).max() + df.low.rolling(9).min()) / 2
    base = (df.high.rolling(26).max() + df.low.rolling(26).min()) / 2
    span_a = ((conv + base) / 2).shift(26)
    span_b = ((df.high.rolling(52).max() + df.low.rolling(52).min()) / 2).shift(26)
    return pd.DataFrame({"tenkan": conv, "kijun": base,
                         "senkou_a": span_a, "senkou_b": span_b})


# ------------------------------------------------------------------ #
# VOLUME
# ------------------------------------------------------------------ #
def vwap_intraday(df: pd.DataFrame) -> pd.Series:
    tp = (df.high + df.low + df.close) / 3
    day = df.index.normalize() if isinstance(df.index, pd.DatetimeIndex) else None
    num = (tp * df.volume).groupby(day).cumsum()
    den = df.volume.groupby(day).cumsum().replace(0, np.nan)
    return num / den


def obv(df: pd.DataFrame) -> pd.Series:
    d = df.close.diff().fillna(0)
    return (np.sign(d) * df.volume).cumsum()


def mfi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df.high + df.low + df.close) / 3
    mf = tp * df.volume
    pos = mf.where(tp > tp.shift(1), 0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(1), 0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def volume_zscore(volume: pd.Series, n: int = 20) -> pd.Series:
    m = volume.rolling(n).mean(); s = volume.rolling(n).std()
    return (volume - m) / s.replace(0, np.nan)


# ------------------------------------------------------------------ #
# LEVELS
# ------------------------------------------------------------------ #
def fibonacci_levels(high: float, low: float, trend_up: bool = True) -> dict:
    diff = high - low
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    if trend_up:
        return {f"fib_{r}": round(high - diff * r, 2) for r in ratios}
    return {f"fib_{r}": round(low + diff * r, 2) for r in ratios}


def pivot_points(prev_day: dict | pd.Series) -> dict:
    """Classic floor pivots + CPR (Central Pivot Range - Indian intraday staple)."""
    p = (prev_day.high + prev_day.low + prev_day.close) / 3
    bc = (prev_day.high + prev_day.low) / 2
    tc = p - bc + p
    return {"pivot": round(p, 2),
            "r1": round(2 * p - prev_day.low, 2), "s1": round(2 * p - prev_day.high, 2),
            "r2": round(p + (prev_day.high - prev_day.low), 2),
            "s2": round(p - (prev_day.high - prev_day.low), 2),
            "cpr_top": round(max(tc, bc), 2), "cpr_bottom": round(min(tc, bc), 2),
            "cpr_width": round(abs(tc - bc), 2)}


def weekly_pivots(df_daily: pd.DataFrame) -> dict:
    last_week = df_daily.iloc[-5:]
    return pivot_points(last_week)


def relative_strength(close: pd.Series, benchmark: pd.Series, n: int = 63) -> float:
    a = close.pct_change(n).iloc[-1]; b = benchmark.pct_change(n).iloc[-1]
    return float(a - b)


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the standard swing-analysis panel to OHLCV df."""
    out = df.copy()
    out["rsi"] = rsi(out.close)
    m = macd(out.close)
    out[["macd", "macd_sig", "macd_hist"]] = m
    bb = bollinger(out.close)
    out[["bb_mid", "bb_upper", "bb_lower"]] = bb[["mid", "upper", "lower"]]
    st = supertrend(out)
    out["st_dir"] = st.direction
    a = adx(out)
    out["adx"] = a.adx
    out["atr"] = atr(out)
    out["ema50"] = ema(out.close, 50)
    out["ema200"] = ema(out.close, 200)
    out["volz"] = volume_zscore(out.volume)
    out["ret_1m"] = out.close.pct_change(21)
    out["ret_3m"] = out.close.pct_change(63)
    out["hi_52w"] = out.close.rolling(252, min_periods=60).max()
    return out
