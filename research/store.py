"""Research artifact store: create / generate / save / load / list JSON dossiers.

Everything the case-study & radar engines produce is persisted here so the
frontend always has a browsable audit trail of what was known and when.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import settings

ROOT = settings.PROJECT_ROOT / "research" / "store"
ROOT.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())


def save(namespace: str, key: str, payload: dict,
         meta: dict | None = None) -> Path:
    ns = ROOT / _slug(namespace)
    ns.mkdir(parents=True, exist_ok=True)
    doc = {
        "namespace": _slug(namespace),
        "key": _slug(key),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "meta": meta or {},
        "payload": payload,
    }
    path = ns / f"{_slug(key)}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load(namespace: str, key: str) -> dict | None:
    path = ROOT / _slug(namespace) / f"{_slug(key)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_snapshot(namespace: str) -> dict | None:
    """Most recently saved artifact in a namespace."""
    ns = ROOT / _slug(namespace)
    if not ns.exists():
        return None
    files = sorted(ns.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def list_artifacts(namespace: str | None = None) -> list[dict]:
    out = []
    dirs = [ROOT / _slug(namespace)] if namespace else \
        [d for d in ROOT.iterdir() if d.is_dir()]
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                head = json.loads(p.read_text(encoding="utf-8"))
                try:
                    rel = p.relative_to(settings.PROJECT_ROOT)
                except ValueError:
                    rel = p
                out.append({
                    "namespace": d.name, "key": head.get("key", p.stem),
                    "saved_at": head.get("saved_at"),
                    "meta": head.get("meta", {}),
                    "path": str(rel),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return sorted(out, key=lambda a: a["saved_at"] or "", reverse=True)
