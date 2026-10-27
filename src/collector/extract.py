"""一覧ページHTMLから対象ファイルへのリンクと、その表の基準日を取り出す。

拡張子と文言を主条件にし（ファイル名の付け方より変わりにくい）、href_pattern は確認用に使う。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, Tag

from .config import LinkRule

AS_OF_RE = re.compile(r"(令和|平成)\s*(\d+|元)\s*年\s*(\d+)\s*月\s*(\d+)\s*日\s*現在")
# 「令和8年10月1日」と「現在」が別のタグに分かれていても拾えるよう、連続するテキストノードをまとめて見る
_AS_OF_WINDOW = 6


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


@dataclass(frozen=True)
class Link:
    url: str
    text: str
    as_of_text: str | None   # リンクから遡って最も近い「〇年〇月〇日現在」


@dataclass
class Extraction:
    links: list[Link]
    warnings: list[str] = field(default_factory=list)


def extract_links(html: bytes | str, base_url: str, rule: LinkRule) -> Extraction:
    soup = BeautifulSoup(html, "html.parser")
    needles = [nfkc(t) for t in rule.text_contains]
    href_re = re.compile(rule.href_pattern) if rule.href_pattern else None

    links: list[Link] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"].strip())
        if not urlparse(url).path.lower().endswith(rule.ext):
            continue
        text = " ".join(nfkc(a.get_text()).split())
        if not all(n in text for n in needles):
            continue
        if url in seen:  # 同じファイルへのリンクが複数あっても1件として数える
            continue
        seen.add(url)
        if href_re and not href_re.search(url):
            warnings.append(f"リンク「{text}」のURLが想定パターンと異なります: {url}（ファイル名の付け方が変わった可能性）")
        links.append(Link(url=url, text=text, as_of_text=_nearest_as_of(a)))
    return Extraction(links=links, warnings=warnings)


def _nearest_as_of(a: Tag) -> str | None:
    window: list[str] = []
    for s in a.find_all_previous(string=True):
        if isinstance(s, Comment):
            continue
        window.insert(0, nfkc(str(s)))
        del window[_AS_OF_WINDOW:]
        if m := AS_OF_RE.search("".join(window).replace("\n", "")):
            return m.group(0)
    return None
