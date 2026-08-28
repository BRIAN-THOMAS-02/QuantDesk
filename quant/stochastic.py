"""Stochastic process models used across the system.

- GBM            : drift/diffusion baseline for Monte Carlo
- OrnsteinUhlenbeck : mean-reversion (pairs/spread modeling)
- MertonJumpDiffusion : fat-tail index modelling (event risk)
- Heston         : stochastic volatility (smile-aware scenario pricing)

Discretization: Euler-Maruyama with full truncation where variance hits zero.
"""
from __future__ import annotations

import math

import numpy as np


class OrnsteinUhlenbeck:

    def __init__(self, theta: float, mu: float, sigma: float):
        self.theta, self.mu, self.sigma = theta, mu, sigma

    def simulate(self, x0: float, T: float = 1.0, steps: int = 252,
                 n_paths: int = 1000, seed: int | None = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        dt = T / steps
        x = np.empty((n_paths, steps + 1))
        x[:, 0] = x0
        for t in range(1, steps + 1):
            x[:, t] = (x[:, t - 1] + self.theta * (self.mu - x[:, t - 1]) * dt
                       + self.sigma * math.sqrt(dt) * rng.standard_normal(n_paths))
        return x

    @staticmethod
    def calibrate(spread: np.ndarray, dt: float = 1 / 252) -> "OrnsteinUhlenbeck":
        """OLS on dx = theta(mu - x)dt + sigma dW."""
        x, y = spread[:-1], spread[1:]
        dx = y - x
        A = np.vstack([np.ones_like(x), x]).T
        coef, *_ = np.linalg.lstsq(A, dx, rcond=None)
        a, b = coef
        theta = -b / dt
        theta = max(theta, 1e-6)
        mu = a / (theta * dt) if theta * dt else x.mean()
        resid = dx - (a + b * x)
        sigma = resid.std(ddof=2) / math.sqrt(dt)
        half_life = math.log(2) / theta if theta > 0 else float("inf")
        ou = OrnsteinUhlenbeck(theta, float(mu), float(sigma))
        ou.half_life_days = half_life
        return ou


class MertonJumpDiffusion:

    def __init__(self, mu: float, sigma: float, jump_intensity: float,
                 jump_mean: float, jump_std: float):
        self.lam, self.m, self.v = jump_intensity, jump_mean, jump_std
        self.mu, self.sigma = mu, sigma

    def simulate(self, S0: float, T: float = 1.0, steps: int = 252,
                 n_paths: int = 5000, seed: int | None = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        dt = T / steps
        # compensator keeps martingale property under Q
        k = math.exp(self.m + 0.5 * self.v ** 2) - 1
        drift = self.mu - 0.5 * self.sigma ** 2 - self.lam * k

        log_paths = [np.log(np.full(n_paths, S0))]
        for _ in range(steps):
            z = rng.standard_normal(n_paths)
            jumps = rng.poisson(self.lam * dt, n_paths)
            jump_sizes = np.where(
                jumps > 0,
                jumps * self.m + np.sqrt(jumps) * self.v * rng.standard_normal(n_paths),
                0.0)
            log_paths.append(log_paths[-1] + drift * dt
                             + self.sigma * math.sqrt(dt) * z + jump_sizes)
        return np.exp(np.array(log_paths)).T


class Heston:

    def __init__(self, kappa: float, theta_v: float, xi: float, rho: float,
                 v0: float | None = None):
        """kappa: mean-reversion speed of variance; theta_v: long-run var;
        xi: vol-of-vol; rho: corr spot/var; v0: initial variance."""
        self.kappa, self.theta_v, self.xi, self.rho = kappa, theta_v, xi, rho
        self.v0 = v0 or theta_v

    def simulate(self, S0: float, mu: float, T: float = 1.0, steps: int = 252,
                 n_paths: int = 5000, seed: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(seed)
        dt = T / steps
        S = np.empty((n_paths, steps + 1))
        v = np.empty((n_paths, steps + 1))
        S[:, 0], v[:, 0] = S0, self.v0
        for t in range(1, steps + 1):
            z1 = rng.standard_normal(n_paths)
            z2 = self.rho * z1 + math.sqrt(1 - self.rho ** 2) * rng.standard_normal(n_paths)
            v_t = np.maximum(v[:, t - 1], 0)                     # full truncation
            v_new = v_t + self.kappa * (self.theta_v - v_t) * dt \
                + self.xi * np.sqrt(v_t * dt) * z2
            v[:, t] = np.maximum(v_new, 0)                       # keep stored var >= 0
            S[:, t] = S[:, t - 1] * np.exp(
                (mu - 0.5 * v_t) * dt + np.sqrt(v_t * dt) * z1)
        return S, v


def estimate_gbm_params(prices: np.ndarray | "pd.Series", freq: int = 252) -> dict:
    """Method-of-moments calibration from a price series."""
    import pandas as pd
    p = pd.Series(prices).dropna().values
    logret = np.diff(np.log(p))
    mu_d, sd_d = logret.mean(), logret.std(ddof=1)
    return {
        "mu_annual": round(float(mu_d * freq), 4),
        "sigma_annual": round(float(sd_d * math.sqrt(freq)), 4),
        "sharpe_raw": round(float(mu_d / sd_d * math.sqrt(freq)), 2) if sd_d else 0,
    }
