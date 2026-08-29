"""Social & news OSINT — multi-source, no API keys required.

Design: a resilience-first source registry.  Each source is a no-API endpoint
(Google News search RSS, reputable finance RSS feeds, Reddit public JSON) that
is probed for reachability and probed again whenever buzz is requested.  A
source that is blocked in the current network simply reports its status honestly
and is skipped — it never fakes data.  This replaces the old "Instagram excluded"
limitation: blocked feeds are visible as unreachable, not hidden.

Sentiment is a transparent local heuristic (headline keywords + source
authority + recency).  No model, no API.
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from utils.helpers import logger

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0 Safari/537.36"),
       "Accept": "application/rss+xml, application/xml, text/xml, */*"}
TIMEOUT = 10


# ------------------------------------------------------------------ #
# low-level fetchers
# ------------------------------------------------------------------ #
def _clean(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _parse_rss(xml_bytes: bytes, limit: int = 12) -> list:
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        if len(items) >= limit:
            break
        items.append({
            "title": _clean(it.findtext("title") or ""),
            "source": _clean(it.findtext("source") or "feed"),
            "published": _clean(it.findtext("pubDate") or ""),
            "link": (it.findtext("link") or "").strip(),
        })
    return items


def _google_news(query: str, limit: int = 12) -> list:
    q = urllib.parse.quote(query)
    url = (f"https://news.google.com/rss/search?q={q}"
            "&hl=en-IN&gl=IN&ceid=IN:en")
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    items = _parse_rss(r.content, limit)
    for it in items:
        it["source"] = "Google News"
    return items


def _feed_rss(url: str, limit: int = 12) -> list:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return _parse_rss(r.content, limit)


def _reddit_public(sub: str, query: str, limit: int = 8) -> list:
    """Probe the few Reddit entry points that might still return JSON.  Most
    paths 403 in many networks, so this is best-effort and reports its failure
    honestly rather than faking mentions."""
    q = urllib.parse.quote(query)
    candidates = [
        f"https://www.reddit.com/search.json?q={q}&sort=top&t=month&limit={limit}",
        f"https://old.reddit.com/r/{sub}/top.json?t=week&limit={limit}",
        f"https://www.reddit.com/r/{sub}/search.json?q={q}&sort=top&t=week&limit={limit}",
    ]
    last_err = "no endpoint reachable"
    for url in candidates:
        h = dict(UA)
        h["Accept"] = "application/json"
        try:
            r = requests.get(url, headers=h, timeout=TIMEOUT)
            if r.status_code != 200 or not r.text.strip().startswith("{"):
                last_err = f"HTTP {r.status_code}"
                continue
            data = r.json()
            posts = []
            for ch in data.get("data", {}).get("children", []):
                d = ch.get("data", {})
                if not d.get("title"):
                    continue
                posts.append({
                    "title": d.get("title"),
                    "source": f"r/{d.get('subreddit', sub)}",
                    "subreddit": d.get("subreddit", sub),
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "published": datetime.fromtimestamp(
                        d.get("created_utc", 0), tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                    "link": "https://www.reddit.com"
                            + (d.get("permalink") or d.get("url") or ""),
                })
            if posts:
                return posts
        except (requests.RequestException, ValueError, PermissionError) as e:
            last_err = e.__class__.__name__
            continue
    raise RuntimeError(f"reddit blocked ({last_err})")


# ------------------------------------------------------------------ #
# source registry
# ------------------------------------------------------------------ #
FEED_URLS = {
    "livemint": ("Livemint Markets", "https://www.livemint.com/rss/market"),
    "bloomberg": ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    "etmarkets": ("Economic Times",
                  "https://feeds.feedburner.com/EconomicTimesMarkets"),
    "hbl": ("Hindu BusinessLine",
            "https://www.thehindubusinessline.com/thehindubusinessline/rss10feeds/markets.xml"),
}


def _build_sources() -> dict:
    sources = {
        "google_news": {
            "label": "Google News (India)",
            "kind": "news_rss",
            "fetch": _google_news,
            "authoritative": True,
        },
    }
    for key, (label, url) in FEED_URLS.items():
        def _mk(u=url):
            def fetch(_q: str, limit: int = 12) -> list:
                return _feed_rss(u, limit)
            return fetch
        sources[key] = {
            "label": label, "kind": "feed_rss", "url": url,
            "authoritative": False, "fetch": _mk(url),
        }

    def reddit_fetch(query: str, limit: int = 8) -> list:
        q = query.split()[0]
        last = RuntimeError("no sub tried")
        for sub in ("IndianStockMarket", "IndiaInvestments", "StockMarket"):
            try:
                return _reddit_public(sub, q, limit)
            except RuntimeError as e:
                last = e
                continue
        raise last

    sources["reddit"] = {
        "label": "Reddit (India subs)", "kind": "reddit",
        "authoritative": False, "fetch": reddit_fetch,
    }
    return sources


SOURCES = {k: v["fetch"] for k, v in _build_sources().items()}


class SocialSource:
    """Plug-in point for authenticated social feeds (praw / IG graph API).
    Subclass and register in SOURCES-like dict to activate when credentials
    exist."""
    name = "base"

    def fetch(self, query: str, limit: int = 8) -> list:       # pragma: no cover
        raise NotImplementedError


# ------------------------------------------------------------------ #
# heuristic sentiment + scoring
# ------------------------------------------------------------------ #
_POS = re.compile(r"\b(rally|surge|gains?|record high|outperform|upbeat|bullish|"
                  r"strong|beat|upgrade|optimis?tic|recovery|growth|profit|win|"
                  r"soars?|climbs?|bounces?|rises?|highs?)\b", re.I)
_NEG = re.compile(r"\b(crash|plunge|drop|fall|lose?|losses?|sell[io]|bearish|weak|"
                  r"warn|debt|fraud|probe|inquiry|investigat|down|decline|slump|"
                  r"downturn|recessi|suspend|delisted|default|fear|tumble|slips?|"
                  r"cut|downgrade|reduces?|worst|record low)\b", re.I)


def _sentiment(text: str) -> int:
    p = len(_POS.findall(text or ""))
    n = len(_NEG.findall(text or ""))
    return 1 if p > n else (-1 if n > p else 0)


def _authority(source: str, authoritative: bool) -> float:
    if authoritative:
        return 1.0
    s = (source or "").lower()
    if s in ("bloomberg", "livemint markets", "reuters", "economic times"):
        return 0.8
    return 0.5


def _recency_weight(published: str) -> float:
    try:
        dt = parsedate_to_datetime(published) if published else None
        if not dt:
            return 0.5
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        days = max(0.0, age / 86400.0)
        return round(max(0.1, 1.0 - days / 14.0), 2)       # fades over 2 weeks
    except Exception:
        return 0.5


def _score_item(item: dict, authoritative: bool) -> float:
    s = _sentiment(item.get("title", ""))
    auth = _authority(item.get("source", ""), authoritative)
    rec = _recency_weight(item.get("published", ""))
    base = 1.0 + (0.5 if s > 0 else 0.0) + (0.3 if s < 0 else 0.0)
    return round(base * auth * rec, 3)


# alias map: ticker -> the names that might appear in a headline
_ALIASES = {
    "RELIANCE": ["reliance", "ril"],
    "INFY": ["infosys", "infy"],
    "HDFCBANK": ["hdfc bank", "hdfcbank"],
    "SBIN": ["state bank of india"],
    "TATAMOTORS": ["tata motors", "tvm"],
    "MARUTI": ["maruti"],
    "ICICIBANK": ["icici bank", "icicibank"],
    "TCS": ["tata consult", "tcs"],
    "WIPRO": ["wipro"],
    "BHARTIARTL": ["bharti", "airtel"],
    "NIFTY": ["nifty"],
    "SENSEX": ["sensex"],
    "INDIAVIX": ["india vix", "nifty vix"],
}


def _relevant(symbol: str, item: dict) -> bool:
    """Does this headline actually mention the instrument (or its aliases)?"""
    text = " ".join(filter(None, [item.get("title"), item.get("link")]))
    sym = symbol.upper()
    names = [sym.lower()] + _ALIASES.get(sym, [])
    return any(n in text.lower() for n in names)


# ------------------------------------------------------------------ #
# buzz aggregate
# ------------------------------------------------------------------ #
def buzz(symbol: str, extra_queries: list | None = None,
         limit_per_source: int = 12) -> dict:
    """Aggregate cross-source social/news buzz for one instrument.

    Sources are probed live; blocked ones are reported as unreachable (never
    hidden, never faked).  The buzz score combines cross-source mention
    breadth, sentiment tilt and source authority.
    """
    query = f"{symbol} stock India shares"
    symsrc = _build_sources()

    feeds = {}
    reach = []                   # per-source status
    all_items = []
    sentiment_tally = {1: 0, 0: 0, -1: 0}
    relevant = []                # items that actually mention the symbol

    for key, cfg in symsrc.items():
        label = cfg["label"]
        try:
            items = cfg["fetch"](query, limit_per_source) or []
            for it in items:
                if key in ("livemint", "bloomberg", "etmarkets", "hbl"):
                    it["source"] = label
                it["kind"] = key
                it["authority"] = _authority(
                    cfg["label"], cfg.get("authoritative", False))
                it["score"] = it.get("score", 0) or 0
                it["weight"] = _score_item(it, cfg.get("authoritative", False))
                s = _sentiment(it.get("title", ""))
                sentiment_tally[s] = sentiment_tally.get(s, 0) + 1
                it["relevant"] = _relevant(symbol, it)
                all_items.append(it)
                if it["relevant"]:
                    relevant.append(it)
            feeds[key] = {"source": label, "status": "ok", "items": items}
            reach.append({"name": label, "ok": True,
                          "items": len(items), "status": "ok"})
        except Exception as e:
            feeds[key] = {"source": label,
                          "status": f"unreachable ({e.__class__.__name__})",
                          "items": []}
            reach.append({"name": label, "ok": False, "items": 0,
                          "status": f"unreachable ({e.__class__.__name__})"})
            logger.debug("buzz source %s failed for %s: %s", key, symbol, e)

    mentions = len(all_items)
    relevant_items = len(relevant)
    unique_sources = len({it.get("source") or it.get("kind") for it in all_items})
    positive = sentiment_tally.get(1, 0)
    negative = sentiment_tally.get(-1, 0)
    neutral = sentiment_tally.get(0, 0)
    tilt = round((positive - negative) / max(1, mentions) * 100) if mentions else 0

    buzz_score = int(min(100, relevant_items * 6 + unique_sources * 5
                         + max(0, tilt) * 0.5))
    reachable = sum(1 for r in reach if r["ok"])

    # curated list: relevant items first, then top-weighted as fallback
    ordered = sorted(all_items,
                     key=lambda x: (x.get("relevant", False),
                                    x.get("weight", 0)), reverse=True)[:10]

    return {
        "symbol": symbol.upper(),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feed_reachability": reach,
        "sources_reachable": reachable,
        "sources_total": len(symsrc),
        "buzz_score": buzz_score,
        "mentions": mentions,
        "relevant_mentions": relevant_items,
        "unique_sources": unique_sources,
        "sentiment": {"positive": positive, "neutral": neutral,
                      "negative": negative, "tilt_pct": tilt},
        "feeds": feeds,
        "top_items": ordered,
        "note": (f"Multi-source scan — {reachable}/{len(symsrc)} sources live; "
                 f"{relevant_items} of {mentions} mentions reference "
                 f"{symbol.upper()} directly. Unreachable feeds are shown, "
                 f"not hidden."),
    }
