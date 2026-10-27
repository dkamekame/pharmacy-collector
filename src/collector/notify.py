"""実行結果の要約とSlack通知。「変更なし」だけの週は通知しない（停滞は警告で拾う）。"""

from __future__ import annotations

from datetime import datetime

import requests

from .runner import JST, RegionResult

NOTIFY_STATUSES = {"new", "replaced", "skipped", "failed"}
SLACK_ICONS = {
    "new": ":new:",
    "replaced": ":arrows_counterclockwise:",
    "unchanged": ":white_check_mark:",
    "skipped": ":double_vertical_bar:",
    "failed": ":x:",
    "dry-run": ":mag:",
}


def describe(r: RegionResult) -> str:
    month = f"{r.data_month}（基準日 {r.as_of}）" if r.as_of else (r.data_month or "")
    match r.status:
        case "new":
            return f"新しい版を取得 {month} / {len(r.files)}ファイル"
        case "replaced":
            return f"同じ月のファイルが差し替えられました（訂正版の可能性）{month} / {len(r.files)}ファイル"
        case "unchanged":
            return f"変更なし {month}"
        case "skipped":
            return f"保存せず {month}"
        case "dry-run":
            return f"抽出OK {month} / {', '.join(r.source_urls)}"
        case _:
            return f"失敗: {r.error}"


def format_summary(results: list[RegionResult]) -> str:
    lines = []
    for r in results:
        lines.append(f"[{r.region}] {r.label}: {describe(r)}")
        lines += [f"    保存先: {ref}" for ref in r.storage_refs]
        lines += [f"    警告: {w}" for w in r.warnings]
    return "\n".join(lines)


def needs_notification(results: list[RegionResult]) -> bool:
    return any(r.status in NOTIFY_STATUSES or r.warnings for r in results)


def build_message(results: list[RegionResult], now: datetime, run_url: str | None = None) -> str:
    lines = [f"*厚生局 保険薬局指定一覧 収集結果* {now.astimezone(JST):%Y-%m-%d %H:%M} JST"]
    for r in results:
        lines.append(f"{SLACK_ICONS.get(r.status, ':grey_question:')} *{r.label}*: {describe(r)}")
        for ref in r.storage_refs:
            lines.append(f"　<{ref}|保存先を開く>" if ref.startswith("http") else f"　保存先: {ref}")
        lines += [f"　:warning: {w}" for w in r.warnings]
    if run_url:
        lines.append(f"<{run_url}|実行ログを開く>")
    return "\n".join(lines)


def post_slack(webhook_url: str, text: str) -> None:
    resp = requests.post(webhook_url, json={"text": text}, timeout=10)
    resp.raise_for_status()
