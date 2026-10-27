from datetime import datetime, timezone

import pytest

from collector.manifest import Manifest, classify

PREV = {"data_month": "2026-10", "sources": [{"url": "u", "sha256": "aaa", "size": 1}]}
NOW = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("prev, month, shas, expected", [
    (None, "2026-10", ["aaa"], "new"),
    (PREV, "2026-10", ["aaa"], "unchanged"),
    (PREV, "2026-11", ["bbb"], "new"),
    (PREV, "2026-10", ["bbb"], "replaced"),
    (PREV, "2026-09", ["bbb"], "older"),
])
def test_classify(prev, month, shas, expected):
    assert classify(prev, month, shas) == expected


def test_round_trip_and_revision_labels(tmp_path):
    m = Manifest()
    assert m.next_label("kanto", "2026-10") == "2026-10"
    m.record("kanto", data_month="2026-10", as_of="2026-10-01", label="2026-10", status="new",
             sources=[{"url": "u", "sha256": "aaa", "size": 1}], files=["f"], storage_refs=["r"], now=NOW)
    assert m.next_label("kanto", "2026-10") == "2026-10_rev2"
    assert m.next_label("kanto", "2026-11") == "2026-11"

    path = tmp_path / "state" / "manifest.json"
    m.save(path)
    loaded = Manifest.load(path)
    assert loaded.get("kanto")["fetched_at"] == "2026-11-02T00:00:00Z"
    assert loaded.get("kanto")["history"][0]["sha256"] == ["aaa"]


def test_load_missing_file_returns_empty(tmp_path):
    assert Manifest.load(tmp_path / "none.json").get("kanto") is None
