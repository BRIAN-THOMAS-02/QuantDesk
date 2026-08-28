"""Strategy interface + Signal model shared by all strategies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class Signal:
    symbol: str
    strategy: str
    direction: int                      # +1 long / -1 short / 0 flat
    entry: float | None = None
    stop: float | None = None
    target1: float | None = None        # book 50% here (R=1 style)
    target2: float | None = None
    rr: float | None = None             # reward:risk to T2
    holding_period: str = "swing"       # swing | intraday | positional
    confidence: float = 0.0             # 0-100
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    rationale: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    @property
    def side(self) -> str:
        return {1: "BUY", -1: "SELL/SHORT", 0: "NO TRADE"}[self.direction]


class StrategyBase:
    """Subclasses implement generate(df) -> Signal for the latest bar."""

    name: str = "base"
    holding_period: str = "swing"
    description: str = ""

    def generate(self, df: pd.DataFrame) -> Signal:
        raise NotImplementedError

    def _mk(self, symbol: str, direction: int, entry=None, stop=None,
            t1=None, t2=None, conf=0.0, **rationale) -> Signal:
        rr = abs((t2 - entry) / (entry - stop)) if \
            (entry and stop and t2 and entry != stop) else None
        return Signal(symbol=symbol, strategy=self.name, direction=direction,
                      entry=entry, stop=stop, target1=t1, target2=t2,
                      rr=round(rr, 2) if rr else None,
                      holding_period=self.holding_period,
                      confidence=round(conf, 1), rationale=rationale)
