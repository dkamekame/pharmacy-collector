from dataclasses import replace

import pytest

from collector.extract import extract_links
from conftest import FILE_URLS, PAGE_URLS, fixture_html

REGIONS = ["kanto", "tohoku", "tokai_hokuriku"]


@pytest.mark.parametrize("region", REGIONS)
def test_extracts_exactly_the_pharmacy_file(config, region):
    """実ページ（2026-10-27保存）から、薬局のファイル1件だけを拾う。PDFや医科・歯科・新規指定などは除外。"""
    rule = config.regions[region].link
    result = extract_links(fixture_html(region), PAGE_URLS[region], rule)

    assert [link.url for link in result.links] == [FILE_URLS[region]]
    assert result.links[0].as_of_text.replace(" ", "") == "令和8年10月1日現在"
    assert result.warnings == []


@pytest.mark.parametrize("region, text_alone_is_ambiguous", [
    ("kanto", True),            # 「薬局（PDF）」が都県ごとにある
    ("tohoku", True),           # 「薬局［629KB］」のPDFが県ごとにある
    ("tokai_hokuriku", False),  # PDFは「（富山薬局）」なので「（薬局）」とは区別できる
])
def test_both_conditions_are_needed(config, region, text_alone_is_ambiguous):
    """実ページには紛らわしいリンクがあり、拡張子だけ・文言だけでは1件に絞れないことを確かめる。"""
    rule = config.regions[region].link
    html = fixture_html(region)
    ext_only = extract_links(html, PAGE_URLS[region], replace(rule, text_contains=()))
    text_only = extract_links(html, PAGE_URLS[region], replace(rule, ext=(".zip", ".xlsx", ".xls", ".pdf")))
    assert len(ext_only.links) > 1   # 医科・歯科や新規指定などのZIP/xlsxがある
    assert (len(text_only.links) > 1) is text_alone_is_ambiguous


def test_no_links_when_wording_changes(config):
    html = fixture_html("tokai_hokuriku").replace("（薬局）".encode(), "（保険薬局）".encode())
    result = extract_links(html, PAGE_URLS["tokai_hokuriku"], config.regions["tokai_hokuriku"].link)
    assert result.links == []


def test_warns_when_href_naming_changes(config):
    html = fixture_html("tokai_hokuriku").replace(b"2610-01-04.zip", b"yakkyoku_202610.zip")
    result = extract_links(html, PAGE_URLS["tokai_hokuriku"], config.regions["tokai_hokuriku"].link)
    assert len(result.links) == 1
    assert "想定パターンと異なります" in result.warnings[0]


def test_duplicate_links_count_once(config):
    rule = config.regions["tokai_hokuriku"].link
    html = b'<p>' + "令和8年10月1日現在".encode() + b'</p>' + (
        '<a href="/tokaihokuriku/2610-01-04.zip">（薬局）ZIP</a>'
        '<a href="/tokaihokuriku/2610-01-04.zip">（薬局）ZIP</a>'
    ).encode()
    assert len(extract_links(html, PAGE_URLS["tokai_hokuriku"], rule).links) == 1


def test_as_of_split_across_tags_and_fullwidth_digits(config):
    rule = replace(config.regions["tokai_hokuriku"].link, href_pattern=None)
    html = "<p><strong>令和８年１０月</strong>１日 現在</p><a href='x/2610-01-04.zip'>（薬局）</a>".encode()
    link = extract_links(html, "https://example.test/a/", rule).links[0]
    assert link.as_of_text == "令和8年10月1日 現在"
    assert link.url == "https://example.test/a/x/2610-01-04.zip"


def test_as_of_uses_nearest_preceding_date(config):
    rule = replace(config.regions["tokai_hokuriku"].link, href_pattern=None)
    html = (
        "<p>令和8年9月1日現在（別の表）</p><table><tr><td>…</td></tr></table>"
        "<h2>一覧</h2><p>令和8年10月1日現在</p><a href='/2610-01-04.zip'>（薬局）</a>"
        "<p>令和8年11月1日現在（後ろの表）</p>"
    ).encode()
    link = extract_links(html, "https://example.test/", rule).links[0]
    assert link.as_of_text == "令和8年10月1日現在"
