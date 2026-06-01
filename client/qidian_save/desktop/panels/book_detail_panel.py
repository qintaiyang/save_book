"""书籍详情面板 — 书籍信息 + 目录列表 + 勾选章节 + 批量备份"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QCheckBox, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from ...qidian_client import get_catalog as qidian_catalog, load_cookies


class _DetailSignal(QObject):
    catalog_ready = pyqtSignal(dict)
    catalog_error = pyqtSignal(str)
    backup_done = pyqtSignal(int, bool, list)  # (task_id, is_server_crawl, checked_indices)
    backup_failed = pyqtSignal(str)
    backup_finished = pyqtSignal()
    backup_warning = pyqtSignal(str)  # 可恢复的警告，不影响继续


CHK = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled


class BookDetailPanel(QWidget):
    def __init__(self, client, on_backup_started):
        super().__init__()
        self.client = client
        # on_backup_started(task_id, server_crawl, book_id, qd_cookies)
        self.on_backup_started = on_backup_started
        self.book_id = ""
        self._sig = _DetailSignal()
        self._sig.catalog_ready.connect(self._on_catalog)
        self._sig.catalog_error.connect(lambda e: self.label_author.setText(f"获取目录失败: {e}"))
        self._sig.backup_done.connect(self._on_backup_done)
        self._sig.backup_failed.connect(lambda e: QMessageBox.critical(self, "创建失败", e))
        self._sig.backup_finished.connect(self._on_backup_finished)
        self._last_clicked_row = -1
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QLabel("书籍详情")
        header.setProperty("widget-type", "panel-title")
        layout.addWidget(header)

        # Book info card
        info_card = QFrame()
        info_card.setStyleSheet("background: white; border-radius: 12px; padding: 20px;")
        info_layout = QVBoxLayout(info_card)
        info_layout.setSpacing(6)

        self.label_title = QLabel("请先搜索并选择一本书")
        self.label_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1f2937;")
        info_layout.addWidget(self.label_title)

        self.label_author = QLabel("")
        self.label_author.setStyleSheet("font-size: 13px; color: #6b7280;")
        info_layout.addWidget(self.label_author)

        self.label_chapters = QLabel("")
        self.label_chapters.setStyleSheet("font-size: 13px; color: #6b7280;")
        info_layout.addWidget(self.label_chapters)

        layout.addWidget(info_card)

        # ── Catalog table ──
        table_frame = QFrame()
        table_frame.setStyleSheet("background: white; border-radius: 12px;")

        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["", "章节名", "状态"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.itemClicked.connect(self._on_item_clicked)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        tl.addWidget(self.table)
        layout.addWidget(table_frame, 1)

        # ── Bottom controls: select-all + backup ──
        controls = QFrame()
        controls.setStyleSheet("background: white; border-radius: 12px; padding: 16px;")
        cr = QHBoxLayout(controls)
        cr.setSpacing(12)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setProperty("btn-type", "secondary")
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        cr.addWidget(self.btn_select_all)

        self.chk_server_crawl = QCheckBox("服务器抓取")
        self.chk_server_crawl.setStyleSheet("font-size: 12px; color: #6b7280;")
        cr.addWidget(self.chk_server_crawl)

        self.label_selected = QLabel("已选 0 章")
        self.label_selected.setStyleSheet("font-size: 13px; color: #6b7280;")
        cr.addWidget(self.label_selected)

        cr.addStretch()

        self.btn_backup = QPushButton("  开始备份")
        self.btn_backup.setProperty("btn-type", "secondary")
        self.btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_backup.clicked.connect(self._start_backup)
        cr.addWidget(self.btn_backup)

        layout.addWidget(controls)

    # ── Public ──

    def load_book(self, book_id: str, book_name: str):
        self.book_id = book_id
        self.label_title.setText(book_name)
        self.label_author.setText("加载中...")
        self.table.setRowCount(0)
        self._last_clicked_row = -1

        def _load():
            try:
                qd_cookies = load_cookies()
                cat = qidian_catalog(book_id, cookies=qd_cookies or None)
                self._sig.catalog_ready.emit(cat)
            except Exception as e:
                print(f"[detail] 目录加载异常: {e}", file=sys.stderr)
                self._sig.catalog_error.emit(str(e))

        threading.Thread(target=_load, daemon=True).start()

    def _on_catalog(self, cat: dict):
        self.label_author.setText(f"作者: {cat.get('authorName', cat.get('author', '未知'))}")
        total = cat["totalChapters"]
        self.label_chapters.setText(f"共 {total} 章")

        chapters = cat.get("chapters", [])
        self.table.setRowCount(len(chapters))
        for i, ch in enumerate(chapters):
            chk = QTableWidgetItem("")
            chk.setFlags(CHK)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, i)  # row index for shift-click
            self.table.setItem(i, 0, chk)

            self.table.setItem(i, 1, QTableWidgetItem(ch["chapterName"]))

            bought = "已购" if (not ch.get("isVip") or ch.get("isBuy")) else "未购"
            item_b = QTableWidgetItem(bought)
            item_b.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, item_b)

        self._update_selected_count()
        self.btn_select_all.setText("全选")

    # ── Selection ──

    def _on_item_clicked(self, item):
        """处理点击：Qt 自动切换复选框状态，此处处理 Shift 连选"""
        if item.column() != 0:
            return

        row = item.row()
        shift_held = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier

        if shift_held and self._last_clicked_row >= 0 and self._last_clicked_row != row:
            # 以锚点（第一个点击的行）状态为准填充区间
            # （Qt 已自动切换了当前点击的行，我们覆盖回去）
            anchor_item = self.table.item(self._last_clicked_row, 0)
            target_state = anchor_item.checkState()
            r1, r2 = min(self._last_clicked_row, row), max(self._last_clicked_row, row)
            for r in range(r1, r2 + 1):
                ci = self.table.item(r, 0)
                if ci:
                    ci.setCheckState(target_state)

        self._last_clicked_row = row
        QTimer.singleShot(0, self._update_selected_count)

    def _toggle_select_all(self):
        """全选/取消"""
        all_checked = True
        for i in range(self.table.rowCount()):
            ci = self.table.item(i, 0)
            if ci and ci.checkState() != Qt.CheckState.Checked:
                all_checked = False
                break

        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for i in range(self.table.rowCount()):
            ci = self.table.item(i, 0)
            if ci:
                ci.setCheckState(new_state)

        self._update_selected_count()
        self.btn_select_all.setText("取消全选" if new_state == Qt.CheckState.Checked else "全选")

    def _update_selected_count(self):
        count = 0
        for i in range(self.table.rowCount()):
            ci = self.table.item(i, 0)
            if ci and ci.checkState() == Qt.CheckState.Checked:
                count += 1
        self.label_selected.setText(f"已选 {count} 章")
        self.btn_backup.setEnabled(count > 0)

    # ── Backup ──

    def _start_backup(self):
        if not self.book_id:
            QMessageBox.warning(self, "提示", "请先选择一本书")
            return

        checked_rows = []
        for i in range(self.table.rowCount()):
            ci = self.table.item(i, 0)
            if ci and ci.checkState() == Qt.CheckState.Checked:
                checked_rows.append(i)

        if not checked_rows:
            QMessageBox.warning(self, "提示", "请先勾选要备份的章节")
            return

        # 传递实际勾选的行号（0-based），不再转换为 start/end 范围
        checked_indices = sorted(checked_rows)

        # 服务端爬取：服务端只认 start/end 范围，非连续选取只能走最小-最大范围
        # 本地爬取：客户端用 checked_indices 精确过滤，只爬勾选的章节
        start = checked_indices[0] + 1
        end = checked_indices[-1] + 1

        self.btn_backup.setEnabled(False)
        self.btn_backup.setText("创建任务...")

        server_crawl = self.chk_server_crawl.isChecked()

        # Cookie 准备（主线程，可弹对话框）
        qd_cookies = load_cookies()
        cookies_ref = ""
        try:
            cr = self.client.upload_qidian_cookies(qd_cookies)
            cookies_ref = cr.get("cookiesRef", "")
        except Exception as e:
            ret = QMessageBox.warning(
                self, "Cookie 上传失败",
                f"Cookie 上传失败: {e}\n\n"
                "付费章节可能无法解码。是否继续备份？\n"
                "（选「否」取消操作，仅免费章节可正常下载）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                self._sig.backup_finished.emit()
                return

        def _do():
            try:
                if server_crawl:
                    result = self.client.start_backup(self.book_id, start, end,
                                                      cookies_ref=cookies_ref,
                                                      server_crawl=True,
                                                      chapter_ids=checked_indices)
                else:
                    result = self.client.start_backup(self.book_id, start, end,
                                                      cookies_ref=cookies_ref,
                                                      server_crawl=False,
                                                      chapter_ids=checked_indices)
                task_id = result["taskId"]
                self._sig.backup_done.emit(task_id, server_crawl, checked_indices)
            except Exception as e:
                print(f"[detail] 备份创建异常: {e}", file=sys.stderr)
                self._sig.backup_failed.emit(str(e))
            finally:
                self._sig.backup_finished.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _on_backup_finished(self):
        self.btn_backup.setEnabled(True)
        self.btn_backup.setText("  开始备份")

    def _on_backup_done(self, task_id: int, server_crawl: bool, checked_indices: list):
        qd_cookies = load_cookies()
        self.on_backup_started(task_id, server_crawl, self.book_id, qd_cookies, checked_indices)
