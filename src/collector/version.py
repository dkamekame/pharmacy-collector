"""版（基準月）の判定。ページの「〇年〇月〇日現在」を第一候補、ファイル名の年月を照合用にする。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from .config import VersionToken
from .errors import VersionError
from .extract import AS_OF_RE, Link, nfkc

ERA_BASE_YEAR = {"令和": 2018, "平成": 1988}


@dataclass(frozen=True)
class DataVersion:
    month: str              # "2026-10"
    as_of: str | None       # "2026-10-01"（ページから読めた場合のみ）
    warnings: tuple[str, ...] = ()


def parse_as_of(text: str) -> date | None:
    m = AS_OF_RE.search(nfkc(text))
    if not m:
        return None
    era, year, month, day = m.groups()
    try:
        return date(ERA_BASE_YEAR[era] + (1 if year == "元" else int(year)), int(month), int(day))
    except ValueError:
        return None


def parse_href_token(url: str, token: VersionToken) -> tuple[int, int] | None:
    filename = urlparse(url).path.rsplit("/", 1)[-1]
    m = re.search(token.pattern, filename)
    if not m:
        return None
    groups = m.groupdict()
    month = int(groups["month"])
    year = 2018 + int(groups["reiwa"]) if token.era == "reiwa" else 2000 + int(groups["yy"])
    return (year, month) if 1 <= month <= 12 else None


def determine_version(link: Link, token: VersionToken | None) -> DataVersion:
    page = parse_as_of(link.as_of_text) if link.as_of_text else None
    href = parse_href_token(link.url, token) if token else None

    warnings: list[str] = []
    if page and href and (page.year, page.month) != href:
        warnings.append(
            f"ページの基準日（{page.isoformat()}）とファイル名の年月（{href[0]}-{href[1]:02d}）が一致しません"
            "（ページの基準日を採用）"
        )
    elif page and token and not href:
        warnings.append(f"ファイル名から年月を読み取れませんでした: {link.url}（ページの基準日を採用）")
    elif href and not page:
        warnings.append("ページから基準日（〇年〇月〇日現在）を読み取れませんでした（ファイル名の年月を採用）")

    if page:
        return DataVersion(month=f"{page.year}-{page.month:02d}", as_of=page.isoformat(), warnings=tuple(warnings))
    if href:
        return DataVersion(month=f"{href[0]}-{href[1]:02d}", as_of=None, warnings=tuple(warnings))
    raise VersionError(f"ページの基準日もファイル名の年月も読み取れず、どの月の版か判定できません: {link.url}")
