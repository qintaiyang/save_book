"""在线备份面板 — 只显示任务状态、进度、下载结果"""

import json
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QLabel, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from ..components import PageHeader, SurfaceCard, configure_page_layout


class _ApkSignals(QObject):
    task_ready = pyqtSignal(dict)
    artifacts_ready = pyqtSignal(list)
    error = pyqtSignal(str)


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
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "在线备份", "查看任务状态、进度和下载备份结果", "ONLINE BACKUP"
        ))

        # 任务卡片
        task_card = SurfaceCard()
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(20, 18, 20, 18)
        task_layout.setSpacing(10)

        self.login_status_label = QLabel("请先到“登录”页面完成起点账号登录")
        self.login_status_label.setProperty("ui-role", "status")
        self.login_status_label.setWordWrap(True)
        task_layout.addWidget(self.login_status_label)

        self.task_status = QLabel("没有正在进行的任务。请先搜索书籍并选择章节。")
        self.task_status.setProperty("ui-role", "status")
        self.task_status.setWordWrap(True)
        task_layout.addWidget(self.task_status)

        action_row = QHBoxLayout()
        self.btn_refresh = QPushButton("  刷新任务")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.clicked.connect(self._refresh_task)
        self.btn_refresh.setEnabled(False)
        action_row.addWidget(self.btn_refresh)

        self.btn_download = QPushButton("  下载结果")
        self.btn_download.setProperty("btn-type", "primary")
        self.btn_download.clicked.connect(self._download_results)
        self.btn_download.setEnabled(False)
        action_row.addWidget(self.btn_download)

        action_row.addStretch()
        task_layout.addLayout(action_row)

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

    # ── 公开方法 ──

    def load_task(self, task_id: int, target_ref: dict = None):
        self.task_id = int(task_id or 0)
        self._target_ref = dict(target_ref or {})
        if self.task_id:
            self.task_status.setText(f"任务 #{self.task_id}: 正在刷新状态...")
            self._refresh_task()

    def set_login_online(self, online: bool):
        if online:
            self.login_status_label.setText("起点账号已登录，可以创建备份任务。")
        else:
            self.login_status_label.setText("请先到“登录”页面完成起点账号登录")

    # ── 内部方法 ──

    def _run(self, func, ok_signal):
        def worker():
            try:
                ok_signal.emit(func())
            except Exception as exc:
                self._sig.error.emit(str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_task(self):
        if not self.task_id:
            return
        self.btn_refresh.setEnabled(False)
        self._run(lambda: self.client.get_apk_task(self.task_id), self._sig.task_ready)

    def _on_task_ready(self, data: dict):
        self.task_id = int(data.get("taskId") or self.task_id or 0)
        self._task_status = str(data.get("status", ""))
        progress = f"{data.get('progressDone', 0)}/{data.get('progressTotal', 0)}"
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
        self.btn_download.setEnabled(len(artifacts) > 0)

        if not self.debug_mode:
            return
        self.artifacts_table.setRowCount(len(artifacts))
        for row, item in enumerate(artifacts):
            self.artifacts_table.setItem(row, 0, QTableWidgetItem(str(item.get("artifactId", ""))))
            self.artifacts_table.setItem(row, 1, QTableWidgetItem(str(item.get("filename", ""))))
            self.artifacts_table.setItem(row, 2, QTableWidgetItem(str(item.get("artifactType", ""))))
            self.artifacts_table.setItem(row, 3, QTableWidgetItem(str(item.get("sizeBytes", ""))))

    def _download_results(self):
        if not self._artifacts:
            QMessageBox.information(self, "提示", "暂无可下载结果，请刷新任务")
            return

        # Filter artifacts: only download text artifacts (skip .qd, metadata, etc.)
        merge_text = bool(self._target_ref.get("mergeText"))
        text_artifacts = [
            a for a in self._artifacts
            if a.get("artifactType") in ("text", "") or a.get("filename", "").endswith(".txt")
        ]

        if not text_artifacts:
            QMessageBox.information(self, "提示", "暂无可下载的章节文本结果")
            return

        # If mergeText is true, pick the merge artifact (largest text file)
        if merge_text:
            selected = max(text_artifacts, key=lambda a: a.get("sizeBytes", 0))
            text_artifacts = [selected]

        save_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not save_dir:
            return

        saved_files = []
        for art in text_artifacts:
            artifact_id = art.get("artifactId")
            filename = art.get("filename", f"chapter_{artifact_id}.txt")
            try:
                data = self.client.download_apk_artifact(self.task_id, artifact_id)
                dest = Path(save_dir) / filename
                if isinstance(data, bytes):
                    dest.write_bytes(data)
                else:
                    dest.write_text(str(data), encoding="utf-8")
                saved_files.append(str(dest))
            except Exception as e:
                QMessageBox.warning(self, "下载失败", f"{filename}: {e}")

        if saved_files:
            QMessageBox.information(
                self, "下载完成",
                f"已保存 {len(saved_files)} 个文件到:\n{save_dir}"
            )
