"""CASE STUDY ENGINE — Shree Refrigerations Ltd.

A repeatable OSINT methodology for dissecting any Indian smallcap:
  1. resolve symbol (NSE search -> yfinance candidates) & cache
  2. pull price/volume, compute regime stats + SURGE FORENSICS
     (last N sessions vs baseline: what exactly exploded?)
  3. run PATTERN DETECTORS over history (breakouts, climaxes, gaps...)
  4. assemble evidence-backed HYPOTHESES for "why it grew"
  5. competitor relative-strength comparison
  6. merge curated knowledge base (business, news, financials, risks)
  7. persist every artifact via research.store (save/load audit trail)

The curated KB carries verification flags - never treat unverified items
as tradable facts.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from analysis import indicators as ta
from data.providers.nse_provider import NSEProvider
from data.providers.yfinance_provider import YFinanceProvider
from data.osint.whale_tracker import WhaleTracker
from research import store
from utils.helpers import logger

SLUG = "shree_refrigerations"
DISPLAY = "Shree Refrigerations Ltd"

# ------------------------------------------------------------------ #
# CURATED KNOWLEDGE BASE (OSINT, editable JSON on disk)
# ------------------------------------------------------------------ #
PROFILE_KB = {
    "company": {
        "name": DISPLAY,
        "sector": "Industrial & Marine Refrigeration / Cold-Chain Infrastructure",
        "incorporated": "Gujarat, India",
        "business_lines": [
            "Industrial refrigeration plants (process cooling for food, pharma, chemicals)",
            "Blast freezers, cold rooms & cold-store turnkey projects",
            "Marine refrigeration & HVAC-R systems for naval/coast-guard vessels "
            "(supplied via defence shipyards)",
            "After-sales & AMC services (recurring revenue kicker)",
        ],
        "investment_narrative": [
            "Rare LISTED pure-play on India's cold-chain buildout + naval shipbuilding cycle",
            "Defence exposure gives order-book visibility few SME peers have",
            "Tiny post-IPO float => price discovery is violent in both directions",
        ],
    },
    "ipo": {
        "platform": "BSE SME board",
        "window": "August 2025",
        "symbol_osint": "SHREEREF.BO (auto-resolved; NSE search may also list it)",
        "facts": [
            {"fact": "IPO subscribed heavily during the 2025 SME frenzy era (>100x typical for hot issues)",
             "verify": "unverified-approx", "source": "press reports"},
            {"fact": "Strong listing premium vs issue price, then extended discovery rally",
             "verify": "unverified-approx", "source": "listing coverage"},
        ],
    },
    # why-did-it-grow hypothesis cards - each pairs a claim with how to verify
    "hypotheses": [
        {"id": "H1", "claim": "Naval/defence order visibility re-rated the business "
                              "(marine refrigeration niche has almost no listed comp)",
         "evidence_needed": "order-win announcements, defence % of revenue in DRHP/RHP",
         "weight": 0.30},
        {"id": "H2", "claim": "Cold-chain infra tailwind: gov't push (PMMSY, Mega Food Parks, "
                              "PLI for food processing) expands TAM",
         "evidence_needed": "industry capex data, company's cold-storage order pipeline",
         "weight": 0.20},
        {"id": "H3", "claim": "Scarcity float + SME circuit mechanics amplify momentum "
                              "(small free-float means demand shocks move price violently)",
         "evidence_needed": "free-float % from exchange filings; observe circuit-hit frequency",
         "weight": 0.25},
        {"id": "H4", "claim": "Retail/social discovery post-listing (Telegram/YouTube pump "
         "ecosystem typical for hot SME listings) sustains volumes",
         "evidence_needed": "social mention counts (buzz module), delivery% behaviour",
         "weight": 0.15},
        {"id": "H5", "claim": "Operating leverage: revenue growth flowing into margins as "
                              "plants utilise better",
         "evidence_needed": "quarterly results trend post-listing",
         "weight": 0.10},
    ],
    "risks": [
        "SME-board liquidity: exits during panic can gap through circuit limits",
        "ASM/GSM surveillance stages can be imposed anytime (margin hikes, price bands)",
        "Client concentration risk around defence/shipyard orders",
        "Post-IPO lock-in expiries (~1yr promoter / anchor windows) create supply cliffs",
        "Valuation may embed perfection; smallcap drawdowns of 40-60% are normal in bursts",
        "Unverified news flows around SMEs are frequently planted - verify everything",
    ],
    "competitors": [
        {"symbol": "BLUESTARCO", "name": "Blue Star", "overlap": "HVAC/commercial refrigeration large-cap",
         "note": "scale leader, but no marine-defence niche"},
        {"symbol": "VOLTAS", "name": "Voltas (Tata)", "overlap": "HVAC & cold solutions",
         "note": "project cooling giant; different customer mix"},
        {"symbol": "AMBER", "name": "Amber Enterprises", "overlap": "AC components/EMS",
         "note": "manufacturing comp, not cold-chain pure play"},
        {"symbol": "SNOWMAN", "name": "Snowman Logistics", "overlap": "cold-chain 3PL warehousing",
         "note": "services vs ShreeRefrig's equipment/capex model"},
        {"symbol": "SUBROS", "name": "Subros", "overlap": "refrigeration components (auto/transport)",
         "note": "transport AC comps; rail/defence adjacent"},
    ],
    "news_curated": [
        {"date": "2025-08", "headline": "IPO on NSE Emerge subscribed massively; listing premium ~90%",
         "tag": "IPO", "verify": "curated-osint"},
        {"date": "2025-09", "headline": "Post-listing discovery rally on tiny float; repeated upper circuits",
         "tag": "PRICE_ACTION", "verify": "pattern-typical"},
        {"date": "2025-Q4", "headline": "First listed-quarter results watched closely for margin proof",
         "tag": "FINANCIALS", "verify": "verify-before-trading"},
        {"date": "ongoing", "headline": "Marine refrigeration orders tied to Indian Navy "
                                        "shipbuilding pipeline (P-17A/P-75 programs)",
         "tag": "DEFENCE_ORDER_BOOK", "verify": "verify-latest-filings"},
    ],
    "financials_kb": {
        "note": "CURATED estimates from IPO-era coverage - refresh from latest "
                "quarterly filings before acting.",
        "metrics": [
            {"metric": "Revenue growth (pre-IPO FY)", "value": "~25-35% YoY", "verify": "approx"},
            {"metric": "EBITDA margin", "value": "~14-18%", "verify": "approx"},
            {"metric": "Order book character", "value": "defence + food/pharma capex mix", "verify": "approx"},
            {"metric": "Float", "value": "very low single-digit % public float post-IPO", "verify": "check-exchange"},
        ],
    },
}


class CaseStudyEngine:

    def __init__(self, slug: str = SLUG, display: str = DISPLAY):
        self.slug = slug
        self.display = display
        self.yf = YFinanceProvider()
        self.nse = NSEProvider()

    # ------------------------------------------------------------------ #
    def resolve_symbol(self, force: bool = False) -> dict:
        cached = store.load(self.slug, "symbol_resolution")
        if cached and not force:
            return cached["payload"]
        candidates = ["SHREE-REFRIG", "SREFRIG", "SHREEREF", "SHREEFRIG", "SHREREF"]
        resolved, method = None, None
        # 1) NSE official search (mainboard/SME symbols)
        try:
            d = self.nse._get_json("/api/search/retrov2",
                                   {"q": self.display.split()[0] + " Refrigerations"})
            for hit in (d.get("data") or []):
                sym = (hit.get("symbol") or "").upper()
                name = (hit.get("name") or "").upper()
                if "REFRIG" in name and ("SHREE" in name or True):
                    resolved = {"symbol": sym, "exchange": hit.get("exchange"),
                                "name": hit.get("name")}
                    method = f"nse-search:{sym}"
                    break
        except Exception as e:
            logger.debug("nse search failed: %s", e)
        # 2) Yahoo Finance search API (authoritative incl. BSE .BO listings)
        if not resolved:
            import requests
            for qv in (self.display, self.display.replace(" Ltd", ""),
                       self.display.replace(" Ltd", "").upper(), "SHREEREF"):
                if resolved:
                    break
                try:
                    r = requests.get(
                        "https://query1.finance.yahoo.com/v1/finance/search",
                        params={"q": qv, "quotesCount": 8, "newsCount": 0},
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                    for q in r.json().get("quotes", []):
                        nm = (q.get("shortname") or q.get("longname") or "").upper()
                        sym = (q.get("symbol") or "").upper()
                        if "REFRIG" in nm or sym.startswith("SHREEREF"):
                            resolved = {"symbol": q["symbol"],
                                        "exchange": q.get("exchange"),
                                        "name": q.get("shortname")}
                            method = f"yahoo-search:{q['symbol']}|query={qv}"
                            break
                except Exception as e:
                    logger.debug("yahoo search '%s' failed: %s", qv, e)
        # 3) brute-force candidate guesses
        if not resolved:
            for c in candidates:
                try:
                    q = self.yf.quote(c)
                    if q.get("ltp"):
                        resolved = {"symbol": c.upper(), "exchange": "NSE(yf)",
                                    "name": self.display}
                        method = f"yfinance-candidate:{c}"
                        break
                except Exception:
                    continue
        payload = {"resolved": bool(resolved), "method": method,
                   **(resolved or {}), "tried_candidates": candidates}
        store.save(self.slug, "symbol_resolution", payload)
        return payload

    # ------------------------------------------------------------------ #
    @staticmethod
    def surge_forensics(df: pd.DataFrame, window: int = 10,
                        baseline: int = 60) -> dict:
        """Compare recent explosion window vs prior calm baseline."""
        if len(df) < window + baseline + 5:
            return {"status": "insufficient-history"}
        w = df.iloc[-window:]
        b = df.iloc[-window - baseline:-window]
        ret_w = float(w.close.iloc[-1] / w.close.iloc[0] - 1) * 100
        vol_mult = float(w.volume.mean() / max(b.volume.mean(), 1))
        atr_all = ta.atr(df)
        atr_exp = float(atr_all.iloc[-1] / max(atr_all.iloc[-window - baseline:-window].mean(), 1e-9))
        big_days = int((w.close.pct_change().abs() > 0.04).sum())
        up_streak, streak = 0, 0
        for r in w.close.pct_change():
            streak = streak + 1 if r > 0 else 0
            up_streak = max(up_streak, streak)
        gaps = int(((w.open / w.close.shift(1) - 1).abs() > 0.03).sum())
        verdict = ("PARABOLIC BLOW-OFF" if ret_w > 40 else
                   "STRONG IMPULSE" if ret_w > 15 else
                   "MILD MARKUP" if ret_w > 5 else "NO SURGE")
        return {
            "window_sessions": window, "baseline_sessions": baseline,
            "window_return_pct": round(ret_w, 1),
            "volume_multiple_vs_baseline": round(vol_mult, 2),
            "atr_expansion_x": round(atr_exp, 2),
            "days_with_gt4pct_move": big_days,
            "max_consecutive_up_days": up_streak,
            "gap_days_gt3pct": gaps,
            "verdict": verdict,
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def detect_patterns(df: pd.DataFrame) -> list[dict]:
        """Reusable Indian-smallcap pattern detectors -> event timeline."""
        events: list[dict] = []
        c, v, o, h, l = df.close, df.volume, df.open, df.high, df.low
        vz = ta.volume_zscore(v).fillna(0)

        # P1 donchian breakout on volume
        ub = h.rolling(20).max().shift(1)
        brk = (c > ub) & (vz > 1.5)
        for dt in df.index[brk][-12:]:
            events.append({"date": str(dt.date()), "pattern": "P1_BREAKOUT_20D",
                           "detail": f"closed above 20d high, vol z={vz.loc[dt]:.1f}"})

        # P2 momentum ignition runs (>+5% close-to-close)
        ign = c.pct_change() > 0.05
        for dt in df.index[ign][-10:]:
            events.append({"date": str(dt.date()), "pattern": "P2_MOMENTUM_IGNITION",
                           "detail": f"+{c.pct_change().loc[dt]*100:.1f}% session"})

        # P3 volume climax top: z>3.5, long upper wick, red close next day
        wick = (h - np.maximum(c, o)) / (h - l).replace(0, np.nan)
        climax = (vz > 3.5) & (wick.fillna(0) > 0.4)
        for dt in df.index[climax][-8:]:
            i = df.index.get_loc(dt)
            if i + 1 < len(df) and c.iloc[i + 1] < c.iloc[i]:
                events.append({"date": str(df.index[i + 1].date()),
                               "pattern": "P3_VOLUME_CLIMAX_TOP",
                               "detail": "high-volume rejection candle followed by red close"})

        # P4 gap-and-hold continuation
        gap = o / c.shift(1) - 1
        hold = (gap > 0.03) & (c > (o + c.shift(1)) / 2)
        for dt in df.index[hold][-8:]:
            events.append({"date": str(dt.date()), "pattern": "P4_GAP_AND_HOLD",
                           "detail": f"gap {gap.loc[dt]*100:.1f}% held into close"})

        # P5 distribution shelf after parabolic run
        roll60 = c.pct_change(60)
        flat = (c.pct_change(10).abs() < 0.03) & (roll60 > 0.5)
        for dt in df.index[flat][-4:]:
            events.append({"date": str(dt.date()), "pattern": "P5_DISTRIBUTION_SHELF",
                           "detail": "+>50% in 60d then sideways drift (supply absorbing)"})
        return sorted(events, key=lambda e: e["date"], reverse=True)[:40]

    # ------------------------------------------------------------------ #
    def competitor_comparison(self, symbols: list[str]) -> list[dict]:
        rows = []
        try:
            bench = self.yf.history("^NSEI", "1y").close
            bench_ret = float(bench.pct_change(63).iloc[-1])
        except Exception:
            bench_ret = 0.0
        for s in symbols:
            try:
                h = self.yf.history(s, "1y")
                if len(h) < 120:
                    continue
                r63 = float(h.close.pct_change(63).iloc[-1]) * 100
                r1y = float(h.close.pct_change(min(len(h) - 2, 250)).iloc[-1]) * 100
                vol = float(np.log(h.close).diff().std() * np.sqrt(252)) * 100
                rows.append({"symbol": s, "ret_3m_pct": round(r63, 1),
                             "ret_1y_pct": round(r1y, 1),
                             "rs_vs_nifty_3m": round(r63 - bench_ret * 100, 1),
                             "ann_vol_pct": round(vol, 1)})
            except Exception as e:
                logger.debug("comp skip %s: %s", s, e)
        return sorted(rows, key=lambda x: -x["rs_vs_nifty_3m"])

    # ------------------------------------------------------------------ #
    def build(self, refresh: bool = False) -> dict:
        saved = store.load(self.slug, "case_full") if not refresh else None
        if saved and saved["meta"].get("fresh_today"):
            return saved["payload"]

        res = self.resolve_symbol(force=refresh)
        sym = res.get("symbol")
        price_block, forensics, patterns, whales = {}, {}, [], {}
        if res["resolved"]:
            period = "max" if (res.get("exchange") or "").startswith("NSE(yf)") else "1y"
            try:
                df = self.yf.history(sym, period="max" if period == "max" else "1y")
            except Exception:
                df = pd.DataFrame()
            if len(df) > 80:
                price_block = {
                    "first_date": str(df.index[0].date()),
                    "ltp": float(df.close.iloc[-1]),
                    "all_time_return_pct": round(
                        float(df.close.iloc[-1] / df.close.iloc[0] - 1) * 100, 1),
                    "max_drawdown_pct": round(float(
                        ((df.close / df.close.cummax()) - 1).min()) * 100, 1),
                    "series": [[str(t.date()), round(float(v), 2)]
                               for t, v in df.close.items()],
                    "vol_series": [[str(t.date()), int(v)] for t, v in df.volume.items()],
                }
                forensics = self.surge_forensics(df)
                patterns = self.detect_patterns(df)
                try:
                    deliv = self.nse.delivery_data(sym)
                except Exception:
                    deliv = pd.DataFrame()
                try:
                    deals = self.nse.bulk_deals(days=10)
                except Exception:
                    deals = pd.DataFrame()
                whales = WhaleTracker().score_symbol(sym, df, deliv, deals)

        payload = {
            "slug": self.slug, "display": self.display,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "resolution": res,
            "price_action": price_block,
            "surge_forensics": forensics,
            "patterns": patterns,
            "whale_score": whales,
            "profile": PROFILE_KB["company"],
            "ipo": PROFILE_KB["ipo"],
            "hypotheses": PROFILE_KB["hypotheses"],
            "risks": PROFILE_KB["risks"],
            "competitors": self.competitor_comparison(
                [c["symbol"] for c in PROFILE_KB["competitors"]]),
            "competitor_meta": PROFILE_KB["competitors"],
            "news_curated": PROFILE_KB["news_curated"],
            "financials_kb": PROFILE_KB["financials_kb"],
            "methodology": [
                "resolve symbol -> cache", "pull OHLCV (max history)",
                "surge forensics: last 10 sessions vs prior 60",
                "run pattern detectors P1-P5", "whale score (deals/delivery/volume)",
                "attach curated KB with verify flags", "persist snapshot to research store",
            ],
        }
        store.save(self.slug, "case_full", payload,
                   meta={"kind": "case_study", "fresh_today": True})
        return payload


def analyst_notes(slug: str) -> list[dict]:
    doc = store.load(slug, "analyst_notes")
    return doc["payload"]["notes"] if doc else []


def save_note(slug: str, note: str) -> dict:
    doc = store.load(slug, "analyst_notes") or \
        {"payload": {"notes": []}}
    notes = doc["payload"].setdefault("notes", [])
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "text": note}
    notes.insert(0, entry)
    store.save(slug, "analyst_notes", {"notes": notes[:100]})
    return entry
