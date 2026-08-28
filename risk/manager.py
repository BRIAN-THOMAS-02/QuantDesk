"""Risk management: position sizing, Kelly, portfolio heat, VaR/CVaR,
correlation-aware exposure. Every trade MUST pass through here."""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import settings
from quant.monte_carlo import mc_var


class RiskManager:

    def __init__(self, capital: float = settings.CAPITAL):
        self.capital = capital
        self.open_risk = 0.0            # rupees at risk across open trades

    # ------------------------------------------------------------------ #
    def atr_position_size(self, entry: float, stop: float,
                          risk_pct: float | None = None) -> dict:
        risk_pct = (risk_pct or settings.RISK_PER_TRADE_PCT) / 100
        dist = abs(entry - stop)
        if dist <= 0:
            return {"qty": 0, "reason": "zero stop distance"}
        risk_rs = self.capital * risk_pct
        qty = int(risk_rs // dist)
        notional = qty * entry
        leverage_cap = self.capital * 5          # rough MIS/CO cap for swing cash
        if notional > leverage_cap:
            qty = int(leverage_cap // entry)
        return {
            "qty": qty, "entry": round(entry, 2), "stop": round(stop, 2),
            "risk_rs": round(qty * dist, 0),
            "notional_rs": round(qty * entry, 0),
            "risk_pct_of_capital": round(qty * dist / self.capital * 100, 2),
        }

    def kelly_size(self, win_rate: float, rr: float,
                   kelly_fraction: float = 0.5) -> dict:
        f = win_rate - (1 - win_rate) / rr if rr > 0 else 0.0
        f_h = max(f * kelly_fraction, 0.0)
        return {"full_kelly_fraction": round(f, 4),
                "applied_fraction": round(f_h, 4),
                "allocation_rs": round(self.capital * f_h, 0),
                "note": "half-Kelly default; never exceed 25% single idea"}

    def targets_from_rr(self, entry: float, stop: float,
                        r1: float = 1.0, r2: float = 2.0) -> tuple[float, float]:
        d = abs(entry - stop)
        return round(entry + r1 * d, 2), round(entry + r2 * d, 2)

    # ------------------------------------------------------------------ #
    def register_open_risk(self, qty: int, entry: float, stop: float):
        self.open_risk += qty * abs(entry - stop)

    def heat(self) -> dict:
        pct = self.open_risk / self.capital * 100
        return {"open_risk_rs": round(self.open_risk, 0),
                "heat_pct": round(pct, 2),
                "status": ("BLOCKED - reduce positions" if pct > 10 else
                           "CAUTION - near limit" if pct > 7 else "OK")}

    def can_take_trade(self, qty: int, entry: float, stop: float,
                       max_heat_pct: float = 8.0) -> tuple[bool, str]:
        new_risk = qty * abs(entry - stop)
        total = (self.open_risk + new_risk) / self.capital * 100
        if total > max_heat_pct:
            return False, f"heat would hit {total:.1f}% > {max_heat_pct}% limit"
        return True, "ok"

    # ------------------------------------------------------------------ #
    def portfolio_var(self, returns: pd.DataFrame | pd.Series,
                      value: float | None = None,
                      weights: list[float] | None = None,
                      alpha: float = 0.95, horizon_days: int = 1) -> dict:
        res = mc_var(returns, weights=weights, portfolio_value=value or self.capital,
                     horizon_days=horizon_days, alpha=alpha)
        res["interpretation"] = (
            f"With {alpha:.0%} confidence you lose less than "
            f"₹{res['var_amount']:,.0f} in {horizon_days}d; "
            f"if breached expect ~₹{res['cvar_amount']:,.0f} average.")
        return res

    @staticmethod
    def correlation_risk(returns: pd.DataFrame, threshold: float = 0.75) -> dict:
        c = returns.corr()
        pairs = []
        cols = c.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                if c.iloc[i, j] >= threshold:
                    pairs.append({"a": cols[i], "b": cols[j],
                                  "corr": round(float(c.iloc[i, j]), 3)})
        return {"high_corr_pairs": pairs,
                "advice": "Treat high-corr clusters as ONE position for heat limits."}

    @staticmethod
    def trailing_stop(price: float, prev_stop: float | None,
                      atr_now: float, mult: float = 3.0) -> float:
        """Chandelier-style long trail."""
        cand = price - mult * atr_now
        return max(cand, prev_stop or cand)
