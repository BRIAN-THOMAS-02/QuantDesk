"""Black-Scholes-Merton option pricing with full Greeks + implied volatility.

Vectorized (numpy) so it prices entire chains at once.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


def _d1_d2(S, K, T, r, sigma, q=0.0):
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return d1, d1 - sigma * np.sqrt(T)


def bs_price(S, K, T, r, sigma, kind="CE", q=0.0):
    """kind: 'CE' (call) or 'PE' (put)."""
    call = kind.upper() in ("CE", "CALL", "C")
    if T <= 0 or sigma <= 0:
        return np.maximum(S - K, 0.0) if call else np.maximum(K - S, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if call:
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


# --------------------------------------------------------------------- #
# GREEKS
# --------------------------------------------------------------------- #
def greeks(S, K, T, r, sigma, kind="CE", q=0.0) -> dict:
    call = kind.upper() in ("CE", "CALL", "C")
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    if T <= 0 or sigma <= 0:
        intrinsic = np.maximum(S - K, 0) if call else np.maximum(K - S, 0)
        return {"delta": float(np.sign(intrinsic)) if np.any(intrinsic > 0) else 0.0,
                "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    pdf1 = norm.pdf(d1)
    gamma = np.exp(-q * T) * pdf1 / (S * sigma * np.sqrt(T))
    vega = S * np.exp(-q * T) * pdf1 * np.sqrt(T)          # per 1.00 vol; /100 for per-point
    if call:
        delta = np.exp(-q * T) * norm.cdf(d1)
        theta = (-S * np.exp(-q * T) * pdf1 * sigma / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)
                 + q * S * np.exp(-q * T) * norm.cdf(d1))
        rho = K * T * np.exp(-r * T) * norm.cdf(d2)
    else:
        delta = -np.exp(-q * T) * norm.cdf(-d1)
        theta = (-S * np.exp(-q * T) * pdf1 * sigma / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)
                 - q * S * np.exp(-q * T) * norm.cdf(-d1))
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2)
    # per calendar day
    return {"delta": float(np.round(delta, 4)), "gamma": float(np.round(gamma, 6)),
            "theta": float(np.round(theta / 365, 4)),
            "vega": float(np.round(vega / 100, 4)),   # per 1 vol point
            "rho": float(np.round(rho / 100, 4))}


def greek_chain(chain: pd.DataFrame, r: float = 0.065, days_to_expiry=None):
    """Attach BS price + greeks to an NSE option_chain DataFrame (needs spot,
    strike, ce_iv/pe_iv and expiry info in days). Adds columns ce_bs, pe_bs,
    ce_delta... pe_rho."""
    import pandas as pd
    df = chain.copy()
    if days_to_expiry is None:
        exp = pd.to_datetime(df["expiry"].iloc[0], errors="coerce")
        if pd.notna(exp):
            days_to_expiry = max((exp - pd.Timestamp.now()).days, 0)
        else:
            days_to_expiry = 7
    T = max(days_to_expiry, 1e-6) / 365.0
    S, K = df["spot"].values, df["strike"].values
    for side in ("ce", "pe"):
        kind = "CE" if side == "ce" else "PE"
        iv = pd.to_numeric(df[f"{side}_iv"], errors="coerce").replace(0, np.nan).values / 100.0
        fill = np.nanmedian(iv) if not np.all(np.isnan(iv)) else 0.20
        iv = np.where(np.isnan(iv), fill, iv)
        df[f"{side}_bs"] = bs_price(S, K, T, r, iv, kind=kind, q=0.0)
        g = [greeks(float(S[i]), float(K[i]), T, r, float(iv[i]), kind=kind)
             for i in range(len(df))]
        for k_ in ("delta", "gamma", "theta", "vega"):
            df[f"{side}_{k_}"] = [x[k_] for x in g]
    return df


# --------------------------------------------------------------------- #
# IMPLIED VOLATILITY
# --------------------------------------------------------------------- #
def implied_vol(price, S, K, T, r, kind="CE", q=0.0,
                lo=1e-4, hi=5.0, tol=1e-6) -> float | None:
    """Bisection IV - robust for illiquid Indian strikes."""
    call = kind.upper() in ("CE", "CALL", "C")
    f = lambda s: float(bs_price(S, K, T, r, s, kind, q)) - price
    try:
        if f(lo) * f(hi) > 0:
            return None
        return float(brentq(f, lo, hi, xtol=tol))
    except (ValueError, RuntimeError):
        return None


def newton_iv(price, S, K, T, r, kind="CE", q=0.0, guess=0.2,
              iters: int = 60, tol: float = 1e-7) -> float | None:
    sig = guess
    for _ in range(iters):
        p = float(bs_price(S, K, T, r, sig, kind, q))
        diff = p - price
        if abs(diff) < tol:
            return float(sig)
        v = greeks(S, K, T, r, sig, kind, q)["vega"] * 100   # back to per-unit vol
        if v < 1e-10:
            break
        sig -= diff / v
        if not (1e-4 < sig < 5.0):
            break
    return implied_vol(price, S, K, T, r, kind, q)


# --------------------------------------------------------------------- #
def put_call_parity_check(S, K, T, r, call_px, put_px) -> dict:
    """C = P + S - K*e^{-rT}. Deviation signals arb/mispricing."""
    lhs = call_px - put_px
    rhs = S - K * np.exp(-r * T)
    return {"parity_lhs": round(float(lhs), 4), "parity_rhs": round(float(rhs), 4),
            "arb_gap": round(float(lhs - rhs), 4),
            "signal": "CALL RICH" if lhs > rhs else "PUT RICH"}


def payoff_diagram(legs: list[dict], spots: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """legs: [{'type':'CE','strike':K,'premium':p,'qty':+/-n,'side':'buy/sell'}, ...]"""
    total = np.zeros_like(spots, dtype=float)
    for leg in legs:
        qty = leg["qty"] * (-1 if leg.get("side") == "sell" else 1)
        intrinsic = (np.maximum(spots - leg["strike"], 0) if leg["type"] == "CE"
                     else np.maximum(leg["strike"] - spots, 0))
        total += qty * (intrinsic - leg["premium"])
    return spots, total
