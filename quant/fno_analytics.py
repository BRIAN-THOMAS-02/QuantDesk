"""Comprehensive F&O Analytics: Alpha/Beta (CAPM), F&O integration, 
Put-Call parity, Max Pain, PCR, OI analysis, strategy Greeks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from quant.black_scholes import bs_price, greeks, implied_vol
from quant.futures import (futures_fair_value, futures_basis, cash_futures_arbitrage,
                           futures_greeks, term_structure_analysis, roll_yield)
from quant.options_analytics import (full_greeks, iv_surface, skew_metrics, 
                                      term_structure_iv, put_call_parity, max_pain,
                                      pcr_analysis, oi_walls, oi_change_analysis,
                                      position_greeks, strategy_payoff_with_greeks)
from config import settings


@dataclass
class AlphaBeta:
    """CAPM Alpha/Beta for an instrument vs benchmark."""
    alpha: float              # annualized %
    beta: float
    r_squared: float
    tracking_error: float     # annualized %
    information_ratio: float
    alpha_t_stat: float
    benchmark_corr: float


def capm_alpha_beta(returns: pd.Series, benchmark_returns: pd.Series,
                    rf: float = settings.RISK_FREE_RATE) -> AlphaBeta:
    """
    Calculate CAPM Alpha/Beta using OLS regression.
    r_asset - rf = alpha + beta * (r_bench - rf) + epsilon
    """
    # Align series
    df = pd.DataFrame({"asset": returns, "bench": benchmark_returns}).dropna()
    if len(df) < 30:
        return AlphaBeta(0, 0, 0, 0, 0, 0, 0)
    
    # Excess returns
    y = df["asset"] - rf / 252
    x = df["bench"] - rf / 252
    
     # OLS: y = alpha + beta * x
    X = np.vstack([np.ones(len(x)), x]).T
    beta_alpha = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha_daily, beta = beta_alpha[0], beta_alpha[1]
    
    # Annualize
    alpha_annual = alpha_daily * 252 * 100
    
    # R-squared
    y_pred = alpha_daily + beta * x
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    
    # Tracking error
    te_daily = np.std(y - y_pred, ddof=1)
    tracking_error = te_daily * math.sqrt(252) * 100
    
    # Information ratio
    info_ratio = alpha_daily * 252 / (te_daily * math.sqrt(252)) if te_daily > 0 else 0
    
    # Alpha t-stat
    se_alpha = te_daily / math.sqrt(len(x) * (1 - r2)) if r2 < 1 else 0
    alpha_t = alpha_daily / se_alpha if se_alpha > 0 else 0
    
    # Correlation
    corr = np.corrcoef(df["asset"], df["bench"])[0, 1]
    
    return AlphaBeta(
        alpha=round(alpha_annual, 3),
        beta=round(beta, 4),
        r_squared=round(r2, 4),
        tracking_error=round(tracking_error, 2),
        information_ratio=round(info_ratio, 3),
        alpha_t_stat=round(alpha_t, 2),
        benchmark_corr=round(corr, 4),
    )


def rolling_alpha_beta(returns: pd.Series, benchmark_returns: pd.Series,
                       window: int = 252) -> pd.DataFrame:
    """Rolling CAPM alpha/beta."""
    df = pd.DataFrame({"asset": returns, "bench": benchmark_returns}).dropna()
    results = []
    for i in range(window, len(df)):
        window_df = df.iloc[i-window:i]
        ab = capm_alpha_beta(window_df["asset"], window_df["bench"])
        results.append({
            "date": df.index[i],
            "alpha": ab.alpha,
            "beta": ab.beta,
            "r2": ab.r_squared,
            "info_ratio": ab.information_ratio,
        })
    return pd.DataFrame(results).set_index("date")


@dataclass
class FNOInstrumentAnalytics:
    """Complete analytics for one F&O instrument."""
    symbol: str
    spot: float
    futures_price: float
    dte: int
    
    # Futures analytics
    fair_value: float
    basis: float
    basis_pct: float
    annualized_basis: float
    implied_carry: float
    arb_signal: str
    futures_greeks: dict
    
    # Options analytics
    atm_iv: float
    skew_rr_25d: float
    skew_bf_25d: float
    iv_term_structure: list[dict]
    pcr_oi: float
    pcr_vol: float
    max_pain: float
    distance_to_pain_pct: float
    oi_walls: dict
    parity_gap_avg: float
    
    # Alpha/Beta vs Nifty
    alpha: float
    beta: float
    r_squared: float
    info_ratio: float


def instrument_fno_analytics(
    symbol: str,
    spot: float,
    futures_price: float,
    dte: int,
    chain: pd.DataFrame,
    returns: pd.Series,
    benchmark_returns: pd.Series,
    r: float = settings.RISK_FREE_RATE,
    div_yield: float = 0.0,
) -> FNOInstrumentAnalytics:
    """Complete F&O analytics for one instrument."""
    
    # Futures
    fair = futures_fair_value(spot, r, div_yield, dte)
    basis_data = futures_basis(spot, futures_price, dte)
    arb = cash_futures_arbitrage(spot, futures_price, dte, r, div_yield)
    fg = futures_greeks(spot, futures_price, dte, r, div_yield)
    
    # Options
    atm_iv_val = 0
    if not chain.empty:
        chain_iv = iv_surface(chain, spot, r)
        atm_iv_val = atm_iv(chain_iv, spot)
        skew = skew_metrics(chain_iv, spot)
        iv_ts = term_structure_iv(chain_iv, spot)
        pcr = pcr_analysis(chain)
        mp = max_pain(chain)
        walls = oi_walls(chain)
        parity_df = put_call_parity(chain, spot, r)
        parity_gap = parity_df["parity_gap"].mean()
    else:
        skew = {"rr_25d": 0, "bf_25d": 0, "atm_iv": 0}
        iv_ts = []
        pcr = {"pcr_oi": 0, "pcr_vol": 0}
        mp = {"max_pain": 0, "distance_to_pain_pct": 0}
        walls = {"resistance": [], "support": []}
        parity_gap = 0
    
    # Alpha/Beta
    ab = capm_alpha_beta(returns, benchmark_returns)
    
    return FNOInstrumentAnalytics(
        symbol=symbol,
        spot=spot,
        futures_price=futures_price,
        dte=dte,
        fair_value=round(fair, 2),
        basis=round(basis_data["basis"], 2),
        basis_pct=round(basis_data["basis_pct"], 4),
        annualized_basis=round(basis_data["annualized_basis"], 4),
        implied_carry=round(basis_data["implied_carry"], 6),
        arb_signal=arb["arb_signal"],
        futures_greeks=fg.__dict__,
        atm_iv=round(atm_iv_val, 2),
        skew_rr_25d=round(skew.get("rr_25d", 0), 2),
        skew_bf_25d=round(skew.get("bf_25d", 0), 2),
        iv_term_structure=iv_ts.to_dict("records") if isinstance(iv_ts, pd.DataFrame) else [],
        pcr_oi=round(pcr.get("pcr_oi", 0), 3),
        pcr_vol=round(pcr.get("pcr_vol", 0), 3),
        max_pain=round(mp.get("max_pain", 0), 2),
        distance_to_pain_pct=round(mp.get("distance_to_pain_pct", 0), 2),
        oi_walls=walls,
        parity_gap_avg=round(parity_gap, 2) if isinstance(parity_gap, float) else 0,
        alpha=ab.alpha,
        beta=ab.beta,
        r_squared=ab.r_squared,
        info_ratio=ab.information_ratio,
    )


# ------------------------------------------------------------------ #
# Strategy-specific Greeks (Delta-neutral, Gamma scalping, etc.)
# ------------------------------------------------------------------ #
def delta_neutral_hedge(positions: list[dict], spot: float, 
                        r: float = settings.RISK_FREE_RATE) -> dict:
    """
    Calculate futures contracts needed to delta-hedge an options portfolio.
    """
    total_delta = 0
    for pos in positions:
        K = pos["strike"]
        T = pos["dte"] / 365.0
        sigma = pos["sigma"]
        kind = pos["type"]
        qty = pos["qty"] * (1 if pos.get("side", "buy") == "buy" else -1)
        g = greeks(spot, K, T, r, sigma, kind)
        total_delta += g["delta"] * qty
    
    # Futures delta = 1 per contract
    hedge_qty = -total_delta
    return {
        "portfolio_delta": round(total_delta, 2),
        "hedge_futures_qty": round(hedge_qty, 2),
        "direction": "SELL" if hedge_qty < 0 else "BUY",
    }


def gamma_scalping_pnl(spot_path: np.ndarray, gamma: float, 
                       delta_hedge_freq: str = "daily") -> dict:
    """
    Estimate P&L from gamma scalping (re-hedging delta).
    Assumes delta is hedged at frequency, capturing gamma * (dS)^2 / 2.
    """
    if len(spot_path) < 2:
        return {"gamma_pnl": 0, "theta_cost": 0, "net": 0}
    
    # Daily returns
    rets = np.diff(spot_path) / spot_path[:-1]
    # Gamma P&L = 0.5 * gamma * (dS)^2 summed
    gamma_pnl = 0.5 * gamma * np.sum((spot_path[:-1] * rets) ** 2)
    # Theta cost (approximate daily theta * days)
    days = len(spot_path) - 1
    theta_cost = -0.5 * gamma * spot_path[0] ** 2 * 0.01 * days  # rough
    
    return {
        "gamma_pnl": round(gamma_pnl, 2),
        "theta_cost": round(theta_cost, 2),
        "net_gamma_pnl": round(gamma_pnl + theta_cost, 2),
    }


def calendar_spread_analysis(near_chain: pd.DataFrame, far_chain: pd.DataFrame,
                              spot: float, r: float = settings.RISK_FREE_RATE) -> dict:
    """
    Analyze calendar spreads (same strike, different expiries).
    """
    if near_chain.empty or far_chain.empty:
        return {}
    
    # Merge on strike
    merged = near_chain[["strike", "ce_ltp", "pe_ltp", "ce_iv", "pe_iv"]].copy()
    merged.columns = ["strike", "ce_ltp_near", "pe_ltp_near", "ce_iv_near", "pe_iv_near"]
    far_data = far_chain[["strike", "ce_ltp", "pe_ltp", "ce_iv", "pe_iv"]].copy()
    far_data.columns = ["strike", "ce_ltp_far", "pe_ltp_far", "ce_iv_far", "pe_iv_far"]
    
    merged = merged.merge(far_data, on="strike", how="inner")
    if merged.empty:
        return {}
    
    merged["ce_calendar_cost"] = merged["ce_ltp_far"] - merged["ce_ltp_near"]
    merged["pe_calendar_cost"] = merged["pe_ltp_far"] - merged["pe_ltp_near"]
    merged["iv_spread"] = merged["ce_iv_far"] - merged["ce_iv_near"]
    
    # Best calendar spread candidates (lowest cost for calls/puts)
    best_call = merged.nsmallest(3, "ce_calendar_cost")[["strike", "ce_calendar_cost", "iv_spread"]]
    best_put = merged.nsmallest(3, "pe_calendar_cost")[["strike", "pe_calendar_cost", "iv_spread"]]
    
    return {
        "call_calendars": best_call.to_dict("records"),
        "put_calendars": best_put.to_dict("records"),
    }


def diagonal_spread_analysis(chain: pd.DataFrame, spot: float) -> dict:
    """
    Diagonal spreads: different strikes, different expiries.
    """
    # Simplified: find best diagonal candidates
    if chain.empty:
        return {}
    
    # Group by expiry
    expiries = chain["expiry"].unique()
    if len(expiries) < 2:
        return {}
    
    results = []
    for i, exp_near in enumerate(expiries[:-1]):
        for exp_far in expiries[i+1:]:
            near = chain[chain["expiry"] == exp_near]
            far = chain[chain["expiry"] == exp_far]
            cal = calendar_spread_analysis(near, far, spot)
            if cal:
                results.append({"near_expiry": exp_near, "far_expiry": exp_far, **cal})
    
    return {"diagonals": results[:5]}  # top 5


# ------------------------------------------------------------------ #
# Portfolio Margin & Risk
# ------------------------------------------------------------------ #
def span_margin_estimate(positions: list[dict], spot: float, 
                         volatility_pct: float = 15.0) -> dict:
    """
    Simplified SPAN-like margin estimation for F&O portfolio.
    """
    total_span = 0
    total_exposure = 0
    
    for pos in positions:
        K = pos["strike"]
        T = pos["dte"] / 365.0
        sigma = pos["sigma"]
        kind = pos["type"]
        qty = abs(pos["qty"])
        lot = pos.get("lot_size", 50)
        
        if kind in ("FUT", "futures"):
            # Futures margin
            contract_val = spot * qty * lot
            span = contract_val * 0.12
            exposure = contract_val * (volatility_pct / 100) * 0.5
        else:
            # Options margin (simplified)
            premium = bs_price(spot, K, T, settings.RISK_FREE_RATE, sigma, kind)
            if pos.get("side", "buy") == "buy":
                # Long option: premium paid is max loss
                span = premium * qty * lot
                exposure = 0
            else:
                # Short option: SPAN-like
                span = spot * qty * lot * 0.15
                exposure = spot * qty * lot * (volatility_pct / 100) * 0.3
        
        total_span += span
        total_exposure += exposure
    
    return {
        "span_margin": round(total_span, 0),
        "exposure_margin": round(total_exposure, 0),
        "total_margin": round(total_span + total_exposure, 0),
    }


# ------------------------------------------------------------------ #
# Scenario Analysis (What-if)
# ------------------------------------------------------------------ #
def scenario_analysis(positions: list[dict], spot: float, 
                      spot_shocks: list[float] = None,
                      vol_shocks: list[float] = None,
                      time_shocks: list[int] = None,
                      r: float = settings.RISK_FREE_RATE) -> pd.DataFrame:
    """
    What-if scenarios: spot move, vol change, time decay.
    Returns P&L and Greeks for each scenario.
    """
    if spot_shocks is None:
        spot_shocks = [-0.10, -0.05, -0.02, 0, 0.02, 0.05, 0.10]
    if vol_shocks is None:
        vol_shocks = [0]
    if time_shocks is None:
        time_shocks = [0, 1, 3, 5]
    
    results = []
    for ds in spot_shocks:
        for dv in vol_shocks:
            for dt in time_shocks:
                new_spot = spot * (1 + ds)
                pnl = 0
                greeks_sum = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
                
                for pos in positions:
                    K = pos["strike"]
                    T = max((pos["dte"] - dt) / 365.0, 1/365)
                    sigma = pos["sigma"] * (1 + dv)
                    kind = pos["type"]
                    qty = pos["qty"] * (1 if pos.get("side", "buy") == "buy" else -1)
                    premium = pos.get("premium", bs_price(spot, K, T, r, sigma, kind))
                    
                    new_premium = bs_price(new_spot, K, T, r, sigma, kind)
                    pnl += qty * (new_premium - premium) * pos.get("lot_size", 50)
                    
                    g = greeks(new_spot, K, T, r, sigma, kind)
                    for k in greeks_sum:
                        greeks_sum[k] += g[k] * qty
                
                results.append({
                    "spot_shock_pct": ds * 100,
                    "vol_shock_pct": dv * 100,
                    "days_passed": dt,
                    "new_spot": round(new_spot, 2),
                    "pnl": round(pnl, 0),
                    **{k: round(v, 2) for k, v in greeks_sum.items()},
                })
    
    return pd.DataFrame(results)


# ------------------------------------------------------------------ #
# Implied Forward & Dividend Yield Estimation
# ------------------------------------------------------------------ #
def implied_dividend_yield(spot: float, futures_price: float, dte: int,
                           r: float = settings.RISK_FREE_RATE) -> float:
    """
    Extract implied dividend yield from futures basis.
    F = S * exp((r - q) * T) => q = r - ln(F/S) / T
    """
    if dte <= 0 or spot <= 0:
        return 0.0
    T = dte / 365.0
    return r - math.log(futures_price / spot) / T


def implied_forward_rate(spot: float, futures_price: float, dte: int) -> float:
    """
    Implied forward rate from futures price.
    F = S * exp(r * T) => r = ln(F/S) / T
    """
    if dte <= 0 or spot <= 0:
        return 0.0
    T = dte / 365.0
    return math.log(futures_price / spot) / T


# ------------------------------------------------------------------ #
# Complete F&O Dashboard Data
# ------------------------------------------------------------------ #
def complete_fno_dashboard(symbol: str, spot: float, futures_price: float,
                            dte: int, chain: pd.DataFrame,
                            returns: pd.Series, benchmark_returns: pd.Series,
                            prev_chain: Optional[pd.DataFrame] = None) -> dict:
    """
    Complete F&O dashboard data for one instrument.
    """
    # Core analytics
    analytics = instrument_fno_analytics(
        symbol, spot, futures_price, dte, chain, returns, benchmark_returns
    )
    
    # Chain with IV
    chain_iv = iv_surface(chain, spot) if not chain.empty else pd.DataFrame()
    
    # OI change
    oi_change = oi_change_analysis(chain, prev_chain) if prev_chain is not None else pd.DataFrame()
    
    # Term structure
    # (need multiple expiries for full term structure)
    
    return {
        "symbol": symbol,
        "spot": spot,
        "futures_price": futures_price,
        "dte": dte,
        "analytics": analytics.__dict__,
        "chain_iv": chain_iv.to_dict("records") if not chain_iv.empty else [],
        "oi_change": oi_change.to_dict("records") if not oi_change.empty else [],
        "skew_metrics": skew_metrics(chain_iv, spot) if not chain_iv.empty else {},
        "pcr": pcr_analysis(chain) if not chain.empty else {},
        "max_pain": max_pain(chain) if not chain.empty else {},
        "oi_walls": oi_walls(chain) if not chain.empty else {},
        "parity": put_call_parity(chain, spot).to_dict("records") if not chain.empty else [],
    }