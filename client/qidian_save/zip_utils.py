"""Utilities for safely extracting zip files returned by the server."""
import re
from pathlib import Path
import zipfile


class UnsafeZipPathError(ValueError):
    """Raised when a zip member would extract outside the target directory."""


def _safe_member_path(output_dir: Path, member_name: str) -> Path:
    target_root = output_dir.resolve()
    member_path = Path(member_name)

    if member_path.is_absolute():
        raise UnsafeZipPathError(f"Unsafe absolute zip path: {member_name}")

    target = (target_root / member_path).resolve()
    if target != target_root and target_root not in target.parents:
        raise UnsafeZipPathError(f"Unsafe zip path traversal: {member_name}")
    return target


def sanitize_filename(name: str, max_len: int = 60) -> str:
    """过滤文件名中的危险字符以确保跨平台安全

    移除路径遍历字符（/ \\ ..）、Windows 保留字符（: * ? \" < > |）、
    以及控制字符/空字节。返回空串时使用 '_' 兜底。
    """
    if not name:
        return "_"
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', str(name))
    safe = safe.strip()
    if not safe or safe in (".", ".."):
        return "_"
    return safe[:max_len]


def safe_extract_zip(zf: zipfile.ZipFile, output_dir: str | Path) -> list[Path]:
    """Extract all zip members after verifying they stay under output_dir."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    for info in zf.infolist():
        target = _safe_member_path(output_root, info.filename)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target.open("wb") as dst:
            dst.write(src.read())
        extracted.append(target)
    return extracted
