"""Abstract market data provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class DataProvider(ABC):
    """All providers return OHLCV DataFrames indexed by date (ascending)."""

    name: str = "base"

    @abstractmethod
    def history(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """Columns: open high low close volume. interval: 1d/1h/15m/5m."""

    @abstractmethod
    def quote(self, symbol: str) -> dict:
        """Latest snapshot: ltp, prev_close, change_pct, volume, etc."""

    # optional capabilities -------------------------------------------------
    def option_chain(self, underlying: str, expiry: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support option chains")

    def expiries(self, underlying: str) -> list[str]:
        raise NotImplementedError

    def futures_expiry(self, symbol: str) -> dict:
        raise NotImplementedError

    def delivery_data(self, symbol: str) -> pd.DataFrame:
        raise NotImplementedError

    def bulk_deals(self) -> pd.DataFrame:
        raise NotImplementedError

    def fii_dii(self) -> pd.DataFrame:
        raise NotImplementedError

    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df.dropna(subset=["close"])
