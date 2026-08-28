"""Cox-Ross-Rubinstein binomial tree pricing (handles American exercise)."""
from __future__ import annotations

import math

import numpy as np

from quant.black_scholes import bs_price


def crr_price(S: float, K: float, T: float, r: float, sigma: float,
              kind: str = "CE", american: bool = True, steps: int = 300,
              q: float = 0.0) -> float:
    call = kind.upper() in ("CE", "CALL", "C")
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    disc = math.exp(-r * dt)
    p = (math.exp((r - q) * dt) - d) / (u - d)
    p = min(max(p, 0.0), 1.0)

    j = np.arange(steps + 1)
    ST = S * u ** (steps - j) * d ** j
    V = np.maximum(ST - K, 0.0) if call else np.maximum(K - ST, 0.0)

    for i in range(steps - 1, -1, -1):
        V = disc * (p * V[:-1] + (1 - p) * V[1:])
        ST = ST[:i + 1] / u                     # roll tree one step down
        if american:
            intrinsic = np.maximum(ST - K, 0.0) if call else np.maximum(K - ST, 0.0)
            V = np.maximum(V, intrinsic)
    return float(V[0])


def early_exercise_premium(S, K, T, r, sigma, kind="CE", q=0.0, steps=200) -> dict:
    """American vs European gap - matters for deep ITM puts & dividends."""
    eu = bs_price(S, K, T, r, sigma, kind, q)
    am = crr_price(S, K, T, r, sigma, kind, american=True, steps=steps, q=q)
    return {"european": round(eu, 2), "american": round(am, 2),
            "early_exercise_value": round(am - eu, 2)}
