"""ダウンロードしたファイルの検証。エラーページを原本として保存しないための関門。"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

from .errors import ValidationError

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")   # 旧形式の .xls
EXPECTED_MAGIC = {".zip": ZIP_MAGIC, ".xlsx": ZIP_MAGIC, ".xlsm": ZIP_MAGIC, ".xls": OLE_MAGIC}
SIZE_CHANGE_WARN_RATIO = 0.5


def url_filename(url: str) -> str:
    return unquote(PurePosixPath(urlparse(url).path).name)


def validate_download(content: bytes, url: str, min_size: int, prev_size: int | None = None) -> list[str]:
    """不正なら ValidationError、気になる点があれば警告文のリストを返す。"""
    name = url_filename(url)
    ext = PurePosixPath(name).suffix.lower()

    magic = EXPECTED_MAGIC.get(ext)
    if magic and not content.startswith(magic):
        head = content[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        hint = "（HTMLが返されました。エラーページかアクセス制限の可能性）" if head.startswith((b"<!doctype", b"<html")) else ""
        raise ValidationError(f"{name} が {ext} 形式ではありません{hint}")
    if len(content) < min_size:
        raise ValidationError(f"{name} のサイズが小さすぎます（{len(content):,} バイト < {min_size:,} バイト）")

    warnings = []
    if prev_size and abs(len(content) - prev_size) / prev_size >= SIZE_CHANGE_WARN_RATIO:
        warnings.append(f"{name} のサイズが前回から大きく変わりました（{prev_size:,} → {len(content):,} バイト）")
    return warnings


def xlsx_sheet_names(content: bytes) -> list[str]:
    """xlsx（中身はZIP）の xl/workbook.xml からシート名を読む。openpyxl は使わない。"""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            root = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise ValidationError(f"xlsx のシート一覧を読み取れません: {e}") from e
    return [el.attrib["name"] for el in root.iter()
            if el.tag.rsplit("}", 1)[-1] == "sheet" and "name" in el.attrib]


def check_expected_sheets(content: bytes, url: str, expected: tuple[str, ...]) -> None:
    """東北のように複数県を1ファイルにまとめた xlsx で、県のシートが揃っているかを確かめる。"""
    sheets = xlsx_sheet_names(content)
    if missing := [s for s in expected if s not in sheets]:
        raise ValidationError(
            f"{url_filename(url)} に想定のシートがありません: {', '.join(missing)}（実際のシート: {', '.join(sheets) or 'なし'}）"
        )
