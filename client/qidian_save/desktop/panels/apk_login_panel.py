# -*- coding: utf-8 -*-
"""起点账号登录面板 — 账号密码 / 手机验证码 / 滑块验证"""

import json
import os
import secrets
import threading
import urllib.parse

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QLabel, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from ..components import PageHeader, SurfaceCard, configure_page_layout

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebChannel = None
    QWebEngineView = None


class _ApkLoginSignals(QObject):
    session_ready = pyqtSignal(dict)
    error = pyqtSignal(str)


class _CaptchaBridge(QObject):
    captcha_done = pyqtSignal(dict)

    @pyqtSlot(str)
    def submitCaptcha(self, raw: str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": "invalid captcha payload"}
        self.captcha_done.emit(payload)


class ApkLoginPanel(QWidget):
    """起点账号登录面板 — 支持密码登录和手机验证码登录。"""

    def __init__(self, client, on_session_authenticated=None, debug_mode: bool = False):
        super().__init__()
        self.client = client
        self.on_session_authenticated = on_session_authenticated
        self.debug_mode = bool(debug_mode)
        self.session_id = 0
        self._captcha_state = secrets.token_urlsafe(12)
        self._captcha_callback_url = ""
        self._captcha_bridge = None
        self._captcha_channel = None
        self._web_view = None
        self._captcha_dialog = None
        self._login_mode = "password"
        self._pending_stage = ""
        self._sig = _ApkLoginSignals()
        self._sig.session_ready.connect(self._on_session_ready)
        self._sig.error.connect(lambda msg: QMessageBox.warning(self, "登录", msg))
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "登录",
            "使用起点账号登录，完成验证后即可创建在线备份",
            "LOGIN",
        ))

        login_card = SurfaceCard()
        login_layout = QVBoxLayout(login_card)
        login_layout.setContentsMargins(20, 18, 20, 18)
        login_layout.setSpacing(12)

        login_title = QLabel("起点账号登录")
        login_title.setProperty("ui-role", "section-title")
        login_layout.addWidget(login_title)

        login_intro = QLabel(
            "账号密码只会提交给你配置的服务端。"
            "客户端不包含逆向签名、APK 解密密钥或其他敏感逻辑。"
        )
        login_intro.setProperty("ui-role", "status")
        login_intro.setWordWrap(True)
        login_layout.addWidget(login_intro)

        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self.btn_mode_password = QRadioButton("账号密码")
        self.btn_mode_phone = QRadioButton("手机验证码")
        self.btn_mode_password.setChecked(True)
        self._mode_group.addButton(self.btn_mode_password)
        self._mode_group.addButton(self.btn_mode_phone)
        self.btn_mode_password.toggled.connect(lambda checked: checked and self._set_login_mode("password"))
        self.btn_mode_phone.toggled.connect(lambda checked: checked and self._set_login_mode("phone_code"))
        mode_row.addWidget(self.btn_mode_password)
        mode_row.addWidget(self.btn_mode_phone)
        mode_row.addStretch()
        login_layout.addLayout(mode_row)

        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("手机号 / 邮箱 / 起点账号")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("起点密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.sms_code_label = QLabel("短信验证码")
        self.sms_code_label.setProperty("ui-role", "status")
        self.sms_code_label.hide()

        self.sms_code_input = QLineEdit()
        self.sms_code_input.setPlaceholderText("收到短信后输入 6 位验证码")
        self.sms_code_input.textChanged.connect(self._refresh_sms_submit_state)
        self.sms_code_input.returnPressed.connect(self._submit_sms_code)
        self.sms_code_input.setEnabled(False)
        self.sms_code_input.hide()

        self.challenge_input = QLineEdit()
        self.challenge_input.setPlaceholderText(
            "完成滑块后，把页面复制出的验证结果粘贴到这里"
        )
        self.challenge_input.hide()

        self.login_status = QLabel('状态：未开始。先填写账号密码，然后点击“检测账号”。')
        self.login_status.setProperty("ui-role", "status")
        self.login_status.setWordWrap(True)

        self.challenge_hint = QLabel(
            "如果服务端要求滑块验证，这里会告诉你下一步怎么做。"
        )
        self.challenge_hint.setProperty("ui-role", "status")
        self.challenge_hint.setWordWrap(True)

        self.debug_view = QLabel("")
        self.debug_view.setProperty("ui-role", "status")
        self.debug_view.setWordWrap(True)
        self.debug_view.setVisible(self.debug_mode)

        self.btn_create_session = QPushButton("  检测账号")
        self.btn_create_session.setProperty("btn-type", "primary")
        self.btn_create_session.clicked.connect(self._create_session)

        self.btn_submit_sms = QPushButton("  提交短信验证码")
        self.btn_submit_sms.setProperty("btn-type", "primary")
        self.btn_submit_sms.clicked.connect(self._submit_sms_code)
        self.btn_submit_sms.setEnabled(False)
        self.btn_submit_sms.hide()

        row = QHBoxLayout()
        row.addWidget(self.account_input)
        row.addWidget(self.password_input)
        login_layout.addLayout(row)
        login_layout.addWidget(self.sms_code_label)
        login_layout.addWidget(self.sms_code_input)
        login_layout.addWidget(self.challenge_input)

        action_row = QHBoxLayout()
        action_row.addWidget(self.btn_create_session)
        action_row.addWidget(self.btn_submit_sms)
        action_row.addStretch()
        login_layout.addLayout(action_row)
        login_layout.addWidget(self.login_status)
        login_layout.addWidget(self.challenge_hint)
        login_layout.addWidget(self.debug_view)
        layout.addWidget(login_card)

        self.captcha_card = SurfaceCard()
        captcha_layout = QVBoxLayout(self.captcha_card)
        captcha_layout.setContentsMargins(20, 18, 20, 18)
        captcha_layout.setSpacing(10)
        captcha_title = QLabel("滑块验证")
        captcha_title.setProperty("ui-role", "section-title")
        captcha_layout.addWidget(captcha_title)
        self.captcha_status = QLabel("需要滑块时会自动在这里打开。")
        self.captcha_status.setProperty("ui-role", "status")
        self.captcha_status.setWordWrap(True)
        captcha_layout.addWidget(self.captcha_status)
        self._init_embedded_captcha(captcha_layout)
        self.captcha_card.hide()
        layout.addWidget(self.captcha_card)

        layout.addStretch()
        self._set_login_mode("password")

    # ---- helpers ----

    def _run(self, func, ok_signal):
        def worker():
            try:
                ok_signal.emit(func())
            except Exception as exc:
                self._sig.error.emit(str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _set_login_mode(self, mode: str):
        self._login_mode = mode
        is_phone = mode == "phone_code"
        self.account_input.setPlaceholderText("手机号" if is_phone else "手机号 / 邮箱 / 起点账号")
        self.password_input.setVisible(not is_phone)
        self.sms_code_label.setVisible(is_phone)
        self.sms_code_input.setVisible(is_phone)
        self.sms_code_input.setEnabled(False)
        self.btn_submit_sms.setVisible(False)
        self.btn_create_session.setText("  发送短信验证码" if is_phone else "  检测账号")
        if is_phone:
            self.login_status.setText("状态：未开始。先填写手机号并发送短信验证码。")
        else:
            self.login_status.setText('状态：未开始。先填写账号密码，然后点击“检测账号”。')

    # ---- captcha ----

    def _captcha_url(self):
        base_url = getattr(self.client, "base_url", "")
        url = f"{base_url.rstrip('/')}/api/v1/apk/captcha/tencent" if base_url else "/api/v1/apk/captcha/tencent"
        params = {}
        if self._captcha_callback_url:
            params["callback"] = self._captcha_callback_url
        if self._captcha_state:
            params["state"] = self._captcha_state
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def _init_embedded_captcha(self, layout):
        if QWebEngineView is None or QWebChannel is None or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.captcha_status.setText(
                "当前环境没有内嵌浏览器组件，"
                "会自动打开系统浏览器完成滑块。"
            )
            return
        self.captcha_status.setText("需要滑块时会自动弹出验证窗口。")

    def _close_captcha_popup(self):
        if self._captcha_dialog is not None:
            self._captcha_dialog.close()
            self._captcha_dialog.deleteLater()
            self._captcha_dialog = None
        self._web_view = None
        self._captcha_bridge = None
        self._captcha_channel = None

    def _show_captcha_popup(self, url: str):
        self._close_captcha_popup()
        dialog = QDialog(self)
        dialog.setWindowTitle("滑块验证")
        dialog.resize(520, 700)
        dialog.setModal(False)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        view = QWebEngineView(dialog)
        view.setMinimumSize(480, 620)
        bridge = _CaptchaBridge()
        bridge.captcha_done.connect(self._handle_captcha_callback)
        channel = QWebChannel(view.page())
        channel.registerObject("captchaBridge", bridge)
        view.page().setWebChannel(channel)
        view.load(QUrl(url))
        layout.addWidget(view)
        self._captcha_dialog = dialog
        self._web_view = view
        self._captcha_bridge = bridge
        self._captcha_channel = channel
        dialog.show()

    def _open_captcha(self):
        url = self._captcha_url()
        self.captcha_card.hide()
        self.captcha_status.setText(
            "请在弹出的窗口里完成滑块，完成后会自动提交。"
        )
        if QWebEngineView is not None and QWebChannel is not None and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self._show_captcha_popup(url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    # ---- session ----

    def _create_session(self):
        account = self.account_input.text().strip()
        password = self.password_input.text()
        client_meta = {"platform": "desktop"}
        if self._login_mode == "phone_code":
            client_meta["loginMode"] = "phone_code"
        self.sms_code_input.setEnabled(False)
        self.login_status.setText("状态：正在发送登录请求，请稍等。")
        self.challenge_hint.setText(
            "如果需要滑块验证或短信验证码，服务端会返回下一步。"
        )
        self._run(
            lambda: self.client.create_apk_login_session(account, password, client_meta),
            self._sig.session_ready,
        )

    def _refresh_sms_submit_state(self, *_args):
        can_submit = (
            self._pending_stage == "need_sms"
            and bool(self.sms_code_input.text().strip())
        )
        self.btn_submit_sms.setEnabled(can_submit)

    def _submit_sms_code(self):
        if not self.session_id:
            QMessageBox.warning(self, "登录", "请先点击“检测账号”")
            return
        phone_code = self.sms_code_input.text().strip()
        if not phone_code:
            QMessageBox.warning(self, "登录", "请输入短信验证码")
            return
        self.login_status.setText("状态：正在提交短信验证码，请稍等。")
        self._run(
            lambda: self.client.submit_apk_login_challenge(
                self.session_id,
                {"kind": "sms", "phoneCode": phone_code},
            ),
            self._sig.session_ready,
        )

    def _handle_captcha_callback(self, payload: dict):
        if self._pending_stage == "need_sms":
            self.login_status.setText(
                "状态：滑块验证已完成，"
                "请继续输入收到的短信验证码。"
            )
            return
        if self._pending_stage == "authenticated":
            return
        if payload.get("state") and payload.get("state") != self._captcha_state:
            self.login_status.setText("状态：滑块回调已忽略，请重新打开滑块。")
            return
        ticket = str(payload.get("ticket") or "")
        randstr = str(payload.get("randstr") or "")
        if not ticket or not randstr:
            self.login_status.setText("状态：滑块没有返回有效结果，请重试。")
            return
        self.challenge_input.setText(json.dumps({"ticket": ticket, "randstr": randstr}, ensure_ascii=False))
        self._close_captcha_popup()
        if self.session_id:
            self._submit_captcha_answer()

    def _submit_captcha_answer(self):
        raw = self.challenge_input.text().strip()
        if not raw:
            payload = {"answer": {}, "kind": "captcha"}
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"answer": raw, "kind": "captcha"}
            else:
                if isinstance(parsed, dict):
                    payload = dict(parsed)
                    payload.setdefault("kind", "captcha")
                    if "answer" not in payload:
                        answer = {k: v for k, v in payload.items() if k != "kind"}
                        payload = {"answer": answer, "kind": payload["kind"]}
                else:
                    payload = {"answer": parsed, "kind": "captcha"}
        self.login_status.setText("状态：正在提交滑块验证，请稍等。")
        self._run(
            lambda: self.client.submit_apk_login_challenge(self.session_id, payload),
            self._sig.session_ready,
        )

    def _on_session_ready(self, data: dict):
        self.session_id = int(data.get("sessionId") or self.session_id or 0)
        result = data.get("challengeResult") if isinstance(data.get("challengeResult"), dict) else {}
        stage = str(data.get("stage", ""))
        verified = stage == "authenticated"
        self._pending_stage = stage

        if verified:
            self._close_captcha_popup()
            self.sms_code_label.setVisible(self._login_mode == "phone_code")
            self.sms_code_input.setVisible(self._login_mode == "phone_code")
            self.sms_code_input.setEnabled(False)
            self.sms_code_input.clear()
            self.btn_submit_sms.hide()
            self.login_status.setText("状态：起点账号登录成功！")
            self.challenge_hint.setText(
                "现在可以去搜索书籍，"
                "选择章节后创建在线备份。"
            )
            if self.on_session_authenticated:
                self.on_session_authenticated(self.session_id)
        elif result and not result.get("ok"):
            message = str(result.get("message") or "验证码失败")
            self.login_status.setText(f"状态：{message}，登录未完成。")
            self.challenge_hint.setText(
                "请重新点击“检测账号”，"
                "打开新的滑块页面后再试一次。"
            )
        elif stage == "need_sms":
            self._close_captcha_popup()
            self.challenge_input.clear()
            self.sms_code_label.show()
            self.sms_code_input.show()
            self.sms_code_input.setEnabled(True)
            self.sms_code_input.setFocus()
            self.btn_submit_sms.show()
            self.login_status.setText(
                "状态：短信验证码已发送，"
                "请输入收到的 6 位验证码。"
            )
            self.challenge_hint.setText(
                "输入短信验证码后，"
                "按回车或点击“提交短信验证码”继续。"
            )
        elif stage == "need_captcha" or data.get("challenge"):
            self.sms_code_input.setEnabled(False)
            self.btn_submit_sms.hide()
            if self._login_mode != "phone_code":
                self.sms_code_label.hide()
                self.sms_code_input.hide()
            self.login_status.setText("状态：需要完成滑块验证。")
            self.challenge_hint.setText(
                "已自动打开滑块窗口。完成后会自动提交。"
            )
            self._open_captcha()
        else:
            self.login_status.setText("状态：账号检查完成，请按页面提示继续。")
            self.challenge_hint.setText("请按页面提示继续。")

        challenge = data.get("challenge")
        detail = {"challenge": challenge, "result": result} if result else challenge
        self.debug_view.setText(json.dumps(detail, ensure_ascii=False, indent=2) if detail else "")
