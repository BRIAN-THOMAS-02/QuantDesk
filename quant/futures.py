"""Futures pricing, term structure, and Greeks for Indian markets.

Covers:
- Cost-of-carry model with dividends
- Futures basis, fair value, convenience yield
- Term structure of futures prices
- Futures Greeks: Delta=1, Gamma=0, Theta (cost of carry), Vega=0, Rho
- Cash-futures arbitrage bounds
- Roll yield and calendar spreads
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from quant.black_scholes import bs_price, greeks, implied_vol
from config import settings


@dataclass
class FuturesContract:
    symbol: str
    underlying: str
    expiry: pd.Timestamp
    lot_size: int
    strike_step: float = 50.0  # for options on futures


@dataclass
class FuturesGreeks:
    """Greeks for a futures position (per contract)."""
    delta: float = 1.0          # ∂F/∂S = 1 (for linear futures)
    gamma: float = 0.0          # ∂²F/∂S² = 0
    theta: float = 0.0          # ∂F/∂t = cost of carry per day
    vega: float = 0.0           # ∂F/∂σ = 0
    rho: float = 0.0            # ∂F/∂r = T * F (approx)
    carry: float = 0.0          # annualized cost of carry
    basis: float = 0.0          # F - S
    basis_pct: float = 0.0      # (F - S) / S * 100
    annualized_basis: float = 0.0  # basis * 252 / DTE


def cost_of_carry(spot: float, futures: float, dte: int, 
                  div_yield: float = 0.0) -> float:
    """
    Implied cost of carry from futures price.
    F = S * exp((r - q) * T)  =>  r - q = ln(F/S) / T
    """
    if dte <= 0 or spot <= 0:
        return 0.0
    T = dte / 365.0
    return math.log(futures / spot) / T


def futures_fair_value(spot: float, r: float, q: float, dte: int) -> float:
    """Fair value under cost-of-carry: F = S * exp((r - q) * T)"""
    if dte <= 0:
        return spot
    T = dte / 365.0
    return spot * math.exp((r - q) * T)


def futures_basis(spot: float, futures: float, dte: int) -> dict:
    """Basis analysis: futures - spot, annualized, carry implied."""
    if dte <= 0 or spot <= 0:
        return {"basis": 0, "basis_pct": 0, "annualized_basis": 0, "implied_carry": 0}
    basis = futures - spot
    basis_pct = (basis / spot) * 100
    annualized_basis = basis_pct * 365 / dte
    implied_carry = cost_of_carry(spot, futures, dte)
    return {
        "basis": round(basis, 2),
        "basis_pct": round(basis_pct, 4),
        "annualized_basis": round(annualized_basis, 4),
        "implied_carry": round(implied_carry, 6),
    }


def cash_futures_arbitrage(spot: float, futures: float, dte: int, 
                           r: float = settings.RISK_FREE_RATE,
                           div_yield: float = 0.0,
                           transaction_cost_pct: float = 0.001) -> dict:
    """
    Cash-futures arbitrage bounds.
    Lower bound: F >= S * exp((r - q) * T) - transaction costs
    Upper bound: F <= S * exp((r - q) * T) + transaction costs (for reverse arb)
    """
    fair = futures_fair_value(spot, r, div_yield, dte)
    tc = spot * transaction_cost_pct
    return {
        "fair_value": round(fair, 2),
        "lower_bound": round(fair - tc, 2),
        "upper_bound": round(fair + tc, 2),
        "mispricing": round(futures - fair, 2),
        "mispricing_pct": round((futures - fair) / fair * 100, 4),
        "arb_signal": ("BUY_SPOT_SELL_FUT" if futures > fair + tc else
                       "SELL_SPOT_BUY_FUT" if futures < fair - tc else "FAIR"),
    }


def roll_yield(near_futures: float, far_futures: float, dte_near: int, dte_far: int) -> dict:
    """Calendar spread roll yield (annualized)."""
    if dte_near <= 0 or dte_far <= dte_near:
        return {"roll_yield_annualized": 0, "spread": 0}
    spread = far_futures - near_futures
    days_diff = dte_far - dte_near
    ann_yield = (spread / near_futures) * (365 / days_diff) * 100
    return {
        "spread": round(spread, 2),
        "days_diff": days_diff,
        "roll_yield_annualized": round(ann_yield, 4),
    }


def futures_greeks(spot: float, futures: float, dte: int, 
                   r: float = settings.RISK_FREE_RATE,
                   div_yield: float = 0.0) -> FuturesGreeks:
    """Complete Greeks for a futures contract."""
    if dte <= 0:
        T = 0
    else:
        T = dte / 365.0
    carry = r - div_yield
    basis_data = futures_basis(spot, futures, dte)
    return FuturesGreeks(
        delta=1.0,
        gamma=0.0,
        theta=round(-carry * futures / 365, 6),  # daily decay
        vega=0.0,
        rho=round(futures * T, 6),
        carry=round(carry, 6),
        basis=basis_data["basis"],
        basis_pct=basis_data["basis_pct"],
        annualized_basis=basis_data["annualized_basis"],
    )


def term_structure_analysis(expiries_data: list[dict], spot: float) -> dict:
    """
    Analyze futures term structure from multiple expiries.
    expiries_data: [{"expiry": "2026-09-25", "futures_price": 24500, "dte": 30}, ...]
    """
    if not expiries_data:
        return {}
    df = pd.DataFrame(expiries_data)
    df["basis"] = df["futures_price"] - spot
    df["basis_pct"] = (df["basis"] / spot) * 100
    df["annualized_basis"] = df["basis_pct"] * 365 / df["dte"]
    
    # Contango/Backwardation
    if len(df) >= 2:
        df = df.sort_values("dte")
        near, far = df.iloc[0], df.iloc[-1]
        structure = "CONTANGO" if far["futures_price"] > near["futures_price"] else "BACKWARDATION"
    else:
        structure = "SINGLE"
    
    return {
        "spot": spot,
        "structure": structure,
        "curve": df.to_dict("records"),
        "near_term": df.iloc[0].to_dict() if len(df) else {},
        "far_term": df.iloc[-1].to_dict() if len(df) else {},
    }


def futures_margin_estimate(futures_price: float, lot_size: int, 
                            volatility_pct: float = 15.0,
                            margin_pct: float = 0.12) -> dict:
    """Estimate SPAN-like margin for a futures position."""
    contract_value = futures_price * lot_size
    span_margin = contract_value * margin_pct
    exposure_margin = contract_value * (volatility_pct / 100) * 0.5  # rough
    total_margin = span_margin + exposure_margin
    return {
        "contract_value": round(contract_value, 0),
        "span_margin": round(span_margin, 0),
        "exposure_margin": round(exposure_margin, 0),
        "total_margin": round(total_margin, 0),
        "margin_pct_of_value": round(total_margin / contract_value * 100, 2),
    }