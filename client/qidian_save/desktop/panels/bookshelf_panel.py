"""书架面板 — 显示起点账号的书架，选择书籍跳转到详情"""
import threading, sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFrame,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from ...qidian_client import get_bookshelf, load_cookies


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QLabel("我的书架")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f2937;")
        layout.addWidget(header)

        desc = QLabel("需要先进行起点扫码登录，才能在书架中看到已购买的书籍")
        desc.setStyleSheet("font-size: 13px; color: #6b7280;")
        layout.addWidget(desc)

        # Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background: white; border-radius: 12px; padding: 12px 20px;")
        tr = QHBoxLayout(toolbar)
        tr.setSpacing(12)

        self.btn_refresh = QPushButton("  刷新书架")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._load_bookshelf)
        tr.addWidget(self.btn_refresh)

        tr.addStretch()
        self.status_label = QLabel("点击「刷新书架」加载")
        self.status_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
        tr.addWidget(self.status_label)

        layout.addWidget(toolbar)

        # Books table
        table_frame = QFrame()
        table_frame.setStyleSheet("background: white; border-radius: 12px;")

        tl = QVBoxLayout(table_frame)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["书籍 ID", "书名", "作者", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                border: none; border-radius: 12px;
                font-size: 13px;
                gridline-color: #f3f4f6;
            }
            QTableWidget::item { padding: 8px 12px; }
            QTableWidget::item:selected { background: #eff6ff; color: #1f2937; }
            QHeaderView::section {
                background: #f8fafc; border: none;
                padding: 10px 12px; font-weight: bold;
                font-size: 12px; color: #64748b;
            }
        """)
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
        self.status_extra.setStyleSheet("font-size: 12px; color: #9ca3af;")
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
            item.setForeground(QColor("#007aff"))
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
        self.status_label.setText("未登录起点 — 请先到「起点扫码」面板扫码登录")
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("  刷新书架")
        self.table.setRowCount(0)
