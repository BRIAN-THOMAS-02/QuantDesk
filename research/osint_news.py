"""Social & news OSINT fetchers (no API keys required).

- Google News RSS  : headlines per query (reliable, unauthenticated)
- Reddit public JSON: mention counts + top posts (rate-limited, may 403)
- Instagram/X      : NO public unauthenticated API -> documented limitation,
  the architecture leaves a SocialSource plug-in point for when the user
  supplies credentials (praw / official APIs).

All responses degrade gracefully to empty results with a status note.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from utils.helpers import logger

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantDesk-Research/1.0"}
TIMEOUT = 12


def _clean(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


# ------------------------------------------------------------------ #
def google_news(query: str, limit: int = 10) -> dict:
    url = ("https://news.google.com/rss/search?"
           f"q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en")
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            if len(items) >= limit:
                break
            items.append({
                "title": _clean(item.findtext("title") or ""),
                "source": _clean(item.findtext("source") or ""),
                "published": item.findtext("pubDate") or "",
                "link": (item.findtext("link") or "").strip(),
            })
        return {"source": "google_news_rss", "query": query,
                "status": "ok", "items": items}
    except (requests.RequestException, ET.ParseError) as e:
        logger.debug("google_news failed for %s: %s", query, e)
        return {"source": "google_news_rss", "query": query,
                "status": f"unavailable ({e.__class__.__name__})", "items": []}


def reddit_buzz(query: str, limit: int = 8) -> dict:
    """Public search endpoint; respects Reddit rate limits via short timeout."""
    url = "https://www.reddit.com/search.json"
    params = {"q": query, "sort": "top", "t": "month", "limit": limit}
    try:
        r = requests.get(url, headers=UA, params=params, timeout=TIMEOUT)
        if r.status_code == 403:
            raise PermissionError("reddit blocked this client")
        r.raise_for_status()
        posts = []
        for child in r.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            posts.append({
                "title": d.get("title"),
                "subreddit": d.get("subreddit"),
                "score": d.get("score"),
                "comments": d.get("num_comments"),
                "created_utc": datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc).isoformat(timespec="seconds"),
                "permalink": "https://reddit.com" + (d.get("permalink") or ""),
            })
        total_score = sum(p["score"] or 0 for p in posts)
        return {"source": "reddit_public_json", "query": query, "status": "ok",
                "mentions_30d_sample": len(posts), "total_upvotes": total_score,
                "posts": posts}
    except (requests.RequestException, ValueError, PermissionError) as e:
        logger.debug("reddit failed for %s: %s", query, e)
        return {"source": "reddit_public_json", "query": query,
                "status": f"unavailable ({e.__class__.__name__})",
                "mentions_30d_sample": 0, "posts": []}


# ------------------------------------------------------------------ #
class SocialSource:
    """Plug-in point for authenticated social feeds (praw / IG graph API).
    Subclass and register in SOURCES to activate once credentials exist."""
    name = "base"

    def fetch(self, query: str) -> dict:      # pragma: no cover
        raise NotImplementedError


SOURCES = {"google_news": google_news, "reddit": reddit_buzz}


def buzz(symbol: str, extra_queries: list[str] | None = None) -> dict:
    """Aggregate social/news buzz for one instrument."""
    queries = [f"{symbol} stock India", *(extra_queries or [])]
    out = {"symbol": symbol.upper(), "fetched_at":
           datetime.now(timezone.utc).isoformat(timespec="seconds"), "feeds": {}}
    news = google_news(queries[0])
    out["feeds"]["news"] = news
    out["feeds"]["reddit"] = reddit_buzz(f"{symbol} shares OR stock")
    out["buzz_score"] = min(100, news["items"].__len__() * 12
                            + out["feeds"]["reddit"]["mentions_30d_sample"] * 4)
    out["note"] = ("Instagram/X excluded: no public unauthenticated API - "
                   "add credentials via research.osint_news.SOURCES to activate.")
    return out
