""".qd 上传解密面板 — ADB 拉取 → 选章节 → 上传服务端解密"""
import os, sys, threading, sqlite3, zipfile, json, tempfile, re
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


# ── 工具函数（无解密逻辑） ─────────────────────────────────────────

def _load_chapter_names(book_dir: Path, book_id: str = "") -> dict:
    """从书籍目录的 SQLite DB 加载 ChapterId → (order_num, ChapterName)"""
    candidates = []
    if book_id:
        candidates.append(book_dir / f"{book_id}.qd")
    candidates.append(book_dir.with_suffix(".qd"))
    candidates.append(book_dir.parent / "0.qd")

    for db_path in candidates:
        if db_path.exists() and db_path.stat().st_size >= 100:
            try:
                conn = sqlite3.connect(str(db_path))
                cur = conn.cursor()
                cur.execute(
                    "SELECT ChapterId, ChapterName FROM chapter "
                    "WHERE ChapterName IS NOT NULL "
                    "ORDER BY VolumeCode, ShowOrder"
                )
                rows = cur.fetchall()
                total = len(rows)
                digits = len(str(total))
                mapping = {"_digits": digits}
                for i, (cid, cname) in enumerate(rows, start=1):
                    mapping[str(cid)] = (i, cname)
                conn.close()
                return mapping
            except Exception:
                continue
    return {}


def _sanitize_filename(name: str) -> str:
    invalid = r'<>:"/\|?*'
    for ch in invalid:
        name = name.replace(ch, " ")
    name = name.strip(". ")
    if len(name) > 120:
        name = name[:120].rstrip()
    return name or "未命名"


class _DecryptSignal(QObject):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    book_list_ready = pyqtSignal(list)
    decrypt_done = pyqtSignal(str)
    params_ready = pyqtSignal(str, str, str)
    busy_changed = pyqtSignal(bool)
    book_name_ready = pyqtSignal(str, str)  # bookId, bookName


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
        self._sig.book_name_ready.connect(self._apply_book_name)
        self._qd_dir = ""
        self._chapter_map = {}
        self._pending_open_dir = None
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

        # ── 底部：操作按钮 + 日志 ──
        bottom = QFrame()
        bottom.setStyleSheet("background: white; border-radius: 10px; padding: 10px;")
        bl = QVBoxLayout(bottom)
        bl.setSpacing(6)

        action_row = QHBoxLayout()

        # 参数区域
        params_row = QHBoxLayout()
        params_row.setSpacing(6)
        self.input_qimei = QLineEdit()
        self.input_qimei.setPlaceholderText("QIMEI36（未设置则跳过解密）")
        params_row.addWidget(self.input_qimei, 1)

        self.input_pool = QLineEdit()
        self.input_pool.setPlaceholderText("Pool")
        params_row.addWidget(self.input_pool, 1)

        self.input_userid = QLineEdit()
        self.input_userid.setPlaceholderText("UserID")
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

        self.btn_decrypt = QPushButton("  上传解密选中章节")
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

        self.btn_merge = QPushButton("  合并已解密")
        self.btn_merge.setProperty("btn-type", "secondary")
        self.btn_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_merge.setFixedHeight(40)
        self.btn_merge.clicked.connect(self._do_merge)
        action_row.addWidget(self.btn_merge)

        self.chk_no_copyright = QCheckBox("不含版权信息")
        self.chk_no_copyright.setChecked(True)
        self.chk_no_copyright.setStyleSheet("font-size: 12px; color: #64748b;")
        action_row.addWidget(self.chk_no_copyright)

        self.chk_include_toc = QCheckBox("包含目录")
        self.chk_include_toc.setChecked(False)
        self.chk_include_toc.setStyleSheet("font-size: 12px; color: #64748b;")
        action_row.addWidget(self.chk_include_toc)

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
        self.input_device.clear()
        self.input_device.addItem("自动检测（首个设备）", "")
        try:
            from ...adb_utils import list_devices
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
        serial = self.input_device.currentData()
        if serial:
            return serial
        from ...adb_utils import list_devices
        devices = list_devices()
        real = [d for d in devices if "emulator" not in d["serial"]]
        return (real[0] if real else devices[0])["serial"] if devices else None

    def _check_device(self):
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

    def _qd_default_dir(self) -> str:
        """获取 qd_files 默认路径"""
        return str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")

    # ── root 直接提取 ──────────────────────────────────────────────

    def _root_extract(self):
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
                    self._sig.params_ready.emit(qimei36, user_id, pool_b64)

                self._sig.log.emit(f"🛠️ root 提取完成: {', '.join(collected)}")
            except Exception as e:
                self._sig.error.emit(f"root 提取失败: {e}")

        threading.Thread(target=_run, daemon=True).start()

    # ── 拉取书籍 ────────────────────────────────────────────────────

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
                output = self._qd_default_dir()
                self._qd_dir = output
                self._sig.log.emit(f"正在从 {label} 拉取 .qd 文件...")
                result = pull_device_files(output, device_serial=serial)
                qd_count = result["qdFiles"]
                self._sig.log.emit(f"拉取完成：{qd_count} 个文件")
                self._scan_local_books(output)
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _scan_local_books(self, qd_dir: str):
        """扫描本地 qd_files 目录，匹配章节名映射"""
        self._sig.log.emit("正在读取书籍信息...")
        base = Path(qd_dir)
        books = []

        for user_dir in sorted(base.iterdir()):
            if not user_dir.is_dir():
                continue
            for book_dir in sorted(user_dir.iterdir()):
                if not book_dir.is_dir():
                    continue
                book_id = book_dir.name
                if book_id == "0" or not book_id.isdigit():
                    continue
                qd_files = sorted(book_dir.glob("*.qd"))
                chapter_files = [f for f in qd_files if f.stem != "-10000" and f.stem.lstrip("-").isdigit()]
                if not chapter_files:
                    continue

                # 从 SQLite DB 加载章节名映射（有序）
                name_map = _load_chapter_names(book_dir, book_id)
                chapters = []
                for cf in chapter_files:
                    ch_id = cf.stem
                    entry = name_map.get(ch_id, None)
                    display_name = entry[1] if entry else ch_id
                    chapters.append({
                        "id": ch_id, "name": display_name, "size": cf.stat().st_size,
                    })

                # 从 SQLite 元数据获取真实书名
                db_book_name = self._get_book_name(book_dir, book_id)
                books.append({
                    "bookId": book_id,
                    "bookName": db_book_name or f"书籍 {book_id}",
                    "userId": user_dir.name, "bookDir": str(book_dir),
                    "chapters": chapters, "downloaded": len(chapters), "total": len(chapters),
                })

        self._sig.book_list_ready.emit(books)

    @staticmethod
    def _get_book_name(book_dir: Path, book_id: str) -> str:
        """从 SQLite DB 元数据章节提取真实书名"""
        candidates = []
        if book_id:
            candidates.append(book_dir / f"{book_id}.qd")
        candidates.append(book_dir.with_suffix(".qd"))
        candidates.append(book_dir.parent / "0.qd")
        for db_path in candidates:
            if db_path.exists() and db_path.stat().st_size >= 100:
                try:
                    conn = sqlite3.connect(str(db_path))
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT ChapterName FROM chapter WHERE ChapterId=-10000 LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        name = row[0]
                        if name.startswith("{") and '"BookName"' in name:
                            try:
                                data = json.loads(name)
                                if data.get("BookName"):
                                    return data["BookName"]
                            except Exception:
                                pass
                        return name
                    cur.execute(
                        "SELECT ChapterName FROM chapter "
                        "WHERE VolumeCode=0 AND ChapterName IS NOT NULL "
                        "AND ChapterName != '版权信息' "
                        "ORDER BY ShowOrder LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return row[0]
                    conn.close()
                except Exception:
                    pass
        return ""

    def _show_books(self, books: list):
        self.tree.clear()
        self._chapter_map = {}

        if not books:
            item = QTreeWidgetItem(["  未找到书籍，请先连接手机拉取"])
            self.tree.addTopLevelItem(item)
            self._set_busy(False)
            return

        user_books = {}
        for b in books:
            uid = b.get("userId", "unknown")
            user_books.setdefault(uid, []).append(b)

        for uid, ub in user_books.items():
            user_item = QTreeWidgetItem([f"  👤 用户 {uid}", f"{len(ub)} 本书", ""])
            user_item.setData(0, Qt.ItemDataRole.UserRole, ("user", uid))
            user_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            user_item.setExpanded(True)

            for b in ub:
                book_item = QTreeWidgetItem([f"  📖 {b['bookName']} ({b['bookId']})", f"{b['total']} 章", ""])
                book_item.setData(0, Qt.ItemDataRole.UserRole, b)
                book_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

                for ch in b["chapters"]:
                    size_kb = ch.get("size", 0) // 1024
                    ch_item = QTreeWidgetItem([f"  📄 {ch['name']}", ch["id"], f"{size_kb}KB"])
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
        if column == 0:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and isinstance(data, tuple) and data[0] == "chapter":
                QTimer.singleShot(0, self._update_selected_count)

    def _toggle_select_all(self):
        book_item = None
        selected = self.tree.selectedItems()
        for item in selected:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("bookId"):
                book_item = item
                break
            elif isinstance(data, tuple) and data[0] == "chapter":
                book_item = item.parent()
                break
            elif isinstance(data, tuple) and data[0] == "user":
                if item.childCount() > 0:
                    book_item = item.child(0)
                break

        if not book_item:
            for i in range(self.tree.topLevelItemCount()):
                user = self.tree.topLevelItem(i)
                if user.childCount() > 0:
                    book_item = user.child(0)
                    break

        if not book_item:
            return

        all_checked = True
        for k in range(book_item.childCount()):
            if book_item.child(k).checkState(0) != Qt.CheckState.Checked:
                all_checked = False
                break

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
        self.btn_decrypt.setText(f"  上传解密选中章节 ({count})" if count else "  上传解密选中章节")
        self.btn_decrypt.setEnabled(count > 0)

    # ── 解密（走服务端 API） ────────────────────────────────────────

    def _do_decrypt(self):
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
        self._sig.log.emit(f"准备上传 {len(chapters_to_decrypt)} 章到服务端解密...")

        def _run():
            try:
                qimei = self.input_qimei.text().strip()
                pool = self.input_pool.text().strip()
                uid = self.input_userid.text().strip()

                if not qimei or not pool or not uid:
                    self._sig.error.emit("请先填写解密参数（QIMEI36/Pool/UserID）或点「加载」从配置读取")
                    self._set_busy_from_thread(False)
                    return

                # 按书籍从对应目录收集 .qd 文件
                qd_files = []
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
                                qd_files.append((str(fp), f"{bid}/{ch_id}.qd"))
                            else:
                                self._sig.log.emit(f"⚠ 未找到章节文件: {bid}/{ch_id}.qd")

                if not qd_files:
                    self._sig.error.emit("未找到对应的 .qd 文件")
                    self._set_busy_from_thread(False)
                    return

                # 打包 zip 上传服务端解密
                import time as _time
                zip_path = os.path.join(tempfile.gettempdir(), f"qd_decrypt_{int(_time.time())}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fp, arcname in qd_files:
                        zf.write(fp, arcname)

                self._sig.log.emit(f"已打包 {len(qd_files)} 个文件，上传服务端解密...")
                result = self.client.decrypt_qd_zip(zip_path, qimei, uid, pool)
                result_zip = result["zip_path"]
                task_id = result.get("task_id")
                if task_id:
                    self._sig.log.emit(f"解密任务 ID: {task_id}")

                # 构建 chapterId → bookId 映射
                ch_to_bid = {}
                for bid, ch_id, _ in chapters_to_decrypt:
                    ch_to_bid[ch_id] = bid

                success = 0
                failed = 0
                by_book = {}
                with zipfile.ZipFile(result_zip, "r") as zf:
                    for name in zf.namelist():
                        if name == "_errors.json":
                            try:
                                errors = json.loads(zf.read(name))
                                failed = len(errors)
                                self._sig.log.emit(f"⚠️ {failed} 章解密失败")
                            except Exception:
                                pass
                            continue

                        if not name.endswith(".txt"):
                            continue

                        # 服务端返回扁平文件名: {chapterId}.txt
                        chapter_id = name.replace(".txt", "")
                        bid = ch_to_bid.get(chapter_id)
                        if not bid:
                            self._sig.log.emit(f"⚠ 未知章节 ID: {chapter_id}，跳过")
                            failed += 1
                            continue

                        # 查找对应书籍目录
                        for i in range(self.tree.topLevelItemCount()):
                            user_item = self.tree.topLevelItem(i)
                            for j in range(user_item.childCount()):
                                book_item = user_item.child(j)
                                bdata = book_item.data(0, Qt.ItemDataRole.UserRole)
                                if not bdata or bdata["bookId"] != bid:
                                    continue
                                u_path = bdata.get("userId", uid)
                                book_dir = Path(self._qd_dir) / u_path / bid

                                # 用有序章节名重命名输出文件
                                name_map = _load_chapter_names(book_dir, bid)
                                entry = name_map.get(chapter_id, None)
                                if entry:
                                    order_num, ch_name = entry
                                    safe_name = _sanitize_filename(ch_name)
                                    digits = name_map.get("_digits", 0)
                                    out_name = f"{order_num:0{digits}d}. {safe_name}.txt" if digits else name
                                else:
                                    out_name = name
                                out_path = book_dir / out_name
                                counter = 1
                                while out_path.exists():
                                    out_path = book_dir / f"{out_path.stem}_{counter}.txt"
                                    counter += 1
                                out_path.write_bytes(zf.read(name))
                                success += 1
                                by_book.setdefault(bid, 0)
                                by_book[bid] += 1
                                self._sig.log.emit(f"✅ {out_name}")
                                break

                by_book_str = ", ".join(f"{k}: {v}章" for k, v in by_book.items())
                self._pending_open_dir = self._qd_dir or self._qd_default_dir()
                self._sig.decrypt_done.emit(
                    f"✅ 解密完成！{success} 成功, {failed} 失败\n📁 {by_book_str}"
                )
            except Exception as e:
                self._sig.error.emit(str(e))
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

    def _on_decrypt_done(self, msg: str):
        self._append_log(msg)
        self._set_busy(False)
        try:
            folder = self._pending_open_dir or self._qd_dir or self._qd_default_dir()
            self._pending_open_dir = None
            if folder:
                os.startfile(folder)
        except Exception:
            pass

    # ── 合并已解密 ──────────────────────────────────────────────────

    def _do_merge(self):
        base_dir = self._qd_dir or self._qd_default_dir()
        include_metadata = not self.chk_no_copyright.isChecked()
        include_toc = self.chk_include_toc.isChecked()
        self._set_busy(True, "合并中...")
        self._sig.log.emit(f"开始合并，扫描目录: {base_dir}")

        def _run():
            try:
                base = Path(base_dir)
                if not base.exists():
                    self._sig.error.emit(f"目录不存在: {base_dir}")
                    self._set_busy_from_thread(False)
                    return

                merged_dir = base.parent / "merged"
                merged_dir.mkdir(parents=True, exist_ok=True)

                # 扫描所有用户/书籍目录下的 .txt
                book_groups = {}
                total_found = 0
                for user_dir in sorted(base.iterdir()):
                    if not user_dir.is_dir():
                        continue
                    for book_dir in sorted(user_dir.iterdir()):
                        if not book_dir.is_dir():
                            continue
                        book_id = book_dir.name
                        if not book_id.isdigit():
                            continue
                        tz_files = sorted(book_dir.glob("*.txt"))
                        tz_files = [f for f in tz_files
                                    if not f.name.startswith("0. ") and f.stem != "-10000"]
                        if not tz_files:
                            continue

                        book_name = self._get_book_name(book_dir, book_id) or f"书籍{book_id}"
                        # 将单个书籍目录下的所有 .txt 按文件名排序后合并到一条记录
                        book_groups[book_name] = tz_files
                        total_found += len(tz_files)
                        self._sig.log.emit(f"  找到 {book_name}: {len(tz_files)} 章")

                if not book_groups:
                    self._sig.error.emit("未找到任何已解密的 .txt 文件，请先解密")
                    self._set_busy_from_thread(False)
                    return

                total_merged = 0
                for book_name, txt_files in sorted(book_groups.items()):
                    safe_name = _sanitize_filename(book_name)
                    out_path = merged_dir / f"{safe_name}.txt"
                    lines = []
                    if include_toc:
                        lines.append(f"《{book_name}》")
                        lines.append("=" * 40)
                        for tf in txt_files:
                            title_clean = re.sub(r"^\d+\.\s*", "", tf.stem)
                            lines.append(f"  {title_clean}")
                        lines.append("=" * 40)
                        lines.append("")

                    chapter_texts = []
                    for tf in txt_files:
                        text = tf.read_text("utf-8", errors="replace")
                        if not include_metadata:
                            tlines = text.splitlines()
                            clean_start = 0
                            for i, tl in enumerate(tlines[:10]):
                                if any(kw in tl for kw in ["版权所有", "本书来自", "www.", ".com", "免责"]):
                                    clean_start = i + 1
                                else:
                                    break
                            text = "\n".join(tlines[clean_start:]).strip()
                        chapter_texts.append(text)

                    merged_text = "\n\n".join(chapter_texts)
                    out_path.write_text(merged_text, encoding="utf-8")
                    self._sig.log.emit(f"  ✅ 已合并: {safe_name}.txt ({len(txt_files)} 章)")
                    total_merged += len(txt_files)

                self._pending_open_dir = str(merged_dir)
                self._sig.decrypt_done.emit(
                    f"✅ 合并完成！共 {total_merged} 章合并到 {len(book_groups)} 本书\n📁 {merged_dir}"
                )
            except Exception as e:
                import traceback
                self._sig.log.emit(f"❌ 合并异常: {e}")
                self._sig.log.emit(traceback.format_exc())
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

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
        d = self._qd_dir or self._qd_default_dir()
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _fill_params(self, qimei36: str, user_id: str, pool_b64: str):
        if qimei36:
            self.input_qimei.setText(qimei36)
        if user_id:
            self.input_userid.setText(user_id)
        if pool_b64:
            self.input_pool.setText(pool_b64)

    def _apply_book_name(self, book_id: str, book_name: str):
        for i in range(self.tree.topLevelItemCount()):
            user_item = self.tree.topLevelItem(i)
            for j in range(user_item.childCount()):
                book_item = user_item.child(j)
                bdata = book_item.data(0, Qt.ItemDataRole.UserRole)
                if not bdata or not isinstance(bdata, dict):
                    continue
                if bdata.get("bookId") == book_id:
                    book_item.setText(0, f"  📖 {book_name} ({book_id})")
                    bdata["bookName"] = book_name
                    return

    def _append_log(self, text: str):
        self.log_output.append(text)

    def _set_busy(self, busy: bool, text: str = ""):
        self.btn_pull.setEnabled(not busy)
        self.btn_pull.setText("拉取中..." if busy else "  📱 拉取书籍")
        if not busy:
            self._update_selected_count()
        QTimer.singleShot(10, lambda: None)

    def _set_busy_from_thread(self, busy: bool):
        self._sig.busy_changed.emit(busy)
