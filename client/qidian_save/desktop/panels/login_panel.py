"""OAuth 登录面板 — 支持 GitHub Device Flow（样式由全局 QSS 控制）"""
import webbrowser, threading, time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


class _LoginSignal(QObject):
    device_code_ready = pyqtSignal(dict)
    poll_result = pyqtSignal(dict)
    login_error = pyqtSignal(str)
    login_success = pyqtSignal(str)
    status_update = pyqtSignal(str, bool)


class LoginPanel(QWidget):
    def __init__(self, client, on_login_success):
        super().__init__()
        self.client = client
        self.on_login_success = on_login_success
        self._sig = _LoginSignal()
        self._sig.device_code_ready.connect(self._on_device_code)
        self._sig.poll_result.connect(self._on_poll_result)
        self._sig.login_error.connect(lambda e: self._set_status(f"登录失败: {e}", error=True))
        self._sig.login_success.connect(self._on_login_success)
        self._sig.status_update.connect(self._set_status)
        self._device_code = ""
        self._polling = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        section = QFrame()
        section.setObjectName("section")
        section.setFixedWidth(520)
        sl = QVBoxLayout(section)
        sl.setSpacing(16)

        title = QLabel("欢迎使用 qidian_save")
        title.setProperty("widget-type", "panel-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(title)

        subtitle = QLabel("登录以开始备份你的起点书籍")
        subtitle.setProperty("widget-type", "panel-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(subtitle)

        # ── GitHub Device Flow ──
        self.btn_github = QPushButton("  使用 GitHub 登录")
        self.btn_github.setProperty("btn-type", "secondary")
        self.btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_github.setFixedHeight(44)
        self.btn_github.clicked.connect(self._start_github_login)
        sl.addWidget(self.btn_github)

        # ── Device Code display ──
        self.code_card = QFrame()
        self.code_card.setStyleSheet("background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px;")
        self.code_card.setVisible(False)
        cc = QVBoxLayout(self.code_card)
        cc.setSpacing(8)

        self.label_code = QLabel("")
        self.label_code.setStyleSheet("font-size: 28px; font-weight: bold; color: #166534; letter-spacing: 4px;")
        self.label_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc.addWidget(self.label_code)

        self.label_uri = QLabel("")
        self.label_uri.setStyleSheet("font-size: 13px; color: #15803d;")
        self.label_uri.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc.addWidget(self.label_uri)

        self.btn_open = QPushButton("  打开浏览器")
        self.btn_open.setProperty("btn-type", "secondary")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.clicked.connect(self._open_browser)
        cc.addWidget(self.btn_open)

        sl.addWidget(self.code_card)

        # ── Status ──
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.status_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        sl.addWidget(divider)

        hint = QLabel("或粘贴已有 Token")
        hint.setProperty("widget-type", "panel-subtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(hint)

        tr = QHBoxLayout()
        self.input_token = QLineEdit()
        self.input_token.setPlaceholderText("粘贴 JWT Token...")
        tr.addWidget(self.input_token, 1)

        self.btn_apply = QPushButton("应用")
        self.btn_apply.setProperty("btn-type", "secondary")
        self.btn_apply.setFixedWidth(80)
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self._apply_token)
        tr.addWidget(self.btn_apply)
        sl.addLayout(tr)

        layout.addWidget(section)

    def _set_status(self, text: str, error: bool = False):
        p = self.status_label
        p.setText(text)
        p.setProperty("widget-type", "status-error" if error else "status-info")
        # 强制 QSS 重新计算
        if p.style():
            p.style().unpolish(p)
            p.style().polish(p)

    def show_auto_login_status(self, text: str, error: bool = False):
        """从外部设置自动登录状态（MainWindow._try_auto_login 调用）"""
        self._set_status(text, error)

    def _start_github_login(self):
        self.btn_github.setEnabled(False)
        self._set_status("正在发起登录...")

        def _run():
            try:
                result = self.client.login_github_device_code()
                self._sig.device_code_ready.emit(result)
            except Exception as e:
                self._sig.login_error.emit(str(e))
                QTimer.singleShot(0, lambda: self.btn_github.setEnabled(True))

        threading.Thread(target=_run, daemon=True).start()

    def _on_device_code(self, data: dict):
        self._device_code = data["device_code"]
        user_code = data["user_code"]
        uri = data["verification_uri"]

        self.label_code.setText(user_code)
        self.label_uri.setText(f"在浏览器中输入以上代码 — {uri}")
        self.code_card.setVisible(True)
        self.btn_github.setEnabled(True)
        self._set_status("请在浏览器中完成 GitHub 授权")

        self._start_polling()

    def _open_browser(self):
        webbrowser.open("https://github.com/login/device")

    def _start_polling(self):
        self._polling = True
        interval = 5

        def _poll():
            nonlocal interval
            while self._polling:
                try:
                    result = self.client.login_github_poll_token(self._device_code)
                    self._sig.poll_result.emit(result)
                    status = result.get("status")

                    if status == "success":
                        self._polling = False
                        return
                    elif status == "slow_down":
                        interval = result.get("interval", interval + 5)
                    elif status == "expired":
                        self._sig.status_update.emit("登录已过期，请重新点击登录", True)
                        self._polling = False
                        return
                    elif status == "denied":
                        self._sig.status_update.emit("用户取消了授权", True)
                        self._polling = False
                        return
                    elif status == "pending":
                        self._sig.status_update.emit("等待扫码中...", False)
                except Exception as e:
                    if self._polling:
                        self._sig.login_error.emit(str(e))
                    self._polling = False
                    return

                time.sleep(interval)

        threading.Thread(target=_poll, daemon=True).start()

    def _on_poll_result(self, result: dict):
        if result.get("status") == "success":
            token = result["token"]
            user = result.get("user", {})
            self._set_status(f"登录成功！用户: {user.get('username', '')}")
            self._sig.login_success.emit(token)

    def _on_login_success(self, token: str):
        self.on_login_success(token)

    def _apply_token(self):
        token = self.input_token.text().strip()
        if not token:
            QMessageBox.warning(self, "提示", "请输入 Token")
            return
        try:
            self.client.set_token(token)
            user = self.client.get_me()
            self.on_login_success(token)
        except Exception as e:
            QMessageBox.critical(self, "登录失败", f"Token 无效: {str(e)}")
