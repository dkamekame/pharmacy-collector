"""取得履歴（state/manifest.json）。前回との差分判定と、取得履歴の記録に使う。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def classify(prev: dict | None, month: str, sha256s: list[str]) -> str:
    """new（新しい版）/ unchanged / replaced（同じ月の差し替え）/ older（保存済みより古い版）"""
    if prev is None:
        return "new"
    if [s["sha256"] for s in prev["sources"]] == sha256s:
        return "unchanged"
    if month > prev["data_month"]:
        return "new"
    if month == prev["data_month"]:
        return "replaced"
    return "older"


class Manifest:
    def __init__(self, data: dict | None = None):
        self.data = data or {"schema": SCHEMA_VERSION, "regions": {}}

    @classmethod
    def load(cls, path: str | Path) -> Manifest:
        path = Path(path)
        if not path.exists():
            return cls()
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def get(self, region: str) -> dict | None:
        return self.data["regions"].get(region)

    def mark_checked(self, region: str, now: datetime) -> None:
        if state := self.get(region):
            state["last_checked_at"] = iso_utc(now)

    def next_label(self, region: str, month: str) -> str:
        """同じ月の2回目以降（差し替え）は 2026-10_rev2 のように別名にして、前の原本を上書きしない。"""
        history = (self.get(region) or {}).get("history", [])
        revision = sum(1 for h in history if h["data_month"] == month) + 1
        return month if revision == 1 else f"{month}_rev{revision}"

    def record(self, region: str, *, data_month: str, as_of: str | None, label: str, status: str,
               sources: list[dict], files: list[str], storage_refs: list[str], now: datetime) -> None:
        state = self.data["regions"].setdefault(region, {"history": []})
        timestamp = iso_utc(now)
        state.update(
            data_month=data_month,
            as_of=as_of,
            label=label,
            sources=sources,
            files=files,
            storage_refs=storage_refs,
            fetched_at=timestamp,
            last_checked_at=timestamp,
        )
        state["history"].append({
            "data_month": data_month,
            "as_of": as_of,
            "label": label,
            "status": status,
            "sha256": [s["sha256"] for s in sources],
            "fetched_at": timestamp,
        })
