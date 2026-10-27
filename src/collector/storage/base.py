from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    """保存先。Google Drive などに差し替えるときは、これを実装したクラスを追加する。"""

    name: str

    def save(self, region: str, month: str, label: str, files: list[Path]) -> str:
        """files を保存し、保存先を示す文字列（パスやURL）を返す。失敗時は StorageError。

        month: 基準月（2026-10）。label: ファイル名に入る版名（差し替え時は 2026-10_rev2）。
        """
        ...
