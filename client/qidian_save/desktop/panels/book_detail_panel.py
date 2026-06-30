"""书籍详情面板 — 书籍信息 + 目录列表 + 勾选章节 + 批量备份"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QApplication, QLineEdit,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from ...qidian_client import get_catalog as qidian_catalog, load_cookies
from ...proxy import parse_proxy_urls
from ...advanced_backup import format_advanced_backup_error
from ..components import PageHeader, SurfaceCard, configure_page_layout


class _DetailSignal(QObject):
    catalog_ready = pyqtSignal(dict)
    catalog_error = pyqtSignal(str)
    backup_done = pyqtSignal(int, bool, list, object)
    advanced_backup_done = pyqtSignal(int, object)
    backup_failed = pyqtSignal(str)
    backup_finished = pyqtSignal()
    backup_warning = pyqtSignal(str)  # 可恢复的警告，不影响继续


CHK = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled


class BookDetailPanel(QWidget):
    def __init__(
        self,
        client,
        on_backup_started,
        get_apk_session_id=None,
        on_apk_task_started=None,
        on_advanced_task_started=None,
        debug_mode: bool = False,
    ):
        super().__init__()
        self.client = client
        self.debug_mode = bool(debug_mode)
        # on_backup_started(task_id, server_crawl, book_id, qd_cookies)
        self.on_backup_started = on_backup_started
        self.get_apk_session_id = get_apk_session_id or (lambda: 0)
        self.on_apk_task_started = on_apk_task_started
        self.on_advanced_task_started = on_advanced_task_started
        self.book_id = ""
        self.book_name = ""
        self._chapters = []
        self._sig = _DetailSignal()
        self._sig.catalog_ready.connect(self._on_catalog)
        self._sig.catalog_error.connect(lambda e: self.label_author.setText(f"获取目录失败: {e}"))
        self._sig.backup_done.connect(self._on_backup_done)
        self._sig.advanced_backup_done.connect(self._on_advanced_backup_done)
        self._sig.backup_failed.connect(lambda e: QMessageBox.critical(self, "创建失败", e))
        self._sig.backup_finished.connect(self._on_backup_finished)
        self._last_clicked_row = -1
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "书籍详情", "选择章节并创建在线备份任务", "BOOK WORKSPACE"
        ))

        # Book info card
        info_card = SurfaceCard()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 18, 20, 18)
        info_layout.setSpacing(6)

        self.label_title = QLabel("请先搜索并选择一本书")
        self.label_title.setProperty("ui-role", "section-title")
        info_layout.addWidget(self.label_title)

        self.label_author = QLabel("")
        self.label_author.setProperty("ui-role", "muted")
        info_layout.addWidget(self.label_author)

        self.label_chapters = QLabel("")
        self.label_chapters.setProperty("ui-role", "muted")
        info_layout.addWidget(self.label_chapters)

        layout.addWidget(info_card)

        # ── Catalog table ──
        table_frame = SurfaceCard()

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

        options = SurfaceCard()
        option_layout = QVBoxLayout(options)
        option_layout.setContentsMargins(18, 14, 18, 14)
        option_layout.setSpacing(10)

        option_title = QLabel("输出增强")
        option_title.setProperty("ui-role", "section-title")
        option_layout.addWidget(option_title)

        option_row = QHBoxLayout()
        option_row.setSpacing(16)
        self.chk_preview = QCheckBox("补全公开试读")
        self.chk_preview.setChecked(True)
        option_row.addWidget(self.chk_preview)

        self.chk_merge = QCheckBox("合并为一个 TXT")
        self.chk_merge.setChecked(False)
        option_row.addWidget(self.chk_merge)
        option_row.addStretch()
        option_layout.addLayout(option_row)

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText(
            "可选代理，逗号分隔，例如 http://127.0.0.1:7890"
        )
        self.proxy_input.setClearButtonEnabled(True)
        option_layout.addWidget(self.proxy_input)
        # 普通模式隐藏代理和 chk_preview，但保留 chk_merge
        for w in (self.chk_preview, self.proxy_input):
            w.setVisible(self.debug_mode)
        layout.addWidget(options)

        # ── Bottom controls: select-all + backup ──
        controls = SurfaceCard()
        cr = QHBoxLayout(controls)
        cr.setContentsMargins(18, 13, 18, 13)
        cr.setSpacing(12)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setProperty("btn-type", "secondary")
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        cr.addWidget(self.btn_select_all)

        self.chk_server_crawl = QCheckBox("服务器抓取")
        self.chk_server_crawl.setVisible(self.debug_mode)
        cr.addWidget(self.chk_server_crawl)

        self.chk_apk_backup = QCheckBox("在线备份")
        self.chk_apk_backup.setChecked(True)
        self.chk_apk_backup.setVisible(self.debug_mode)
        cr.addWidget(self.chk_apk_backup)

        self.label_selected = QLabel("已选 0 章")
        self.label_selected.setProperty("ui-role", "status")
        cr.addWidget(self.label_selected)

        cr.addStretch()

        self.btn_backup = QPushButton("  开始在线备份")
        self.btn_backup.setProperty("btn-type", "primary")
        self.btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_backup.clicked.connect(self._start_backup)
        cr.addWidget(self.btn_backup)

        self.btn_advanced_backup = QPushButton("  高级备份")
        self.btn_advanced_backup.setProperty("btn-type", "secondary")
        self.btn_advanced_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_advanced_backup.clicked.connect(self._start_advanced_backup_from_ui)
        cr.addWidget(self.btn_advanced_backup)

        layout.addWidget(controls)

    # ── Public ──

    def load_book(self, book_id: str, book_name: str):
        self.load_book_context(book_id, book_name)
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

    def load_book_context(self, book_id: str, book_name: str):
        self.book_id = str(book_id)
        self.book_name = str(book_name)
        self.label_title.setText(self.book_name)

    def _on_catalog(self, cat: dict):
        self.label_author.setText(f"作者: {cat.get('authorName', cat.get('author', '未知'))}")
        total = cat["totalChapters"]
        self.label_chapters.setText(f"共 {total} 章")

        chapters = cat.get("chapters", [])
        self._chapters = list(chapters)
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
        if hasattr(self, "btn_advanced_backup"):
            self.btn_advanced_backup.setEnabled(count > 0)

    # ── Backup ──

    def _backup_options(self) -> dict:
        return {
            "preview_enabled": self.chk_preview.isChecked(),
            "merge_enabled": self.chk_merge.isChecked(),
            "proxy_urls": parse_proxy_urls(self.proxy_input.text()),
            "proxy_rotate_every": 50,
        }

    def _selected_rows(self) -> list[int]:
        checked_rows = []
        for i in range(self.table.rowCount()):
            ci = self.table.item(i, 0)
            if ci and ci.checkState() == Qt.CheckState.Checked:
                checked_rows.append(i)
        return checked_rows

    def _build_apk_target_ref(self, checked_indices: list[int]) -> dict:
        chapter_ids = []
        chapter_names = {}
        chapters = []
        for row in checked_indices:
            if row < 0 or row >= len(self._chapters):
                continue
            chapter = self._chapters[row]
            raw_id = chapter.get("chapterId")
            if raw_id in (None, ""):
                continue
            chapter_id = int(raw_id)
            chapter_name = str(chapter.get("chapterName") or raw_id)
            chapter_ids.append(chapter_id)
            chapter_names[str(chapter_id)] = chapter_name
            chapters.append({
                "chapterId": str(chapter_id),
                "chapterName": chapter_name,
            })
        return {
            "bookId": self.book_id,
            "bookName": self.book_name or self.label_title.text(),
            "chapterIds": chapter_ids,
            "chapterNames": chapter_names,
            "chapters": chapters,
            "chapterIndexes": checked_indices,
            "wholeBook": False,
            "downloadMode": "batch",
            "timeout": 60,
            "mergeText": self.chk_merge.isChecked(),
        }

    def _build_advanced_target_ref(self, checked_indices: list[int]) -> dict:
        try:
            book_id = int(self.book_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("bookId 必须是数字") from exc

        chapter_ids = []
        chapter_names = {}
        chapters = []
        for row in checked_indices:
            if row < 0 or row >= len(self._chapters):
                continue
            chapter = self._chapters[row]
            raw_id = chapter.get("chapterId")
            if raw_id in (None, ""):
                continue
            chapter_id = int(raw_id)
            chapter_name = str(chapter.get("chapterName") or raw_id)
            chapter_ids.append(chapter_id)
            chapter_names[str(chapter_id)] = chapter_name
            chapters.append({
                "chapterId": str(chapter_id),
                "chapterName": chapter_name,
            })
        return {
            "bookId": book_id,
            "bookName": self.book_name or self.label_title.text(),
            "chapterIds": chapter_ids,
            "chapterNames": chapter_names,
            "chapters": chapters,
            "chapterIndexes": checked_indices,
            "wholeBook": False,
            "mergeText": self.chk_merge.isChecked(),
            "timeout": 60,
        }

    def _start_apk_backup(self, checked_indices: list[int]):
        session_id = int(self.get_apk_session_id() or 0)
        if not session_id:
            QMessageBox.warning(self, "提示", "请先到“登录”页面完成起点账号登录")
            return
        try:
            target_ref = self._build_apk_target_ref(checked_indices)
        except (TypeError, ValueError):
            QMessageBox.warning(self, "提示", "目录里存在无效章节 ID，无法创建 APK 备份")
            return
        if not target_ref["chapterIds"]:
            QMessageBox.warning(self, "提示", "没有可提交的章节 ID")
            return
        self.btn_backup.setEnabled(False)
        self.btn_backup.setText("创建任务...")

        def _do():
            try:
                result = self.client.create_apk_backup_task(session_id, target_ref)
                task_id = result["taskId"]
                if self.on_apk_task_started:
                    self.on_apk_task_started(task_id, target_ref)
            except Exception as e:
                print(f"[detail] APK 备份创建异常: {e}", file=sys.stderr)
                self._sig.backup_failed.emit(str(e))
            finally:
                self._sig.backup_finished.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _start_advanced_backup_from_ui(self):
        if not self.book_id:
            QMessageBox.warning(self, "提示", "请先选择一本书")
            return
        checked_rows = self._selected_rows()
        if not checked_rows:
            QMessageBox.warning(self, "提示", "请先勾选要备份的章节")
            return
        self._start_advanced_backup(sorted(checked_rows))

    def _start_advanced_backup(self, checked_indices: list[int]):
        try:
            target_ref = self._build_advanced_target_ref(checked_indices)
        except (TypeError, ValueError):
            QMessageBox.warning(self, "提示", "目录里存在无效书籍或章节 ID，无法创建高级备份")
            return
        if not target_ref["chapterIds"]:
            QMessageBox.warning(self, "提示", "没有可提交的章节 ID")
            return

        self.btn_backup.setEnabled(False)
        self.btn_advanced_backup.setEnabled(False)
        self.btn_advanced_backup.setText("创建任务...")

        def _do():
            try:
                result = self.client.create_advanced_backup_task(target_ref)
                task_id = result["taskId"]
                self._sig.advanced_backup_done.emit(task_id, target_ref)
            except Exception as e:
                print(f"[detail] 高级备份创建异常: {e}", file=sys.stderr)
                self._sig.backup_failed.emit(format_advanced_backup_error(e))
            finally:
                self._sig.backup_finished.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _start_backup(self):
        if not self.book_id:
            QMessageBox.warning(self, "提示", "请先选择一本书")
            return

        checked_rows = self._selected_rows()

        if not checked_rows:
            QMessageBox.warning(self, "提示", "请先勾选要备份的章节")
            return

        # 传递实际勾选的行号（0-based），不再转换为 start/end 范围
        checked_indices = sorted(checked_rows)
        if (not self.debug_mode) or self.chk_apk_backup.isChecked():
            self._start_apk_backup(checked_indices)
            return

        # 服务端爬取：服务端只认 start/end 范围，非连续选取只能走最小-最大范围
        # 本地爬取：客户端用 checked_indices 精确过滤，只爬勾选的章节
        start = checked_indices[0] + 1
        end = checked_indices[-1] + 1

        self.btn_backup.setEnabled(False)
        self.btn_backup.setText("创建任务...")

        server_crawl = self.chk_server_crawl.isChecked()
        try:
            backup_options = self._backup_options()
        except ValueError as exc:
            QMessageBox.warning(self, "代理配置错误", str(exc))
            self._sig.backup_finished.emit()
            return

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
                self._sig.backup_done.emit(
                    task_id, server_crawl, checked_indices, backup_options
                )
            except Exception as e:
                print(f"[detail] 备份创建异常: {e}", file=sys.stderr)
                self._sig.backup_failed.emit(str(e))
            finally:
                self._sig.backup_finished.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _on_backup_finished(self):
        self.btn_backup.setEnabled(True)
        self.btn_backup.setText("  开始在线备份")
        if hasattr(self, "btn_advanced_backup"):
            self.btn_advanced_backup.setEnabled(True)
            self.btn_advanced_backup.setText("  高级备份")
        self._update_selected_count()

    def _on_backup_done(
        self,
        task_id: int,
        server_crawl: bool,
        checked_indices: list,
        backup_options: dict,
    ):
        qd_cookies = load_cookies()
        self.on_backup_started(
            task_id,
            server_crawl,
            self.book_id,
            qd_cookies,
            checked_indices,
            backup_options,
        )

    def _on_advanced_backup_done(self, task_id: int, target_ref: dict):
        if self.on_advanced_task_started:
            self.on_advanced_task_started(task_id, target_ref)
