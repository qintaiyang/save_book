"""Catalog-aware TXT book generation."""
from __future__ import annotations

from pathlib import Path

from .zip_utils import sanitize_filename


def merge_chapters(
    chapter_dir: str | Path,
    book_name: str,
    chapters: list[dict],
    *,
    output_path: str | Path | None = None,
    include_toc: bool = True,
) -> Path:
    """Merge chapter ID text files in catalog order."""
    root = Path(chapter_dir)
    output = (
        Path(output_path)
        if output_path
        else root / f"{sanitize_filename(book_name, max_len=120)}.txt"
    )
    lines: list[str] = [f"《{book_name}》", "=" * 48]

    if include_toc:
        lines.extend(["", "目录", "-" * 48])
        current_volume = None
        for chapter in chapters:
            volume = chapter.get("volumeName") or "正文"
            if volume != current_volume:
                lines.append(f"\n{volume}")
                current_volume = volume
            lines.append(f"  {chapter.get('chapterName', chapter['chapterId'])}")
        lines.extend(["", "=" * 48])

    current_volume = None
    for chapter in chapters:
        chapter_id = str(chapter["chapterId"])
        chapter_name = chapter.get("chapterName") or chapter_id
        volume = chapter.get("volumeName") or "正文"
        if volume != current_volume:
            lines.extend(["", volume, "=" * 32])
            current_volume = volume

        chapter_path = root / f"{chapter_id}.txt"
        lines.extend(["", chapter_name, ""])
        if chapter_path.exists():
            text = chapter_path.read_text(encoding="utf-8", errors="replace").strip()
            lines.append(text or "[本章内容为空]")
        else:
            lines.append("[本章未保存]")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output

