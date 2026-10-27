import io
import zipfile

import pytest

from collector.archive import extract_excels, normalized_name
from collector.errors import ArchiveError
from conftest import TOKAI_PREFS, kanto_zip, make_zip, tokai_zip


def test_cp932_names_with_backslash_folders_are_decoded(tmp_path):
    """東海北陸の実ファイルと同じ構成: CP932・UTF-8フラグなし・「\\」区切り・フォルダのエントリあり。"""
    written, warnings = extract_excels(tokai_zip(), tmp_path, "tokai_hokuriku", "2026-10")
    names = sorted(p.name for p in written)
    assert names == sorted(f"tokai_hokuriku_2026-10_2610({p}薬局)コード内容別医療機関一覧表.xlsx" for p in TOKAI_PREFS)
    assert warnings == []   # フォルダのエントリを「Excel以外」と誤報しない
    assert all(p.stat().st_size > 0 for p in written)


def test_kanto_zip_with_slash_folder(tmp_path):
    written, warnings = extract_excels(kanto_zip(), tmp_path, "kanto", "2026-10")
    assert len(written) == 10
    assert "kanto_2026-10_135コード内容別一覧表(薬局)東京r0810.xlsx" in {p.name for p in written}
    assert warnings == []


def test_utf8_flagged_names_are_kept(tmp_path):
    written, _ = extract_excels(make_zip(["東京都.xlsx"], cp932=False), tmp_path, "kanto", "2026-10")
    assert [p.name for p in written] == ["kanto_2026-10_東京都.xlsx"]


def test_ignores_junk_and_reports_non_excel(tmp_path):
    data = make_zip(["a.xlsx", "__MACOSX/._a.xlsx", "Thumbs.db", "~$a.xlsx", "readme.txt"], cp932=False)
    written, warnings = extract_excels(data, tmp_path, "r", "2026-10")
    assert [p.name for p in written] == ["r_2026-10_a.xlsx"]
    assert "readme.txt" in warnings[0]


def test_same_basename_in_subfolders_does_not_collide(tmp_path):
    written, _ = extract_excels(make_zip(["A/x.xlsx", "B/x.xlsx"], cp932=False), tmp_path, "r", "2026-10")
    assert sorted(p.name for p in written) == ["r_2026-10_A_x.xlsx", "r_2026-10_B_x.xlsx"]


@pytest.mark.parametrize("evil", ["../evil.xlsx", "/etc/evil.xlsx", "C:/evil.xlsx", "a/../../evil.xlsx"])
def test_rejects_path_traversal(tmp_path, evil):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(evil, b"x")
    with pytest.raises(ArchiveError):
        extract_excels(buf.getvalue(), tmp_path, "r", "2026-10")


def test_rejects_non_zip(tmp_path):
    with pytest.raises(ArchiveError):
        extract_excels(b"<html>not found</html>", tmp_path, "r", "2026-10")


@pytest.mark.parametrize("original, expected", [
    ("2610-01-04.zip", "r_2026-10_2610-01-04.zip"),
    ("コード内容別（薬局） 一覧.xlsx", "r_2026-10_コード内容別(薬局)_一覧.xlsx"),
    ('a:b*c?.xlsx', "r_2026-10_a_b_c_.xlsx"),
])
def test_normalized_name(original, expected):
    assert normalized_name("r", "2026-10", original) == expected
