"""Live worked examples: recompute a formula on REAL current market data
so the UI's (i) panel shows actual intermediate numbers, not just theory."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _fmt(x, nd=4):
    try:
        f = float(x)
        return round(f, nd) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return x


def live_example(fid: str, ctx: dict) -> dict | None:
    """ctx: {symbol, df(OHLCV daily), spot, provider, params{...}}
    Returns {'rows': [(step, value)...], 'note': str} or None."""
    df = ctx.get("df")
    if df is None or len(df) < 60:
        return None
    close, high, low = df["close"], df["high"], df["low"]
    fn = _EXAMPLES.get(fid)
    if fn is None:
        return None
    try:
        return fn(ctx, df, close, high, low)
    except Exception:
        return None


def _rsi(ctx, df, close, high, low):
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return {"rows": [
        ("last change ΔP", _fmt(d.iloc[-1], 2)),
        ("avg gain (Wilder 14)", _fmt(gain.iloc[-1], 3)),
        ("avg loss (Wilder 14)", _fmt(loss.iloc[-1], 3)),
        ("RS = avgGain/avgLoss", _fmt(rs.iloc[-1], 3)),
        ("RSI = 100-100/(1+RS)", _fmt(rsi.iloc[-1], 2)),
    ], "note": "Computed on live daily closes."}


def _macd(ctx, df, close, high, low):
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    line = e12 - e26
    sig = line.ewm(span=9, adjust=False).mean()
    return {"rows": [("EMA12", _fmt(e12.iloc[-1], 2)), ("EMA26", _fmt(e26.iloc[-1], 2)),
                     ("MACD line", _fmt(line.iloc[-1], 3)), ("Signal EMA9", _fmt(sig.iloc[-1], 3)),
                     ("Histogram", _fmt((line - sig).iloc[-1], 3))],
            "note": "Positive & rising histogram = accelerating momentum."}


def _boll(ctx, df, close, high, low):
    m = close.rolling(20).mean(); sd = close.rolling(20).std()
    u, l = m + 2 * sd, m - 2 * sd
    pctb = (close - l) / (u - l).replace(0, np.nan)
    bw = (u - l) / m * 100
    return {"rows": [("SMA20 mid", _fmt(m.iloc[-1], 2)), ("σ (20d stdev)", _fmt(sd.iloc[-1], 2)),
                     ("Upper (+2σ)", _fmt(u.iloc[-1], 2)), ("Lower (−2σ)", _fmt(l.iloc[-1], 2)),
                     ("%B position", _fmt(pctb.iloc[-1], 3)), ("Bandwidth %", _fmt(bw.iloc[-1], 2))],
            "note": "%B>1 riding upper band in trend; bandwidth at lows = squeeze watch."}


def _atr(ctx, df, close, high, low):
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 14, adjust=False).mean()
    c = close.iloc[-1]
    return {"rows": [
        ("today TR", _fmt(tr.iloc[-1], 2)),
        ("ATR(14)", _fmt(a.iloc[-1], 2)),
        ("ATR % of price", _fmt(a.iloc[-1] / c * 100, 2)),
        ("suggested stop (2×ATR below)", _fmt(c - 2 * a.iloc[-1], 2)),
    ], "note": "This is exactly how Risk tab sizes your stop distance."}


def _adx(ctx, df, close, high, low):
    up = high.diff(); dn = -low.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    n = 14
    tr_s = pd.concat([high - low, (high - close.shift()).abs(),
                      (low - close.shift()).abs()], axis=1).max(axis=1)\
        .ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr_s
    mdi = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr_s
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return {"rows": [("+DI", _fmt(pdi.iloc[-1], 1)), ("−DI", _fmt(mdi.iloc[-1], 1)),
                     ("DX", _fmt(dx.iloc[-1], 1)), ("ADX(14)", _fmt(adx.iloc[-1], 1))],
            "note": "ADX>25 = tradeable trend; direction read from which DI leads."}


def _supertrend(ctx, df, close, high, low):
    hl2 = (high + low) / 2
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 10, adjust=False).mean()
    ub, lb = (hl2 + 3 * a).values, (hl2 - 3 * a).values
    c = close.values
    st = np.full(len(df), np.nan); dirn = np.ones(len(df), dtype=int)
    fub, flb = ub.copy(), lb.copy()
    for i in range(1, len(df)):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        dirn[i] = (-1 if c[i] < flb[i] else 1) if dirn[i - 1] == 1 else \
                  (1 if c[i] > fub[i] else -1)
        st[i] = flb[i] if dirn[i] == 1 else fub[i]
    return {"rows": [("direction today", "LONG" if dirn[-1] == 1 else "SHORT"),
                     ("supertrend line", _fmt(st[-1], 2)),
                     ("final UB", _fmt(fub[-1], 2)), ("final LB", _fmt(flb[-1], 2))],
            "note": "Line = dynamic trailing stop while trend holds."}


def _volz(ctx, df, close, high, low):
    v = df["volume"].astype(float)
    mu, sd = v.rolling(20).mean(), v.rolling(20).std()
    z = (v - mu) / sd.replace(0, np.nan)
    return {"rows": [("today volume", int(v.iloc[-1])), ("20d mean", _fmt(mu.iloc[-1], 0)),
                     ("20d σ", _fmt(sd.iloc[-1], 0)), ("z-score", _fmt(z.iloc[-1], 2))],
            "note": "z>2 = institutional-grade volume surge."}


def _ccvol(ctx, df, close, high, low):
    lr = np.log(close / close.shift(1))
    v20 = lr.rolling(20).std() * math.sqrt(252) * 100
    return {"rows": [("daily log-return today %", _fmt(lr.iloc[-1] * 100, 3)),
                     ("σ_daily(20)", _fmt(lr.rolling(20).std().iloc[-1] * 100, 3)),
                     ("annualized % (√252)", _fmt(v20.iloc[-1], 2))],
            "note": f"√252 = {math.sqrt(252):.3f} annualization factor"}


def _ewma(ctx, df, close, high, low):
    lr = np.log(close / close.shift(1)).dropna()
    var = lr.var(ddof=1); lam = 0.94
    for r in lr.iloc[-250:]:
        var = lam * var + (1 - lam) * r ** 2
    return {"rows": [("λ", lam), ("variance forecast (next day)", _fmt(var, 6)),
                     ("annualized forecast %", _fmt(math.sqrt(var * 252) * 100, 2))],
            "note": "RiskMetrics recursion - what MC simulations here use as σ input."}


def _yz(ctx, df, close, high, low):
    o, h, l, c = (np.log(df[k]) for k in ("open", "high", "low", "close"))
    n = 20
    co, oc = c - o, o - c.shift(1)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    vos = co.rolling(n).var(ddof=1)
    vrs = ((h - o) * (h - c) + (l - o) * (l - c)).rolling(n).mean()
    von = oc.rolling(n).var(ddof=1)
    yz = np.sqrt((von + k * vos + (1 - k) * vrs) * 252) * 100
    return {"rows": [("overnight var", _fmt(von.iloc[-1], 5)), ("open-close var", _fmt(vos.iloc[-1], 5)),
                     ("RS component", _fmt(vrs.iloc[-1], 5)), ("k weight", _fmt(k, 3)),
                     ("Yang-Zhang vol %", _fmt(yz.iloc[-1], 2))],
            "note": "Compare vs ATM IV: YZ >> IV ⇒ premium is cheap."}


def _pk(ctx, df, close, high, low):
    hl = (np.log(high / low)) ** 2
    pk = np.sqrt(hl.rolling(20).mean() / (4 * math.log(2)) * 252) * 100
    cc = np.log(close / close.shift(1)).rolling(20).std() * math.sqrt(252) * 100
    return {"rows": [("Parkinson % (range-based)", _fmt(pk.iloc[-1], 2)),
                     ("close-close % for reference", _fmt(cc.iloc[-1], 2)),
                     ("efficiency gain", "~5x fewer samples needed")],
            "note": "PK >> CC means big intraday ranges with quiet closes."}


def _bslive(ctx, df, close, high, low):
    p = ctx.get("params", {})
    S = float(p.get("S") or close.iloc[-1])
    K = float(p.get("K") or S)
    T = float(p.get("T_days") or 7) / 365.0
    r = float(p.get("r") or 0.065)
    sig = float(p.get("sigma") or 0.18)
    from quant.black_scholes import bs_price, greeks
    call = bs_price(S, K, T, r, sig, "CE"); put = bs_price(S, K, T, r, sig, "PE")
    gc = greeks(S, K, T, r, sig, "CE")
    d1 = (math.log(S / K) + (r + sig ** 2 / 2) * T) / (sig * math.sqrt(T))
    rows = [("ln(S/K)", _fmt(math.log(S / K), 4)),
            ("σ√T (total move scale)", _fmt(sig * math.sqrt(T), 4)),
            ("d1", _fmt(d1, 4)), ("d2 = d1 − σ√T", _fmt(d1 - sig * math.sqrt(T), 4)),
            ("N(d1)", _fmt(_norm_cdf(d1), 4)),
            ("Call price ₹", _fmt(call, 2)), ("Put price ₹", _fmt(put, 2)),
            ("Call delta", gc["delta"]), ("Gamma", gc["gamma"]),
            ("Theta/day ₹", gc["theta"]), ("Vega/pt ₹", gc["vega"])]
    return {"rows": rows,
            "note": f"S={S} K={K} T={T*365:.0f}d r={r:.1%} σ={sig:.0%}. N(d1)≈prob of finishing ITM under risk-neutral drift."}


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _gbmcal(ctx, df, close, high, low):
    lr = np.log(close / close.shift(1)).dropna()
    mu, sd = lr.mean() * 252, lr.std(ddof=1) * math.sqrt(252)
    return {"rows": [("μ̂ annualized", _fmt(mu, 4)), ("σ̂ annualized", _fmt(sd, 4)),
                     ("raw sharpe μ/σ", _fmt(mu / sd, 2) if sd else None)],
            "note": "These are the exact parameters fed into Monte Carlo paths."}


_EXAMPLES = {
    "rsi": _rsi, "macd": _macd, "bollinger": _boll, "atr": _atr, "adx": _adx,
    "supertrend": _supertrend, "volume_zscore": _volz, "realized_vol_cc": _ccvol,
    "ewma_vol": _ewma, "yang_zhang": _yz, "parkinson": _pk,
    "bs_price": _bslive, "delta": _bslive, "gamma": _bslive, "theta": _bslive,
    "vega": _bslive, "implied_vol": _bslive,
    "estimate_gbm_params": _gbmcal, "gbm": _gbmcal,
}
