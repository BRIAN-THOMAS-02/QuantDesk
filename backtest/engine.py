"""Vectorized backtesting engine with ATR stops, scale-outs, costs & slippage.

Design: strategies expose `entries(df) -> bool Series` (long entries).
Engine walks bars, manages one position at a time, applies:
  - stop loss   = entry - atr_mult * ATR
  - T1 partial  = +1R -> sell half, trail rest on supertrend/EMA
  - time stop   = max_hold sessions
Costs: brokerage+taxes per side (Indian equity delivery approx) + slippage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import settings
from analysis import indicators as ta


@dataclass
class BTConfig:
    capital: float = settings.CAPITAL
    risk_pct: float = settings.RISK_PER_TRADE_PCT / 100
    atr_mult_stop: float = 2.0
    t1_r_multiple: float = 1.0        # take half off at +1R
    max_hold_days: int = 20
    commission_pct: float = 0.03      # round-turn-ish per side incl taxes
    slippage_pct: float = 0.05
    allow_short: bool = False


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    metrics: dict
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    params: dict = field(default_factory=dict)


def run_backtest(df: pd.DataFrame, entries: pd.Series,
                 cfg: BTConfig | None = None,
                 symbol: str = "?", strategy: str = "?") -> BacktestResult:
    cfg = cfg or BTConfig()
    df = df.copy()
    df["atr"] = ta.atr(df)
    df["ema20"] = ta.ema(df.close, 20)
    ent = entries.reindex(df.index).fillna(False).values
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    atr = df.atr.values; ema20 = df.ema20.values

    cash = cfg.capital
    qty = 0; entry_px = 0.0; stop = 0.0; t1_done = False; risk_per_share = 0.0
    hold = 0; entry_i = -1
    equity_curve = []; trades = []

    for i in range(len(df)):
        px_open_slip = o[i] * (1 + cfg.slippage_pct / 100)

        # ---------------- manage open position ---------------- #
        if qty > 0:
            hold += 1
            exit_px = None; reason = None
            if l[i] <= stop and i > entry_i:                    # stop hit intrabar
                exit_px = min(stop, o[i]) if o[i] < stop else stop
                reason = "STOP"
            elif not t1_done and h[i] >= entry_px + cfg.t1_r_multiple * risk_per_share:
                exit_px = entry_px + cfg.t1_r_multiple * risk_per_share
                reason = "T1"
            elif c[i] < ema20[i] and t1_done:                   # trail after T1
                exit_px = c[i]; reason = "TRAIL"
            elif hold >= cfg.max_hold_days:
                exit_px = c[i]; reason = "TIME"
            if exit_px is not None:
                fill = exit_px * (1 - cfg.slippage_pct / 100)
                if reason == "T1":                               # scale out HALF
                    half = max(qty // 2, 1)
                    proceeds = half * fill * (1 - cfg.commission_pct / 100)
                    pnl = proceeds - half * entry_px * (1 + cfg.commission_pct / 100)
                    cash += proceeds; qty -= half; t1_done = True
                    stop = max(stop, entry_px)                   # breakeven trail
                    trades.append({
                        "entry_date": df.index[entry_i], "exit_date": df.index[i],
                        "entry": round(entry_px, 2), "exit": round(fill, 2),
                        "qty": half, "pnl": round(pnl, 2),
                        "r_mult": round(pnl / (risk_per_share * half), 2)
                        if risk_per_share else None,
                        "reason": "T1", "hold_days": hold})
                    continue
                proceeds = qty * fill * (1 - cfg.commission_pct / 100)
                pnl = proceeds - qty * entry_px * (1 + cfg.commission_pct / 100)
                cash += proceeds
                trades.append({
                    "entry_date": df.index[entry_i], "exit_date": df.index[i],
                    "entry": round(entry_px, 2), "exit": round(fill, 2),
                    "qty": qty, "pnl": round(pnl, 2),
                    "r_mult": round(pnl / (risk_per_share * qty), 2)
                    if risk_per_share else None,
                    "reason": reason, "hold_days": hold})
                qty = 0; t1_done = False; hold = 0

        # ---------------- new entry ---------------- #
        elif ent[i] and i < len(df) - 1:
            buy_px = c[i]                                        # signal on close
            risk_per_share = cfg.atr_mult_stop * atr[i]
            if risk_per_share <= 0 or np.isnan(risk_per_share):
                continue
            risk_rs = cfg.capital * cfg.risk_pct
            qty = int(risk_rs // risk_per_share)
            if qty <= 0:
                continue
            cost = qty * buy_px
            if cost > cash:                                      # cap by cash
                qty = int(cash // (buy_px * (1 + cfg.commission_pct / 100)))
                if qty <= 0:
                    continue
                cost = qty * buy_px
            entry_px = buy_px
            stop = buy_px - risk_per_share
            cash -= cost * (1 + cfg.commission_pct / 100)
            entry_i = i; hold = 0; t1_done = False

        equity_curve.append(cash + qty * c[i])

    eq = pd.Series(equity_curve, index=df.index[-len(equity_curve):])
    rets = eq.pct_change().dropna()
    tr_df = pd.DataFrame(trades)
    metrics = compute_metrics(eq, rets, tr_df, cfg.capital)
    return BacktestResult(symbol=symbol, strategy=strategy, metrics=metrics,
                          trades=tr_df, equity=eq, returns=rets,
                          params=cfg.__dict__.copy())


# --------------------------------------------------------------------- #
def compute_metrics(eq: pd.Series, rets: pd.Series,
                    trades: pd.DataFrame, capital: float) -> dict:
    rf_daily = settings.RISK_FREE_RATE / settings.TRADING_DAYS
    total_ret = float(eq.iloc[-1] / capital - 1) if len(eq) else 0.0
    years = len(eq) / settings.TRADING_DAYS if len(eq) else 1
    cagr = float((eq.iloc[-1] / capital) ** (1 / years) - 1) \
        if years > 0 and eq.iloc[-1] > 0 else 0.0
    vol = float(rets.std(ddof=1) * np.sqrt(settings.TRADING_DAYS)) if len(rets) else 0
    sharpe = float((rets.mean() - rf_daily) / rets.std(ddof=1)
                   * np.sqrt(settings.TRADING_DAYS)) if len(rets) > 2 and rets.std() else 0
    downside = rets[rets < 0]
    sortino = float((rets.mean() - rf_daily) /
                    downside.std(ddof=1) * np.sqrt(settings.TRADING_DAYS)) \
        if len(downside) > 2 and downside.std() else sharpe
    peak = eq.cummax()
    dd = (eq / peak - 1)
    mdd = float(dd.min()) if len(dd) else 0.0
    calmar = abs(cagr / mdd) if mdd else 0.0

    if trades is None or len(trades) == 0:
        return {"total_return_pct": round(total_ret * 100, 2), "cagr_pct": round(cagr * 100, 2),
                "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
                "max_drawdown_pct": round(mdd * 100, 2), "calmar": round(calmar, 2),
                "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
                "expectancy_rs": 0.0, "avg_hold_days": 0.0, "exposure_pct": 0.0}
    wins = trades[trades.pnl > 0]; losses = trades[trades.pnl <= 0]
    win_rate = len(wins) / len(trades)
    pf = float(wins.pnl.sum() / abs(losses.pnl.sum())) if len(losses) and losses.pnl.sum() else \
        (float("inf") if len(wins) else 0.0)
    expectancy = float(trades.pnl.mean())
    avg_r = float(pd.to_numeric(trades.r_mult, errors="coerce").mean())
    return {
        "total_return_pct": round(total_ret * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "calmar": round(calmar, 2),
        "volatility_pct": round(vol * 100, 2),
        "trades": int(len(trades)),
        "win_rate_pct": round(win_rate * 100, 1),
        "profit_factor": round(pf, 2) if np.isfinite(pf) else 99.0,
        "expectancy_rs": round(expectancy, 0),
        "avg_r_multiple": round(avg_r, 2) if np.isfinite(avg_r) else None,
        "avg_hold_days": round(float(trades.hold_days.mean()), 1),
        "best_trade": round(float(trades.pnl.max()), 0),
        "worst_trade": round(float(trades.pnl.min()), 0),
        "final_equity": round(float(eq.iloc[-1]), 0),
        "exposure_pct": round(len(trades) and float(
            trades.hold_days.sum() / max(len(eq), 1) * 100), 1),
    }
