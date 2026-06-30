"""高级备份面板 — 创建后查看任务状态并下载 archive."""

import io
import threading
import zipfile

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...advanced_backup import format_advanced_backup_error
from ...zip_utils import safe_extract_zip
from ..components import PageHeader, StatCard, SurfaceCard, configure_page_layout
from .apk_backup_panel import _rename_downloaded_chapter_files


DOWNLOADABLE_STATUSES = {"completed", "partial_failed", "failed"}


class _AdvancedSignals(QObject):
    tasks_ready = pyqtSignal(list)
    task_ready = pyqtSignal(dict)
    artifacts_ready = pyqtSignal(list)
    error = pyqtSignal(str)
    download_done = pyqtSignal(int, str)
    download_error = pyqtSignal(str)


class AdvancedBackupPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.task_id = 0
        self._task_status = ""
        self._target_ref = {}
        self._artifacts = []
        self._sig = _AdvancedSignals()
        self._sig.tasks_ready.connect(self._on_tasks_ready)
        self._sig.task_ready.connect(self._on_task_ready)
        self._sig.artifacts_ready.connect(self._on_artifacts_ready)
        self._sig.error.connect(self._on_error)
        self._sig.download_done.connect(self._on_download_done)
        self._sig.download_error.connect(self._on_download_error)
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self, margins=(28, 20, 28, 20), spacing=14)
        self.header = PageHeader(
            "高级备份",
            "使用服务端凭据创建高级备份，查看任务状态并下载 archive",
            "ADVANCED BACKUP",
        )
        layout.addWidget(self.header)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self.stat_tasks = StatCard("任务列表", "0", "neutral")
        self.stat_current = StatCard("当前任务", "无任务", "accent")
        self.stat_progress = StatCard("进度", "0/0", "accent")
        summary_row.addWidget(self.stat_tasks, 1)
        summary_row.addWidget(self.stat_current, 1)
        summary_row.addWidget(self.stat_progress, 1)
        layout.addLayout(summary_row)

        task_card = SurfaceCard()
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(18, 16, 18, 16)
        task_layout.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("任务状态")
        title.setProperty("ui-role", "section-title")
        head.addWidget(title)
        head.addStretch()

        self.btn_refresh_list = QPushButton("  刷新列表")
        self.btn_refresh_list.setProperty("btn-type", "secondary")
        self.btn_refresh_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_list.clicked.connect(self.refresh_tasks)
        head.addWidget(self.btn_refresh_list)

        self.btn_refresh_task = QPushButton("  刷新状态")
        self.btn_refresh_task.setProperty("btn-type", "secondary")
        self.btn_refresh_task.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_task.clicked.connect(self._refresh_task)
        self.btn_refresh_task.setEnabled(False)
        head.addWidget(self.btn_refresh_task)

        self.btn_download = QPushButton("  下载 archive")
        self.btn_download.setProperty("btn-type", "primary")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self._download_archive)
        self.btn_download.setEnabled(False)
        head.addWidget(self.btn_download)
        task_layout.addLayout(head)

        self.task_status = QLabel("尚未选择高级备份任务。可以从书籍详情页创建，或刷新历史任务。")
        self.task_status.setProperty("ui-role", "status")
        self.task_status.setWordWrap(True)
        task_layout.addWidget(self.task_status)
        layout.addWidget(task_card)

        list_card = SurfaceCard()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(4)
        self.task_table.setHorizontalHeaderLabels(["ID", "书籍", "状态", "进度"])
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        list_layout.addWidget(self.task_table)
        layout.addWidget(list_card, 1)

    def _run(self, func, ok_signal):
        def worker():
            try:
                ok_signal.emit(func())
            except Exception as exc:
                self._sig.error.emit(format_advanced_backup_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_tasks(self):
        self.btn_refresh_list.setEnabled(False)
        self._run(lambda: self.client.list_advanced_backup_tasks(limit=50), self._sig.tasks_ready)

    def load_task(self, task_id: int, target_ref: dict | None = None):
        self.task_id = int(task_id or 0)
        if target_ref:
            self._target_ref = dict(target_ref)
        if not self.task_id:
            return
        self.stat_current.set_value(f"#{self.task_id}")
        self.stat_progress.set_value("--")
        self.task_status.setText(f"任务 #{self.task_id}: 正在刷新状态...")
        self.btn_refresh_task.setEnabled(True)
        self._refresh_task()

    def _refresh_task(self):
        if not self.task_id:
            return
        self.btn_refresh_task.setEnabled(False)
        self._run(lambda: self.client.get_advanced_backup_task(self.task_id), self._sig.task_ready)

    def _on_tasks_ready(self, tasks: list):
        self.btn_refresh_list.setEnabled(True)
        self.stat_tasks.set_value(str(len(tasks)))
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            task_id = int(task.get("taskId") or 0)
            target_ref = task.get("targetRef") if isinstance(task.get("targetRef"), dict) else {}
            book_name = target_ref.get("bookName") or str(target_ref.get("bookId") or "")
            status = str(task.get("status") or "")
            progress = f"{task.get('progressDone', 0)}/{task.get('progressTotal', 0)}"
            values = [str(task_id), str(book_name), status, progress]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, task)
                self.task_table.setItem(row, col, item)
        if tasks and not self.task_id:
            self.task_table.selectRow(0)
            first = tasks[0]
            self.load_task(first.get("taskId", 0), first.get("targetRef") or {})
        elif not tasks:
            self.task_status.setText("没有高级备份任务。请先在书籍详情页选择章节并创建任务。")

    def _on_table_selection_changed(self):
        selected = self.task_table.selectedItems()
        if not selected:
            return
        task = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(task, dict):
            self.load_task(task.get("taskId", 0), task.get("targetRef") or {})

    def _on_task_ready(self, data: dict):
        self.task_id = int(data.get("taskId") or self.task_id or 0)
        if isinstance(data.get("targetRef"), dict):
            self._target_ref = data["targetRef"]
        self._task_status = str(data.get("status") or "")
        progress = f"{data.get('progressDone', 0)}/{data.get('progressTotal', 0)}"
        self.stat_current.set_value(f"#{self.task_id}" if self.task_id else "无任务")
        self.stat_progress.set_value(progress)
        error = str(data.get("error") or "")
        suffix = f"。错误: {error}" if error else ""
        self.task_status.setText(f"任务 #{self.task_id}: {self._task_status} ({progress}){suffix}")
        self.btn_refresh_task.setEnabled(True)
        self.btn_download.setEnabled(self._task_status in DOWNLOADABLE_STATUSES)
        if self._task_status in DOWNLOADABLE_STATUSES:
            self._run(
                lambda: self.client.list_advanced_backup_task_artifacts(self.task_id),
                self._sig.artifacts_ready,
            )

    def _on_artifacts_ready(self, artifacts: list):
        self._artifacts = list(artifacts)
        self.btn_download.setEnabled(
            self._task_status in DOWNLOADABLE_STATUSES or bool(self._artifacts)
        )

    def _on_error(self, message: str):
        self.btn_refresh_list.setEnabled(True)
        self.btn_refresh_task.setEnabled(bool(self.task_id))
        QMessageBox.warning(self, "高级备份", message)

    def _download_archive(self):
        if not self.task_id or self._task_status not in DOWNLOADABLE_STATUSES:
            QMessageBox.information(self, "提示", "任务完成后才能下载 archive")
            return
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not save_dir:
            return

        self.btn_download.setEnabled(False)
        self.btn_download.setText("下载中...")

        def _do():
            try:
                data = self.client.download_advanced_backup_task_archive(self.task_id)
                with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                    saved_files = safe_extract_zip(zf, save_dir)
                saved_files = _rename_downloaded_chapter_files(
                    save_dir,
                    saved_files,
                    self._target_ref,
                )
                self._sig.download_done.emit(len(saved_files), save_dir)
            except Exception as exc:
                self._sig.download_error.emit(format_advanced_backup_error(exc))

        threading.Thread(target=_do, daemon=True).start()

    def _on_download_done(self, count: int, save_dir: str):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("  下载 archive")
        QMessageBox.information(self, "下载完成", f"已保存 {count} 个文件到:\n{save_dir}")

    def _on_download_error(self, message: str):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("  下载 archive")
        QMessageBox.warning(self, "下载失败", message)
