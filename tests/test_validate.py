import pytest

from collector.errors import ValidationError
from collector.validate import check_expected_sheets, validate_download, xlsx_sheet_names
from conftest import TOHOKU_SHEETS, tohoku_xlsx, tokai_zip

URL = "https://x/tokaihokuriku/2610-01-04.zip"


def test_accepts_zip():
    assert validate_download(tokai_zip(), URL, min_size=10_000) == []


def test_rejects_html_error_page_with_hint():
    with pytest.raises(ValidationError, match="HTMLが返されました"):
        validate_download(b"<!DOCTYPE html><html>503</html>" + b" " * 20_000, URL, min_size=10_000)


def test_rejects_too_small():
    with pytest.raises(ValidationError, match="小さすぎます"):
        validate_download(b"PK\x03\x04" + b"0" * 100, URL, min_size=10_000)


def test_rejects_xls_without_ole_header():
    with pytest.raises(ValidationError):
        validate_download(b"PK\x03\x04" + b"0" * 20_000, "https://x/a.xls", min_size=10_000)


def test_warns_on_large_size_change():
    content = tokai_zip()
    warnings = validate_download(content, URL, min_size=10_000, prev_size=len(content) * 3)
    assert "大きく変わりました" in warnings[0]


def test_reads_sheet_names():
    assert xlsx_sheet_names(tohoku_xlsx()) == TOHOKU_SHEETS


def test_missing_prefecture_sheet_fails():
    content = tohoku_xlsx(sheets=["青森県", "岩手県", "宮城県", "秋田県", "山形県"])
    with pytest.raises(ValidationError, match="福島県"):
        check_expected_sheets(content, "https://x/a.xlsx", tuple(TOHOKU_SHEETS))


def test_sheet_check_rejects_non_xlsx():
    with pytest.raises(ValidationError):
        xlsx_sheet_names(tokai_zip())   # ZIPだが workbook.xml がない
