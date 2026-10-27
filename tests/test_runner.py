import json
from datetime import datetime, timezone

from collector.runner import run
from collector.storage import LocalStorage
from conftest import FILE_URLS, PAGE_URLS, FakeClient, site_responses, tohoku_xlsx, tokai_zip

NOW = datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc)
TOKAI = ["tokai_hokuriku"]


def _run(config, tmp_path, client, regions=TOKAI, **kw):
    kw.setdefault("now", NOW)
    return run(config, client, tmp_path / "manifest.json", [LocalStorage(tmp_path / "data")],
               tmp_path / "staging", regions=regions, **kw)


def test_tokai_first_run_saves_raw_and_extracted(config, tmp_path):
    [r] = _run(config, tmp_path, FakeClient(site_responses()))

    assert r.status == "new", r.error
    assert (r.data_month, r.as_of) == ("2026-10", "2026-10-01")
    month_dir = tmp_path / "data" / "tokai_hokuriku" / "2026-10"
    assert (month_dir / "tokai_hokuriku_2026-10_2610-01-04.zip").exists()
    assert len(list(month_dir.glob("*.xlsx"))) == 6
    assert sorted(p.name for p in (tmp_path / "data" / "tokai_hokuriku" / "latest").iterdir()) == \
        sorted(p.name for p in month_dir.iterdir())
    assert r.warnings == []

    state = json.loads((tmp_path / "manifest.json").read_text())["regions"]["tokai_hokuriku"]
    assert state["sources"][0]["url"] == FILE_URLS["tokai_hokuriku"]
    assert len(state["files"]) == 7


def test_all_three_regions_with_config_only(config, tmp_path):
    """関東・東北はコードを変えず config.yaml の追加だけで動く（設計どおりかの確認）。"""
    results = _run(config, tmp_path, FakeClient(site_responses()), regions=None)
    by_region = {r.region: r for r in results}

    assert [r.status for r in results] == ["new", "new", "new"], [r.error for r in results]
    assert len(by_region["kanto"].files) == 11            # 原本ZIP + 10都県
    assert by_region["tohoku"].files == ["tohoku_2026-10_shitei-touhoku-yakkyoku-r0810.xlsx"]
    assert len(by_region["tokai_hokuriku"].files) == 7    # 原本ZIP + 6県
    assert all(r.warnings == [] for r in results)


def test_one_region_failure_does_not_stop_others(config, tmp_path):
    responses = site_responses()
    del responses[PAGE_URLS["kanto"]]   # 関東の一覧ページだけ取れない
    results = _run(config, tmp_path, FakeClient(responses), regions=None)
    assert [r.status for r in results] == ["failed", "new", "new"]
    assert "HTTP 404" in results[0].error


def test_zip_excel_count_mismatch_fails(config, tmp_path):
    responses = {**site_responses(), FILE_URLS["tokai_hokuriku"]: tokai_zip(prefs=["富山", "石川", "岐阜", "静岡", "愛知"])}
    [r] = _run(config, tmp_path, FakeClient(responses))
    assert r.status == "failed"
    assert "5件" in r.error and "想定6件" in r.error


def test_tohoku_missing_prefecture_sheet_fails(config, tmp_path):
    responses = {**site_responses(), FILE_URLS["tohoku"]: tohoku_xlsx(sheets=["青森県", "岩手県"])}
    [r] = _run(config, tmp_path, FakeClient(responses), regions=["tohoku"])
    assert r.status == "failed"
    assert "宮城県" in r.error


def test_second_run_is_unchanged(config, tmp_path):
    _run(config, tmp_path, FakeClient(site_responses()))
    [r] = _run(config, tmp_path, FakeClient(site_responses()))
    assert r.status == "unchanged"
    assert r.files == []


def test_replaced_file_in_same_month_is_kept_separately(config, tmp_path):
    _run(config, tmp_path, FakeClient(site_responses()))
    [r] = _run(config, tmp_path, FakeClient({**site_responses(), FILE_URLS["tokai_hokuriku"]: tokai_zip(seed=1)}))

    assert r.status == "replaced"
    region_dir = tmp_path / "data" / "tokai_hokuriku"
    assert (region_dir / "2026-10").exists() and (region_dir / "2026-10_rev2").exists()
    assert all(name.startswith("tokai_hokuriku_2026-10_rev2_") for name in r.files)


def test_link_missing_fails(config, tmp_path):
    responses = site_responses()
    responses[PAGE_URLS["tokai_hokuriku"]] = responses[PAGE_URLS["tokai_hokuriku"]].replace(
        "（薬局）".encode(), "（保険薬局）".encode())
    [r] = _run(config, tmp_path, FakeClient(responses))
    assert r.status == "failed"
    assert "0件" in r.error and "ページ構造" in r.error


def test_error_page_instead_of_zip_fails_and_does_not_update_manifest(config, tmp_path):
    responses = {**site_responses(), FILE_URLS["tokai_hokuriku"]: b"<html>Service Unavailable</html>" * 500}
    [r] = _run(config, tmp_path, FakeClient(responses))
    assert r.status == "failed"
    assert "HTML" in r.error
    assert json.loads((tmp_path / "manifest.json").read_text())["regions"] == {}


def test_dry_run_downloads_nothing(config, tmp_path):
    client = FakeClient(site_responses())
    [r] = _run(config, tmp_path, client, dry_run=True)
    assert r.status == "dry-run"
    assert r.source_urls == [FILE_URLS["tokai_hokuriku"]]
    assert client.requested == [PAGE_URLS["tokai_hokuriku"]]
    assert not (tmp_path / "manifest.json").exists()


def test_stale_warning(config, tmp_path):
    _run(config, tmp_path, FakeClient(site_responses()))
    [r] = _run(config, tmp_path, FakeClient(site_responses()), now=datetime(2026, 12, 20, tzinfo=timezone.utc))
    assert r.status == "unchanged"
    assert r.stale_days == 80
    assert any("新しい版がありません" in w for w in r.warnings)
