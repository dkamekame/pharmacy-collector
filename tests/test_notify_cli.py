import json
from datetime import datetime, timezone

import pytest

from collector import cli, notify
from collector.runner import RegionResult
from conftest import ROOT, PAGE_URLS, FakeClient, site_responses

NOW = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)


def test_unchanged_only_is_not_notified():
    results = [RegionResult("kanto", "関東信越厚生局", status="unchanged", data_month="2026-10")]
    assert not notify.needs_notification(results)


def test_message_contains_status_links_and_warnings():
    results = [
        RegionResult("kanto", "関東信越厚生局", status="new", data_month="2026-11", as_of="2026-11-01",
                     files=["a"] * 11, storage_refs=["https://github.com/o/r/releases/tag/data-2026-11"]),
        RegionResult("tohoku", "東北厚生局", status="failed", error="対象リンクが0件でした"),
        RegionResult("tokai_hokuriku", "東海北陸厚生局", status="unchanged", data_month="2026-10",
                     warnings=["基準日 2026-10-01 から50日間、新しい版がありません"]),
    ]
    assert notify.needs_notification(results)
    text = notify.build_message(results, NOW, run_url="https://github.com/o/r/actions/runs/1")
    assert "2026-11-02 09:00 JST" in text
    assert ":new: *関東信越厚生局*: 新しい版を取得 2026-11（基準日 2026-11-01） / 11ファイル" in text
    assert "<https://github.com/o/r/releases/tag/data-2026-11|保存先を開く>" in text
    assert ":x: *東北厚生局*: 失敗: 対象リンクが0件でした" in text
    assert ":warning: 基準日 2026-10-01 から50日間" in text
    assert "<https://github.com/o/r/actions/runs/1|実行ログを開く>" in text


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """実ネットワークの代わりに FakeClient を使い、Slack 送信を記録する。"""
    posted = []
    responses = site_responses()
    monkeypatch.setattr(cli, "PoliteClient", lambda cfg: FakeClient(responses))
    monkeypatch.setattr(notify, "post_slack", lambda url, text: posted.append(text))
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    for key in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(key, raising=False)
    args = ["run", "--config", str(ROOT / "config.yaml"), "--manifest", str(tmp_path / "m.json"),
            "--data-dir", str(tmp_path / "data"), "--report-json", str(tmp_path / "report.json")]
    return args, responses, posted


def test_cli_success_then_quiet_second_run(cli_env, tmp_path):
    args, _, posted = cli_env
    assert cli.main(args) == 0
    assert len(posted) == 1 and ":new:" in posted[0]
    report = json.loads((tmp_path / "report.json").read_text())
    assert [r["status"] for r in report["results"]] == ["new", "new", "new"]

    assert cli.main(args) == 0
    assert len(posted) == 1   # 2回目は全地域「変更なし」なので通知しない


def test_cli_region_failure_exits_1_and_notifies(cli_env):
    args, responses, posted = cli_env
    responses[PAGE_URLS["tohoku"]] = "<html><body>メンテナンス中</body></html>".encode()
    assert cli.main(args) == 1
    assert ":x: *東北厚生局*: 失敗: 対象リンクが0件でした" in posted[0]


def test_cli_config_error_exits_2_and_notifies(cli_env, tmp_path):
    args, _, posted = cli_env
    bad = tmp_path / "bad.yaml"
    bad.write_text("http: {}\nregions: {}\n", encoding="utf-8")
    assert cli.main([*args, "--config", str(bad)]) == 2
    assert "異常終了" in posted[0]


def test_cli_dry_run_does_not_notify_or_write(cli_env, tmp_path):
    args, _, posted = cli_env
    assert cli.main([*args, "--dry-run"]) == 0
    assert posted == []
    assert not (tmp_path / "m.json").exists()
