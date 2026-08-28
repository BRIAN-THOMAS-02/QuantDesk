"""Paper trading broker: fills at next close, persists to JSON, tracks P&L.
Safe playground that mirrors live order flow exactly (same API surface)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import settings
from utils.helpers import logger

STATE_FILE = settings.PROJECT_ROOT / "logs" / "paper_portfolio.json"


class PaperBroker:
    """Same method signatures as KiteOrderManager -> swap seamlessly."""

    def __init__(self):
        self.state = self._load()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return {"cash": settings.CAPITAL, "positions": {}, "orders": [],
                "realized_pnl": 0.0}

    def save(self):
        STATE_FILE.write_text(json.dumps(self.state, indent=2, default=str))

    # ------------------------------------------------------------------ #
    def place_order(self, symbol: str, side: str, qty: int,
                    price: float, product: str = "CNC",
                    tag: str | None = None) -> dict:
        side = side.upper()
        now = datetime.now().isoformat(timespec="seconds")
        order = {"order_id": f"P{len(self.state['orders']) + 1:05d}",
                 "time": now, "symbol": symbol.upper(), "side": side,
                 "qty": qty, "price": round(price, 2), "product": product,
                 "tag": tag}
        pos = self.state["positions"].setdefault(symbol.upper(), {
            "qty": 0, "avg_price": 0.0})

        if side == "BUY":
            total_cost = qty * price
            if total_cost > self.state["cash"]:
                return {"status": "REJECTED", "reason": "insufficient paper cash"}
            new_qty = pos["qty"] + qty
            pos["avg_price"] = ((pos["avg_price"] * pos["qty"]) + total_cost) / new_qty \
                if new_qty else 0.0
            pos["qty"] = new_qty
            self.state["cash"] -= total_cost
        else:  # SELL
            if pos["qty"] < qty:
                return {"status": "REJECTED", "reason": f"only {pos['qty']} held"}
            realized = qty * (price - pos["avg_price"])
            self.state["cash"] += qty * price
            self.state["realized_pnl"] += realized
            pos["qty"] -= qty
            if pos["qty"] == 0:
                pos["avg_price"] = 0.0
        self.state["orders"].append(order)
        self.save()
        logger.info("PAPER %s %s x%d @%.2f", side, symbol, qty, price)
        return {"status": "FILLED", **order}

    def portfolio(self, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        rows, mv_total = [], 0.0
        for sym, p in self.state["positions"].items():
            if p["qty"] <= 0:
                continue
            ltp = prices.get(sym, p["avg_price"])
            mv = p["qty"] * ltp
            mv_total += mv
            rows.append({"symbol": sym, "qty": p["qty"],
                         "avg": round(p["avg_price"], 2), "ltp": ltp,
                         "value": round(mv, 0),
                         "pnl": round((ltp - p["avg_price"]) * p["qty"], 0),
                         "pnl_pct": round((ltp / p["avg_price"] - 1) * 100, 2)
                         if p["avg_price"] else 0})
        return {
            "cash": round(self.state["cash"], 0),
            "market_value": round(mv_total, 0),
            "net_liquidation": round(self.state["cash"] + mv_total, 0),
            "realized_pnl": round(self.state["realized_pnl"], 0),
            "positions": rows}

    def orders(self) -> list[dict]:
        return list(reversed(self.state["orders"]))
