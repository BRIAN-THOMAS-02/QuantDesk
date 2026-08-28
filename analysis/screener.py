"""Swing-trade candidate screener: ranks universe by multi-factor score.

Factors (each 0-100, weighted):
  trend      - price vs EMA200/EMA50, Supertrend direction
  momentum   - 3m return + RSI sweet-spot (50-70)
  strength   - ADX > 20 & volume z-score
  proximity  - nearness to 52w high (breakout candidates)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.indicators import compute_all, rsi
from config import settings
from data.providers.yfinance_provider import YFinanceProvider
from utils.helpers import logger


class Screener:

    def __init__(self, provider=None, universe: list[str] | None = None,
                 benchmark: str = "^NSEI"):
        self.provider = provider or YFinanceProvider()
        self.universe = universe or settings.SWING_UNIVERSE
        self.benchmark_symbol = benchmark
        self._bench_close: pd.Series | None = None
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ #
    def benchmark(self) -> pd.Series:
        if self._bench_close is None:
            b = self.provider.history(self.benchmark_symbol, period="1y")
            self._bench_close = b["close"]
        return self._bench_close

    def load(self, symbol: str, refresh: bool = False) -> pd.DataFrame:
        if refresh or symbol not in self._cache:
            df = compute_all(self.provider.history(symbol, period="1y"))
            if not df.empty:
                self._cache[symbol] = df
        return self._cache.get(symbol, pd.DataFrame())

    # ------------------------------------------------------------------ #
    @staticmethod
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, x))

    @classmethod
    def _score_row(cls, row: pd.Series) -> tuple[float, dict]:
        parts = {}
        # Trend: graded by distance above EMAs (saturates ~5%/3% above)
        t200 = cls._clip01(float(row.close / row.ema200 - 1) * 20) * 40 \
            if row.ema200 else 0
        t50 = cls._clip01(float(row.close / row.ema50 - 1) * 33) * 30 \
            if row.ema50 else 0
        tst = 30 if row.st_dir == 1 else 0
        parts["trend"] = round(t200 + t50 + tst, 1)

        # Momentum: smooth preference around RSI 58, penalize <45 & >80
        r = float(row.rsi)
        base = 100 * np.exp(-((r - 58) / 16) ** 2)
        if r < 45 or r > 80:
            base *= 0.35
        ret3 = float(np.nan_to_num(row.ret_3m))
        pace_bonus = 12 if 0.02 < ret3 < 0.55 else (-15 if ret3 < 0 else 0)
        parts["momentum"] = round(min(base + max(pace_bonus, 0), 100), 1)

        # Strength: ADX curve (peaks ~28) + volume confirmation
        adx_v = float(np.nan_to_num(row.adx))
        adx_pts = 55 / (1 + np.exp(-(adx_v - 22) / 5))          # logistic 0..55
        vz = float(np.nan_to_num(row.volz))
        vol_pts = min(max(vz, 0), 3) * 15                        # up to 45
        parts["strength"] = round(min(adx_pts + vol_pts, 100), 1)

        prox = float(row.close / row.hi_52w) if row.hi_52w else 0
        parts["proximity_52wh"] = round(cls._clip01(prox) * 100, 1)

        total = (0.35 * parts["trend"] + 0.25 * parts["momentum"]
                 + 0.20 * parts["strength"] + 0.20 * parts["proximity_52wh"])
        return round(total, 1), parts

    # ------------------------------------------------------------------ #
    def run(self, top_n: int = 12, refresh: bool = False) -> pd.DataFrame:
        bench = self.benchmark()
        rows = []
        for sym in self.universe:
            try:
                df = self.load(sym, refresh=refresh)
                if len(df) < 210:
                    continue
                last = df.iloc[-1]
                rs_vs_nifty = float(df.close.pct_change(63).iloc[-1]
                                    - bench.pct_change(63).iloc[-1])
                score, parts = self._score_row(last)
                rows.append({
                    "symbol": sym, "close": round(last.close, 2),
                    "rsi": round(last.rsi, 1),
                    "adx": round(last.adx, 1) if np.isfinite(last.adx) else None,
                    "st_dir": int(last.st_dir),
                    "above_emas": bool(last.close > last.ema50 > last.ema200),
                    "ret_3m_pct": round(last.ret_3m * 100, 1),
                    "rs_vs_nifty_pct": round(rs_vs_nifty * 100, 1),
                    "vol_z": round(float(np.nan_to_num(last.volz)), 2),
                    "pct_from_52wh": round((last.close / last.hi_52w - 1) * 100, 1),
                    "atr_pct": round(last.atr / last.close * 100, 2),
                    "factors": parts, "score": score,
                })
            except Exception as e:
                logger.debug("screener skip %s: %s", sym, e)
        res = pd.DataFrame(rows).sort_values("score", ascending=False)
        return res.head(top_n).reset_index(drop=True)

    def explain(self, symbol: str) -> str:
        """Human-readable factor breakdown for the UI detail view."""
        df = self.load(symbol)
        if df.empty:
            return f"No data for {symbol}"
        last = df.iloc[-1]
        score, parts = self._score_row(last)
        lines = [f"{symbol}: composite {score}/100",
                 f"  Trend     : {parts['trend']:.0f}  "
                 f"(>EMA200:{last.close > last.ema200} >EMA50:{last.close > last.ema50} "
                 f"ST:{'long' if last.st_dir == 1 else 'short'})",
                 f"  Momentum  : {parts['momentum']:.0f}  RSI={last.rsi:.1f} 3m={last.ret_3m*100:.1f}%"]
        return "\n".join(lines)
