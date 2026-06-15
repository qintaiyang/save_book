"""APK backup panel: thin, beginner-friendly client for the public APK API."""

import json
import os
import secrets
import threading
import urllib.parse

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..components import PageHeader, SurfaceCard, configure_page_layout

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:  # pragma: no cover - optional runtime dependency
    QWebChannel = None
    QWebEngineView = None


class _ApkSignals(QObject):
    session_ready = pyqtSignal(dict)
    task_ready = pyqtSignal(dict)
    artifacts_ready = pyqtSignal(list)
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


class ApkBackupPanel(QWidget):
    def __init__(self, client, on_session_authenticated=None, on_go_search=None):
        super().__init__()
        self.client = client
        self.on_session_authenticated = on_session_authenticated
        self.on_go_search = on_go_search
        self.session_id = 0
        self.task_id = 0
        self._captcha_state = secrets.token_urlsafe(12)
        self._captcha_callback_url = ""
        self._captcha_bridge = None
        self._captcha_channel = None
        self._web_view = None
        self._captcha_dialog = None
        self._login_mode = "password"
        self._pending_stage = ""
        self._sig = _ApkSignals()
        self._sig.session_ready.connect(self._on_session_ready)
        self._sig.task_ready.connect(self._on_task_ready)
        self._sig.artifacts_ready.connect(self._on_artifacts_ready)
        self._sig.error.connect(lambda msg: QMessageBox.warning(self, "快速备份", msg))
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "快速备份", "先完成账号验证，再回到搜索书籍和书籍详情里选择章节", "FAST BACKUP"
        ))

        login_card = SurfaceCard()
        login_layout = QVBoxLayout(login_card)
        login_layout.setContentsMargins(20, 18, 20, 18)
        login_layout.setSpacing(12)

        login_title = QLabel("第 1 步：登录起点账号")
        login_title.setProperty("ui-role", "section-title")
        login_layout.addWidget(login_title)

        login_intro = QLabel("账号密码只会提交给你配置的服务端。客户端不包含逆向签名、APK 解密密钥或其他敏感逻辑。")
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
        self.sms_code_input.setEnabled(False)
        self.sms_code_input.hide()
        self.challenge_input = QLineEdit()
        self.challenge_input.setPlaceholderText("完成滑块后，把页面复制出的验证结果粘贴到这里")
        self.challenge_input.hide()

        self.login_status = QLabel("状态：未开始。先填写账号密码，然后点击“检测账号”。")
        self.login_status.setProperty("ui-role", "status")
        self.login_status.setWordWrap(True)
        self.challenge_hint = QLabel("如果服务端要求滑块验证，这里会告诉你下一步怎么做。")
        self.challenge_hint.setProperty("ui-role", "status")
        self.challenge_hint.setWordWrap(True)
        self.debug_view = QLabel("")
        self.debug_view.setProperty("ui-role", "status")
        self.debug_view.setWordWrap(True)
        self.debug_view.hide()
        self.challenge_view = self.debug_view

        self.btn_create_session = QPushButton("  检测账号")
        self.btn_create_session.setProperty("btn-type", "primary")
        self.btn_create_session.clicked.connect(self._create_session)
        self.btn_submit_sms = QPushButton("  提交短信验证码")
        self.btn_submit_sms.setProperty("btn-type", "primary")
        self.btn_submit_sms.clicked.connect(self._submit_challenge)
        self.btn_submit_sms.setEnabled(False)
        self.btn_submit_sms.hide()
        self.btn_toggle_debug = QPushButton("  高级信息")
        self.btn_toggle_debug.setProperty("btn-type", "secondary")
        self.btn_toggle_debug.setCheckable(True)
        self.btn_toggle_debug.toggled.connect(self.debug_view.setVisible)

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
        action_row.addWidget(self.btn_toggle_debug)
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
        self.captcha_title = QLabel("滑块验证")
        self.captcha_title.setProperty("ui-role", "section-title")
        captcha_layout.addWidget(self.captcha_title)
        self.captcha_status = QLabel("需要滑块时会自动在这里打开。")
        self.captcha_status.setProperty("ui-role", "status")
        self.captcha_status.setWordWrap(True)
        captcha_layout.addWidget(self.captcha_status)
        self._init_embedded_captcha(captcha_layout)
        self.captcha_card.hide()
        layout.addWidget(self.captcha_card)

        task_card = SurfaceCard()
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(20, 18, 20, 18)
        task_layout.setSpacing(10)

        task_title = QLabel("第 2 步：去搜索书籍并选择章节")
        task_title.setProperty("ui-role", "section-title")
        task_layout.addWidget(task_title)

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText('高级目标 JSON，仅调试用，例如 {"bookId":1045968909,"chapterIds":[854441356]}')
        self.target_input.hide()
        self.task_status = QLabel("状态：账号验证完成后，请去“搜索书籍”，在书籍详情里勾选章节并选择快速备份。")
        self.task_status.setProperty("ui-role", "status")
        self.task_status.setWordWrap(True)
        self.btn_create_task = QPushButton("  去搜索书籍")
        self.btn_create_task.setProperty("btn-type", "primary")
        self.btn_create_task.clicked.connect(self._go_search)
        self.btn_create_task.setEnabled(False)
        self.btn_refresh_task = QPushButton("  刷新任务")
        self.btn_refresh_task.setProperty("btn-type", "secondary")
        self.btn_refresh_task.clicked.connect(self._refresh_task)
        self.btn_toggle_target = QPushButton("  高级目标")
        self.btn_toggle_target.setProperty("btn-type", "secondary")
        self.btn_toggle_target.setCheckable(True)
        self.btn_toggle_target.toggled.connect(self.target_input.setVisible)
        task_actions = QHBoxLayout()
        task_actions.addWidget(self.btn_create_task)
        task_actions.addWidget(self.btn_refresh_task)
        task_actions.addWidget(self.btn_toggle_target)
        task_actions.addStretch()
        task_layout.addWidget(self.target_input)
        task_layout.addLayout(task_actions)
        task_layout.addWidget(self.task_status)
        layout.addWidget(task_card)

        artifact_card = SurfaceCard()
        artifact_layout = QVBoxLayout(artifact_card)
        artifact_layout.setContentsMargins(0, 0, 0, 0)
        self.artifacts_table = QTableWidget()
        self.artifacts_table.setColumnCount(4)
        self.artifacts_table.setHorizontalHeaderLabels(["ID", "文件名", "类型", "大小"])
        self.artifacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        artifact_layout.addWidget(self.artifacts_table)
        layout.addWidget(artifact_card, 1)

        self._set_login_mode("password")

    def _run(self, func, ok_signal):
        def worker():
            try:
                ok_signal.emit(func())
            except Exception as exc:
                self._sig.error.emit(str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _set_verified_state(self, verified: bool):
        self.btn_create_task.setEnabled(verified)
        self._refresh_sms_submit_state(verified=verified)

    def _refresh_sms_submit_state(self, *_args, verified: bool = False):
        can_submit_sms = (
            not verified
            and self._pending_stage == "need_sms"
            and bool(self.sms_code_input.text().strip())
        )
        self.btn_submit_sms.setEnabled(can_submit_sms)

    def _go_search(self):
        if self.on_go_search:
            self.on_go_search()

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
        self.login_status.setText(
            "状态：未开始。先填写手机号并发送短信验证码。"
            if is_phone else
            "状态：未开始。先填写账号密码，然后点击“检测账号”。"
        )

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
            self.captcha_status.setText("当前环境没有内嵌浏览器组件，会自动打开系统浏览器完成滑块。")
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
        self.captcha_status.setText("请在弹出的窗口里完成滑块，完成后会自动提交。")
        if QWebEngineView is not None and QWebChannel is not None and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self._show_captcha_popup(url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    def _create_session(self):
        account = self.account_input.text().strip()
        password = self.password_input.text()
        client_meta = {"platform": "desktop"}
        if self._login_mode == "phone_code":
            client_meta["loginMode"] = "phone_code"
        self._set_verified_state(False)
        self.login_status.setText("状态：正在发送登录请求，请稍等。")
        self.challenge_hint.setText("如果需要滑块验证或短信验证码，服务端会返回下一步。")
        self._run(
            lambda: self.client.create_apk_login_session(account, password, client_meta),
            self._sig.session_ready,
        )

    def _submit_challenge(self):
        if not self.session_id:
            QMessageBox.warning(self, "快速备份", "请先点击“检测账号”")
            return
        if self._pending_stage == "need_sms":
            self._submit_sms_code(start_task=False)
            return
        self._submit_captcha_answer(start_task=False)

    def _handle_captcha_callback(self, payload: dict):
        if self._pending_stage == "need_sms":
            self.login_status.setText("状态：滑块验证已完成，请继续输入收到的短信验证码。")
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
            self._submit_captcha_answer(start_task=False)

    def _submit_challenge_and_start(self):
        if not self.session_id:
            QMessageBox.warning(self, "快速备份", "请先点击“检测账号”")
            return
        if self._pending_stage == "need_sms":
            self._submit_sms_code(start_task=True)
            return
        self._submit_captcha_answer(start_task=True)

    def _submit_challenge_request(self, payload: dict, start_task: bool):
        try:
            request_payload = dict(payload or {})
            if start_task:
                request_payload["startTask"] = True
                request_payload["targetRef"] = self._target_ref()
        except ValueError as exc:
            QMessageBox.warning(self, "快速备份", str(exc))
            return
        self.login_status.setText("状态：正在提交验证码，请稍等。")
        self._run(
            lambda: self.client.submit_apk_login_challenge(
                self.session_id,
                request_payload,
            ),
            self._sig.session_ready,
        )

    def _submit_captcha_answer(self, start_task: bool):
        try:
            payload = self._captcha_payload()
        except ValueError as exc:
            QMessageBox.warning(self, "快速备份", str(exc))
            return
        self._submit_challenge_request(payload, start_task=start_task)

    def _submit_sms_code(self, start_task: bool):
        try:
            payload = self._sms_payload()
        except ValueError as exc:
            QMessageBox.warning(self, "快速备份", str(exc))
            return
        self._submit_challenge_request(payload, start_task=start_task)

    def _challenge_payload(self, start_task: bool = False):
        return self._sms_payload() if self._pending_stage == "need_sms" else self._captcha_payload(start_task=start_task)

    def _sms_payload(self):
        phone_code = self.sms_code_input.text().strip()
        if not phone_code:
            raise ValueError("请输入短信验证码")
        return {"kind": "sms", "phoneCode": phone_code}

    def _captcha_payload(self, start_task: bool = False):
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
        if start_task:
            payload["startTask"] = True
            payload["targetRef"] = self._target_ref()
        return payload

    def _target_ref(self):
        raw_target = self.target_input.text().strip()
        try:
            target = json.loads(raw_target) if raw_target else None
        except json.JSONDecodeError as exc:
            raise ValueError('高级目标必须是 JSON，例如 {"bookId":1045968909,"chapterId":854441356}') from exc
        if target is not None:
            if not isinstance(target, dict):
                raise ValueError("高级目标 JSON 必须是对象")
            return target

        return {}

    def _create_task(self):
        if not self.session_id:
            QMessageBox.warning(self, "快速备份", "请先完成账号验证")
            return
        try:
            target = self._target_ref()
        except ValueError as exc:
            QMessageBox.warning(self, "快速备份", str(exc))
            return
        self.task_status.setText("状态：正在创建备份任务，请稍等。")
        self._run(
            lambda: self.client.create_apk_backup_task(
                self.session_id,
                target,
            ),
            self._sig.task_ready,
        )

    def _refresh_task(self):
        if not self.task_id:
            return
        self._run(lambda: self.client.get_apk_task(self.task_id), self._sig.task_ready)
        self._run(lambda: self.client.list_apk_task_artifacts(self.task_id), self._sig.artifacts_ready)

    def load_task(self, task_id: int):
        self.task_id = int(task_id or 0)
        if self.task_id:
            self.task_status.setText(f"任务 #{self.task_id}: 正在刷新状态...")
            self._refresh_task()

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
            self.login_status.setText("状态：账号登录已确认，可以去搜索书籍。")
            self.challenge_hint.setText("下一步：点击“去搜索书籍”，选择一本书后在详情页勾选章节并选择快速备份。")
            if self.on_session_authenticated:
                self.on_session_authenticated(self.session_id)
        elif result and not result.get("ok"):
            message = str(result.get("message") or "验证码失败")
            self.login_status.setText(f"状态：{message}，账号登录未完成。")
            self.challenge_hint.setText("请重新点击“检测账号”，打开新的滑块页面后再试一次。")
        elif stage == "need_sms":
            self._close_captcha_popup()
            self.challenge_input.clear()
            self.sms_code_label.show()
            self.sms_code_input.show()
            self.sms_code_input.setEnabled(True)
            self.btn_submit_sms.show()
            self.login_status.setText("状态：短信验证码已发送，请输入收到的 6 位验证码。")
            self.challenge_hint.setText("输入短信验证码后，点击“提交短信验证码”继续。")
        elif stage == "need_captcha" or data.get("challenge"):
            self.sms_code_input.setEnabled(False)
            self.btn_submit_sms.hide()
            if self._login_mode != "phone_code":
                self.sms_code_label.hide()
                self.sms_code_input.hide()
            self.login_status.setText("状态：需要完成滑块验证。")
            self.challenge_hint.setText(
                "已自动打开滑块窗口。完成后客户端会自动提交，不需要任何手动按钮。"
            )
            self._open_captcha()
        else:
            self.login_status.setText("状态：账号检查完成，请按页面提示继续。")
            self.challenge_hint.setText("如果页面没有下一步提示，请打开“高级信息”查看服务端返回内容。")
        self._set_verified_state(verified)
        challenge = data.get("challenge")
        detail = {"challenge": challenge, "result": result} if result else challenge
        self.debug_view.setText(json.dumps(detail, ensure_ascii=False, indent=2) if detail else "")
        if data.get("taskId") or data.get("task"):
            self._on_task_ready(data.get("task") or {"taskId": data.get("taskId")})

    def _on_task_ready(self, data: dict):
        self.task_id = int(data.get("taskId") or self.task_id or 0)
        if "status" in data:
            self.task_status.setText(
                f"任务 #{self.task_id}: {data.get('status')} "
                f"{data.get('progressDone', 0)}/{data.get('progressTotal', 0)}"
            )
        else:
            self.task_status.setText(f"任务 #{self.task_id} 已创建")
            self._refresh_task()

    def _on_artifacts_ready(self, artifacts: list):
        self.artifacts_table.setRowCount(len(artifacts))
        for row, item in enumerate(artifacts):
            self.artifacts_table.setItem(row, 0, QTableWidgetItem(str(item.get("artifactId", ""))))
            self.artifacts_table.setItem(row, 1, QTableWidgetItem(str(item.get("filename", ""))))
            self.artifacts_table.setItem(row, 2, QTableWidgetItem(str(item.get("artifactType", ""))))
            self.artifacts_table.setItem(row, 3, QTableWidgetItem(str(item.get("sizeBytes", ""))))
