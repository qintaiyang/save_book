""".qd 解密面板 — 小白模式：拉取 → 选书 → 选章节 → 一键解密"""
import os, sys, threading, sqlite3, zipfile, subprocess, json, tempfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QFrame, QMessageBox, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QCheckBox, QAbstractItemView,
    QComboBox,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon


from ...zip_utils import safe_extract_zip


class _DecryptSignal(QObject):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    book_list_ready = pyqtSignal(list)
    decrypt_done = pyqtSignal(str)
    params_ready = pyqtSignal(str, str, str)
    busy_changed = pyqtSignal(bool)
    # capture_status 已废弃，由 extract_params() 替代


class QDDecryptPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._sig = _DecryptSignal()
        self._sig.log.connect(self._append_log)
        self._sig.error.connect(lambda e: self._append_log(f"❌ {e}"))
        self._sig.book_list_ready.connect(self._show_books)
        self._sig.decrypt_done.connect(self._on_decrypt_done)
        self._sig.params_ready.connect(self._fill_params)
        self._sig.busy_changed.connect(self._set_busy)
        self._qd_dir = ""           # 拉取到的 qd_files 目录
        self._current_book_id = ""  # 当前选中的书籍 ID
        self._current_book_dir = "" # 当前选中的书籍目录
        self._chapter_map = {}      # chapterId → chapterName 映射
        self._selected_ids = set()  # 用户勾选的章节 ID
        self._init_ui()
        self._check_device()

    # ── UI ──────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── 顶部：状态 + 操作按钮 ──
        top = QFrame()
        top.setStyleSheet("background: white; border-radius: 10px; padding: 14px;")
        tr = QHBoxLayout(top)
        tr.setSpacing(10)

        self.label_device = QPushButton("⏳ 检测 ADB...")
        self.label_device.setStyleSheet("font-size: 13px; padding: 4px 8px; border: none; text-align: left; background: transparent;")
        self.label_device.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label_device.clicked.connect(self._check_device)
        tr.addWidget(self.label_device)

        self.input_device = QComboBox()
        self.input_device.setMinimumWidth(200)
        self.input_device.setFixedHeight(34)
        self.input_device.setStyleSheet(
            "padding: 2px 4px; font-size: 13px; border: 1px solid #d0d0d0; border-radius: 6px;"
        )
        tr.addWidget(self.input_device)

        self.btn_pull = QPushButton("  拉取书籍")
        self.btn_pull.setProperty("btn-type", "secondary")
        self.btn_pull.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pull.setFixedHeight(38)
        self.btn_pull.clicked.connect(self._pull_books)
        tr.addWidget(self.btn_pull)

        self.btn_open_dir = QPushButton("  打开目录")
        self.btn_open_dir.setProperty("btn-type", "secondary")
        self.btn_open_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dir.setFixedHeight(38)
        self.btn_open_dir.clicked.connect(self._open_dir)
        tr.addWidget(self.btn_open_dir)

        self.btn_root_extract = QPushButton("  root提取")
        self.btn_root_extract.setProperty("btn-type", "secondary")
        self.btn_root_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_root_extract.setFixedHeight(38)
        self.btn_root_extract.clicked.connect(self._root_extract)
        tr.addWidget(self.btn_root_extract)

        layout.addWidget(top)

        # ── 中部：书籍 + 章节列表 ──
        center = QFrame()
        center.setStyleSheet("background: white; border-radius: 10px;")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["书名 / 章节", "状态", "大小"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: none; border-radius: 10px;
                font-size: 13px;
            }
            QTreeWidget::item { padding: 6px 10px; }
            QTreeWidget::item:selected { background: #eff6ff; color: #1f2937; }
            QHeaderView::section {
                background: #f8fafc; border: none;
                padding: 8px 10px; font-weight: bold;
                font-size: 12px; color: #64748b;
            }
        """)
        self.tree.setColumnCount(3)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.itemChanged.connect(self._on_item_changed)
        cl.addWidget(self.tree)

        layout.addWidget(center, 1)

        # ── 底部：解密按钮 + 日志 ──
        bottom = QFrame()
        bottom.setStyleSheet("background: white; border-radius: 10px; padding: 10px;")
        bl = QVBoxLayout(bottom)
        bl.setSpacing(6)

        action_row = QHBoxLayout()

        # 参数区域折叠成一行小字
        params_row = QHBoxLayout()
        params_row.setSpacing(6)
        self.input_qimei = QLineEdit()
        self.input_qimei.setPlaceholderText("QIMEI36（未设置则跳过解密）")
        # 输入框样式由全局 QSS 控制
        params_row.addWidget(self.input_qimei, 1)

        self.input_pool = QLineEdit()
        self.input_pool.setPlaceholderText("Pool")
        # 输入框样式由全局 QSS 控制
        params_row.addWidget(self.input_pool, 1)

        self.input_userid = QLineEdit()
        self.input_userid.setPlaceholderText("UserID")
        # 输入框样式由全局 QSS 控制
        params_row.addWidget(self.input_userid, 1)

        btn_load = QPushButton("加载")
        btn_load.setProperty("btn-type", "secondary")
        btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_load.clicked.connect(self._load_config)
        params_row.addWidget(btn_load)

        btn_save = QPushButton("保存")
        btn_save.setProperty("btn-type", "secondary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._save_config)
        params_row.addWidget(btn_save)

        bl.addLayout(params_row)

        self.btn_decrypt = QPushButton("  解密选中章节")
        self.btn_decrypt.setProperty("btn-type", "secondary")
        self.btn_decrypt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_decrypt.setFixedHeight(40)
        self.btn_decrypt.setEnabled(False)
        self.btn_decrypt.clicked.connect(self._do_decrypt)
        action_row.addWidget(self.btn_decrypt)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setProperty("btn-type", "secondary")
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        action_row.addWidget(self.btn_select_all)

        action_row.addStretch()

        bl.addLayout(action_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(120)
        self.log_output.setStyleSheet("""
            border: 1px solid #e5e7eb; border-radius: 6px;
            padding: 8px; font-size: 12px; color: #374151;
            background: #fafafa;
        """)
        bl.addWidget(self.log_output)

        layout.addWidget(bottom)

    # ── ADB 检测 ────────────────────────────────────────────────────

    def _refresh_device_list(self):
        """刷新设备下拉列表"""
        from ...adb_utils import list_devices
        self.input_device.clear()
        self.input_device.addItem("自动检测（首个设备）", "")
        try:
            devices = list_devices()
            for d in devices:
                label = d["serial"]
                if "emulator" in label:
                    label += "  [模拟器]"
                else:
                    label += "  [真机]"
                self.input_device.addItem(label, d["serial"])
        except Exception:
            pass

    def _resolve_serial(self) -> str | None:
        """从下拉框获取用户选择的设备，未选择时自动检测"""
        serial = self.input_device.currentData()
        if serial:
            return serial
        # 自动检测模式
        from ...adb_utils import list_devices
        devices = list_devices()
        real = [d for d in devices if "emulator" not in d["serial"]]
        return (real[0] if real else devices[0])["serial"] if devices else None

    def _check_device(self):
        """检测 ADB 状态并刷新下拉列表"""
        self._refresh_device_list()
        try:
            from ...adb_utils import list_devices
            devices = list_devices()
            real = [d for d in devices if "emulator" not in d["serial"]]
            if real:
                text = f"✅ 真机已连接 ({real[0]['serial']})"
                color = "#065f46"
            elif devices:
                text = f"✅ 模拟器已连接 ({devices[0]['serial']})"
                color = "#065f46"
            else:
                text = "❌ 未检测到设备（点击重试）"
                color = "#dc2626"
            self.label_device.setText(text)
            self.label_device.setStyleSheet(
                f"font-size: 13px; padding: 4px 8px; border: none; text-align: left; background: transparent; color: {color};"
            )
        except FileNotFoundError:
            self.label_device.setText("❌ 未找到 adb（点击重试）")
            self.label_device.setStyleSheet(
                "font-size: 13px; padding: 4px 8px; border: none; text-align: left; background: transparent; color: #dc2626;"
            )
        except Exception as e:
            self.label_device.setText(f"❌ ADB 异常: {str(e)[:40]}")
            self.label_device.setStyleSheet(
                "font-size: 13px; padding: 4px 8px; border: none; text-align: left; background: transparent; color: #dc2626;"
            )

    # ── root 直接提取 ──────────────────────────────────────────────

    def _root_extract(self):
        """从已 root 设备/模拟器直接提取解密参数"""
        serial = self._resolve_serial()
        label = serial or "当前设备"
        self._append_log(f"正在通过 root 从 {label} 提取参数...")

        def _run():
            try:
                from ...adb_utils import extract_params, load_config, save_config

                result = extract_params(device_serial=serial)
                qimei36 = result.get("qimei36", "")
                user_id = result.get("userId", "")
                pool_b64 = result.get("pool_b64", "")

                if result.get("errors"):
                    for e in result["errors"]:
                        self._sig.error.emit(f"⚠️ {e}")

                collected = []
                if qimei36:
                    self._sig.log.emit(f"✅ 提取 QIMEI36: {qimei36}")
                    collected.append("QIMEI36")
                if user_id:
                    self._sig.log.emit(f"✅ 提取 userId: {user_id}")
                    collected.append("userId")
                if pool_b64:
                    self._sig.log.emit(f"✅ 提取 Pool: {pool_b64[:40]}...")
                    collected.append("Pool")

                if qimei36 or user_id or pool_b64:
                    cfg = load_config()
                    if qimei36:
                        cfg["qimei36"] = qimei36
                    if user_id:
                        cfg["userId"] = user_id
                    if pool_b64:
                        cfg["pool_b64"] = pool_b64
                    save_config(cfg)

                    # 回填 UI（通过信号桥安全更新主线程）
                    self._sig.params_ready.emit(qimei36, user_id, pool_b64)

                self._sig.log.emit(f"🛠️ root 提取完成: {', '.join(collected)}")
            except Exception as e:
                self._sig.error.emit(f"root 提取失败: {e}")

        threading.Thread(target=_run, daemon=True).start()

    # ── 拉取书籍 ────────────────────────────────────────────────────

    # （mitmproxy 参数捕获已移除，使用 🛠️ root提取 替代）

    def _pull_books(self):
        serial = self._resolve_serial()
        if not serial:
            self._sig.error.emit("未检测到 Android 设备，请连接 USB 或输入端口号")
            return
        label = serial

        self._set_busy(True, "拉取中...")

        def _run():
            try:
                from ...adb_utils import pull_device_files

                output = str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")
                self._qd_dir = output
                self._sig.log.emit(f"正在从 {label} 拉取 .qd 文件...")
                result = pull_device_files(output, device_serial=serial)
                qd_count = result["qdFiles"]
                self._sig.log.emit(f"拉取完成：{qd_count} 个文件")

                # 扫描拉取到的目录，识别书籍
                self._scan_local_books(output)
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _scan_local_books(self, qd_dir: str):
        """扫描本地 qd_files 目录，根据 .qd 文件名 + SQLite + 书架匹配书籍"""
        self._sig.log.emit("正在读取书籍信息...")
        base = Path(qd_dir)
        books = []

        # 尝试从书架获取书名映射（静默，失败不阻塞）
        book_names = {}  # bookId → bookName
        try:
            from ...qidian_client import get_bookshelf, load_cookies
            cookies = load_cookies()
            if cookies:
                shelf = get_bookshelf(cookies)
                for b in shelf:
                    book_names[b["bookId"]] = b["bookName"]
                if book_names:
                    self._sig.log.emit(f"已从书架匹配 {len(book_names)} 本书名")
        except Exception:
            pass

        for user_dir in sorted(base.iterdir()):
            if not user_dir.is_dir():
                continue

            # 找书籍子目录（每个子目录名 = bookId，内含章节 .qd 文件）
            for book_dir in sorted(user_dir.iterdir()):
                if not book_dir.is_dir():
                    continue
                book_id = book_dir.name
                if book_id == "0" or not book_id.isdigit():
                    continue

                # 列出该目录下所有 .qd 文件（排除 -10000.qd 元数据文件）
                qd_files = sorted(book_dir.glob("*.qd"))
                chapter_files = [f for f in qd_files if f.stem != "-10000" and f.stem.lstrip("-").isdigit()]

                if not chapter_files:
                    continue

                # 尝试从 SQLite 数据库读取章节名（优先书籍目录内，兼容旧版 userId 根目录）
                db_path = book_dir / f"{book_id}.qd"
                if not db_path.exists():
                    db_path = user_dir / f"{book_id}.qd"
                chapter_names = {}  # chapterId → {name, isVip}
                if db_path.exists() and db_path.stat().st_size > 1000:
                    hdr = db_path.read_bytes()[:4]
                    if hdr == b"SQLi":
                        try:
                            conn = sqlite3.connect(str(db_path))
                            cur = conn.cursor()
                            cur.execute("SELECT ChapterId, ChapterName, IsVip FROM chapter")
                            for r in cur.fetchall():
                                chapter_names[str(r[0])] = {
                                    "name": r[1] or str(r[0]),
                                    "isVip": bool(r[2]),
                                }
                            conn.close()
                        except Exception:
                            pass

                # 组装章节列表：只包含实际有 .qd 文件的章节
                chapters = []
                for cf in chapter_files:
                    cid = cf.stem
                    info = chapter_names.get(cid, {"name": cid, "isVip": False})
                    chapters.append({
                        "id": cid,
                        "name": info["name"],
                        "isVip": info["isVip"],
                        "size": cf.stat().st_size,
                    })

                # 从书架匹配书名，没有则用 ID
                book_name = book_names.get(book_id, f"书籍 {book_id}")

                books.append({
                    "bookId": book_id,
                    "bookName": book_name,
                    "userId": user_dir.name,
                    "bookDir": str(book_dir),
                    "chapters": chapters,
                    "downloaded": len(chapters),
                    "total": len(chapters),
                })

        self._sig.book_list_ready.emit(books)

    def _show_books(self, books: list):
        self.tree.clear()
        self._chapter_map = {}

        if not books:
            item = QTreeWidgetItem(["  未找到书籍，请先连接手机拉取"])
            self.tree.addTopLevelItem(item)
            self._set_busy(False)
            return

        # 按用户分组（dict 插入有序，Python 3.7+）
        user_books = {}
        for b in books:
            uid = b.get("userId", "unknown")
            user_books.setdefault(uid, []).append(b)

        for uid, ub in user_books.items():
            # 用户级别
            user_item = QTreeWidgetItem([f"  👤 用户 {uid}", f"{len(ub)} 本书", ""])
            user_item.setData(0, Qt.ItemDataRole.UserRole, ("user", uid))
            user_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            user_item.setExpanded(True)

            for b in ub:
                vip_count = sum(1 for ch in b["chapters"] if ch["isVip"])
                free_count = sum(1 for ch in b["chapters"] if not ch["isVip"])
                label = f"  📖 {b['bookName']} ({b['bookId']})"
                status = f"{b['total']} 章"
                info = f"免费{free_count}+付费{vip_count}"

                book_item = QTreeWidgetItem([label, status, info])
                book_item.setData(0, Qt.ItemDataRole.UserRole, b)
                book_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

                # 显示所有章节（带复选框）
                for ch in b["chapters"]:
                    vip_tag = "🔒" if ch["isVip"] else "📄"
                    size_kb = ch.get("size", 0) // 1024
                    ch_item = QTreeWidgetItem([
                        f"  {vip_tag} {ch['name']}",
                        ch["id"],
                        f"{size_kb}KB",
                    ])
                    ch_item.setData(0, Qt.ItemDataRole.UserRole, ("chapter", b["bookId"], ch))
                    ch_item.setFlags(ch_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    ch_item.setCheckState(0, Qt.CheckState.Unchecked)
                    self._chapter_map[ch["id"]] = ch["name"]
                    book_item.addChild(ch_item)

                user_item.addChild(book_item)

            self.tree.addTopLevelItem(user_item)

        total_chapters = sum(b['total'] for b in books)
        self._sig.log.emit(f"找到 {len(user_books)} 个用户, {len(books)} 本书, 共 {total_chapters} 章")
        self._set_busy(False)

    # ── 全选/取消 ───────────────────────────────────────────────────

    def _on_item_changed(self, item, column):
        """章节勾选状态变化时更新按钮"""
        if column == 0:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and isinstance(data, tuple) and data[0] == "chapter":
                QTimer.singleShot(0, self._update_selected_count)

    def _toggle_select_all(self):
        """全选当前选中书籍的全部章节"""
        # 找当前选中的书籍节点
        book_item = None
        selected = self.tree.selectedItems()
        for item in selected:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("bookId"):
                # 选中了书籍节点
                book_item = item
                break
            elif isinstance(data, tuple) and data[0] == "chapter":
                # 选中了章节 → 找父节点（书籍）
                book_item = item.parent()
                break
            elif isinstance(data, tuple) and data[0] == "user":
                # 选中了用户 → 取该用户下第一本书
                if item.childCount() > 0:
                    book_item = item.child(0)
                break

        # 仍然没找到 → 取树中第一本书
        if not book_item:
            for i in range(self.tree.topLevelItemCount()):
                user = self.tree.topLevelItem(i)
                if user.childCount() > 0:
                    book_item = user.child(0)
                    break

        if not book_item:
            return  # 树上没有书

        # 检查该书籍下是否全部已选
        all_checked = True
        for k in range(book_item.childCount()):
            if book_item.child(k).checkState(0) != Qt.CheckState.Checked:
                all_checked = False
                break

        # 切换该书籍下所有章节
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for k in range(book_item.childCount()):
            book_item.child(k).setCheckState(0, new_state)

        self._update_selected_count()

    def _update_selected_count(self):
        count = 0
        for i in range(self.tree.topLevelItemCount()):
            user = self.tree.topLevelItem(i)
            for j in range(user.childCount()):
                book = user.child(j)
                for k in range(book.childCount()):
                    if book.child(k).checkState(0) == Qt.CheckState.Checked:
                        count += 1
        self.btn_decrypt.setText(f"  解密选中章节 ({count})" if count else "  解密选中章节")
        self.btn_decrypt.setEnabled(count > 0)

    # ── 解密 ────────────────────────────────────────────────────────

    def _do_decrypt(self):
        # 收集勾选的章节（3 层树：User → Book → Chapter）
        chapters_to_decrypt = []
        for i in range(self.tree.topLevelItemCount()):
            user_item = self.tree.topLevelItem(i)
            for j in range(user_item.childCount()):
                book = user_item.child(j)
                for k in range(book.childCount()):
                    ch = book.child(k)
                    if ch.checkState(0) == Qt.CheckState.Checked:
                        ch_data = ch.data(0, Qt.ItemDataRole.UserRole)
                        if ch_data:
                            _, bid, ch_info = ch_data
                            chapters_to_decrypt.append((bid, ch_info["id"], ch_info["name"]))

        if not chapters_to_decrypt:
            return

        self._set_busy(True, "解密中...")
        self._sig.log.emit(f"准备解密 {len(chapters_to_decrypt)} 章（来自 {len(set(c[0] for c in chapters_to_decrypt))} 本书）...")

        def _run():
            try:
                qimei = self.input_qimei.text().strip()
                pool = self.input_pool.text().strip()
                uid = self.input_userid.text().strip()

                if not qimei or not pool or not uid:
                    self._sig.error.emit("请先填写解密参数（QIMEI36/Pool/UserID）或点「加载」从配置读取")
                    self._set_busy_from_thread(False)
                    return

                # 按书籍分组，从对应目录收集 .qd 文件
                import time, tempfile
                qd_files = []  # [(full_path, arcname_in_zip)]
                for i in range(self.tree.topLevelItemCount()):
                    user_item = self.tree.topLevelItem(i)
                    for j in range(user_item.childCount()):
                        book_item = user_item.child(j)
                        bdata = book_item.data(0, Qt.ItemDataRole.UserRole)
                        if not bdata:
                            continue
                        bid = bdata["bookId"]
                        u_dir = bdata.get("userId", uid)

                        book_chapters = [c for c in chapters_to_decrypt if c[0] == bid]
                        if not book_chapters:
                            continue

                        book_dir = Path(self._qd_dir) / u_dir / bid
                        if not book_dir.exists():
                            self._sig.log.emit(f"⚠ 未找到书籍目录: {bid}")
                            continue

                        for ch_id, _ch_name in [(c[1], c[2]) for c in book_chapters]:
                            fp = book_dir / f"{ch_id}.qd"
                            if fp.exists():
                                # arcname 用 bookId/chapterId.qd 避免跨书文件名冲突
                                qd_files.append((str(fp), f"{bid}/{ch_id}.qd"))
                            else:
                                self._sig.log.emit(f"⚠ 未找到章节文件: {bid}/{ch_id}.qd")

                if not qd_files:
                    self._sig.error.emit("未找到对应的 .qd 文件（章节可能未下载到手机）")
                    self._set_busy_from_thread(False)
                    return

                # 打包 zip
                zip_path = os.path.join(tempfile.gettempdir(), f"qd_decrypt_{int(time.time())}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fp, arcname in qd_files:
                        zf.write(fp, arcname)

                self._sig.log.emit(f"已打包 {len(qd_files)} 个文件，上传服务端解密...")

                # 上传解密
                result = self.client.decrypt_qd_zip(zip_path, qimei, uid, pool)
                result_zip = result["zip_path"]
                task_id = result.get("task_id")
                if task_id:
                    self._sig.log.emit(f"解密任务 ID: {task_id}")

                # 解压结果
                extract_dir = tempfile.mkdtemp(prefix="qd_decrypt_", dir=self._qd_dir)
                with zipfile.ZipFile(result_zip, "r") as zf:
                    safe_extract_zip(zf, extract_dir)

                txt_count = len(list(Path(extract_dir).rglob("*.txt")))
                self._sig.decrypt_done.emit(
                    f"✅ 解密完成！{txt_count} 个文件\n"
                    f"📁 {extract_dir}"
                )
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _on_decrypt_done(self, msg: str):
        self._append_log(msg)
        self._set_busy(False)
        # 自动打开目录
        try:
            import subprocess
            subprocess.Popen(["explorer", msg.split("📁 ")[-1].strip()])
        except Exception:
            pass

    # ── 配置管理 ────────────────────────────────────────────────────

    def _load_config(self):
        try:
            from ...adb_utils import load_config
            cfg = load_config()
            self.input_qimei.setText(cfg.get("qimei36", ""))
            self.input_pool.setText(cfg.get("pool_b64", ""))
            self.input_userid.setText(cfg.get("userId", ""))
            self._append_log("✅ 已加载解密配置")
        except Exception as e:
            self._append_log(f"❌ 加载配置失败: {e}")

    def _save_config(self):
        try:
            from ...adb_utils import save_config
            save_config({
                "qimei36": self.input_qimei.text().strip(),
                "pool_b64": self.input_pool.text().strip(),
                "userId": self.input_userid.text().strip(),
            })
            self._append_log("✅ 配置已保存")
        except Exception as e:
            self._append_log(f"❌ 保存失败: {e}")

    # ── 工具 ────────────────────────────────────────────────────────

    def _open_dir(self):
        d = self._qd_dir or str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _fill_params(self, qimei36: str, user_id: str, pool_b64: str):
        if qimei36:
            self.input_qimei.setText(qimei36)
        if user_id:
            self.input_userid.setText(user_id)
        if pool_b64:
            self.input_pool.setText(pool_b64)

    def _append_log(self, text: str):
        self.log_output.append(text)

    def _set_busy(self, busy: bool, text: str = ""):
        self.btn_pull.setEnabled(not busy)
        self.btn_pull.setText("拉取中..." if busy else "  📱 拉取书籍")
        if not busy:
            self._update_selected_count()
        # 强制刷新 UI
        QTimer.singleShot(10, lambda: None)

    def _set_busy_from_thread(self, busy: bool):
        """Safely request busy-state changes from a worker thread."""
        self._sig.busy_changed.emit(busy)

    # 按钮样式由全局 QSS 控制
