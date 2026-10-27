"""ZIP展開とファイル名の正規化。

役所のZIPはファイル名がCP932でUTF-8フラグなしのことが多く、そのまま読むと文字化けする。
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .errors import ArchiveError

EXCEL_EXTS = (".xlsx", ".xls", ".xlsm")
IGNORED_NAMES = {"Thumbs.db", ".DS_Store", "desktop.ini"}
MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024   # 展開後の合計サイズ上限（ZIP爆弾対策）
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\s]+')


def normalized_name(region: str, label: str, original: str) -> str:
    """{地域}_{基準月}_{元ファイル名}。元の名前を残して追跡できるようにする。"""
    name = _UNSAFE_CHARS.sub("_", unicodedata.normalize("NFKC", original)).strip("_") or "file"
    return f"{region}_{label}_{name}"


def open_zip(data: bytes) -> zipfile.ZipFile:
    try:
        # UTF-8フラグのないエントリだけ cp932 で読む（フラグ付きは常にUTF-8で読まれる）
        return zipfile.ZipFile(io.BytesIO(data), metadata_encoding="cp932")
    except UnicodeDecodeError:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ArchiveError(f"ZIPファイルとして開けません: {e}") from e


def excel_members(zf: zipfile.ZipFile) -> tuple[list[tuple[zipfile.ZipInfo, PurePosixPath]], list[str]]:
    """展開対象のExcelと、対象外として読み飛ばしたファイル名を返す。危険なパスがあれば ArchiveError。"""
    members, skipped = [], []
    for info in zf.infolist():
        # Windows で作られたZIPは区切りが「\」のことがある（東海北陸の実ファイルで確認）
        raw = info.filename.replace("\\", "/")
        if raw.endswith("/"):
            continue
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
            raise ArchiveError(f"ZIP内に危険なパスが含まれています: {info.filename}")
        if path.parts[0] == "__MACOSX" or path.name in IGNORED_NAMES or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in EXCEL_EXTS:
            members.append((info, path))
        else:
            skipped.append(info.filename)
    return members, skipped


def extract_excels(data: bytes, dest_dir: Path, region: str, label: str) -> tuple[list[Path], list[str]]:
    """ZIP内のExcelを dest_dir に正規化した名前で書き出す。戻り値は（書き出したパス, 警告）。"""
    with open_zip(data) as zf:
        members, skipped = excel_members(zf)
        if sum(info.file_size for info, _ in members) > MAX_TOTAL_UNCOMPRESSED:
            raise ArchiveError("ZIPの展開後サイズが上限を超えています")

        basenames = [path.name for _, path in members]
        written = []
        for info, path in members:
            # サブフォルダ違いで同名のファイルがあるときだけ、フォルダ名を残して衝突を避ける
            original = "_".join(path.parts) if basenames.count(path.name) > 1 else path.name
            target = dest_dir / normalized_name(region, label, original)
            target.write_bytes(zf.read(info))
            written.append(target)

    warnings = [f"ZIP内のExcel以外のファイルは展開しませんでした: {', '.join(skipped)}"] if skipped else []
    return written, warnings
