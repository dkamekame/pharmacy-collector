import json
import subprocess
import zipfile

import pytest

from collector.errors import StorageError
from collector.storage import GitHubReleaseStorage, LocalStorage


class FakeGh:
    """gh コマンドの呼び出しを記録し、Release の有無に応じて応答する。"""

    def __init__(self, existing: dict[str, list[str]] | None = None):
        self.releases = {tag: list(assets) for tag, assets in (existing or {}).items()}
        self.calls: list[list[str]] = []

    def __call__(self, cmd, capture_output, text):
        self.calls.append(cmd[1:])
        sub, tag = cmd[2], cmd[3]
        if sub == "view":
            if tag not in self.releases:
                return subprocess.CompletedProcess(cmd, 1, "", "release not found")
            body = {"url": f"https://github.com/o/r/releases/tag/{tag}",
                    "assets": [{"name": n} for n in self.releases[tag]]}
            return subprocess.CompletedProcess(cmd, 0, json.dumps(body), "")
        if sub == "create":
            self.releases[tag] = []
        elif sub == "upload":
            self.releases[tag] += [p.rsplit("/", 1)[-1] for p in cmd[4:] if not p.startswith("--")]
        elif sub == "delete-asset":
            self.releases[tag].remove(cmd[4])
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _files(tmp_path, names):
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_bytes(b"x")
        paths.append(p)
    return paths


def test_release_bundles_japanese_names_and_refreshes_latest(tmp_path):
    gh = FakeGh(existing={"latest": ["tokai_hokuriku_2026-09_2609-01-04.zip", "kanto_2026-10_x.zip"]})
    files = _files(tmp_path, ["tokai_hokuriku_2026-10_2610-01-04.zip",
                              "tokai_hokuriku_2026-10_2610(富山薬局)一覧.xlsx",
                              "tokai_hokuriku_2026-10_2610(石川薬局)一覧.xlsx"])

    url = GitHubReleaseStorage(notes="出典", run=gh).save("tokai_hokuriku", "2026-10", "2026-10", files)

    assert url == "https://github.com/o/r/releases/tag/data-2026-10"
    expected = ["tokai_hokuriku_2026-10_2610-01-04.zip", "tokai_hokuriku_2026-10_excel.zip"]
    assert gh.releases["data-2026-10"] == expected
    # latest は同じ地域の古い版だけ消え、他の地域は残る
    assert sorted(gh.releases["latest"]) == sorted(["kanto_2026-10_x.zip", *expected])
    with zipfile.ZipFile(tmp_path / "tokai_hokuriku_2026-10_excel.zip") as zf:
        assert sorted(zf.namelist()) == sorted(f.name for f in files[1:])
    assert ["release", "create", "data-2026-10", "--title", "保険薬局指定一覧 2026-10", "--notes", "出典",
            "--latest=false"] in gh.calls


def test_latest_cleanup_does_not_touch_region_with_same_prefix(tmp_path):
    gh = FakeGh(existing={"latest": ["tokai_2026-09_a.zip", "tokai_hokuriku_2026-10_2610-01-04.zip"]})
    GitHubReleaseStorage(notes="n", run=gh).save("tokai", "2026-10", "2026-10", _files(tmp_path, ["tokai_2026-10_a.zip"]))
    assert sorted(gh.releases["latest"]) == ["tokai_2026-10_a.zip", "tokai_hokuriku_2026-10_2610-01-04.zip"]


def test_release_ascii_only_files_are_uploaded_as_is(tmp_path):
    gh = FakeGh()
    files = _files(tmp_path, ["tohoku_2026-10_shitei-touhoku-yakkyoku-r0810.xlsx"])
    GitHubReleaseStorage(notes="n", run=gh).save("tohoku", "2026-10", "2026-10", files)
    assert gh.releases["data-2026-10"] == ["tohoku_2026-10_shitei-touhoku-yakkyoku-r0810.xlsx"]


def test_release_view_error_other_than_not_found_raises(tmp_path):
    def run(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, 1, "", "HTTP 401: Bad credentials")
    with pytest.raises(StorageError, match="Bad credentials"):
        GitHubReleaseStorage(notes="n", run=run).save("r", "2026-10", "2026-10", _files(tmp_path, ["r_a.zip"]))


def test_local_storage_replaces_latest(tmp_path):
    store = LocalStorage(tmp_path / "data")
    src = tmp_path / "src"
    src.mkdir()
    store.save("r", "2026-10", "2026-10", _files(src, ["r_2026-10_a.zip"]))
    store.save("r", "2026-11", "2026-11", _files(src, ["r_2026-11_a.zip"]))
    assert [p.name for p in (tmp_path / "data" / "r" / "latest").iterdir()] == ["r_2026-11_a.zip"]
    assert (tmp_path / "data" / "r" / "2026-10" / "r_2026-10_a.zip").exists()
