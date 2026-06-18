"""在线备份面板 — 只显示任务状态、进度、下载结果"""

import json
import threading
import io
import zipfile
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QLabel, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from ...zip_utils import safe_extract_zip
from ...zip_utils import sanitize_filename
from ..components import PageHeader, StatCard, SurfaceCard, configure_page_layout


def _chapter_names_from_target_ref(target_ref: dict) -> dict[str, str]:
    names = {}
    chapter_names = target_ref.get("chapterNames")
    if isinstance(chapter_names, dict):
        for key, value in chapter_names.items():
            if value not in (None, ""):
                names[str(key)] = str(value)
    chapters = target_ref.get("chapters")
    if isinstance(chapters, list):
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            chapter_id = chapter.get("chapterId") or chapter.get("id")
            chapter_name = chapter.get("chapterName") or chapter.get("name")
            if chapter_id not in (None, "") and chapter_name not in (None, ""):
                names[str(chapter_id)] = str(chapter_name)
    return names


def _chapter_id_from_archive_name(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^\d+\.\s*", "", stem)
    parts = stem.split("_")
    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
        return parts[1]
    return stem


def _rename_downloaded_chapter_files(save_dir: str, saved_files: list[Path], target_ref: dict) -> list[Path]:
    names = _chapter_names_from_target_ref(target_ref or {})
    if not names:
        return saved_files
    chapter_ids = [str(v) for v in (target_ref or {}).get("chapterIds") or []]
    renamed = []
    used = set()
    for index, path in enumerate(saved_files, start=1):
        path = Path(path)
        if path.suffix.lower() != ".txt":
            renamed.append(path)
            continue
        chapter_id = _chapter_id_from_archive_name(path)
        chapter_name = names.get(chapter_id)
        if not chapter_name:
            renamed.append(path)
            continue
        order = chapter_ids.index(chapter_id) + 1 if chapter_id in chapter_ids else index
        target = Path(save_dir) / f"{order:03d}. {sanitize_filename(chapter_name, max_len=120)}.txt"
        base_target = target
        counter = 2
        while target.exists() and target != path:
            target = base_target.with_name(f"{base_target.stem}_{counter}{base_target.suffix}")
            counter += 1
        if target != path:
            path.replace(target)
        used.add(target.name)
        renamed.append(target)
    return renamed


class _ApkSignals(QObject):
    task_ready = pyqtSignal(dict)
    artifacts_ready = pyqtSignal(list)
    error = pyqtSignal(str)
    download_done = pyqtSignal(int, str)
    download_error = pyqtSignal(str)


class ApkBackupPanel(QWidget):
    def __init__(self, client, on_session_authenticated=None, on_go_search=None, debug_mode: bool = False):
        super().__init__()
        self.client = client
        self.on_session_authenticated = on_session_authenticated
        self.on_go_search = on_go_search
        self.debug_mode = bool(debug_mode)
        self.task_id = 0
        self._task_status = ""
        self._artifacts = []
        self._target_ref = {}
        self._sig = _ApkSignals()
        self._sig.task_ready.connect(self._on_task_ready)
        self._sig.artifacts_ready.connect(self._on_artifacts_ready)
        self._sig.error.connect(lambda msg: QMessageBox.warning(self, "在线备份", msg))
        self._sig.download_done.connect(self._on_download_done)
        self._sig.download_error.connect(self._on_download_error)
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self, margins=(28, 20, 28, 20), spacing=14)
        layout.addWidget(PageHeader(
            "在线备份", "查看任务进度并下载备份结果", "ONLINE BACKUP"
        ))

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self.stat_login = StatCard("登录状态", "未登录", "warning")
        self.stat_task = StatCard("当前任务", "无任务", "neutral")
        self.stat_progress = StatCard("进度", "0/0", "accent")
        summary_row.addWidget(self.stat_login, 1)
        summary_row.addWidget(self.stat_task, 1)
        summary_row.addWidget(self.stat_progress, 1)
        layout.addLayout(summary_row)

        # 任务卡片
        task_card = SurfaceCard()
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(18, 16, 18, 16)
        task_layout.setSpacing(12)

        card_head = QHBoxLayout()
        card_head.setSpacing(12)
        title = QLabel("任务状态")
        title.setProperty("ui-role", "section-title")
        card_head.addWidget(title)
        card_head.addStretch()

        self.btn_refresh = QPushButton("  刷新")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.clicked.connect(self._refresh_task)
        self.btn_refresh.setEnabled(False)
        card_head.addWidget(self.btn_refresh)

        self.btn_download = QPushButton("  下载结果")
        self.btn_download.setProperty("btn-type", "primary")
        self.btn_download.clicked.connect(self._download_results)
        self.btn_download.setEnabled(False)
        card_head.addWidget(self.btn_download)
        task_layout.addLayout(card_head)

        self.login_status_label = QLabel("请先到“登录”页面完成起点账号登录")
        self.login_status_label.setProperty("ui-role", "status")
        self.login_status_label.setWordWrap(True)
        task_layout.addWidget(self.login_status_label)

        self.task_status = QLabel("没有正在进行的任务。请先搜索书籍并选择章节。")
        self.task_status.setProperty("ui-role", "status")
        self.task_status.setWordWrap(True)
        task_layout.addWidget(self.task_status)

        # debug 模式的高级目标输入
        self.target_input = QLabel()
        self.target_input.setProperty("ui-role", "status")
        self.target_input.setWordWrap(True)
        self.target_input.setVisible(self.debug_mode)
        task_layout.addWidget(self.target_input)

        layout.addWidget(task_card)

        # artifact 表格 — 仅 debug 模式显示
        self.artifact_card = SurfaceCard()
        artifact_layout = QVBoxLayout(self.artifact_card)
        artifact_layout.setContentsMargins(0, 0, 0, 0)
        self.artifacts_table = QTableWidget()
        self.artifacts_table.setColumnCount(4)
        self.artifacts_table.setHorizontalHeaderLabels(["ID", "文件名", "类型", "大小"])
        self.artifacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        artifact_layout.addWidget(self.artifacts_table)
        self.artifact_card.setVisible(self.debug_mode)
        layout.addWidget(self.artifact_card, 1)
        if not self.debug_mode:
            layout.addStretch(1)

    # ── 公开方法 ──

    def load_task(self, task_id: int, target_ref: dict = None):
        self.task_id = int(task_id or 0)
        self._target_ref = dict(target_ref or {})
        if self.task_id:
            self.stat_task.set_value("刷新中")
            self.stat_progress.set_value("--")
            self.task_status.setText(f"任务 #{self.task_id}: 正在刷新状态...")
            self._refresh_task()

    def set_login_online(self, online: bool):
        if online:
            self.login_status_label.setText("起点账号已登录，可以创建备份任务。")
            self._set_stat_card(self.stat_login, "已登录", "success")
        else:
            self.login_status_label.setText("请先到“登录”页面完成起点账号登录")
            self._set_stat_card(self.stat_login, "未登录", "warning")

    # ── 内部方法 ──

    def _run(self, func, ok_signal):
        def worker():
            try:
                ok_signal.emit(func())
            except Exception as exc:
                self._sig.error.emit(str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _set_stat_card(self, card: StatCard, value: str, accent: str):
        card.set_value(value)
        card.setProperty("accent", accent)
        card.style().unpolish(card)
        card.style().polish(card)

    def _refresh_task(self):
        if not self.task_id:
            return
        self.btn_refresh.setEnabled(False)
        self._run(lambda: self.client.get_apk_task(self.task_id), self._sig.task_ready)

    def _on_task_ready(self, data: dict):
        self.task_id = int(data.get("taskId") or self.task_id or 0)
        self._task_status = str(data.get("status", ""))
        progress = f"{data.get('progressDone', 0)}/{data.get('progressTotal', 0)}"
        task_accent = "success" if self._task_status == "completed" else "accent"
        self._set_stat_card(self.stat_task, self._task_status or "未知", task_accent)
        self.stat_progress.set_value(progress)
        self.task_status.setText(
            f"任务 #{self.task_id}: {self._task_status} ({progress})"
        )
        self.btn_refresh.setEnabled(True)
        self.btn_download.setEnabled(self._task_status == "completed")

        # debug 模式显示更多信息
        if self.debug_mode:
            self.target_input.setText(json.dumps(data, ensure_ascii=False, indent=2))

        # 自动刷新 artifacts
        if self._task_status == "completed":
            self._run(
                lambda: self.client.list_apk_task_artifacts(self.task_id),
                self._sig.artifacts_ready,
            )

    def _on_artifacts_ready(self, artifacts: list):
        self._artifacts = list(artifacts)
        self.btn_download.setEnabled(self._task_status == "completed" or len(artifacts) > 0)

        if not self.debug_mode:
            return
        self.artifacts_table.setRowCount(len(artifacts))
        for row, item in enumerate(artifacts):
            self.artifacts_table.setItem(row, 0, QTableWidgetItem(str(item.get("artifactId", ""))))
            self.artifacts_table.setItem(row, 1, QTableWidgetItem(str(item.get("filename", ""))))
            self.artifacts_table.setItem(row, 2, QTableWidgetItem(str(item.get("artifactType", ""))))
            self.artifacts_table.setItem(row, 3, QTableWidgetItem(str(item.get("sizeBytes", ""))))

    def _download_results(self):
        if not self.task_id or self._task_status != "completed":
            QMessageBox.information(self, "提示", "任务完成后才能下载结果")
            return

        save_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not save_dir:
            return

        self.btn_download.setEnabled(False)
        self.btn_download.setText("下载中...")

        def _do():
            try:
                data = self.client.download_apk_task_archive(self.task_id)
                with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                    saved_files = safe_extract_zip(zf, save_dir)
                saved_files = _rename_downloaded_chapter_files(
                    save_dir,
                    saved_files,
                    self._target_ref,
                )
                self._sig.download_done.emit(len(saved_files), save_dir)
            except Exception as e:
                self._sig.download_error.emit(str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _on_download_done(self, count: int, save_dir: str):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("  下载结果")
        QMessageBox.information(
            self, "下载完成",
            f"已保存 {count} 个文件到:\n{save_dir}"
        )

    def _on_download_error(self, message: str):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("  下载结果")
        QMessageBox.warning(self, "下载失败", message)
