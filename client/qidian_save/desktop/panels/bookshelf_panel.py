"""书架面板 — 显示起点账号的书架，选择书籍跳转到详情"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from ...qidian_client import get_bookshelf, load_cookies
from ..components import PageHeader, SurfaceCard, configure_page_layout
from ..theme import DARK_TOKENS


class _BookshelfSignal(QObject):
    books_ready = pyqtSignal(list)
    books_error = pyqtSignal(str)
    no_cookies = pyqtSignal()


class BookshelfPanel(QWidget):
    def __init__(self, client, on_select_book):
        super().__init__()
        self.client = client
        self.on_select_book = on_select_book
        self._books_data = []  # [{id, name}, ...] 用于 cellClicked 查找
        self._sig = _BookshelfSignal()
        self._sig.books_ready.connect(self._on_books)
        self._sig.books_error.connect(lambda e: self.status_label.setText(f"加载失败: {e}"))
        self._sig.no_cookies.connect(self._on_no_cookies)
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "我的书架",
            "扫码登录后可查看账号书架并选择书籍备份",
            "QIDIAN LIBRARY",
        ))

        # Toolbar
        toolbar = SurfaceCard()
        tr = QHBoxLayout(toolbar)
        tr.setContentsMargins(18, 12, 18, 12)
        tr.setSpacing(12)

        self.btn_refresh = QPushButton("  刷新书架")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._load_bookshelf)
        tr.addWidget(self.btn_refresh)

        tr.addStretch()
        self.status_label = QLabel("点击「刷新书架」加载")
        self.status_label.setProperty("ui-role", "status")
        tr.addWidget(self.status_label)

        layout.addWidget(toolbar)

        # Books table
        table_frame = SurfaceCard()

        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书籍 ID", "书名", "作者", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.table.cellClicked.connect(self._on_cell_clicked)
        tl.addWidget(self.table)
        layout.addWidget(table_frame, 1)

        self.status_extra = QLabel("")
        self.status_extra.setProperty("ui-role", "status")
        layout.addWidget(self.status_extra)

    def _load_bookshelf(self):
        cookies = load_cookies()
        if not cookies or not cookies.get("ywguid"):
            self._sig.no_cookies.emit()
            return

        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("加载中...")
        self.status_label.setText("正在获取书架...")
        self.table.setRowCount(0)

        def _do():
            try:
                books = get_bookshelf(cookies)
                self._sig.books_ready.emit(books)
            except Exception as e:
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._sig.books_error.emit(str(e))

        threading.Thread(target=_do, daemon=True).start()

    def _on_books(self, books: list):
        self._books_data = [{"id": b["bookId"], "name": b["bookName"]} for b in books]
        self.table.setRowCount(len(books))
        for i, b in enumerate(books):
            self.table.setItem(i, 0, QTableWidgetItem(b["bookId"]))
            self.table.setItem(i, 1, QTableWidgetItem(b["bookName"]))
            self.table.setItem(i, 2, QTableWidgetItem(b["authorName"]))

            item = QTableWidgetItem("查看详情 →")
            item.setForeground(QColor(DARK_TOKENS["accent_highlight"]))
            item.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
            self.table.setItem(i, 3, item)

        self.status_label.setText(f"共 {len(books)} 本书")
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("  刷新书架")

    def _on_cell_clicked(self, row: int, col: int):
        """点击操作列（col=3）的蓝字详情 → 跳转书籍详情。"""
        if col == 3 and row < len(self._books_data):
            book = self._books_data[row]
            self.on_select_book(book["id"], book["name"])

    def _on_no_cookies(self):
        self.status_label.setText("未登录起点 — 请先到「登录」页面完成起点账号登录")
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("  刷新书架")
        self.table.setRowCount(0)
