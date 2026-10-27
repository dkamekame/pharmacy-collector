from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path

import pytest

from collector.config import load_config
from collector.errors import FetchError
from collector.http import Fetched

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

PAGE_URLS = {
    "kanto": "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/chousa/shitei.html",
    "tohoku": "https://kouseikyoku.mhlw.go.jp/tohoku/gyomu/gyomu/hoken_kikan/itiran.html",
    "tokai_hokuriku": "https://kouseikyoku.mhlw.go.jp/tokaihokuriku/newpage_00287.html",
}
FILE_URLS = {
    "kanto": "https://kouseikyoku.mhlw.go.jp/kantoshinetsu/shitei_yakkyoku_r0810.zip",
    "tohoku": "https://kouseikyoku.mhlw.go.jp/tohoku/shitei-touhoku-yakkyoku-r0810.xlsx",
    "tokai_hokuriku": "https://kouseikyoku.mhlw.go.jp/tokaihokuriku/2610-01-04.zip",
}
# 2026-10版の実ファイルで確認した中身の構成
TOKAI_PREFS = ["富山", "石川", "岐阜", "静岡", "愛知", "三重"]
KANTO_PREFS = [("085", "茨城"), ("095", "栃木"), ("105", "群馬"), ("115", "埼玉"), ("125", "千葉"),
               ("135", "東京"), ("145", "神奈川"), ("155", "新潟"), ("195", "山梨"), ("205", "長野")]
TOHOKU_SHEETS = ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"]
TOKAI_DIR = "2610　コード内容別医療機関一覧表（薬局）\\"   # Windows形式の区切り「\」


def fixture_html(region: str) -> bytes:
    return (FIXTURES / f"{region}.html").read_bytes()


def padding(seed: int, size: int = 3_000) -> bytes:
    """圧縮されにくい中身（ファイルサイズの下限チェックを通すため）。"""
    return random.Random(seed).randbytes(size)


class CP932ZipInfo(zipfile.ZipInfo):
    """役所のZIPと同じく、ファイル名をCP932・UTF-8フラグなしで書き込む。"""

    def _encodeFilenameFlags(self):
        return self.filename.encode("cp437"), self.flag_bits


def make_zip(names: list[str], cp932: bool = True, seed: int = 0) -> bytes:
    """名前が / か \\ で終わるものはフォルダのエントリ（中身なし）として書く。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i, name in enumerate(names):
            info = CP932ZipInfo(name.encode("cp932").decode("cp437")) if cp932 else zipfile.ZipInfo(name)
            zf.writestr(info, b"" if name.endswith(("/", "\\")) else padding(seed * 100 + i))
    return buf.getvalue()


def tokai_zip(seed: int = 0, prefs: list[str] = TOKAI_PREFS) -> bytes:
    return make_zip([TOKAI_DIR] + [f"{TOKAI_DIR}2610（{p}薬局）コード内容別医療機関一覧表.xlsx" for p in prefs],
                    seed=seed)


def kanto_zip(seed: int = 0) -> bytes:
    folder = "shitei_yakkyoku_r0810/"
    return make_zip([folder] + [f"{folder}{code}コード内容別一覧表（薬局）{p}r0810.xlsx" for code, p in KANTO_PREFS],
                    seed=seed)


def tohoku_xlsx(seed: int = 0, sheets: list[str] = TOHOKU_SHEETS) -> bytes:
    """xlsx の実体はZIP。検証で見るのは先頭バイト・サイズ・workbook.xml のシート名だけ。"""
    sheet_xml = "".join(f'<sheet name="{s}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1))
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_xml}</sheets></workbook>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/worksheets/sheet1.xml", padding(seed, 20_000))
    return buf.getvalue()


class FakeClient:
    def __init__(self, responses: dict[str, bytes]):
        self.responses = dict(responses)
        self.requested: list[str] = []

    def get(self, url: str) -> Fetched:
        self.requested.append(url)
        if url not in self.responses:
            raise FetchError(f"{url} の取得に失敗しました（HTTP 404）")
        return Fetched(url=url, content=self.responses[url])


def site_responses(seed: int = 0) -> dict[str, bytes]:
    return {
        **{PAGE_URLS[r]: fixture_html(r) for r in PAGE_URLS},
        FILE_URLS["kanto"]: kanto_zip(seed),
        FILE_URLS["tohoku"]: tohoku_xlsx(seed),
        FILE_URLS["tokai_hokuriku"]: tokai_zip(seed),
    }


@pytest.fixture
def config():
    return load_config(ROOT / "config.yaml")
