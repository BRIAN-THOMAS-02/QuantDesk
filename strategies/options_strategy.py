"""Options strategy builder: structures priced via Black-Scholes + live IVs,
with OI-based intelligence (PCR, max pain) from the NSE chain."""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.black_scholes import bs_price, greeks, payoff_diagram


class OptionsStrategyEngine:

    def __init__(self, spot: float, r: float = 0.065):
        self.S = spot
        self.r = r

    # ------------------------------------------------------------------ #
    def _leg_px(self, kind: str, K: float, T_days: int, sigma: float) -> dict:
        T = max(T_days, 0.5) / 365
        px = float(bs_price(self.S, K, T, self.r, sigma, kind))
        g = greeks(self.S, K, T, self.r, sigma, kind)
        return {"price": round(px, 2), **g}

    def structure(self, legs: list[dict], label: str = "") -> dict:
        """legs: [{'type':'CE','strike':K,'days':7,'sigma':.14,'qty':+/-1,'side':'buy'}]"""
        total_cost, detail = 0.0, []
        qty_map = {"buy": 1, "sell": -1}
        for lg in legs:
            q = lg.get("qty", 1) * qty_map.get(lg.get("side", "buy"), 1)
            info = self._leg_px(lg["type"], lg["strike"], lg["days"],
                                lg.get("sigma", 0.15))
            total_cost += q * info["price"]
            detail.append({**lg, **info, "signed_qty": q})
        spots = np.linspace(self.S * 0.9, self.S * 1.1, 200)
        payoff_legs = [{"type": l["type"], "strike": l["strike"],
                        "premium": next(d["price"] for d in detail
                                        if d["strike"] == l["strike"]
                                        and d["type"] == l["type"]),
                        "qty": abs(l.get("qty", 1)),
                        "side": l.get("side", "buy")} for l in legs]
        xs, ys = payoff_diagram(payoff_legs, spots)
        net_premium = sum(-d["signed_qty"] * d["price"] for d in detail)
        breakevens = _breakevens(xs, ys)
        return {
            "label": label, "legs": detail,
            "net_premium": round(net_premium, 2),
            "max_profit": round(float(ys.max()), 2),
            "max_loss": round(float(ys.min()), 2),
            "breakevens": breakevens,
            "payoff": {"spots": [round(x, 1) for x in xs],
                       "pnl": [round(y, 1) for y in ys]},
        }

    # ------------------------------------------------------------------ #
    def covered_call(self, sigma_s=0.18, otm_pct=0.03, days=30) -> dict:
        K = round(self.S * (1 + otm_pct) / 50) * 50
        st = self.structure([
            {"type": "CE", "strike": K, "days": days, "sigma": sigma_s,
             "qty": 1, "side": "sell"}], f"Covered Call {K}CE ({otm_pct:.0%} OTM)")
        st["stock_leg"] = {"shares": 1, "entry": self.S}
        return st

    def cash_secured_put(self, sigma_s=0.18, otm_pct=0.03, days=30) -> dict:
        K = round(self.S * (1 - otm_pct) / 50) * 50
        return self.structure([
            {"type": "PE", "strike": K, "days": days, "sigma": sigma_s,
             "qty": 1, "side": "sell"}], f"Cash-Secured Put {K}PE")

    def bull_call_spread(self, atm=0.0, width=200, sigma_s=0.16, days=30) -> dict:
        k1 = round((self.S * (1 + atm)) / 50) * 50
        k2 = k1 + width
        return self.structure([
            {"type": "CE", "strike": k1, "days": days, "sigma": sigma_s,
             "qty": 1, "side": "buy"},
            {"type": "CE", "strike": k2, "days": days, "sigma": sigma_s * 0.92,
             "qty": 1, "side": "sell"}], f"Bull Call Spread {k1}/{k2}")

    def iron_condor(self, wing=400, body=150, sigma_base=0.15, days=21) -> dict:
        k_pe_sell = round((self.S - body) / 50) * 50
        k_pe_buy = k_pe_sell - wing
        k_ce_sell = round((self.S + body) / 50) * 50
        k_ce_buy = k_ce_sell + wing
        sig = lambda d: sigma_base * (1 + d / self.S * 8)
        return self.structure([
            {"type": "PE", "strike": k_pe_sell, "days": days, "sigma": sig(k_pe_sell),
             "qty": 1, "side": "sell"},
            {"type": "PE", "strike": k_pe_buy, "days": days, "sigma": sig(k_pe_buy) * 1.08,
             "qty": 1, "side": "buy"},
            {"type": "CE", "strike": k_ce_sell, "days": days, "sigma": sig(k_ce_sell),
             "qty": 1, "side": "sell"},
            {"type": "CE", "strike": k_ce_buy, "days": days, "sigma": sig(k_ce_buy) * 1.08,
             "qty": 1, "side": "buy"}],
            f"Iron Condor {k_pe_sell}/{k_pe_buy} x {k_ce_sell}/{k_ce_buy}")

    def straddle_analysis(self, sigma_atm=0.16, days=7) -> dict:
        K = round(self.S / 50) * 50
        return self.structure([
            {"type": "CE", "strike": K, "days": days, "sigma": sigma_atm,
             "qty": 1, "side": "buy"},
            {"type": "PE", "strike": K, "days": days, "sigma": sigma_atm * 1.05,
             "qty": 1, "side": "buy"}], f"Long Straddle {K}")


def _breakevens(xs: np.ndarray, ys: np.ndarray) -> list[float]:
    be = []
    for i in range(1, len(ys)):
        if (ys[i - 1] <= 0 < ys[i]) or (ys[i - 1] >= 0 > ys[i]):
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            be.append(round(float(x0 + (x1 - x0) * (-y0) / (y1 - y0)), 2))
    return be


def oi_intelligence(chain: pd.DataFrame) -> dict:
    """Sentiment read from NSE option chain OI distribution."""
    ce_oi = chain.ce_oi.sum() or 1
    pe_oi = chain.pe_oi.sum()
    pcr = float(pe_oi / ce_oi)
    spot = float(chain.spot.iloc[0])

    strikes = chain.strike.values
    pain = []
    for k in strikes:
        loss = ((chain.ce_oi.values * np.maximum(k - strikes, 0)).sum()
                + (chain.pe_oi.values * np.maximum(strikes - k, 0)).sum())
        pain.append(loss)
    max_pain_strike = float(strikes[int(np.argmin(pain))])
    res_ce = float(chain.loc[chain.ce_oi.idxmax(), "strike"])
    sup_pe = float(chain.loc[chain.pe_oi.idxmax(), "strike"])
    return {
        "pcr": round(pcr, 3),
        "pcr_read": ("BULLISH (put writers dominant)" if pcr > 1.2 else
                     "BEARISH (call writers dominant)" if pcr < 0.7 else "NEUTRAL"),
        "max_pain": max_pain_strike,
        "resistance_max_ce_oi": res_ce,
        "support_max_pe_oi": sup_pe,
        "spot_vs_maxpain_pct": round((spot / max_pain_strike - 1) * 100, 2),
    }
