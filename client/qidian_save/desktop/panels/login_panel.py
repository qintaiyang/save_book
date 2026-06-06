"""登录面板 — 支持邮箱+密码登录/注册（fastapi-users）"""
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QMessageBox, QStackedWidget,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


def _friendly_error(msg: str) -> str:
    """将服务端错误消息转为用户友好的中文提示"""
    if "LOGIN_BAD_CREDENTIALS" in msg:
        return "邮箱或密码错误"
    if "REGISTER_USER_ALREADY_EXISTS" in msg:
        return "该邮箱已注册"
    if "429" in msg:
        return "请求过于频繁，请稍后再试"
    return msg


class _LoginSignal(QObject):
    login_success = pyqtSignal(str)
    login_error = pyqtSignal(str)
    register_ready = pyqtSignal(dict)
    register_error = pyqtSignal(str)
    status_update = pyqtSignal(str, bool)


class LoginPanel(QWidget):
    def __init__(self, client, on_login_success):
        super().__init__()
        self.client = client
        self.on_login_success = on_login_success
        self._sig = _LoginSignal()
        self._sig.login_success.connect(self._on_login_success)
        self._sig.login_error.connect(self._on_login_error)
        self._sig.register_ready.connect(self._on_register_ready)
        self._sig.register_error.connect(lambda e: self._set_status(f"注册失败: {_friendly_error(e)}", error=True))
        self._sig.status_update.connect(self._set_status)
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

        # ── Mode switch: Login / Register ──
        mode_row = QHBoxLayout()
        self.btn_login_mode = QPushButton("登录")
        self.btn_login_mode.setProperty("btn-type", "secondary")
        self.btn_login_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login_mode.clicked.connect(lambda: self._switch_mode("login"))
        mode_row.addWidget(self.btn_login_mode)

        self.btn_register_mode = QPushButton("注册")
        self.btn_register_mode.setProperty("btn-type", "secondary")
        self.btn_register_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_register_mode.clicked.connect(lambda: self._switch_mode("register"))
        mode_row.addWidget(self.btn_register_mode)

        sl.addLayout(mode_row)

        # ── Stack: login / register form ──
        self.stack = QStackedWidget()

        # -- Login form --
        login_form = QFrame()
        lf = QVBoxLayout(login_form)
        lf.setSpacing(10)

        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText("邮箱")
        lf.addWidget(self.input_email)

        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("密码")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.returnPressed.connect(self._do_login)
        lf.addWidget(self.input_password)

        self.btn_login = QPushButton("  登录")
        self.btn_login.setProperty("btn-type", "primary")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFixedHeight(44)
        self.btn_login.clicked.connect(self._do_login)
        lf.addWidget(self.btn_login)

        self.btn_forgot = QPushButton("忘记密码？")
        self.btn_forgot.setStyleSheet("font-size: 12px; color: #6b7280; border: none;")
        self.btn_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_forgot.clicked.connect(self._forgot_password)
        lf.addWidget(self.btn_forgot)

        lf.addStretch()
        login_form.setLayout(lf)
        self.stack.addWidget(login_form)

        # -- Register form --
        register_form = QFrame()
        rf = QVBoxLayout(register_form)
        rf.setSpacing(10)

        self.input_reg_email = QLineEdit()
        self.input_reg_email.setPlaceholderText("邮箱")
        rf.addWidget(self.input_reg_email)

        self.input_reg_username = QLineEdit()
        self.input_reg_username.setPlaceholderText("用户名")
        rf.addWidget(self.input_reg_username)

        self.input_reg_password = QLineEdit()
        self.input_reg_password.setPlaceholderText("密码（至少 8 位）")
        self.input_reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_reg_password.returnPressed.connect(self._do_register)
        rf.addWidget(self.input_reg_password)

        self.btn_register = QPushButton("  注册")
        self.btn_register.setProperty("btn-type", "primary")
        self.btn_register.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_register.setFixedHeight(44)
        self.btn_register.clicked.connect(self._do_register)
        rf.addWidget(self.btn_register)

        rf.addStretch()
        register_form.setLayout(rf)
        self.stack.addWidget(register_form)

        sl.addWidget(self.stack)

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

    def _switch_mode(self, mode: str):
        self.stack.setCurrentIndex(0 if mode == "login" else 1)
        self.btn_login_mode.setProperty("btn-type", "primary" if mode == "login" else "secondary")
        self.btn_register_mode.setProperty("btn-type", "primary" if mode == "register" else "secondary")

    def _set_status(self, text: str, error: bool = False):
        p = self.status_label
        p.setText(text)
        p.setProperty("widget-type", "status-error" if error else "status-info")
        if p.style():
            p.style().unpolish(p)
            p.style().polish(p)

    def show_auto_login_status(self, text: str, error: bool = False):
        self._set_status(text, error)

    # ── Login ──

    def _do_login(self):
        email = self.input_email.text().strip()
        password = self.input_password.text().strip()
        if not email or not password:
            QMessageBox.warning(self, "提示", "请输入邮箱和密码")
            return

        self.btn_login.setEnabled(False)
        self._set_status("正在登录...")

        def _run():
            try:
                result = self.client.login_jwt(email, password)
                token = result["access_token"]
                self.client.set_token(token)
                user = self.client.get_me()
                self._sig.login_success.emit(token)
            except Exception as e:
                self._sig.login_error.emit(str(e))
                QTimer.singleShot(0, lambda: self.btn_login.setEnabled(True))

        threading.Thread(target=_run, daemon=True).start()

    def _on_login_success(self, token: str):
        self.btn_login.setEnabled(True)
        self.on_login_success(token)

    def _on_login_error(self, msg: str):
        self.btn_login.setEnabled(True)
        self._set_status(f"登录失败: {_friendly_error(msg)}", error=True)

    # ── Register ──

    def _do_register(self):
        email = self.input_reg_email.text().strip()
        username = self.input_reg_username.text().strip()
        password = self.input_reg_password.text().strip()

        if not email or not username or not password:
            QMessageBox.warning(self, "提示", "请填写所有字段")
            return
        if len(password) < 8:
            QMessageBox.warning(self, "提示", "密码至少 8 位")
            return

        self.btn_register.setEnabled(False)
        self._set_status("正在注册...")

        def _run():
            try:
                result = self.client.register(email, password, username)
                self._sig.register_ready.emit(result)
            except Exception as e:
                self._sig.register_error.emit(str(e))
                QTimer.singleShot(0, lambda: self.btn_register.setEnabled(True))

        threading.Thread(target=_run, daemon=True).start()

    def _on_register_ready(self, user: dict):
        self.btn_register.setEnabled(True)
        self._set_status(f"注册成功！用户名: {user.get('username', '')}，请登录")
        self._switch_mode("login")
        self.input_email.setText(self.input_reg_email.text())
        self.input_reg_email.clear()
        self.input_reg_username.clear()
        self.input_reg_password.clear()

    # ── Forgot password ──

    def _forgot_password(self):
        email = self.input_email.text().strip()
        if not email:
            QMessageBox.warning(self, "提示", "请先输入邮箱地址")
            return

        def _run():
            try:
                self.client.forgot_password(email)
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self, "密码重置", f"密码重置邮件已发送到 {email}（预留功能，暂不支持实际发信）",
                ))
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "发送失败", str(e)))

        threading.Thread(target=_run, daemon=True).start()

    # ── Token paste ──

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
