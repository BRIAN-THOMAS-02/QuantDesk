"""Portfolio construction: Markowitz mean-variance, max-Sharpe, min-variance,
and Hierarchical Risk Parity (HRP) - all from OSINT price data."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

from config import settings


class PortfolioOptimizer:

    def __init__(self, prices: pd.DataFrame):
        """prices: DataFrame of adjusted closes (columns = symbols)."""
        self.prices = prices.dropna(how="all")
        self.rets = self.prices.pct_change().dropna()
        self.mu = self.rets.mean() * settings.TRADING_DAYS
        self.cov = self.rets.cov() * settings.TRADING_DAYS

    # ------------------------------------------------------------------ #
    def _port_stats(self, w: np.ndarray) -> tuple[float, float]:
        r = float(self.mu.values @ w)
        v = float(np.sqrt(w @ self.cov.values @ w))
        return r, v

    def min_variance(self) -> pd.Series:
        n = len(self.mu)
        res = minimize(lambda w: w @ self.cov.values @ w,
                       np.ones(n) / n, method="SLSQP",
                       bounds=[(0, 1)] * n,
                       constraints={"type": "eq", "fun": lambda w: w.sum() - 1})
        return self._to_weights(res.x, list(self.rets.columns))

    def max_sharpe(self, rf: float = settings.RISK_FREE_RATE) -> pd.Series:
        n = len(self.mu)

        def neg_sharpe(w):
            r, v = self._port_stats(w)
            return -(r - rf) / v if v > 0 else 0

        res = minimize(neg_sharpe, np.ones(n) / n, method="SLSQP",
                       bounds=[(0, 1)] * n,
                       constraints={"type": "eq", "fun": lambda w: w.sum() - 1})
        return self._to_weights(res.x, list(self.rets.columns))

    def efficient_frontier(self, points: int = 25) -> list[dict]:
        n = len(self.mu)
        lo, hi = float(self.mu.min()), float(self.mu.max())
        targets = np.linspace(lo, hi, points)
        frontier = []
        for t in targets:
            cons = [{"type": "eq", "fun": lambda w: w.sum() - 1},
                    {"type": "eq", "fun": lambda w, tt=t: self.mu.values @ w - tt}]
            res = minimize(lambda w: w @ self.cov.values @ w,
                           np.ones(n) / n, method="SLSQP",
                           bounds=[(0, 1)] * n, constraints=cons)
            if res.success:
                r, v = self._port_stats(res.x)
                frontier.append({"ret": round(r * 100, 2),
                                 "vol": round(v * 100, 2),
                                 "sharpe": round((r - settings.RISK_FREE_RATE) / v, 2)
                                 if v else 0})
        return frontier

    # ------------------------------------------------------------------ #
    def hrp(self) -> pd.Series:
        """Hierarchical Risk Parity (Lopez de Prado)."""
        corr = self.rets.corr().values
        dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
        link = linkage(squareform(dist, checks=False), method="single")
        sort_ix = list(leaves_list(link))
        w = pd.Series(1.0, index=self.rets.columns[sort_ix])
        clusters = [w.index.tolist()]
        while len(clusters) > 0:
            clusters = [c[j:k] for c in clusters
                        for j, k in ((0, len(c) // 2), (len(c) // 2, len(c))) if len(c) > 1]
            for i in range(0, len(clusters), 2):
                c1, c2 = clusters[i], clusters[i + 1]
                v1 = self._cluster_var(c1); v2 = self._cluster_var(c2)
                alpha = 1 - v1 / (v1 + v2)
                w[c1] *= alpha; w[c2] *= 1 - alpha
        return self._to_weights(w.sort_index().values,
                                symbols=list(self.rets.columns))

    def _cluster_var(self, items: list[str]) -> float:
        sub = self.cov.loc[items, items].values
        w = np.ones(len(items)) / len(items)
        return float(w @ sub @ w)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_weights(w: np.ndarray, symbols=None, threshold=0.005) -> pd.Series:
        s = pd.Series(w, index=symbols)
        if s is None or getattr(s, "index", None) is None:
            pass
        s = s[s > threshold]
        return (s / s.sum()).round(4).sort_values(ascending=False)

    def summary(self) -> dict:
        ms = self.max_sharpe(); mv = self.min_variance(); h = self.hrp()
        out = {}
        for name, w in (("max_sharpe", ms), ("min_variance", mv), ("hrp", h)):
            aligned = np.zeros(len(self.mu))
            for sym, wt in w.items():
                if sym in self.mu.index:
                    aligned[self.mu.index.get_loc(sym)] = wt
            r, v = self._port_stats(aligned)
            out[name] = {"weights": w.to_dict(),
                         "exp_ret_pct": round(r * 100, 2),
                         "vol_pct": round(v * 100, 2)}
        return out
