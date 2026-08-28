"""Monte Carlo engine: GBM path simulation, option pricing w/ antithetics,
portfolio VaR/CVaR simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_gbm(S0: float, mu: float, sigma: float, T: float = 1.0,
                 steps: int = 252, n_paths: int = 10_000,
                 seed: int | None = 42) -> np.ndarray:
    """Geometric Brownian Motion paths -> array (n_paths, steps+1)."""
    rng = np.random.default_rng(seed)
    dt = T / steps
    z = rng.standard_normal((n_paths, steps))
    log_incr = (mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
    paths = S0 * np.exp(np.cumsum(log_incr, axis=1))
    return np.hstack([np.full((n_paths, 1), S0), paths])


def mc_option_price(S0: float, K: float, T: float, r: float, sigma: float,
                    kind: str = "CE", n_sims: int = 100_000,
                    seed: int | None = None, q: float = 0.0) -> dict:
    """European MC pricing with antithetic variance reduction + std error."""
    call = kind.upper() in ("CE", "CALL", "C")
    rng = np.random.default_rng(seed)
    half = max(n_sims // 2, 1)
    z = rng.standard_normal(half)
    z = np.concatenate([z, -z])
    ST = S0 * np.exp((r - q - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * z)
    payoff = np.maximum(ST - K, 0) if call else np.maximum(K - ST, 0)
    disc = np.exp(-r * T)
    px = disc * payoff.mean()
    se = disc * payoff.std(ddof=1) / np.sqrt(len(payoff))
    return {"price": round(float(px), 4), "std_error": round(float(se), 4),
            "ci95": [round(float(px - 1.96 * se), 4), round(float(px + 1.96 * se), 4)],
            "n_sims": int(len(payoff))}


def mc_var(returns, weights=None, portfolio_value: float = 1_000_000,
           horizon_days: int = 1, alpha: float = 0.95,
           n_sims: int = 50_000, seed: int = 7) -> dict:
    """Parametric-bootstrap VaR/CVaR from historical daily returns.

    returns: DataFrame (cols=assets) or Series for single asset.
    """
    if isinstance(returns, pd.Series):
        returns = returns.to_frame("asset")
    R = returns.dropna().values
    n_assets = R.shape[1]
    w = np.ones(n_assets) / n_assets if weights is None else \
        np.asarray(weights, dtype=float).reshape(-1)
    w = w / w.sum()

    mu, cov = R.mean(axis=0), np.atleast_2d(np.cov(R.T))
    rng = np.random.default_rng(seed)
    sims = rng.multivariate_normal(mu, cov, size=n_sims)
    port_rets = sims @ w * horizon_days
    var_cut = np.percentile(port_rets, (1 - alpha) * 100)

    return {
        "var_amount": round(float(-var_cut * portfolio_value), 2),
        "cvar_amount": round(float(-port_rets[port_rets <= var_cut].mean() * portfolio_value), 2),
        "var_pct": round(float(-var_cut * 100), 3),
        "cvar_pct": round(float(-port_rets[port_rets <= var_cut].mean() * 100), 3),
        "alpha": alpha, "horizon_days": horizon_days,
        "portfolio_value": portfolio_value,
    }


def terminal_distribution_stats(paths: np.ndarray) -> dict:
    term = paths[:, -1]
    return {
        "mean": round(float(term.mean()), 2),
        "median": round(float(np.median(term)), 2),
        "p5": round(float(np.percentile(term, 5)), 2),
        "p25": round(float(np.percentile(term, 25)), 2),
        "p75": round(float(np.percentile(term, 75)), 2),
        "p95": round(float(np.percentile(term, 95)), 2),
        "prob_above_start": round(float((term > paths[0, 0]).mean()), 4),
    }
