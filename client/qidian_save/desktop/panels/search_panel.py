"""搜索书籍面板 — 关键词搜索 + 结果列表 + 跳转到详情"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from ...qidian_client import search_books as qidian_search


class _SearchSignal(QObject):
    results_ready = pyqtSignal(list)
    search_error = pyqtSignal(str)
    search_done = pyqtSignal()


class SearchPanel(QWidget):
    def __init__(self, client, on_select_book):
        super().__init__()
        self.client = client
        self.on_select_book = on_select_book
        self._results_data = []  # [{id, name}, ...]
        self._sig = _SearchSignal()
        self._sig.results_ready.connect(self._on_results)
        self._sig.search_error.connect(lambda e: self.status_label.setText(f"搜索失败: {e}"))
        self._sig.search_done.connect(self._on_search_done)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QLabel("搜索书籍")
        header.setProperty("widget-type", "panel-title")
        layout.addWidget(header)

        # Search input row
        search_bg = QFrame()
        search_bg.setStyleSheet("background: white; border-radius: 12px; padding: 20px;")
        sr = QHBoxLayout(search_bg)
        sr.setSpacing(12)

        self.input_keyword = QLineEdit()
        self.input_keyword.setPlaceholderText("输入书名、作者或关键词...")

        self.input_keyword.returnPressed.connect(self._do_search)
        sr.addWidget(self.input_keyword, 1)

        self.btn_search = QPushButton("  搜索")

        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.clicked.connect(self._do_search)
        sr.addWidget(self.btn_search)

        layout.addWidget(search_bg)

        # Results table
        table_frame = QFrame()
        table_frame.setStyleSheet("background: white; border-radius: 12px;")

        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书籍 ID", "书名", "作者", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.table.cellClicked.connect(self._on_cell_clicked)
        tl.addWidget(self.table)

        layout.addWidget(table_frame, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
        layout.addWidget(self.status_label)

    def _do_search(self):
        keyword = self.input_keyword.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中...")
        self.status_label.setText("正在搜索...")
        self.table.setRowCount(0)

        def _search():
            try:
                print(f"[search] 开始搜索: {keyword}", file=sys.stderr)
                results = qidian_search(keyword)
                print(f"[search] 结果数量: {len(results)}", file=sys.stderr)
                self._sig.results_ready.emit(results)
            except Exception as e:
                print(f"[search] 异常: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._sig.search_error.emit(str(e))
            finally:
                self._sig.search_done.emit()

        threading.Thread(target=_search, daemon=True).start()

    def _on_results(self, results: list):
        self._results_data = [{"id": r["bookId"], "name": r["bookName"]} for r in results]
        self.table.setRowCount(len(results))
        for i, r in enumerate(results):
            self.table.setItem(i, 0, QTableWidgetItem(r["bookId"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["bookName"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["authorName"]))

            item = QTableWidgetItem("查看详情 →")
            item.setForeground(QColor("#007aff"))
            item.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
            self.table.setItem(i, 3, item)

        self.status_label.setText(f"找到 {len(results)} 个结果")

    def _on_cell_clicked(self, row: int, col: int):
        """点击操作列（col=3）的蓝字详情 → 跳转。"""
        if col == 3 and row < len(self._results_data):
            book = self._results_data[row]
            self.on_select_book(book["id"], book["name"])

    def _on_search_done(self):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("  搜索")
