from __future__ import annotations

import shutil
from pathlib import Path

from ..errors import StorageError


class LocalStorage:
    """{root}/{地域}/{版名}/ に保存し、{root}/{地域}/latest/ を最新版で置き換える。"""

    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, region: str, month: str, label: str, files: list[Path]) -> str:
        version_dir = self.root / region / label
        latest_dir = self.root / region / "latest"
        try:
            version_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.copy2(f, version_dir / f.name)
            if latest_dir.exists():
                shutil.rmtree(latest_dir)
            shutil.copytree(version_dir, latest_dir)
        except OSError as e:
            raise StorageError(f"ローカル保存に失敗しました（{version_dir}）: {e}") from e
        return str(version_dir)
