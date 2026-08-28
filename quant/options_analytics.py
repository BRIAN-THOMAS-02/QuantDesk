"""Options Greeks surface, IV skew/smile, term structure for Indian F&O.

Covers:
- Complete Greeks (Delta, Gamma, Theta, Vega, Rho, Vanna, Volga, Charm, Speed, Color)
- IV surface interpolation (smile + term structure)
- Skew metrics: 25d RR, 25d BF, ATM IV
- Term structure of IV (ATM IV by expiry)
- Put-Call parity deviations
- Max Pain calculation
- PCR (Put-Call Ratio) by OI and Volume
- OI analysis: max pain, support/resistance from OI walls
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brentq

from quant.black_scholes import bs_price, greeks, implied_vol
from quant.futures import cost_of_carry
from config import settings


@dataclass
class OptionGreeksFull:
    """Complete Greeks including second/third order."""
    delta: float
    gamma: float
    theta: float      # per day
    vega: float       # per 1% vol
    rho: float        # per 1% rate
    vanna: float      # dDelta/dVol
    volga: float      # dVega/dVol (Vomma)
    charm: float      # dDelta/dt
    speed: float      # dGamma/dSpot
    color: float      # dGamma/dt
    zomma: float      # dGamma/dVol


def vanna(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dDelta/dVol = -d2 * Gamma / sigma"""
    call = kind.upper() in ("CE", "CALL", "C")
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    gamma_val = math.exp(-q * T) * math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) / (spot * sigma * math.sqrt(T))
    if call:
        return -d2 * gamma_val / sigma
    return -(-d2) * gamma_val / sigma  # same magnitude for puts


def volga(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dVega/dVol = Vega * d1 * d2 / sigma"""
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    vega_val = spot * math.exp(-q * T) * math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) * math.sqrt(T) / 100
    return vega_val * d1 * d2 / sigma


def charm(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dDelta/dt (per day)."""
    call = kind.upper() in ("CE", "CALL", "C")
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if T <= 0:
        return 0.0
    N_d1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    N_d2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    pdf_d1 = math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi)
    if call:
        return (-q * math.exp(-q * T) * N_d1 
                - math.exp(-q * T) * pdf_d1 * (r - q) / (sigma * math.sqrt(T))
                + q * math.exp(-q * T) * pdf_d1 * d1 / (2 * T)) / 365
    return (q * math.exp(-q * T) * N_d2 
            - math.exp(-q * T) * pdf_d1 * (r - q) / (sigma * math.sqrt(T))
            - q * math.exp(-q * T) * pdf_d1 * d2 / (2 * T)) / 365


def speed(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dGamma/dSpot."""
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    gamma_val = math.exp(-q * T) * math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) / (spot * sigma * math.sqrt(T))
    return -gamma_val / spot * (d1 / (sigma * math.sqrt(T)) + 1)


def color(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dGamma/dt (per day)."""
    if T <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    gamma_val = math.exp(-q * T) * math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) / (spot * sigma * math.sqrt(T))
    return gamma_val * (q + d1 * (r - q) / (2 * T) + (1 - d1 ** 2) / (2 * T)) / 365


def zomma(spot: float, strike: float, T: float, r: float, sigma: float, 
          kind: str = "CE", q: float = 0.0) -> float:
    """dGamma/dVol."""
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    gamma_val = math.exp(-q * T) * math.exp(-d1 ** 2 / 2) / math.sqrt(2 * math.pi) / (spot * sigma * math.sqrt(T))
    return gamma_val * (d1 * d2 - 1) / sigma


def full_greeks(spot: float, strike: float, T: float, r: float, sigma: float, 
                kind: str = "CE", q: float = 0.0) -> OptionGreeksFull:
    """All Greeks including second/third order."""
    base = greeks(spot, strike, T, r, sigma, kind, q)
    return OptionGreeksFull(
        delta=base["delta"],
        gamma=base["gamma"],
        theta=base["theta"],
        vega=base["vega"],
        rho=base["rho"],
        vanna=vanna(spot, strike, T, r, sigma, kind, q),
        volga=volga(spot, strike, T, r, sigma, kind, q),
        charm=charm(spot, strike, T, r, sigma, kind, q),
        speed=speed(spot, strike, T, r, sigma, kind, q),
        color=color(spot, strike, T, r, sigma, kind, q),
        zomma=zomma(spot, strike, T, r, sigma, kind, q),
    )


# ------------------------------------------------------------------ #
# IV Surface & Skew Analysis
# ------------------------------------------------------------------ #
def iv_surface(chain: pd.DataFrame, spot: float, r: float = settings.RISK_FREE_RATE,
               q: float = 0.0) -> pd.DataFrame:
    """
    Compute implied vol for all strikes in chain.
    chain must have: strike, expiry, ce_ltp, pe_ltp, ce_iv, pe_iv, dte
    """
    df = chain.copy()
    # Fill IV from LTP if missing
    for _, row in df.iterrows():
        T = row.get("dte", 7) / 365.0
        if pd.isna(row.get("ce_iv")) or row.get("ce_iv", 0) == 0:
            iv = implied_vol(row["ce_ltp"], spot, row["strike"], T, r, "CE", q)
            if iv: df.at[row.name, "ce_iv"] = iv * 100
        if pd.isna(row.get("pe_iv")) or row.get("pe_iv", 0) == 0:
            iv = implied_vol(row["pe_ltp"], spot, row["strike"], T, r, "PE", q)
            if iv: df.at[row.name, "pe_iv"] = iv * 100
    return df


def atm_iv(chain: pd.DataFrame, spot: float) -> float:
    """ATM IV from nearest strike."""
    if chain.empty:
        return 0.0
    atm_row = chain.iloc[(chain["strike"] - spot).abs().idxmin()]
    return (atm_row.get("ce_iv", 0) + atm_row.get("pe_iv", 0)) / 2


def skew_metrics(chain: pd.DataFrame, spot: float) -> dict:
    """
    Risk Reversal (25d RR) and Butterfly (25d BF).
    25d RR = IV(25d Call) - IV(25d Put)
    25d BF = (IV(25d Call) + IV(25d Put))/2 - ATM IV
    """
    if chain.empty:
        return {"rr_25d": 0, "bf_25d": 0, "atm_iv": 0}
    
    # Find 25 delta strikes (approximate via delta ~ 0.25)
    calls = chain[chain["ce_iv"] > 0].copy()
    puts = chain[chain["pe_iv"] > 0].copy()
    
    # Approximate 25d strikes
    call_25 = calls.iloc[(calls["strike"] - spot * 1.02).abs().idxmin()] if not calls.empty else None
    put_25 = puts.iloc[(puts["strike"] - spot * 0.98).abs().idxmin()] if not puts.empty else None
    
    atm = atm_iv(chain, spot)
    
    rr = 0.0
    bf = 0.0
    if call_25 is not None and put_25 is not None:
        iv_call_25 = call_25["ce_iv"]
        iv_put_25 = put_25["pe_iv"]
        rr = iv_call_25 - iv_put_25
        bf = (iv_call_25 + iv_put_25) / 2 - atm
    
    return {
        "rr_25d": round(rr, 2),
        "bf_25d": round(bf, 2),
        "atm_iv": round(atm, 2),
        "call_25d_iv": round(call_25["ce_iv"], 2) if call_25 is not None else 0,
        "put_25d_iv": round(put_25["pe_iv"], 2) if put_25 is not None else 0,
    }


def term_structure_iv(chain: pd.DataFrame, spot: float) -> pd.DataFrame:
    """ATM IV by expiry (term structure)."""
    if chain.empty:
        return pd.DataFrame()
    df = chain.copy()
    # Group by expiry, take ATM IV
    expiries = df["expiry"].unique()
    rows = []
    for exp in expiries:
        exp_chain = df[df["expiry"] == exp]
        iv = atm_iv(exp_chain, spot)
        if iv > 0:
            rows.append({"expiry": exp, "atm_iv": round(iv, 2)})
    return pd.DataFrame(rows).sort_values("expiry")


def iv_smile(chain: pd.DataFrame, spot: float, expiry: str) -> pd.DataFrame:
    """IV smile for a specific expiry."""
    exp_chain = chain[chain["expiry"] == expiry].copy()
    if exp_chain.empty:
        return pd.DataFrame()
    exp_chain["moneyness"] = exp_chain["strike"] / spot
    return exp_chain[["strike", "moneyness", "ce_iv", "pe_iv"]].sort_values("strike")


# ------------------------------------------------------------------ #
# Put-Call Parity & Arbitrage
# ------------------------------------------------------------------ #
def put_call_parity(chain: pd.DataFrame, spot: float, r: float = settings.RISK_FREE_RATE) -> pd.DataFrame:
    """
    Check put-call parity: C - P = S - K*exp(-rT)
    Deviation signals mispricing.
    """
    df = chain.copy()
    df["T"] = df.get("dte", 7) / 365.0
    df["parity_rhs"] = spot - df["strike"] * np.exp(-r * df["T"])
    df["parity_lhs"] = df["ce_ltp"] - df["pe_ltp"]
    df["parity_gap"] = df["parity_lhs"] - df["parity_rhs"]
    df["gap_pct"] = (df["parity_gap"] / df["parity_rhs"].abs()) * 100
    return df[["strike", "expiry", "ce_ltp", "pe_ltp", "parity_lhs", "parity_rhs", "parity_gap", "gap_pct"]]


# ------------------------------------------------------------------ #
# Max Pain
# ------------------------------------------------------------------ #
def max_pain(chain: pd.DataFrame) -> dict:
    """
    Max Pain strike = strike where total option writer loss is minimized.
    Total loss = sum(CE_OI * max(K - S, 0)) + sum(PE_OI * max(S - K, 0))
    """
    if chain.empty:
        return {"max_pain": 0, "loss_at_pain": 0, "current_spot": 0}
    
    strikes = chain["strike"].unique()
    ce_oi = chain.set_index("strike")["ce_oi"]
    pe_oi = chain.set_index("strike")["pe_oi"]
    spot = chain["spot"].iloc[0] if "spot" in chain.columns else 0
    
    losses = []
    for S in strikes:
        loss = 0.0
        for K in strikes:
            ce = ce_oi.get(K, 0)
            pe = pe_oi.get(K, 0)
            loss += ce * max(S - K, 0) + pe * max(K - S, 0)
        losses.append((S, loss))
    
    max_pain_strike = min(losses, key=lambda x: x[1])[0]
    return {
        "max_pain": float(max_pain_strike),
        "loss_at_pain": min(losses, key=lambda x: x[1])[1],
        "current_spot": float(spot),
        "distance_to_pain_pct": round((max_pain_strike / spot - 1) * 100, 2) if spot else 0,
    }


# ------------------------------------------------------------------ #
# PCR & OI Analysis
# ------------------------------------------------------------------ #
def pcr_analysis(chain: pd.DataFrame) -> dict:
    """Put-Call Ratio by OI and Volume."""
    if chain.empty:
        return {"pcr_oi": 0, "pcr_vol": 0, "total_ce_oi": 0, "total_pe_oi": 0}
    
    total_ce_oi = chain["ce_oi"].sum()
    total_pe_oi = chain["pe_oi"].sum()
    total_ce_vol = chain["ce_vol"].sum() if "ce_vol" in chain.columns else 0
    total_pe_vol = chain["pe_vol"].sum() if "pe_vol" in chain.columns else 0
    
    return {
        "pcr_oi": round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else 0,
        "pcr_vol": round(total_pe_vol / total_ce_vol, 3) if total_ce_vol else 0,
        "total_ce_oi": int(total_ce_oi),
        "total_pe_oi": int(total_pe_oi),
        "total_ce_vol": int(total_ce_vol),
        "total_pe_vol": int(total_pe_vol),
        "pcr_interpretation": ("BULLISH" if total_pe_oi / total_ce_oi > 1.2 else
                               "BEARISH" if total_pe_oi / total_ce_oi < 0.8 else "NEUTRAL"),
    }


def oi_walls(chain: pd.DataFrame, top_n: int = 5) -> dict:
    """Find OI walls (support/resistance from high OI)."""
    if chain.empty:
        return {"resistance": [], "support": []}
    
    # Resistance = high CE OI above spot, Support = high PE OI below spot
    spot = chain["spot"].iloc[0] if "spot" in chain.columns else 0
    
    ce_walls = chain[chain["strike"] >= spot].nlargest(top_n, "ce_oi")[["strike", "ce_oi"]]
    pe_walls = chain[chain["strike"] <= spot].nlargest(top_n, "pe_oi")[["strike", "pe_oi"]]
    
    return {
        "resistance": ce_walls.rename(columns={"ce_oi": "oi"}).to_dict("records"),
        "support": pe_walls.rename(columns={"pe_oi": "oi"}).to_dict("records"),
        "spot": spot,
    }


def oi_change_analysis(chain: pd.DataFrame, prev_chain: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Analyze OI change vs previous day."""
    if prev_chain is None or prev_chain.empty:
        return pd.DataFrame()
    
    df = chain[["strike", "expiry", "ce_oi", "pe_oi"]].copy()
    prev = prev_chain[["strike", "expiry", "ce_oi", "pe_oi"]].copy()
    prev.columns = ["strike", "expiry", "prev_ce_oi", "prev_pe_oi"]
    
    merged = df.merge(prev, on=["strike", "expiry"], how="left")
    merged["ce_oi_change"] = merged["ce_oi"] - merged["prev_ce_oi"]
    merged["pe_oi_change"] = merged["pe_oi"] - merged["prev_pe_oi"]
    merged["ce_oi_change_pct"] = (merged["ce_oi_change"] / merged["prev_ce_oi"].replace(0, np.nan)) * 100
    merged["pe_oi_change_pct"] = (merged["pe_oi_change"] / merged["prev_pe_oi"].replace(0, np.nan)) * 100
    
    return merged[["strike", "expiry", "ce_oi", "pe_oi", "ce_oi_change", "pe_oi_change",
                   "ce_oi_change_pct", "pe_oi_change_pct"]].sort_values("strike")


# ------------------------------------------------------------------ #
# Position Greeks Aggregation
# ------------------------------------------------------------------ #
def position_greeks(positions: list[dict], spot: float, r: float = settings.RISK_FREE_RATE) -> dict:
    """
    Aggregate Greeks for a portfolio of options positions.
    positions: [{"symbol": "NIFTY", "strike": 24500, "type": "CE", "expiry": "2026-09-25", 
                 "qty": 2, "sigma": 0.15, "dte": 30, "side": "buy"}, ...]
    """
    totals = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0,
              "vanna": 0, "volga": 0, "charm": 0}
    
    for pos in positions:
        K = pos["strike"]
        T = pos["dte"] / 365.0
        sigma = pos["sigma"]
        kind = pos["type"]
        qty = pos["qty"] * (1 if pos.get("side", "buy") == "buy" else -1)
        
        fg = full_greeks(spot, K, T, r, sigma, kind)
        for k in totals:
            totals[k] += getattr(fg, k) * qty
    
    return {k: round(v, 4) for k, v in totals.items()}


# ------------------------------------------------------------------ #
# Strategy Payoff with Greeks
# ------------------------------------------------------------------ #
def strategy_payoff_with_greeks(positions: list[dict], spot_range: np.ndarray, 
                                spot: float, r: float = settings.RISK_FREE_RATE) -> dict:
    """Generate payoff curve with Greeks at each spot point."""
    payoffs = []
    greeks_at_spot = []
    
    for S in spot_range:
        pnl = 0
        greeks_sum = {k: 0 for k in ["delta", "gamma", "theta", "vega", "rho", "vanna", "volga", "charm"]}
        for pos in positions:
            K = pos["strike"]
            T = pos["dte"] / 365.0
            sigma = pos["sigma"]
            kind = pos["type"]
            qty = pos["qty"] * (1 if pos.get("side", "buy") == "buy" else -1)
            premium = pos.get("premium", bs_price(S, K, T, r, sigma, kind))
            
            intrinsic = max(S - K, 0) if kind == "CE" else max(K - S, 0)
            pnl += qty * (intrinsic - premium)
            
            fg = full_greeks(S, K, T, r, sigma, kind)
            for k in greeks_sum:
                greeks_sum[k] += getattr(fg, k) * qty
        
        payoffs.append(pnl)
        greeks_at_spot.append(greeks_sum.copy())
    
    return {
        "spots": spot_range.tolist(),
        "payoff": payoffs,
        "greeks_at_spot": greeks_at_spot,
    }