"""qidian_save 桌面主应用 — FluentWindow 重构版"""
import sys, os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QDialog, QPushButton,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ..api_client import QidianSaveClient
from .. import DATA_DIR
from ..qidian_client import set_cookie_path

from qfluentwidgets import (
    setTheme, Theme, FluentIcon as FIF,
    FluentWindow, NavigationItemPosition,
)
from .theme import DESIGN_TOKENS, apply_design_tokens, load_qss

TOKEN_FILE = DATA_DIR / "token"


def _save_token(token: str):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")


def _load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


from .panels.login_panel import LoginPanel
from .panels.qidian_login_panel import QidianLoginPanel
from .panels.search_panel import SearchPanel
from .panels.book_detail_panel import BookDetailPanel
from .panels.backup_panel import BackupPanel
from .panels.qd_decrypt_panel import QDDecryptPanel
from .panels.usage_panel import UsagePanel
from .panels.bookshelf_panel import BookshelfPanel


# ── 登录对话框 ────────────────────────────────────────────

class LoginDialog(QDialog):
    """全屏居中登录对话框，登录成功后返回 token。"""

    def __init__(self, client: QidianSaveClient, parent=None):
        super().__init__(parent)
        self.client = client
        self._token = ""
        self.setWindowTitle("qidian_save — 登录")
        self.setMinimumSize(500, 500)
        self.resize(520, 600)
        self.setModal(True)
        # 应用全局 QSS 主题
        qss = load_qss(Theme.LIGHT)
        if qss:
            self.setStyleSheet(qss)
        self._init_ui()
        self._try_auto_login()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.login_panel = LoginPanel(self.client, self._on_login_success)
        layout.addWidget(self.login_panel)

    def _on_login_success(self, token: str):
        self._token = token
        self.accept()

    def _try_auto_login(self):
        if not self.client.session.headers.get("Authorization"):
            return
        import requests as _req
        try:
            self.client.get_me()
            token = self.client.session.headers.get("Authorization", "").replace("Bearer ", "")
            if token:
                self._on_login_success(token)
        except Exception:
            pass

    def get_token(self) -> str:
        return self._token


# ── 页面容器 ──────────────────────────────────────────────

class PageWidget(QWidget):
    """单个子界面容器，统一带 statusbar 引用。"""
    def __init__(self, name: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName(name.replace(" ", "-"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        self._inner = widget


# ── 主窗口 ────────────────────────────────────────────────

class MainWindow(FluentWindow):
    def __init__(self, client: QidianSaveClient, token: str):
        super().__init__()
        self.client = client
        self.token = token
        self.current_task_id = None
        self._current_theme = Theme.LIGHT
        self._setup_panels()
        self._setup_theme()
        self._setup_status_bar()
        self._start_usage_timer()

        # 自动应用 QSS
        self._apply_qss()

    # ── 子界面注册 ─────────────────────────────────────────

    def _setup_panels(self):
        """注册所有面板到导航系统。"""
        # 创建面板实例
        self.panels = {}
        self.panels["search"]   = SearchPanel(self.client, self._on_book_selected)
        self.panels["qrcode"]   = QidianLoginPanel(self.client)
        self.panels["bookshelf"] = BookshelfPanel(self.client, self._on_book_selected)
        self.panels["detail"]   = BookDetailPanel(self.client, self._on_backup_started)
        self.panels["backup"]   = BackupPanel(self.client)
        self.panels["decrypt"]  = QDDecryptPanel(self.client)
        self.panels["usage"]    = UsagePanel(self.client)

        # 导航项配置: (key, icon, label, position)
        nav_items = [
            ("search",    FIF.SEARCH,           "搜索书籍",  NavigationItemPosition.TOP),
            ("qrcode",    FIF.QRCODE,           "起点扫码",  NavigationItemPosition.TOP),
            ("bookshelf", FIF.LIBRARY,          "书架",     NavigationItemPosition.TOP),
            ("backup",    FIF.CLOUD_DOWNLOAD,   "在线备份",  NavigationItemPosition.TOP),
            ("decrypt",   FIF.DEVELOPER_TOOLS,  ".qd 解密", NavigationItemPosition.TOP),
            ("usage",     FIF.HISTORY,          "用量查询",  NavigationItemPosition.BOTTOM),
        ]

        for key, icon, label, pos in nav_items:
            widget = self.panels[key]
            widget.setObjectName(f"panel_{key}")
            self.addSubInterface(widget, icon, label, pos)

        # 书籍详情 → 不作为导航项，直接加入内部 stackedWidget 供程序跳转
        self.detail_panel = self.panels["detail"]
        self.detail_panel.setObjectName("panel_detail")
        self.stackedWidget.addWidget(self.detail_panel)
        self.stack: QStackedWidget  # FluentWindow 内部 stack
        # 找到 FluentWindow 内部的 QStackedWidget 以便直接切换

    def _on_book_selected(self, book_id: str, book_name: str):
        self.panels["detail"].load_book(book_id, book_name)
        # 程序跳转到详情面板（不在导航中高亮）
        self.switchTo(self.panels["detail"])

    def _on_backup_started(self, task_id: int):
        self.current_task_id = task_id
        self.panels["backup"].load_task(task_id)
        self.switchTo(self.panels["backup"])

    # ── 主题 ───────────────────────────────────────────────

    def _setup_theme(self):
        setTheme(self._current_theme)
        apply_design_tokens(self._current_theme)

    def _apply_qss(self):
        qss = load_qss(self._current_theme)
        if qss:
            self.setStyleSheet(qss)

    # ── 状态栏 ─────────────────────────────────────────────

    def _setup_status_bar(self):
        """在导航底部添加信息面板（FluentWindow 无原生 QStatusBar）。"""
        self.status_container = QWidget()
        self.status_container.setObjectName("statusBarContainer")
        self.status_container.setFixedHeight(36)
        layout = QHBoxLayout(self.status_container)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self.status_label = QLabel("已登录")
        self.status_label.setFont(QFont(DESIGN_TOKENS["font_family"], 9))
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.usage_indicator = QLabel()
        self.usage_indicator.setFont(QFont(DESIGN_TOKENS["font_family"], 9))
        layout.addWidget(self.usage_indicator)

        # 用可点击容器让 NavigationInterface 接受
        container = QPushButton()
        container.setObjectName("statusBarBtn")
        container.setFixedHeight(36)
        container.setCursor(Qt.CursorShape.ArrowCursor)
        # 把 status_container 放进按钮里
        btn_layout = QHBoxLayout(container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(self.status_container)

        self.navigationInterface.addWidget(
            "statusBar", container,
            position=NavigationItemPosition.BOTTOM,
        )

    # ── 用量定时器 ─────────────────────────────────────────

    def _start_usage_timer(self):
        self._update_usage()
        self._usage_timer = QTimer(self)
        self._usage_timer.timeout.connect(self._update_usage)
        self._usage_timer.start(60000)

    def _update_usage(self):
        if not self.token:
            return
        try:
            usage = self.client.get_usage()
            self.usage_indicator.setText(f"今日 {usage['chaptersUsed']} / {usage['limit']} 次")
        except Exception:
            pass


def main():
    # Qt6 默认启用 DPI 缩放 (PerMonitorV2)。SetProcessDpiAwarenessContext 警告无害
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 全局默认字体
    font = QFont(
        DESIGN_TOKENS["font_family"],
        int(DESIGN_TOKENS["font_size_body"].replace("px", ""))
    )
    app.setFont(font)

    # 初始化
    set_cookie_path()

    base = os.getenv("QIDIAN_SAVE_URL", "https://autohelp.asia/")
    token = os.getenv("QIDIAN_SAVE_TOKEN", "") or _load_token()
    client = QidianSaveClient(base, token=token)

    # ── 登录流程 ──
    if token:
        # 有 token，先验证
        client.set_token(token)
        try:
            client.get_me()
        except Exception:
            token = ""  # 失效，重新登录

    if not token:
        dlg = LoginDialog(client)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        token = dlg.get_token()
        _save_token(token)

    # ── 主窗口 ──
    client.set_token(token)
    window = MainWindow(client, token)
    window.setWindowTitle("qidian_save")
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
