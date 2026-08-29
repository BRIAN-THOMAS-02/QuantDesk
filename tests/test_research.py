"""Tests for research layer: store, expiry calendar, case engine, radar math."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestStore:
    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        from research import store
        monkeypatch.setattr(store, "ROOT", tmp_path / "store")
        store.save("testns", "artifact1", {"a": 1}, meta={"k": "v"})
        doc = store.load("testns", "artifact1")
        assert doc["payload"] == {"a": 1} and doc["meta"]["k"] == "v"
        arts = store.list_artifacts("testns")
        assert len(arts) == 1 and arts[0]["key"] == "artifact1"

    def test_latest_snapshot(self, tmp_path, monkeypatch):
        from research import store
        monkeypatch.setattr(store, "ROOT", tmp_path / "store")
        assert store.latest_snapshot("empty") is None
        store.save("ns2", "x", {"v": 1})
        snap = store.latest_snapshot("ns2")
        assert snap["payload"]["v"] == 1


class TestExpiries:
    def test_weekly_nifty_tuesdays(self):
        from research.expiries import next_expiries
        t = date(2026, 8, 26)          # a Wednesday
        exps = next_expiries("NIFTY", n=3, today=t)
        assert all(e.date.startswith("20") for e in exps)
        d0 = date.fromisoformat(exps[0].date)
        assert d0.weekday() == 1 and d0 > t            # Tuesday strictly after

    def test_monthly_stock_options(self):
        from research.expiries import next_expiries
        exps = next_expiries("TATAMOTORS_STOCK", n=2, today=date(2026, 8, 26))
        assert exps[0].kind == "monthly"
        assert date.fromisoformat(exps[0].date).weekday() == 1   # last Tue of Aug

    def test_commodity_and_currency(self):
        from research.expiries import next_expiries
        g = next_expiries("GOLD", n=2, today=date(2026, 8, 26))
        assert g[0].kind == "commodity" and g[0].date.endswith("-19")
        c = next_expiries("USDINR", n=1, today=date(2026, 8, 26))
        d = date.fromisoformat(c[0].date)
        assert d.weekday() < 5 and d.month >= 8

    def test_unknown_symbol_falls_back_to_monthly(self):
        from research.expiries import next_expiries
        e = next_expiries("RANDOMSTOCK", n=1, today=date(2026, 8, 26))
        assert e[0].kind == "monthly"

    def test_radar_registry_complete(self):
        from research.expiries import RADAR_INSTRUMENTS
        assert {"NIFTY", "BANKNIFTY", "GOLD", "USDINR"} <= set(RADAR_INSTRUMENTS)


class TestCaseEngineMath:
    def _df(self, explosive_last10=True):
        rng = np.random.default_rng(77)
        n = 300
        drift = np.full(n, 0.0004)
        if explosive_last10:
            drift[-10:] = 0.05                      # parabolic window
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.01))),
                          index=pd.bdate_range("2024-01-01", periods=n))
        vol = pd.Series(rng.integers(100_000, 200_000, n), index=close.index)
        vol.iloc[-10:] *= 6                          # volume explosion too
        return pd.DataFrame({
            "open": close.shift(1) * 1.001, "high": close * 1.02,
            "low": close * 0.98, "close": close, "volume": vol}).dropna()

    def test_surge_forensics_flags_parabolic(self):
        from research.case_shree_refrigerations import CaseStudyEngine as C
        f = C.surge_forensics(self._df(True))
        assert f["verdict"] in ("PARABOLIC BLOW-OFF", "STRONG IMPULSE")
        assert f["volume_multiple_vs_baseline"] > 3
        calm = C.surge_forensics(self._df(False))
        assert calm["window_return_pct"] < 15

    def test_pattern_detectors_run(self):
        from research.case_shree_refrigerations import CaseStudyEngine as C
        events = C.detect_patterns(self._df(True))
        kinds = {e["pattern"] for e in events}
        assert any(k.startswith("P2") for k in kinds) or any(k.startswith("P1") for k in kinds)

    def test_kb_integrity(self):
        from research.case_shree_refrigerations import PROFILE_KB
        assert PROFILE_KB["hypotheses"], "need hypotheses"
        for h in PROFILE_KB["hypotheses"]:
            assert 0 < h["weight"] <= 1 and h["claim"]
        syms = [c["symbol"] for c in PROFILE_KB["competitors"]]
        assert len(syms) >= 4


class TestSocialOSINT:
    def test_buzz_degrades_gracefully(self, monkeypatch):
        import research.osint_news as os
        # every source in the registry fails -> buzz must still return a shape
        def boom(_q, limit=12):
            raise RuntimeError("blocked")
        monkeypatch.setattr(os, "_build_sources", lambda: {
             "google_news": {"label": "G", "fetch": boom, "authoritative": True},
             "reddit": {"label": "R", "fetch": boom, "authoritative": False},
         })
        b = os.buzz("TESTSYM")
        assert b["symbol"] == "TESTSYM" and "buzz_score" in b
        assert b["mentions"] == 0 and b["sources_reachable"] == 0
        assert b["top_items"] == []
        for r in b["feed_reachability"]:
            assert r["ok"] is False
