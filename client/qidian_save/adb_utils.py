"""ADB 工具 — 从 Android 设备拉取 QDReader .qd 文件及数据库

ADB 查找优先级：
  1. 项目捆绑的 client/adb/adb.exe
  2. 系统 PATH 中的 adb
"""
import json, os, subprocess, sqlite3, struct, sys, zipfile, re, tempfile
from pathlib import Path
from typing import Optional

ADB_BASE = "/storage/emulated/0/Android/data/com.qidian.QDReader/files/QDReader/book"
PROJECT_DIR = Path(__file__).resolve().parent.parent


def _find_adb() -> str:
    """查找可用的 adb 可执行文件路径

    优先使用项目捆绑的 adb，找不到则回退到系统 PATH。
    """
    bundled = PROJECT_DIR / "adb"
    for exe in ["adb.exe", "adb"]:
        p = bundled / exe
        if p.exists():
            return str(p)
    # 回退到系统 PATH
    return "adb"

# 设备内 priv-app 路径（root 访问）
_PRIV_DB = "/data/data/com.qidian.QDReader/databases"
_PRIV_MMKV = "/data/data/com.qidian.QDReader/files/mmkv"


def _log(msg: str):
    print(f"[adb] {msg}", file=sys.stderr)


# ── 多设备支持 ──────────────────────────────────────────────────────

_ADB_PATH = _find_adb()  # 缓存 adb 路径


def _adb_prefix(device_serial: str | None = None) -> list[str]:
    """返回 adb 前缀，如果指定设备则加 -s"""
    base = [_ADB_PATH]
    return base + ["-s", device_serial] if device_serial else base


def list_devices() -> list[dict]:
    """列出已连接的 ADB 设备

    Returns:
        [{"serial": str, "status": str}, ...]
    """
    try:
        r = subprocess.run([_ADB_PATH, "devices"], capture_output=True, text=True, timeout=5)
        devices = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if "\t" in line:
                serial, status = line.split("\t", 1)
                if status == "device":
                    devices.append({"serial": serial, "status": status})
        return devices
    except Exception:
        return []


# ── 配置管理 ────────────────────────────────────────────────────────

def config_path() -> Path:
    d = PROJECT_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "qd_config.json"


def load_config() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            pass
    return {"qimei36": "", "pool_b64": "", "userId": ""}


def save_config(cfg: dict):
    config_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _log(f"配置已保存 → {config_path()}")


# ── ADB 命令 ────────────────────────────────────────────────────────

def adb_command(cmd: str, timeout: int = 10, device_serial: str | None = None) -> str:
    """执行 adb shell 命令，返回 stdout

    使用 list 形式避免 Git Bash (MSYS2) 路径转换。
    """
    parts = cmd.split()
    base = _adb_prefix(device_serial)
    r = subprocess.run(base + ["shell"] + parts,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.strip()
        if "no devices" in err or "device" not in err.lower():
            raise RuntimeError("未检测到 Android 设备，请连接 USB 并开启调试")
        if err:
            _log(f"adb 警告: {err}")
    return r.stdout


def adb_su(cmd: str, timeout: int = 10, device_serial: str | None = None) -> subprocess.CompletedProcess:
    """以 root 权限执行 adb shell su -c 命令

    注意: su -c 要求 COMMAND 是最后一个参数（之后的参数被视为 user/login），
    所以需要内部引号包装: su -c "cmd"。
    """
    base = _adb_prefix(device_serial)
    return subprocess.run(
        base + ["shell", "su", "-c", f'"{cmd}"'],
        capture_output=True, text=True, timeout=timeout,
    )


def _adb_pull(remote: str, local: str, device_serial: str | None = None) -> bool:
    """用 adb pull 拉取文件"""
    local = str(Path(local).resolve())
    base = _adb_prefix(device_serial)
    r = subprocess.run(base + ["pull", remote, local],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def check_device() -> bool:
    """检查是否有可用的 Android 设备"""
    return len(list_devices()) > 0


def check_root(device_serial: str | None = None) -> bool:
    """检查设备是否有 root 权限 (su)"""
    try:
        r = adb_su("echo ok", timeout=10, device_serial=device_serial)
        return r.stdout.strip() == "ok"
    except Exception:
        return False


# ── Root 提取解密参数 ──────────────────────────────────────────────

def _root_copy(src: str, dst: str, device_serial: str | None = None) -> bool:
    """用 root 权限复制文件到 sdcard 以供 adb pull"""
    r = adb_su(f"cp {src} {dst}", timeout=10, device_serial=device_serial)
    return r.returncode == 0


def _extract_qimei36_from_beacon(data: bytes) -> str:
    """从 beacon 数据库二进制数据中提取 QIMEI36

    beacon DB 使用 Java 序列化格式存储事件，qimei36 以
    0x74(String marker) + 2byte BE length + content 格式出现。
    """
    for m in re.finditer(b"qimei36", data):
        marker = data[m.end()] if m.end() < len(data) else 0
        if marker != 0x74:
            continue
        str_len = (data[m.end() + 1] << 8) | data[m.end() + 2]
        start = m.end() + 3
        if str_len != 36 or start + 36 > len(data):
            continue
        raw = data[start:start + 36]
        val = raw.decode("ascii", errors="replace")
        if all(c in "0123456789abcdef" for c in val):
            return val
    return ""


def _extract_pool_from_mmkv(data: bytes) -> str:
    """从 MMKV pref_utils 数据中提取 Pool

    Pool 以 JSON 格式存储在 pref_fock_key 键下：
      pref_fock_key + protobuf_len + {"timestamp":"<base64>"}
    """
    key_idx = data.find(b"pref_fock_key")
    if key_idx < 0:
        return ""
    for m in re.finditer(rb"[A-Za-z0-9+/]{100,}={0,2}", data[key_idx:]):
        return m.group().decode("ascii", errors="replace")
    return ""


def extract_params(device_serial: str | None = None) -> dict:
    """从已 root 的 Android 设备直接提取解密参数

    步骤:
      1. 检查 root 可用
      2. 拉取 beacon DB → 提取 QIMEI36
      3. 读取书籍目录 → 提取 userId
      4. 拉取 MMKV pref_utils → 提取 Pool

    Args:
        device_serial: 可选，指定设备序列号

    Returns:
        {"qimei36": str, "pool_b64": str, "userId": str, "errors": [str]}
        未提取到的字段为空字符串
    """
    result = {"qimei36": "", "pool_b64": "", "userId": "", "errors": []}

    if not check_root(device_serial):
        result["errors"].append("root 不可用，请确认设备已 root 或使用模拟器")
        return result

    tmp = tempfile.gettempdir()

    # ── 1. 提取 QIMEI36 ──
    for db_name in ["beacon_db_com.qidian.QDReader", "beacon_db_0I000JZU8B16UN21"]:
        remote = f"{_PRIV_DB}/{db_name}"
        local = os.path.join(tmp, db_name)
        if _root_copy(remote, f"/sdcard/{db_name}", device_serial):
            if _adb_pull(f"/sdcard/{db_name}", local, device_serial):
                if os.path.exists(local):
                    data = Path(local).read_bytes()
                    qimei36 = _extract_qimei36_from_beacon(data)
                    if qimei36:
                        result["qimei36"] = qimei36
                        break

    # ── 2. 提取 userId（从书籍目录名） ──
    out = adb_command(
        f"ls {ADB_BASE}", timeout=10, device_serial=device_serial
    )
    for line in out.splitlines():
        uid = line.strip()
        if uid.isdigit():
            result["userId"] = uid
            break

    # ── 3. 提取 Pool（从 MMKV） ──
    if _root_copy(
        f"{_PRIV_MMKV}/pref_utils", "/sdcard/pref_utils", device_serial
    ):
        local = os.path.join(tmp, "pref_utils")
        if _adb_pull("/sdcard/pref_utils", local, device_serial):
            if os.path.exists(local):
                pool = _extract_pool_from_mmkv(Path(local).read_bytes())
                if pool:
                    result["pool_b64"] = pool

    # ── 4. 报错收集 ──
    if not result["qimei36"]:
        result["errors"].append("未提取到 QIMEI36")
    if not result["userId"]:
        result["errors"].append("未提取到 userId（书架为空？）")
    if not result["pool_b64"]:
        result["errors"].append("未提取到 Pool（未下载过付费章节？）")

    return result


# ── 扫描 ────────────────────────────────────────────────────────────

def scan_device(device_serial: str | None = None) -> list[dict]:
    """扫描设备上的所有 .qd 文件和书籍目录

    Args:
        device_serial: 可选，指定设备序列号

    Returns:
        [{"userId": str, "bookId": str, "fileCount": int, "files": [str]}, ...]
    """
    result = []
    out = adb_command(f"ls {ADB_BASE}", device_serial=device_serial)
    user_dirs = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.startswith("total")]

    for uid in user_dirs:
        src_base = f"{ADB_BASE}/{uid}"
        out2 = adb_command(f"ls {src_base}", device_serial=device_serial)
        entries = [l.strip() for l in out2.splitlines()
                   if l.strip() and not l.startswith("total")]

        for entry in entries:
            if entry.endswith(".qd") or entry.endswith(".qd-journal"):
                continue
            # 检查是否为目录（尝试 ls）
            sub_out = adb_command(f"ls {src_base}/{entry}", device_serial=device_serial)
            sub_files = [l.strip() for l in sub_out.splitlines()
                         if l.strip() and not l.startswith("total")]
            qd_files = [f for f in sub_files if f.endswith(".qd")]

            # 也拉一些 SQLite 数据库
            dbs = [f for f in sub_files if f.endswith(".db") or f == "0.qd" and len(sub_files) > 100]

            if qd_files:
                result.append({
                    "userId": uid,
                    "bookId": entry,
                    "fileCount": len(qd_files),
                    "files": qd_files[:10],
                    "databases": dbs[:5],
                })

    return result


def pull_device_files(output_dir: str | Path, device_serial: str | None = None) -> dict:
    """拉取设备上所有 .qd 文件和数据库

    Args:
        output_dir: 本地保存目录
        device_serial: 可选，指定设备序列号

    Returns:
        {"total": int, "qdFiles": int, "databases": int, "users": [{"userId": str, "count": int}]}
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = adb_command(f"ls {ADB_BASE}", device_serial=device_serial)
    user_dirs = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.startswith("total")]

    total_qd = 0
    total_db = 0
    users = []

    for uid in user_dirs:
        local_uid = out_dir / uid
        local_uid.mkdir(parents=True, exist_ok=True)
        src_base = f"{ADB_BASE}/{uid}"

        out2 = adb_command(f"ls {src_base}", device_serial=device_serial)
        entries = [l.strip() for l in out2.splitlines()
                   if l.strip() and not l.startswith("total")]

        count = 0
        for entry in entries:
            # 跳过 .qd-journal 等临时文件
            if entry.endswith(".qd-journal"):
                continue

            if entry.endswith(".qd"):
                # userId 目录下的 .qd 文件通常是 SQLite 数据库（章节名映射用）
                # 提取 bookId (文件名去掉 .qd），拉到对应书籍目录内
                maybe_bid = entry[:-3]
                if maybe_bid.isdigit() and (local_uid / maybe_bid).is_dir():
                    _adb_pull(f"{src_base}/{entry}", str(local_uid / maybe_bid / entry),
                              device_serial=device_serial)
                    total_db += 1
                continue

            # 书籍子目录
            sub_out = adb_command(f"ls {src_base}/{entry}", device_serial=device_serial)
            sub_files = [l.strip() for l in sub_out.splitlines()
                         if l.strip() and not l.startswith("total")]
            if not sub_files:
                continue

            book_dir = local_uid / entry
            book_dir.mkdir(parents=True, exist_ok=True)

            for sf in sub_files:
                if sf.endswith(".qd"):
                    if _adb_pull(f"{src_base}/{entry}/{sf}", str(book_dir / sf),
                                 device_serial=device_serial):
                        total_qd += 1
                        count += 1

        if count:
            users.append({"userId": uid, "count": count})

    return {"total": total_qd + total_db, "qdFiles": total_qd, "databases": total_db, "users": users}


# ── 数据库查看 ──────────────────────────────────────────────────────

def create_qd_zip(qd_dir: str | Path, output_zip: str | Path = None) -> str:
    """将目录下所有 .qd 文件打包为 zip

    Args:
        qd_dir: 包含 .qd 文件的目录
        output_zip: 输出 zip 路径（默认自动生成）

    Returns:
        zip 文件路径
    """
    qd_dir = Path(qd_dir)
    if output_zip is None:
        output_zip = qd_dir.parent / f"{qd_dir.name}_qd_files.zip"

    qd_files = sorted(qd_dir.rglob("*.qd"))
    qd_files = [f for f in qd_files if ".qd-journal" not in f.name]

    if not qd_files:
        raise FileNotFoundError(f"目录下无 .qd 文件: {qd_dir}")

    with zipfile.ZipFile(str(output_zip), "w", zipfile.ZIP_DEFLATED) as zf:
        for f in qd_files:
            arcname = str(f.relative_to(qd_dir))
            zf.write(str(f), arcname)

    _log(f"已打包 {len(qd_files)} 个 .qd 文件 → {output_zip}")
    return str(output_zip)


def inspect_database(db_path: str) -> dict:
    """查看 SQLite 数据库的内容摘要

    Returns:
        {"tables": [{"name": str, "columns": [str], "rowCount": int, "sample": [list]}], ...}
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]

        result = []
        for table in tables:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]

            cur.execute(f'PRAGMA table_info("{table}")')
            cols = [r[1] for r in cur.fetchall()]

            sample = []
            if count > 0 and count < 200:
                cur.execute(f'SELECT * FROM "{table}" LIMIT 5')
                for row in cur.fetchall():
                    sample.append([str(v)[:40] if v is not None else "NULL" for v in row[:6]])

            result.append({
                "name": table,
                "columns": cols,
                "rowCount": count,
                "sample": sample,
            })

        # 章节统计
        vip_stats = None
        for t in tables:
            try:
                cur.execute(f"SELECT IsVip, COUNT(*) FROM \"{t}\" GROUP BY IsVip")
                vip_stats = dict(cur.fetchall())
            except Exception:
                pass

        conn.close()
        return {"dbName": Path(db_path).name, "tables": result, "vipStats": vip_stats}

    except Exception as e:
        return {"dbName": Path(db_path).name, "error": str(e)}
