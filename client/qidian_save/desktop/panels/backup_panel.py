"""在线备份面板 — 任务进度 + 章节列表 + 下载"""
import io, json, os, threading, time, zipfile
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from ... import DATA_DIR
from ...zip_utils import safe_extract_zip, sanitize_filename


class _DownloadSignals(QObject):
    """下载线程 → UI 主线程的信号桥梁"""
    progress = pyqtSignal(int, int)   # (已下载, 总数)
    finished = pyqtSignal(int, int)   # (成功数, 失败数)
    error = pyqtSignal(str)           # 单个章节下载出错


class _CrawlSignals(QObject):
    """本地爬取线程 → UI 主线程的信号"""
    progress = pyqtSignal(int, int, str)  # (当前, 总数, 状态文字)
    batch_done = pyqtSignal(int, str)     # (当前批完成数, 信息)
    finished = pyqtSignal(int, int)       # (成功数, 失败数)
    error = pyqtSignal(str)


class _PollSignals(QObject):
    """轮询线程 → UI 主线程的信号"""
    status_ready = pyqtSignal(int, int, dict)  # (task_id, generation, status)
    error = pyqtSignal(str)


class BackupPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.task_id = 0
        self.task_info = {}
        self._polling = False
        self._server_crawl = True   # default to old flow
        self._book_id = ""
        self._qd_cookies = {}
        self._download_sig = _DownloadSignals()
        self._download_sig.progress.connect(self._on_dl_progress)
        self._download_sig.finished.connect(self._on_dl_finished)
        self._download_sig.error.connect(self._on_dl_error)
        self._crawl_sig = _CrawlSignals()
        self._crawl_sig.progress.connect(self._on_crawl_progress)
        self._crawl_sig.batch_done.connect(self._on_crawl_batch_done)
        self._crawl_sig.finished.connect(self._on_crawl_finished)
        self._crawl_sig.error.connect(self._on_crawl_error)
        self._poll_sig = _PollSignals()
        self._poll_sig.status_ready.connect(self._on_poll_status)
        self._poll_sig.error.connect(self._on_poll_error)
        self._poll_in_flight = False
        self._poll_gen = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_task)
        self.destroyed.connect(self._stop_polling)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QLabel("在线备份")
        header.setProperty("widget-type", "panel-title")
        layout.addWidget(header)

        # Task info card
        info_card = QFrame()
        info_card.setStyleSheet("background: white; border-radius: 12px; padding: 20px;")
        il = QVBoxLayout(info_card)
        il.setSpacing(8)

        self.label_book = QLabel("请先创建备份任务")
        self.label_book.setStyleSheet("font-size: 16px; font-weight: bold; color: #1f2937;")
        il.addWidget(self.label_book)

        self.label_status = QLabel("")
        self.label_status.setStyleSheet("font-size: 13px; color: #6b7280;")
        il.addWidget(self.label_status)

        # Progress bar
        progress_header = QHBoxLayout()
        progress_header.addWidget(QLabel("备份进度:"))
        self.label_progress_text = QLabel("0 / 0")
        self.label_progress_text.setStyleSheet("font-size: 13px; color: #374151;")
        progress_header.addWidget(self.label_progress_text)
        progress_header.addStretch()
        il.addLayout(progress_header)

        self.progress = QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none; border-radius: 6px;
                background: #e5e7eb; height: 12px; text-align: center;
                font-size: 10px; color: #374151;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 6px;
            }
        """)
        self.progress.setValue(0)
        il.addWidget(self.progress)

        layout.addWidget(info_card)

        # Chapters table
        table_frame = QFrame()
        table_frame.setStyleSheet("background: white; border-radius: 12px;")
        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["章节 ID", "章节名", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        tl.addWidget(self.table)
        layout.addWidget(table_frame, 1)

        # Bottom controls
        controls = QFrame()
        controls.setStyleSheet("background: white; border-radius: 12px; padding: 12px;")
        cr = QHBoxLayout(controls)

        self.btn_refresh = QPushButton("  刷新")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._poll_task)
        cr.addWidget(self.btn_refresh)

        self.btn_download_all = QPushButton("  下载全部")
        self.btn_download_all.setProperty("btn-type", "secondary")
        self.btn_download_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_all.clicked.connect(self._download_all)
        cr.addWidget(self.btn_download_all)

        self.label_dl_progress = QLabel("")
        self.label_dl_progress.setStyleSheet("font-size: 12px; color: #374151; padding: 0 8px;")
        cr.addWidget(self.label_dl_progress)

        self.btn_cleanup = QPushButton("  清理任务")
        self.btn_cleanup.setProperty("btn-type", "secondary")
        self.btn_cleanup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cleanup.clicked.connect(self._cleanup)
        cr.addWidget(self.btn_cleanup)

        cr.addStretch()
        layout.addWidget(controls)

    def load_task(self, task_id: int, server_crawl: bool = True,
                  book_id: str = "", qd_cookies: dict = None,
                  checked_indices: list = None):
        self._stop_polling()
        self.task_id = task_id
        self._server_crawl = server_crawl
        self._book_id = book_id
        self._qd_cookies = qd_cookies or {}
        self._checked_indices = checked_indices or []
        self._crawling = False
        self.table.setRowCount(0)
        if server_crawl:
            self._start_polling()
        else:
            self._start_local_crawl()

    def _start_polling(self):
        if self._polling:
            return
        self._polling = True
        self._poll_task()
        self._poll_timer.start(3000)

    def _poll_task(self):
        if not self.task_id or not self._polling or self._poll_in_flight:
            return

        task_id = self.task_id
        gen = self._poll_gen
        self._poll_in_flight = True

        def _run():
            try:
                status = self.client.get_task(task_id)
            except Exception as e:
                self._poll_sig.error.emit(str(e))
                return
            self._poll_sig.status_ready.emit(task_id, gen, status)

        threading.Thread(target=_run, daemon=True).start()

    def _on_poll_status(self, task_id: int, gen: int, status: dict):
        self._poll_in_flight = False
        if task_id != self.task_id or gen != self._poll_gen:
            return
        self.task_info = status
        total = status["totalChapters"]
        completed = status["completedChapters"]
        failed = status["failedChapters"]

        self.label_book.setText(f"{status.get('bookName', '')} ({status.get('bookId', '')})")
        self.label_status.setText(f"状态: {status['status']}  完成: {completed}  失败: {failed}")
        self.label_progress_text.setText(f"{completed} / {total}")
        self.progress.setMaximum(total)
        self.progress.setValue(completed)

        if status["status"] in ("completed", "failed"):
            self._polling = False
            self._poll_timer.stop()

    def _on_poll_error(self, msg: str):
        self._poll_in_flight = False
        self.label_status.setText(f"查询失败: {msg}")

    def _start_local_crawl(self):
        """启动本地爬取线程（通过共享引擎）"""
        if self._crawling:
            return
        self._crawling = True
        self.label_book.setText(f"正在本地爬取... (任务 #{self.task_id})")
        self.label_status.setText("准备中...")

        def _do():
            from ...qidian_client import get_catalog as qidian_catalog
            from ...local_crawl_engine import local_crawl

            try:
                cat = qidian_catalog(self._book_id, cookies=self._qd_cookies)
                if not cat or not cat.get("chapters"):
                    self._crawl_sig.error.emit("获取目录失败")
                    return

                chapters = cat["chapters"]
                if self._checked_indices:
                    target = [chapters[i] for i in self._checked_indices if i < len(chapters)]
                else:
                    target = chapters

                if not target:
                    self._crawl_sig.finished.emit(0, 0)
                    return

                # 包装 Qt 信号为回调
                def _on_progress(cur, total, msg):
                    self._crawl_sig.progress.emit(cur, total, msg)

                def _on_batch_done(count, msg):
                    self._crawl_sig.batch_done.emit(count, msg)

                success, failed = local_crawl(
                    client=self.client, task_id=self.task_id,
                    book_id=self._book_id, chapters=target,
                    qd_cookies=self._qd_cookies,
                    batch_size=50, delay=1.5,
                    on_progress=_on_progress,
                    on_batch_done=_on_batch_done,
                )

                self._crawl_sig.finished.emit(success, failed)

            except Exception as e:
                self._crawl_sig.error.emit(str(e))
            finally:
                self._crawling = False

        import threading
        threading.Thread(target=_do, daemon=True).start()

    def _download_all(self):
        if not self.task_id:
            return

        # 自动保存到 client/data/<BookName>_<bookId>/
        book_name = self.task_info.get('bookName', 'book')
        book_id = self.task_info.get('bookId', self.task_id)
        self._download_dir = str(DATA_DIR / f"{book_name}_{book_id}")
        os.makedirs(self._download_dir, exist_ok=True)

        self.btn_download_all.setEnabled(False)
        self.btn_download_all.setText("下载中...")
        self.label_dl_progress.setText("准备中...")

        def _do():
            success = 0
            failed = 0
            chapters = []
            try:
                chapters = self.client.list_chapters(self.task_id)
                total = len(chapters)
            except Exception as e:
                self._download_sig.error.emit(f"获取章节列表失败: {e}")
                self._download_sig.finished.emit(0, 0)
                return

            for idx, ch in enumerate(chapters):
                cid = ch.get("chapterId", "?")
                cname = ch.get("chapterName", cid)
                has_html = ch.get("hasHtml", False)
                try:
                    safe_name = sanitize_filename(cname)
                    if has_html:
                        content = self.client.download_chapter(
                            self.task_id, cid, format="html"
                        )
                        ext = ".html"
                    else:
                        data = self.client.download_chapter(
                            self.task_id, cid, format="text"
                        )
                        content = data["decodedText"]
                        ext = ".txt"
                    path = os.path.join(self._download_dir, f"{safe_name}{ext}")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    success += 1
                except Exception as e:
                    failed += 1
                    self._download_sig.error.emit(
                        f"章节 {cname} 下载失败: {e}"
                    )
                self._download_sig.progress.emit(success + failed, total)

            self._download_sig.finished.emit(success, failed)

        threading.Thread(target=_do, daemon=True).start()

    def _on_dl_error(self, msg: str):
        """单次下载失败 — 追加到进度标签，不弹模态对话框"""
        current = self.label_dl_progress.text()
        if msg not in current:
            self.label_dl_progress.setText(msg[:80])

    def _on_dl_progress(self, current: int, total: int):
        self.btn_download_all.setText(f"下载中 ({current}/{total})")
        self.label_dl_progress.setText(f"已下载: {current}/{total}")

    def _on_dl_finished(self, success: int, failed: int):
        self.btn_download_all.setEnabled(True)
        self.btn_download_all.setText("  下载全部")
        if failed == 0 and success > 0:
            self.label_dl_progress.setText(f"✅ 全部下载完成 ({success} 章)")
            # 自动打开目录
            if hasattr(self, '_download_dir') and os.path.isdir(self._download_dir):
                try:
                    os.startfile(self._download_dir)
                except Exception:
                    pass
        elif failed > 0 and success > 0:
            self.label_dl_progress.setText(f"⚠️ 完成 {success} 章，{failed} 章失败")
        elif failed > 0:
            self.label_dl_progress.setText(f"❌ 全部失败 ({failed} 章)")
        else:
            self.label_dl_progress.setText("")

    def _on_crawl_progress(self, current: int, total: int, msg: str):
        self.label_status.setText(msg)
        self.label_progress_text.setText(f"{current} / {total}")
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def _on_crawl_batch_done(self, count: int, info: str):
        self.label_dl_progress.setText(info)

    def _on_crawl_error(self, msg: str):
        self.label_status.setText(f"爬取失败: {msg}")

    def _on_crawl_finished(self, success: int, failed: int):
        if failed == 0 and success > 0:
            self.label_status.setText(f"全部完成 ({success} 章)")
        elif failed > 0 and success > 0:
            self.label_status.setText(f"完成 {success} 章, {failed} 章失败")
        elif failed > 0:
            self.label_status.setText(f"全部失败 ({failed} 章)")
        else:
            self.label_status.setText("无章节可处理")

    def _stop_polling(self):
        """停止轮询定时器，清空状态。面板销毁或清理时调用。"""
        self._polling = False
        self._poll_in_flight = False
        self._poll_gen += 1
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()

    def _cleanup(self):
        if not self.task_id:
            return
        try:
            self._stop_polling()
            self.client.cleanup_task(self.task_id)
            self.label_book.setText("任务已清理")
            self.label_status.setText("")
            self.progress.setValue(0)
            self.table.setRowCount(0)
        except Exception as e:
            QMessageBox.warning(self, "清理失败", str(e))
