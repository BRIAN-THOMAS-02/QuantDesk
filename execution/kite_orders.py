"""Live Zerodha order routing - TRIPLE-GUARDED.

Requires ALL of:
  1. KITE_API_KEY + KITE_ACCESS_TOKEN in .env
  2. TRADING_MODE=live in .env
  3. confirm=True passed explicitly on every call

Until then it refuses loudly and the PaperBroker is used instead.
"""
from __future__ import annotations

from config import settings
from utils.helpers import logger


class KiteOrderManager:

    def __init__(self):
        if settings.TRADING_MODE != "live":
            raise RuntimeError("TRADING_MODE != 'live' - refusing to init live orders. "
                               "Use execution.PaperBroker.")
        from data.providers.kite_provider import KiteProvider
        self.kite = KiteProvider().kite          # raises if keys missing
        logger.warning("*** LIVE ORDER ROUTING ENABLED ***")

    def _guard(self, confirm: bool | None):
        if confirm is not True:
            raise RuntimeError("Live orders require confirm=True explicitly.")

    def place_order(self, symbol: str, side: str, qty: int,
                    price: float | None = None, product: str = "MIS",
                    tag: str | None = None, *, confirm: bool = False) -> dict:
        self._guard(confirm)
        params = {
            "tradingsymbol": symbol.upper(), "exchange": "NSE",
            "transaction_type": side.upper(), "quantity": qty,
            "product": product, "order_type": "LIMIT" if price else "MARKET",
            "validity": "DAY",
        }
        if price:
            params["price"] = round(price, 1)
        if tag:
            params["tag"] = tag[:20]
        oid = self.kite.place_order(**params)
        logger.warning("LIVE %s %s x%d -> order %s", side, symbol, qty, oid)
        return {"status": "PLACED", "order_id": oid, **params}

    def positions(self) -> dict:
        return self.kite.positions()

    def cancel_all_pending(self, *, confirm: bool = False):
        self._guard(confirm)
        for o in self.kite.orders():
            if o["status"] in ("OPEN", "TRIGGER PENDING"):
                try:
                    self.kite.cancel_order(o["order_id"])
                except Exception as e:
                    logger.error("cancel failed %s: %s", o["order_id"], e)
