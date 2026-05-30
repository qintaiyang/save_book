"""起点扫码登录面板 — 二维码显示 + 轮询 + 公告"""
import time, threading, sys, base64
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QFrame, QMessageBox, QTextEdit,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap
from ...qidian_client import get_qrcode, poll_qrcode, save_cookies


class _QRSignal(QObject):
    """跨线程信号桥"""
    show_qr = pyqtSignal(bytes, str)
    show_error = pyqtSignal(str)
    show_status = pyqtSignal(str)
    show_info = pyqtSignal(str)
    show_text = pyqtSignal(str)
    done = pyqtSignal()
    poll_result = pyqtSignal(dict)
    poll_error = pyqtSignal(str)
    poll_timeout = pyqtSignal()


_PRIORITY_LABEL = {"urgent": "【紧急】", "important": "【重要】", "normal": ""}


class QidianLoginPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.session_key = ""
        self._polling = False
        self._sig = _QRSignal()
        self._connect_signals()
        self._init_ui()
        # 延迟拉取公告（避免构造函数阻塞，服务器不可达时不卡 UI）
        QTimer.singleShot(0, self._refresh_announcements)

    def _connect_signals(self):
        self._sig.show_qr.connect(self._on_show_qr)
        self._sig.show_error.connect(self._on_error)
        self._sig.show_status.connect(lambda t: self.status_label.setText(t))
        self._sig.show_info.connect(lambda t: self.info_display.setText(t))
        self._sig.show_text.connect(lambda t: (
            self.label_qr.setText(t),
            self.label_qr.setTextFormat(Qt.TextFormat.AutoText),
            self.label_qr.setAlignment(Qt.AlignmentFlag.AlignCenter),
        ))
        self._sig.done.connect(self._on_done)
        self._sig.poll_result.connect(self._on_poll_result)
        self._sig.poll_error.connect(lambda e: self.status_label.setText(f"轮询出错: {e}"))
        self._sig.poll_timeout.connect(lambda: self.status_label.setText("扫码超时，请重试"))

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        section = QFrame()
        section.setObjectName("section")
        section.setStyleSheet("""
            QFrame#section { background: white; border-radius: 12px; padding: 32px; max-width: 520px; }
        """)
        sl = QVBoxLayout(section)
        sl.setSpacing(16)

        title = QLabel("起点扫码登录")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1f2937;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(title)

        self.label_qr = QLabel("点击下方按钮生成二维码，用起点 App 扫码")
        self.label_qr.setStyleSheet("font-size: 13px; color: #6b7280;")
        self.label_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_qr.setMinimumHeight(280)
        self.label_qr.setWordWrap(True)
        sl.addWidget(self.label_qr)

        self.btn_generate = QPushButton("  生成二维码")
        self.btn_generate.setProperty("btn-type", "secondary")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.clicked.connect(self._generate_qr)
        sl.addWidget(self.btn_generate)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 12px; color: #6b7280;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.status_label)

        self.info_display = QTextEdit()
        self.info_display.setReadOnly(True)
        self.info_display.setMaximumHeight(80)
        self.info_display.setStyleSheet("""
            border: 1px solid #e5e7eb; border-radius: 6px;
            padding: 8px; font-size: 11px; color: #374151;
            background: #f9fafb;
        """)
        sl.addWidget(self.info_display)

        layout.addWidget(section)

    # ── 公告 ──

    def _refresh_announcements(self):
        """拉取公告，显示在二维码区域（点击生成二维码后被二维码替换）"""
        try:
            items = self.client.get_announcements()
        except Exception:
            return

        if not items:
            return

        lines = ["📢 公告"]
        for a in items:
            prefix = _PRIORITY_LABEL.get(a.get("priority", ""), "")
            title = a.get("title", "")
            lines.append(f"  {prefix}{title}")
            content = a.get("content", "")
            if content:
                lines.append(f"    {content}")
        self.label_qr.setText("\n".join(lines))
        self.label_qr.setTextFormat(Qt.TextFormat.PlainText)
        self.label_qr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label_qr.setMinimumHeight(100)

    # ── 信号槽 ──

    def _on_show_qr(self, png_data: bytes, session_key: str):
        self.session_key = session_key
        pixmap = QPixmap()
        ok = pixmap.loadFromData(png_data)
        print(f"[qidian_login] QPixmap.loadFromData: {ok}, size={pixmap.size() if ok else 'N/A'}", file=sys.stderr)
        if ok:
            scaled = pixmap.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio)
            self.label_qr.setPixmap(scaled)
            self.status_label.setText("等待起点 App 扫码...")
            self._start_polling()
        else:
            self.label_qr.setText("二维码解码失败")

    def _on_error(self, msg: str):
        QMessageBox.warning(self, "错误", msg)

    def _on_done(self):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("  重新生成")

    def _on_poll_result(self, cookies: dict):
        if cookies and cookies.get("ywguid"):
            save_cookies(cookies)
            ywkey_preview = cookies.get("ywkey", "")[:8] + "..." if cookies.get("ywkey") else "N/A"
            self.status_label.setText("扫码成功!")
            self.info_display.setText(
                f"ywguid: {cookies.get('ywguid', '')}\n"
                f"ywkey: {ywkey_preview}\n"
                f"Cookie 已保存到本地"
            )
        else:
            self.status_label.setText("扫码失败，未获取到有效 Cookie")

    # ── 后台线程 ──

    def _generate_qr(self):
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("生成中...")
        self.status_label.setText("正在获取二维码...")
        self.info_display.clear()
        # 重置二维码区域（清除公告文字）
        self.label_qr.clear()
        self.label_qr.setTextFormat(Qt.TextFormat.AutoText)
        self.label_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_qr.setMinimumHeight(280)

        def _do():
            try:
                print("[qidian_login] 调用 get_qrcode()...", file=sys.stderr)
                result = get_qrcode()
                print(f"[qidian_login] 结果: {list(result.keys())}", file=sys.stderr)

                if "error" in result:
                    self._sig.show_error.emit(result["error"])
                    return

                session_key = result.get("sessionKey", "")
                img_b64 = result.get("imageBase64", "")

                if not session_key:
                    self._sig.show_error.emit("未获取到 SessionKey")
                    return

                if img_b64:
                    img_data = base64.b64decode(img_b64)
                    print(f"[qidian_login] 图片 {len(img_data)} 字节, 魔数: {img_data[:4].hex()}", file=sys.stderr)
                    self._sig.show_qr.emit(img_data, session_key)
                else:
                    self._sig.show_text.emit("二维码数据为空")
            except Exception as e:
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._sig.show_error.emit(f"生成失败: {str(e)}")
            finally:
                self._sig.done.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _start_polling(self):
        if self._polling or not self.session_key:
            return
        self._polling = True

        def _poll():
            try:
                cookies = poll_qrcode(self.session_key, timeout=120)
                self._sig.poll_result.emit(cookies or {})
            except Exception as e:
                import traceback
                traceback.print_exc(file=sys.stderr)
                self._sig.poll_error.emit(str(e))
            finally:
                self._polling = False

        threading.Thread(target=_poll, daemon=True).start()

    def stop_polling(self):
        self._polling = False
