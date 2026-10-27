"""config.yaml の読み込み。地域ごとの違いはすべて設定に寄せ、コードは3地域で共通にする。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import ConfigError

# version_token.era ごとに、pattern に必要な名前付きグループ
REQUIRED_GROUPS = {
    "reiwa": {"reiwa", "month"},     # r0810 → 令和8年10月
    "western2": {"yy", "month"},     # 2610 → 2026年10月
}
REGION_KEY_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class HttpConfig:
    user_agent: str
    interval_sec: float = 3.0
    timeout_sec: float = 30.0
    retries: int = 3


@dataclass(frozen=True)
class LinkRule:
    ext: tuple[str, ...]
    text_contains: tuple[str, ...]
    href_pattern: str | None = None


@dataclass(frozen=True)
class VersionToken:
    pattern: str
    era: str


@dataclass(frozen=True)
class RegionConfig:
    key: str
    label: str
    page_url: str
    link: LinkRule
    expected_links: int = 1
    version_token: VersionToken | None = None
    zip_expected_excels: int | None = None
    expected_sheets: tuple[str, ...] = ()
    min_size_bytes: int = 10_000


@dataclass(frozen=True)
class Config:
    http: HttpConfig
    stale_after_days: int
    regions: dict[str, RegionConfig]


def load_config(path: str | Path) -> Config:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"{path} を読み込めません: {e}") from e

    try:
        http_raw = raw.get("http", {})
        http = HttpConfig(
            user_agent=http_raw["user_agent"],
            interval_sec=float(http_raw.get("interval_sec", 3.0)),
            timeout_sec=float(http_raw.get("timeout_sec", 30.0)),
            retries=int(http_raw.get("retries", 3)),
        )
        stale_after_days = int(raw.get("monitoring", {}).get("stale_after_days", 45))
        regions = {key: _region(key, value) for key, value in raw["regions"].items()}
    except ConfigError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, re.error) as e:
        raise ConfigError(f"{path} の形式が不正です: {type(e).__name__}: {e}") from e

    if not regions:
        raise ConfigError(f"{path} に regions が1つもありません")
    return Config(http=http, stale_after_days=stale_after_days, regions=regions)


def _region(key: str, raw: dict) -> RegionConfig:
    if not REGION_KEY_RE.match(key):
        raise ConfigError(f"地域キー「{key}」は英小文字・数字・_ のみ使えます（ファイル名に使うため）")

    link = raw["link"]
    ext = tuple(e.lower() if e.startswith(".") else f".{e.lower()}" for e in link["ext"])
    href_pattern = link.get("href_pattern")
    if href_pattern:
        re.compile(href_pattern)

    token = None
    if token_raw := raw.get("version_token"):
        era = token_raw["era"]
        if era not in REQUIRED_GROUPS:
            raise ConfigError(f"{key}: version_token.era は {sorted(REQUIRED_GROUPS)} のいずれかにしてください")
        missing = REQUIRED_GROUPS[era] - set(re.compile(token_raw["pattern"]).groupindex)
        if missing:
            raise ConfigError(f"{key}: version_token.pattern に名前付きグループ {sorted(missing)} がありません")
        token = VersionToken(pattern=token_raw["pattern"], era=era)

    zip_expected = raw.get("zip_expected_excels")
    return RegionConfig(
        key=key,
        label=raw.get("label", key),
        page_url=raw["page_url"],
        link=LinkRule(ext=ext, text_contains=tuple(link.get("text_contains", [])), href_pattern=href_pattern),
        expected_links=int(raw.get("expected_links", 1)),
        version_token=token,
        zip_expected_excels=int(zip_expected) if zip_expected is not None else None,
        expected_sheets=tuple(raw.get("expected_sheets") or ()),
        min_size_bytes=int(raw.get("min_size_bytes", 10_000)),
    )
