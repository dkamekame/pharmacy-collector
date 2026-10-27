"""GitHub Releases への保存（gh CLI を使う。Actions では GH_TOKEN を渡す）。

- 基準月ごとの Release（data-2026-10）に各地域のファイルを追加していく
- latest タグの Release は、地域ごとに最新版のファイルへ置き換える
- GitHub はアセット名の日本語などを別の文字に置き換えるため、英数字以外を含む名前のファイル
  （ZIPから展開した日本語名のExcel）は {地域}_{版名}_excel.zip にまとめてから載せる
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

from ..errors import StorageError

SAFE_ASSET_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
LATEST_TAG = "latest"


class GitHubReleaseStorage:
    name = "release"

    def __init__(self, notes: str, run=subprocess.run):
        self.notes = notes
        self._run = run

    def save(self, region: str, month: str, label: str, files: list[Path]) -> str:
        assets = self._prepare_assets(region, label, files)

        release = self._ensure_release(f"data-{month}", f"保険薬局指定一覧 {month}", latest=False)
        self._gh("release", "upload", f"data-{month}", *map(str, assets), "--clobber")

        latest = self._ensure_release(LATEST_TAG, "保険薬局指定一覧（各地域の最新版）", latest=True)
        # 「tokai」と「tokai_hokuriku」のように前方一致する地域キーを取り違えないよう、版名の形まで見る
        own_asset = re.compile(rf"^{re.escape(region)}_\d{{4}}-\d{{2}}(_rev\d+)?_")
        for asset in latest.get("assets", []):
            if own_asset.match(asset["name"]):
                self._gh("release", "delete-asset", LATEST_TAG, asset["name"], "--yes")
        self._gh("release", "upload", LATEST_TAG, *map(str, assets), "--clobber")

        return release["url"]

    def _prepare_assets(self, region: str, label: str, files: list[Path]) -> list[Path]:
        safe = [f for f in files if SAFE_ASSET_NAME.match(f.name)]
        unsafe = [f for f in files if not SAFE_ASSET_NAME.match(f.name)]
        if not unsafe:
            return safe
        bundle = files[0].parent / f"{region}_{label}_excel.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in unsafe:
                zf.write(f, arcname=f.name)   # 日本語名はUTF-8フラグ付きで書かれる
        return [*safe, bundle]

    def _ensure_release(self, tag: str, title: str, latest: bool) -> dict:
        proc = self._gh("release", "view", tag, "--json", "url,assets", check=False)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        if "not found" not in proc.stderr.lower():
            raise StorageError(f"Release {tag} の確認に失敗しました: {proc.stderr.strip()}")
        self._gh("release", "create", tag, "--title", title, "--notes", self.notes,
                 f"--latest={'true' if latest else 'false'}")
        return json.loads(self._gh("release", "view", tag, "--json", "url,assets").stdout)

    def _gh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            proc = self._run(["gh", *args], capture_output=True, text=True)
        except FileNotFoundError as e:
            raise StorageError("gh コマンドが見つかりません（GitHub CLI が必要です）") from e
        if check and proc.returncode != 0:
            raise StorageError(f"gh {' '.join(args[:2])} に失敗しました: {proc.stderr.strip()}")
        return proc
