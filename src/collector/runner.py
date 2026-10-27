"""1回の収集処理。地域ごとに 取得→抽出→版判定→差分判定→検証→展開→保存 を行う。

1つの地域が失敗しても他の地域は続け、結果は RegionResult にまとめて返す。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .archive import extract_excels, normalized_name
from .config import Config, RegionConfig
from .errors import ArchiveError, CollectError, ConfigError, ExtractionError, VersionError
from .extract import extract_links
from .http import Fetched
from .manifest import Manifest, classify
from .storage import Storage
from .validate import check_expected_sheets, url_filename, validate_download
from .version import determine_version

log = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


class Client(Protocol):
    def get(self, url: str) -> Fetched: ...


@dataclass
class RegionResult:
    region: str
    label: str
    status: str = "failed"   # new / replaced / unchanged / skipped / failed / dry-run
    data_month: str | None = None
    as_of: str | None = None
    source_urls: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    storage_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    stale_days: int | None = None


@dataclass
class RunContext:
    client: Client
    manifest: Manifest
    storages: list[Storage]
    staging_dir: Path
    now: datetime
    dry_run: bool = False


def run(config: Config, client: Client, manifest_path: str | Path, storages: list[Storage],
        staging_dir: Path, regions: list[str] | None = None, dry_run: bool = False,
        now: datetime | None = None) -> list[RegionResult]:
    keys = regions or list(config.regions)
    if unknown := [k for k in keys if k not in config.regions]:
        raise ConfigError(f"config.yaml にない地域が指定されました: {', '.join(unknown)}")

    ctx = RunContext(client=client, manifest=Manifest.load(manifest_path), storages=storages,
                     staging_dir=staging_dir, now=now or datetime.now(timezone.utc), dry_run=dry_run)
    results = [collect_region(config.regions[k], ctx) for k in keys]

    if not dry_run:
        today = ctx.now.astimezone(JST).date()
        for r in results:
            _check_stale(r, ctx.manifest.get(r.region), today, config.stale_after_days)
        ctx.manifest.save(manifest_path)
    return results


def collect_region(cfg: RegionConfig, ctx: RunContext) -> RegionResult:
    result = RegionResult(region=cfg.key, label=cfg.label)
    try:
        _collect(cfg, ctx, result)
    except CollectError as e:
        result.status, result.error = "failed", str(e)
        log.error("[%s] 失敗: %s", cfg.key, e)
    except Exception as e:   # 想定外のエラーもその地域だけに閉じ込める
        result.status, result.error = "failed", f"想定外のエラー: {type(e).__name__}: {e}"
        log.exception("[%s] 想定外のエラー", cfg.key)
    return result


def _collect(cfg: RegionConfig, ctx: RunContext, result: RegionResult) -> None:
    log.info("[%s] 一覧ページを取得: %s", cfg.key, cfg.page_url)
    page = ctx.client.get(cfg.page_url)
    extraction = extract_links(page.content, page.url, cfg.link)
    result.warnings += extraction.warnings
    links = extraction.links
    if len(links) != cfg.expected_links:
        found = "、".join(f"「{link.text}」" for link in links) or "なし"
        hint = "ページ構造かリンク文言が変わった可能性があります" if not links else "抽出条件を見直してください"
        raise ExtractionError(f"対象リンクが{len(links)}件でした（想定{cfg.expected_links}件、該当: {found}）。{hint}")

    versions = [determine_version(link, cfg.version_token) for link in links]
    if len({v.month for v in versions}) > 1:
        raise VersionError(f"対象ファイルの基準月がそろっていません: {sorted({v.month for v in versions})}")
    version = versions[0]
    result.warnings += list(dict.fromkeys(w for v in versions for w in v.warnings))
    result.data_month, result.as_of = version.month, version.as_of
    result.source_urls = [link.url for link in links]
    log.info("[%s] 対象: %s（基準月 %s）", cfg.key, ", ".join(result.source_urls), version.month)
    if ctx.dry_run:
        result.status = "dry-run"
        return

    prev = ctx.manifest.get(cfg.key)
    prev_sizes = [s["size"] for s in prev["sources"]] if prev else []
    downloads: list[tuple[str, bytes]] = []
    for i, link in enumerate(links):
        content = ctx.client.get(link.url).content
        prev_size = prev_sizes[i] if i < len(prev_sizes) else None
        result.warnings += validate_download(content, link.url, cfg.min_size_bytes, prev_size)
        if cfg.expected_sheets and url_filename(link.url).lower().endswith((".xlsx", ".xlsm")):
            check_expected_sheets(content, link.url, cfg.expected_sheets)
        downloads.append((link.url, content))

    sources = [{"url": url, "sha256": hashlib.sha256(c).hexdigest(), "size": len(c)} for url, c in downloads]
    status = classify(prev, version.month, [s["sha256"] for s in sources])
    if status == "unchanged":
        ctx.manifest.mark_checked(cfg.key, ctx.now)
        result.status = "unchanged"
        log.info("[%s] 変更なし", cfg.key)
        return
    if status == "older":
        ctx.manifest.mark_checked(cfg.key, ctx.now)
        result.status = "skipped"
        result.warnings.append(
            f"サイト上の版（{version.month}）が保存済みの版（{prev['data_month']}）より古いため保存しませんでした"
        )
        return

    label = ctx.manifest.next_label(cfg.key, version.month)
    dest = ctx.staging_dir / cfg.key / label
    dest.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for url, content in downloads:
        raw = dest / normalized_name(cfg.key, label, url_filename(url))
        raw.write_bytes(content)
        files.append(raw)
        if raw.suffix.lower() == ".zip":
            files += _extract_zip(cfg, content, dest, label, result)

    result.storage_refs = [storage.save(cfg.key, version.month, label, files) for storage in ctx.storages]
    result.files = [f.name for f in files]
    ctx.manifest.record(cfg.key, data_month=version.month, as_of=version.as_of, label=label, status=status,
                        sources=sources, files=result.files, storage_refs=result.storage_refs, now=ctx.now)
    result.status = status
    log.info("[%s] 保存しました（%s、%dファイル）", cfg.key, status, len(files))


def _extract_zip(cfg: RegionConfig, content: bytes, dest: Path, label: str, result: RegionResult) -> list[Path]:
    extracted, warnings = extract_excels(content, dest, cfg.key, label)
    result.warnings += warnings
    if not extracted:
        raise ArchiveError("ZIP内にExcelファイルがありません")
    if cfg.zip_expected_excels is None:
        result.warnings.append(
            f"ZIP内のExcelは{len(extracted)}件でした（config.yaml の zip_expected_excels に設定すると件数を検証します）"
        )
    elif len(extracted) != cfg.zip_expected_excels:
        raise ArchiveError(f"ZIP内のExcelが{len(extracted)}件でした（想定{cfg.zip_expected_excels}件）")
    return extracted


def _check_stale(result: RegionResult, state: dict | None, today: date, limit_days: int) -> None:
    if not state:
        return
    base = date.fromisoformat(state["as_of"] or f"{state['data_month']}-01")
    days = (today - base).days
    if days > limit_days:
        result.stale_days = days
        result.warnings.append(f"基準日 {base.isoformat()} から{days}日間、新しい版がありません（掲載の停止か抽出の不具合の可能性）")
