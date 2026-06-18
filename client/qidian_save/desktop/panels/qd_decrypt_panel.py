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
from ...adb_utils import load_config as _load_adb_config, save_config as _save_adb_config
from ..components import PageHeader, SurfaceCard, configure_page_layout


# ── 工具函数（无解密逻辑） ─────────────────────────────────────────

_MAX_QD_ZIP_UPLOAD_BYTES = 90_000_000

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


def _qd_zip_arcname(chapter: dict) -> str:
    user_id = str(chapter.get("userId", "")).strip() or "unknown"
    book_id = str(chapter["bookId"]).strip()
    chapter_id = str(chapter["chapterId"]).strip()
    return f"{user_id}/{book_id}/{chapter_id}.qd"


def _build_qd_zip_manifest(chapters: list[dict]) -> dict:
    books: dict[str, dict] = {}
    for chapter in chapters:
        book_id = str(chapter.get("bookId", "")).strip()
        chapter_id = str(chapter.get("chapterId", "")).strip()
        if not book_id or not chapter_id:
            continue
        book = books.setdefault(book_id, {
            "bookName": str(chapter.get("bookName", "") or ""),
            "chapters": {},
        })
        if not book.get("bookName") and chapter.get("bookName"):
            book["bookName"] = str(chapter.get("bookName"))
        chapter_name = chapter.get("chapterName")
        if chapter_name:
            book["chapters"][chapter_id] = str(chapter_name)
    return {"books": books}


def _metadata_qd_entries(chapters: list[dict]) -> list[tuple[Path, str]]:
    entries: list[tuple[Path, str]] = []
    seen: set[tuple[str, str]] = set()
    for chapter in chapters:
        user_id = str(chapter.get("userId", "")).strip() or "unknown"
        book_id = str(chapter.get("bookId", "")).strip()
        book_dir = Path(chapter.get("bookDir") or "")
        if not book_id or not book_dir:
            continue
        key = (user_id, book_id)
        if key in seen:
            continue
        meta_path = book_dir / "-10000.qd"
        if meta_path.exists():
            entries.append((meta_path, f"{user_id}/{book_id}/-10000.qd"))
            seen.add(key)
    return entries


def _chapter_id_from_result_name(name: str) -> str:
    stem = Path(name).stem
    match = re.match(r"^(-?\d+)(?:\D|$)", stem)
    return match.group(1) if match else stem


def _chunk_qd_files_by_size(qd_files: list[tuple], max_bytes: int) -> list[list[tuple]]:
    chunks: list[list[tuple]] = []
    current: list[tuple] = []
    current_size = 0
    for item in qd_files:
        file_size = os.path.getsize(item[0])
        if current and current_size + file_size > max_bytes:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(item)
        current_size += file_size
    if current:
        chunks.append(current)
    return chunks


def _build_merged_book_text(
    book_name: str,
    txt_files: list[Path],
    include_metadata: bool,
    include_toc: bool,
    include_chapter_separators: bool = False,
) -> str:
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
        if include_chapter_separators:
            title_clean = re.sub(r"^\d+\.\s*", "", tf.stem)
            text = f"{'=' * 20} {title_clean} {'=' * 20}\n\n{text}"
        chapter_texts.append(text)

    body = "\n\n".join(chapter_texts)
    if lines:
        return "\n".join(lines).rstrip() + "\n\n" + body
    return body


class _DecryptSignal(QObject):
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    book_list_ready = pyqtSignal(list)
    decrypt_done = pyqtSignal(str)
    params_ready = pyqtSignal(str, str, str)
    busy_changed = pyqtSignal(bool)
    book_name_ready = pyqtSignal(str, str)  # bookId, bookName
    seed_status_changed = pyqtSignal(str)


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
        self._decrypt_session_ref = ""
        self._seed_status = "未检测"
        self._init_ui()
        self._sig.seed_status_changed.connect(self.label_seed_status.setText)
        self._load_config_silent()
        self._check_device()

    # ── UI ──────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = configure_page_layout(self, margins=(24, 20, 24, 20), spacing=12)
        layout.addWidget(PageHeader(
            "本地备份",
            "连接设备、拉取章节并上传服务端完成解密",
            "DEVICE WORKSPACE",
        ))

        # ── 顶部：状态 + 操作按钮 ──
        top = SurfaceCard()
        tr = QHBoxLayout(top)
        tr.setContentsMargins(16, 12, 16, 12)
        tr.setSpacing(10)

        self.label_device = QPushButton("检测 ADB...")
        self.label_device.setProperty("btn-type", "ghost")
        self.label_device.setProperty("status", "pending")
        self.label_device.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label_device.clicked.connect(self._check_device)
        tr.addWidget(self.label_device)

        self.input_device = QComboBox()
        self.input_device.setMinimumWidth(200)
        self.input_device.setFixedHeight(34)
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

        self.btn_auto_detect = QPushButton("  自动检测")
        self.btn_auto_detect.setProperty("btn-type", "primary")
        self.btn_auto_detect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_detect.setFixedHeight(38)
        self.btn_auto_detect.clicked.connect(self._auto_detect_seed)
        tr.addWidget(self.btn_auto_detect)

        self.label_seed_status = QLabel("未检测")
        self.label_seed_status.setProperty("ui-role", "status")
        tr.addWidget(self.label_seed_status)

        layout.addWidget(top)

        # ── 中部：书籍 + 章节列表 ──
        center = SurfaceCard()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["书名 / 章节", "状态", "大小"])
        self.tree.setAlternatingRowColors(True)
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
        bottom = SurfaceCard()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(16, 14, 16, 14)
        bl.setSpacing(10)

        action_row = QHBoxLayout()

        # 参数区域
        qimei_row = QHBoxLayout()
        qimei_row.setSpacing(8)
        self.input_qimei = QLineEdit()
        self.input_qimei.setPlaceholderText("QIMEI36（未设置则跳过解密）")
        qimei_row.addWidget(self.input_qimei, 1)
        bl.addLayout(qimei_row)

        params_row = QHBoxLayout()
        params_row.setSpacing(8)
        self.input_pool = QLineEdit()
        self.input_pool.setPlaceholderText("Pool")
        params_row.addWidget(self.input_pool, 1)

        self.input_userid = QLineEdit()
        self.input_userid.setPlaceholderText("UserID（自动从章节目录提取）")
        self.input_userid.hide()
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
        self.btn_decrypt.setProperty("btn-type", "primary")
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

        options_row = QHBoxLayout()
        options_row.setSpacing(14)

        self.chk_no_copyright = QCheckBox("不含版权信息")
        self.chk_no_copyright.setChecked(True)
        options_row.addWidget(self.chk_no_copyright)

        self.chk_include_toc = QCheckBox("包含目录")
        self.chk_include_toc.setChecked(False)
        options_row.addWidget(self.chk_include_toc)

        self.chk_chapter_separator = QCheckBox("单章分割")
        self.chk_chapter_separator.setChecked(False)
        options_row.addWidget(self.chk_chapter_separator)
        options_row.addStretch()

        action_row.addStretch()
        bl.addLayout(action_row)
        bl.addSpacing(2)
        bl.addLayout(options_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(120)
        self.log_output.setProperty("ui-role", "technical-output")
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
                status = "success"
            elif devices:
                text = f"✅ 模拟器已连接 ({devices[0]['serial']})"
                status = "success"
            else:
                text = "❌ 未检测到设备（点击重试）"
                status = "error"
            self.label_device.setText(text)
            self._set_device_status(status)
        except FileNotFoundError:
            self.label_device.setText("❌ 未找到 adb（点击重试）")
            self._set_device_status("error")
        except Exception as e:
            self.label_device.setText(f"❌ ADB 异常: {str(e)[:40]}")
            self._set_device_status("error")

    def _set_device_status(self, status: str):
        self.label_device.setProperty("status", status)
        self.label_device.style().unpolish(self.label_device)
        self.label_device.style().polish(self.label_device)

    def _qd_default_dir(self) -> str:
        """获取 qd_files 默认路径"""
        return str(Path(__file__).resolve().parent.parent.parent.parent / "qd_files")

    # ── 自动检测 TypeB 种子 ──────────────────────────────────────────

    def _auto_detect_seed(self):
        serial = self._resolve_serial()
        if not serial:
            self._sig.error.emit("未检测到 Android 设备")
            return
        self._set_busy(True, "检测中...")
        self._sig.seed_status_changed.emit("正在扫描...")
        self._sig.log.emit("正在扫描设备上的 TypeB 缓存...")

        def _run():
            tmp_dir = None
            try:
                from ...adb_utils import scan_typeb_seeds, _adb_pull
                import tempfile as _tf
                import shutil

                seeds = scan_typeb_seeds(device_serial=serial, first_only=True)
                if not seeds:
                    self._sig.log.emit("未发现可自动提取参数的缓存章节")
                    self._sig.log.emit("请在起点 App 中下载或打开更多章节后，回到这里重新检测")
                    self._seed_status = "未检测"
                    self._sig.seed_status_changed.emit("未检测")
                    self._set_busy_from_thread(False)
                    return

                seed = seeds[0]
                self._sig.log.emit(
                    f"发现 TypeB 种子: userId={seed['userId']} "
                    f"bookId={seed['bookId']} chapterId={seed['chapterId']}"
                )

                tmp_dir = _tf.mkdtemp(prefix="qdseed_")
                local_path = os.path.join(tmp_dir, f"{seed['chapterId']}.qd")
                ok = _adb_pull(seed["remotePath"], local_path, device_serial=serial)
                if not ok or not os.path.exists(local_path):
                    self._sig.error.emit("拉取种子文件失败")
                    self._seed_status = "检测失败"
                    self._sig.seed_status_changed.emit("检测失败")
                    self._set_busy_from_thread(False)
                    return

                self._sig.log.emit("正在上传种子文件到服务端，获取解密参数...")
                result = self.client.create_qd_seed_session(local_path)
                ref = result.get("decryptSessionRef", "")
                masked = result.get("qimei36Masked", {})

                if ref:
                    self._decrypt_session_ref = ref
                    cfg = _load_adb_config()
                    cfg["decryptSessionRef"] = ref
                    _save_adb_config(cfg)
                    self._update_param_inputs_state()
                    self._sig.log.emit(
                        f"✅ 解密参数已就绪！seedChapterId={seed['chapterId']} "
                        f"qimei={masked.get('prefix','')}...{masked.get('suffix','')}"
                    )
                    self._sig.log.emit("现在可以勾选章节并点击「上传解密选中章节」")
                    self._seed_status = "已就绪"
                    self._sig.seed_status_changed.emit("已就绪")
                else:
                    self._sig.error.emit("服务端返回异常，请重试")
                    self._seed_status = "检测失败"
                    self._sig.seed_status_changed.emit("检测失败")

            except Exception as e:
                self._sig.error.emit(f"自动检测失败: {e}")
                self._seed_status = "检测失败"
                self._sig.seed_status_changed.emit("检测失败")
            finally:
                if tmp_dir:
                    try:
                        import shutil
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                    except Exception:
                        pass
                self._set_busy_from_thread(False)

        threading.Thread(target=_run, daemon=True).start()

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
                pool_b64 = result.get("pool_b64", "")

                if result.get("errors"):
                    for e in result["errors"]:
                        self._sig.error.emit(f"⚠️ {e}")

                collected = []
                if qimei36:
                    self._sig.log.emit(f"✅ 提取 QIMEI36: {qimei36}")
                    collected.append("QIMEI36")
                if pool_b64:
                    self._sig.log.emit(f"✅ 提取 Pool: {pool_b64[:40]}...")
                    collected.append("Pool")

                if qimei36 or pool_b64:
                    cfg = load_config()
                    cfg.pop("decryptSessionRef", None)
                    if qimei36:
                        cfg["qimei36"] = qimei36
                    if pool_b64:
                        cfg["pool_b64"] = pool_b64
                    save_config(cfg)
                    self._decrypt_session_ref = ""
                    self._sig.params_ready.emit(qimei36, "", pool_b64)
                    self._seed_status = "手动参数"
                    self._sig.seed_status_changed.emit("手动参数")

                summary = ", ".join(collected) if collected else "无可用参数"
                self._sig.log.emit(f"🛠️ root 提取完成: {summary}")
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
                from ...adb_utils import pull_device_files_auto
                output = self._qd_default_dir()
                self._qd_dir = output
                self._sig.log.emit(f"正在从 {label} 拉取 .qd 文件...")
                result = pull_device_files_auto(output, device_serial=serial)
                mode = result.get("mode", "legacy")
                self._sig.log.emit("使用快速拉取模式" if mode == "tar" else "使用逐文件拉取模式")
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
        meta_path = book_dir / "_book_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
                name = meta.get("bookName")
                if name:
                    return str(name)
            except Exception:
                pass

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
            user_item = QTreeWidgetItem([f"用户 {uid}", f"{len(ub)} 本书", ""])
            user_item.setData(0, Qt.ItemDataRole.UserRole, ("user", uid))
            user_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            user_item.setExpanded(True)

            for b in ub:
                book_item = QTreeWidgetItem([f"{b['bookName']} ({b['bookId']})", f"{b['total']} 章", ""])
                book_item.setData(0, Qt.ItemDataRole.UserRole, b)
                book_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

                for ch in b["chapters"]:
                    size_kb = ch.get("size", 0) // 1024
                    ch_item = QTreeWidgetItem([ch["name"], ch["id"], f"{size_kb}KB"])
                    ch_item.setData(0, Qt.ItemDataRole.UserRole, ("chapter", b, ch))
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

    def _collect_selected_chapters(self) -> list[dict]:
        selected = []
        for i in range(self.tree.topLevelItemCount()):
            user_item = self.tree.topLevelItem(i)
            for j in range(user_item.childCount()):
                book_item = user_item.child(j)
                book_data = book_item.data(0, Qt.ItemDataRole.UserRole)
                if not isinstance(book_data, dict):
                    continue
                for k in range(book_item.childCount()):
                    ch_item = book_item.child(k)
                    if ch_item.checkState(0) != Qt.CheckState.Checked:
                        continue
                    ch_data = ch_item.data(0, Qt.ItemDataRole.UserRole)
                    if not (isinstance(ch_data, tuple) and len(ch_data) >= 3 and ch_data[0] == "chapter"):
                        continue
                    chapter = ch_data[2]
                    chapter_id = str(chapter["id"])
                    selected.append({
                        "userId": str(book_data.get("userId", "")),
                        "bookId": str(book_data["bookId"]),
                        "bookName": str(book_data.get("bookName", "")),
                        "bookDir": str(book_data.get("bookDir") or ""),
                        "chapterId": chapter_id,
                        "chapterName": chapter.get("name", chapter_id),
                    })
        return selected

    # ── 解密（走服务端 API） ────────────────────────────────────────

    def _do_decrypt(self):
        chapters_to_decrypt = self._collect_selected_chapters()

        if not chapters_to_decrypt:
            return

        self._set_busy(True, "解密中...")
        self._sig.log.emit(f"准备上传 {len(chapters_to_decrypt)} 章到服务端解密...")

        def _run():
            try:
                qimei = self.input_qimei.text().strip()
                pool = self.input_pool.text().strip()
                uid = chapters_to_decrypt[0].get("userId", "").strip()
                session_ref = self._decrypt_session_ref

                if not session_ref and (not qimei or not pool):
                    self._sig.error.emit("请先点「自动检测」获取解密参数，或填写 QIMEI36/Pool")
                    self._set_busy_from_thread(False)
                    return

                qd_files = []
                selected_by_chapter = {}
                for chapter in chapters_to_decrypt:
                    bid = chapter["bookId"]
                    ch_id = chapter["chapterId"]
                    book_dir = Path(chapter["bookDir"]) if chapter.get("bookDir") else Path(self._qd_dir) / chapter.get("userId", uid) / bid
                    if not book_dir.exists():
                        self._sig.log.emit(f"⚠ 未找到书籍目录: {chapter.get('userId', '')}/{bid}")
                        continue

                    fp = book_dir / f"{ch_id}.qd"
                    if fp.exists():
                        normalized_chapter = {**chapter, "bookDir": str(book_dir)}
                        qd_files.append((str(fp), _qd_zip_arcname(normalized_chapter), normalized_chapter))
                        selected_by_chapter[ch_id] = normalized_chapter
                    else:
                        self._sig.log.emit(f"⚠ 未找到章节文件: {chapter.get('userId', '')}/{bid}/{ch_id}.qd")

                if not qd_files:
                    self._sig.error.emit("未找到对应的 .qd 文件")
                    self._set_busy_from_thread(False)
                    return

                success = 0
                failed = 0
                by_book = {}
                chunks = _chunk_qd_files_by_size(qd_files, _MAX_QD_ZIP_UPLOAD_BYTES)
                if len(chunks) > 1:
                    self._sig.log.emit(f"文件较大，自动分 {len(chunks)} 批上传解密")

                import time as _time
                for batch_index, batch in enumerate(chunks, start=1):
                    batch_chapters = [item[2] for item in batch]
                    zip_path = os.path.join(
                        tempfile.gettempdir(),
                        f"qd_decrypt_{int(_time.time())}_{batch_index}.zip",
                    )
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for fp, arcname, _chapter in batch:
                            zf.write(fp, arcname)
                        manifest = _build_qd_zip_manifest(batch_chapters)
                        zf.writestr("_manifest.json", json.dumps(manifest, ensure_ascii=False))
                        for meta_path, arcname in _metadata_qd_entries(batch_chapters):
                            zf.write(meta_path, arcname)

                    batch_label = f"第 {batch_index}/{len(chunks)} 批" if len(chunks) > 1 else ""
                    self._sig.log.emit(f"已打包 {len(batch)} 个文件，上传服务端解密...{batch_label}")
                    if session_ref:
                        result = self.client.decrypt_qd_zip(zip_path, decrypt_session_ref=session_ref)
                    else:
                        result = self.client.decrypt_qd_zip(zip_path, qimei, uid, pool)
                    result_zip = result["zip_path"]
                    task_id = result.get("task_id")
                    if task_id:
                        self._sig.log.emit(f"解密任务 ID: {task_id}")

                    with zipfile.ZipFile(result_zip, "r") as zf:
                        for name in zf.namelist():
                            if name == "_errors.json":
                                try:
                                    errors = json.loads(zf.read(name))
                                    failed += len(errors)
                                    self._sig.log.emit(f"⚠️ {len(errors)} 章解密失败")
                                except Exception:
                                    pass
                                continue

                            if name == "_books.json":
                                try:
                                    books = json.loads(zf.read(name).decode("utf-8"))
                                except Exception:
                                    books = {}
                                for book_id, meta in books.items():
                                    if not isinstance(meta, dict):
                                        continue
                                    book_name = str(meta.get("bookName") or "").strip()
                                    if not book_name:
                                        continue
                                    book_targets = [
                                        c for c in selected_by_chapter.values()
                                        if str(c.get("bookId")) == str(book_id)
                                    ]
                                    for chapter in book_targets[:1]:
                                        book_dir = Path(chapter["bookDir"])
                                        (book_dir / "_book_meta.json").write_text(
                                            json.dumps({"bookName": book_name}, ensure_ascii=False),
                                            encoding="utf-8",
                                        )
                                    self._sig.book_name_ready.emit(str(book_id), book_name)
                                    self._sig.log.emit(f"✅ 书名已识别: {book_name}")
                                continue

                            if not name.endswith(".txt"):
                                continue

                            # 服务端兼容返回 {chapterId}.txt 或 {chapterId}. 章节名.txt
                            chapter_id = _chapter_id_from_result_name(name)
                            target = selected_by_chapter.get(chapter_id)
                            if not target:
                                self._sig.log.emit(f"⚠ 未知章节 ID: {chapter_id}，跳过")
                                failed += 1
                                continue

                            bid = target["bookId"]
                            book_dir = Path(target["bookDir"])
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
        include_chapter_separators = self.chk_chapter_separator.isChecked()
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
                        book_groups[(user_dir.name, book_id)] = {
                            "book_name": book_name,
                            "txt_files": tz_files,
                        }
                        total_found += len(tz_files)
                        self._sig.log.emit(f"  找到 {book_name}: {len(tz_files)} 章")

                if not book_groups:
                    self._sig.error.emit("未找到任何已解密的 .txt 文件，请先解密")
                    self._set_busy_from_thread(False)
                    return

                total_merged = 0
                used_names = set()
                for (_uid, book_id), group in sorted(book_groups.items()):
                    book_name = group["book_name"]
                    txt_files = group["txt_files"]
                    safe_name = _sanitize_filename(book_name)
                    out_path = merged_dir / f"{safe_name}.txt"
                    if out_path.name in used_names or out_path.exists():
                        out_path = merged_dir / f"{safe_name}_{book_id}.txt"
                    used_names.add(out_path.name)
                    merged_text = _build_merged_book_text(
                        book_name,
                        txt_files,
                        include_metadata=include_metadata,
                        include_toc=include_toc,
                        include_chapter_separators=include_chapter_separators,
                    )
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
            cfg = _load_adb_config()
            self.input_qimei.setText(cfg.get("qimei36", ""))
            self.input_pool.setText(cfg.get("pool_b64", ""))
            self._decrypt_session_ref = cfg.get("decryptSessionRef", "")
            if self._decrypt_session_ref:
                self._seed_status = "已就绪"
                self.label_seed_status.setText("已就绪")
            self._update_param_inputs_state()
            self._append_log("✅ 已加载解密配置")
        except Exception as e:
            self._append_log(f"❌ 加载配置失败: {e}")

    def _load_config_silent(self):
        """Auto-load config on startup without logging."""
        try:
            cfg = _load_adb_config()
            self.input_qimei.setText(cfg.get("qimei36", ""))
            self.input_pool.setText(cfg.get("pool_b64", ""))
            self._decrypt_session_ref = cfg.get("decryptSessionRef", "")
            if self._decrypt_session_ref:
                self._seed_status = "已就绪"
                self.label_seed_status.setText("已就绪")
            self._update_param_inputs_state()
        except Exception:
            pass

    def _save_config(self):
        try:
            cfg = _load_adb_config()
            # Preserve existing decryptSessionRef if not overwritten
            if self._decrypt_session_ref:
                cfg["decryptSessionRef"] = self._decrypt_session_ref
            if self.input_qimei.text().strip():
                cfg["qimei36"] = self.input_qimei.text().strip()
            if self.input_pool.text().strip():
                cfg["pool_b64"] = self.input_pool.text().strip()
            _save_adb_config(cfg)
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
        if pool_b64:
            self.input_pool.setText(pool_b64)
        if qimei36 or pool_b64:
            self._decrypt_session_ref = ""
            self._seed_status = "手动参数"
            self.label_seed_status.setText("手动参数")
            self._update_param_inputs_state()

    def _update_param_inputs_state(self):
        """有 decryptSessionRef 时禁用手动输入框，防止误输入冲突参数。"""
        disabled = bool(self._decrypt_session_ref)
        for w in (self.input_qimei, self.input_pool):
            w.setEnabled(not disabled)
            w.setToolTip("" if not disabled else "已通过自动检测获取解密参数，无需手动填写")

    def _apply_book_name(self, book_id: str, book_name: str):
        for i in range(self.tree.topLevelItemCount()):
            user_item = self.tree.topLevelItem(i)
            for j in range(user_item.childCount()):
                book_item = user_item.child(j)
                bdata = book_item.data(0, Qt.ItemDataRole.UserRole)
                if not bdata or not isinstance(bdata, dict):
                    continue
                if bdata.get("bookId") == book_id:
                    book_item.setText(0, f"{book_name} ({book_id})")
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
