"""CLI — 纯 API 调用 + ADB 工具（ADB 需本地设备）"""
import sys, os, json, argparse, time, webbrowser, subprocess
from .api_client import QidianSaveClient
from . import DATA_DIR
from .qidian_client import search_books as qidian_search, get_bookshelf, load_cookies, set_cookie_path
from .adb_utils import (
    scan_device, pull_device_files, inspect_database, create_qd_zip,
    load_config, save_config, check_device, check_root, config_path,
    list_devices, extract_params,
)


TOKEN_FILE = DATA_DIR / "token"


def _save_token(token: str):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")


def _load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""

def cmd_desktop(args):
    """启动桌面版"""
    from .desktop.app import main
    main()

def _get_client(args) -> QidianSaveClient:
    base = os.getenv("QIDIAN_SAVE_URL", "https://autohelp.asia/")
    token = os.getenv("QIDIAN_SAVE_TOKEN", "") or _load_token()
    api_key = os.getenv("QIDIAN_SAVE_API_KEY", "")
    return QidianSaveClient(base, token=token, api_key=api_key)

def cmd_login(args):
    """GitHub Device Flow 登录"""
    client = _get_client(args)

    if args.token:
        # 直接设置 Token
        client.set_token(args.token)
        try:
            user = client.get_me()
            print(f"Token 有效！用户: {user.get('username', '')}")
            _save_token(args.token)
            print(f"Token 已保存到 {TOKEN_FILE}")
        except Exception as e:
            print(f"Token 无效: {e}")
        return

    # GitHub Device Flow
    print("正在发起 GitHub Device Flow 登录...")
    dc = client.login_github_device_code()
    print(f"\n请在浏览器中打开: {dc['verification_uri']}")
    print(f"并输入代码: {dc['user_code']}\n")

    webbrowser.open("https://github.com/login/device")

    interval = dc.get("interval", 5)
    while True:
        result = client.login_github_poll_token(dc["device_code"])
        status = result.get("status")

        if status == "success":
            token = result["token"]
            user = result.get("user", {})
            print(f"登录成功！用户: {user.get('username', '')}")
            print(f"Token: {token[:20]}...")
            _save_token(token)
            print(f"Token 已保存到 {TOKEN_FILE}，下次启动将自动登录")
            return
        elif status == "slow_down":
            interval = result.get("interval", interval + 5)
            print(f"[{status}] 慢下来...")
        elif status == "expired":
            print("设备码已过期，请重新运行 login")
            return
        elif status == "denied":
            print("用户取消了授权")
            return
        elif status == "pending":
            print(".", end="", flush=True)

        time.sleep(interval)

def cmd_search(args):
    results = qidian_search(args.keyword)
    print(f"找到 {len(results)} 个结果:\n")
    for r in results:
        print(f"  {r['bookId']:<14} {r['bookName']:<20} {r['authorName']:<12}")

def cmd_catalog(args):
    client = _get_client(args)
    cat = client.get_catalog(args.book_id)
    print(f"{cat.get('bookName', '')} — 共 {cat['totalChapters']} 章")
    for ch in cat["chapters"]:
        vip = "V" if ch["isVip"] else " "
        buy = "✓" if ch["isBuy"] else " "
        print(f"  {vip}{buy} {ch['chapterId']:<12} {ch['chapterName']}")

def cmd_backup(args):
    client = _get_client(args)

    # 1. 尝试获取本地起点 Cookie 并上传到服务端
    cookies_ref = ""
    if args.cookies_ref:
        cookies_ref = args.cookies_ref
        print(f"使用指定 cookies_ref: {cookies_ref}")
    else:
        from .qidian_client import load_cookies as qd_load_cookies, set_cookie_path
        if args.cookie_file:
            set_cookie_path(args.cookie_file)
        else:
            set_cookie_path()
        local_cookies = qd_load_cookies()
        if local_cookies and local_cookies.get("ywguid"):
            print(f"检测到本地起点 Cookie (ywguid={local_cookies['ywguid']}), 上传到服务端...")
            try:
                result = client.upload_qidian_cookies(local_cookies)
                cookies_ref = result.get("cookiesRef", "")
                print(f"Cookie 上传成功, ref={cookies_ref}")
            except Exception as e:
                print(f"Cookie 上传失败: {e}")
                print("仍将尝试备份（可能只能下载免费章节）")
        else:
            print("未检测到起点登录 Cookie。请先扫码登录:")
            print("  方式 1: python -m qidian_save desktop (启动桌面端, 在「起点登录」面板扫码)")
            print("  方式 2: 直接指定 cookies_ref: --cookies-ref <ref>")

    # 2. 启动备份任务
    task = client.start_backup(args.book_id, args.start, args.end, cookies_ref)
    task_id = task["taskId"]
    print(f"任务已创建: {task_id}")

    import time
    while True:
        status = client.get_task(task_id)
        print(f"  进度: {status['completedChapters']}/{status['totalChapters']} 章")
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(3)

    chapters = client.list_chapters(task_id)
    book_name = status.get('bookName', f'book_{args.book_id}')

    # 默认保存到 client/data/<BookName>_<bookId>/（--output 可覆盖）
    output_dir = args.output or str(DATA_DIR / f"{book_name}_{args.book_id}")
    os.makedirs(output_dir, exist_ok=True)

    for ch in chapters:
        safe_name = ch.get("chapterName", ch["chapterId"]).replace("/", "_")[:60]
        has_html = ch.get("hasHtml", False)
        if has_html:
            content = client.download_chapter_html(task_id, ch["chapterId"])
            ext = ".html"
        else:
            data = client.download_chapter(task_id, ch["chapterId"])
            content = data["decodedText"]
            ext = ".txt"
        path = os.path.join(output_dir, f"{safe_name}{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [+] {path}")

    client.cleanup_task(task_id)
    print(f"完成! 共 {len(chapters)} 章保存到 {output_dir}")

def cmd_decrypt(args):
    """解密 .qd 文件 — 支持单文件或目录（目录会自动打包 zip 上传）

    解密参数从命令行或配置文件 (qd-config) 读取。
    """
    client = _get_client(args)

    qimei36 = args.qimei36
    user_id = args.user_id
    pool_b64 = args.pool_b64

    # 命令行参数未提供时从配置文件读取
    if not qimei36 or not user_id or not pool_b64:
        cfg = load_config()
        qimei36 = qimei36 or cfg.get("qimei36", "")
        user_id = user_id or cfg.get("userId", "")
        pool_b64 = pool_b64 or cfg.get("pool_b64", "")

    if not qimei36 or not user_id or not pool_b64:
        print("缺少解密参数，请通过命令行提供或先运行: qd-config --set key=value")
        return

    input_path = Path(args.file)

    if input_path.is_dir():
        # 目录模式：打包 zip → 上传服务端解密 → 下载结果 zip → 解压
        print(f"正在打包 {input_path} 中的 .qd 文件...")
        zip_path = create_qd_zip(input_path)
        print(f"已打包: {zip_path}")

        output_zip = str(input_path.parent / f"{input_path.name}_decrypted.zip")
        print("正在上传服务端解密...")
        result = client.decrypt_qd_zip(zip_path, qimei36, user_id, pool_b64, output_zip)
        result_zip = result["zip_path"]
        if result.get("task_id"):
            print(f"解密任务 ID: {result['task_id']}")

        # 解压结果
        import zipfile
        extract_dir = input_path.parent / f"{input_path.name}_decrypted"
        with zipfile.ZipFile(result_zip, "r") as zf:
            zf.extractall(str(extract_dir))
        print(f"解密完成！{len(list(extract_dir.iterdir()))} 个文件已保存到: {extract_dir}")
    else:
        # 单文件模式：上传单个 .qd 文件
        result = client.decrypt_qd(args.file, qimei36, user_id, pool_b64)
        output = args.output or f"{args.file}.txt"
        with open(output, "w", encoding="utf-8") as f:
            f.write(result["decodedText"])
        extra = f" (taskId={result.get('taskId')})" if result.get("taskId") else ""
        print(f"解密完成: {output}{extra}")

def cmd_bookshelf(args):
    """查看起点书架（需要已登录的 Cookie）"""
    if args.cookie_file:
        set_cookie_path(args.cookie_file)
    else:
        set_cookie_path()  # 使用默认路径
    cookies = load_cookies()
    if not cookies or not cookies.get("ywguid"):
        print("未检测到起点登录 Cookie，请先用 desktop 端扫码登录")
        return
    books = get_bookshelf(cookies)
    if not books:
        print("书架为空或 Cookie 已过期")
        return
    print(f"共 {len(books)} 本书:\n")
    for b in books:
        print(f"  {b['bookId']:<14} {b['bookName']:<20} {b['authorName']}")

def cmd_usage(args):
    client = _get_client(args)
    u = client.get_usage()
    print(f"今日用量: {u['chaptersUsed']} / {u['limit']} 次")
    print(f"剩余: {u['remaining']} 次")


def cmd_renew_api_key(args):
    """重新生成 API Key"""
    client = _get_client(args)
    print("正在重新生成 API Key...")
    result = client.renew_api_key()
    api_key = result.get("api_key", "未知")
    print(f"\n新的 API Key: {api_key}")
    print("请更新你的 API Key 配置。旧的 API Key 已失效。")


# ── .qd 配置 ──────────────────────────────────────────────────────

def cmd_qd_config(args):
    """查看/设置 .qd 解密配置"""
    cfg = load_config()
    if args.set:
        parts = args.set.split("=", 1)
        if len(parts) != 2:
            print("格式错误: 使用 --set key=value")
            return
        key, val = parts[0].strip(), parts[1].strip()
        if key in cfg:
            cfg[key] = val
            save_config(cfg)
            print(f"已设置 {key}={val[:20]}...")
        else:
            print(f"未知配置项: {key} (可选: {', '.join(cfg.keys())})")
        return

    print("=== .qd 解密配置 ===")
    for k, v in cfg.items():
        status = "[OK]" if v else "[空]"
        val = v[:50] if v else ""
        print(f"  {k:12s}: {status} {val}")
    print(f"\n配置路径: {config_path()}")


# ── mitmproxy 已废弃，使用 adb-extract 替代 ──────────────────────────
# 原 capture_addon.py / _capture_runner.py 已删除
pass


# ── ADB 操作 ──────────────────────────────────────────────────────

def _resolve_device(serial: str | None) -> str | None:
    """解析 --device 参数，自动处理单设备情况"""
    if serial:
        return serial
    devices = list_devices()
    if len(devices) == 0:
        return None
    if len(devices) == 1:
        return devices[0]["serial"]
    # 多设备时提示用户
    print(f"[!] 检测到 {len(devices)} 个设备，请用 --device / -s 指定:\n")
    for d in devices:
        print(f"    python -m qidian_save <命令> -s {d['serial']}")
    print()
    return None


def cmd_adb_scan(args):
    """扫描 Android 设备上的 .qd 文件"""
    serial = _resolve_device(args.device)
    print("=== ADB 扫描设备 ===")
    if not check_device():
        print("[!!] 未检测到 Android 设备，请连接 USB 并开启调试")
        return

    books = scan_device(device_serial=serial)
    if not books:
        print("  未找到 .qd 文件（可能尚未打开过付费章节）")
        return

    for b in books:
        print(f"\n  userId={b['userId']}, bookId={b['bookId']}:")
        print(f"    .qd 文件: {b['fileCount']} 个")
        for f in b.get('files', [])[:5]:
            print(f"      {f}")
        if b.get('databases'):
            print(f"    数据库: {', '.join(b['databases'])}")
        if b['fileCount'] > 5:
            print(f"    ... 还有 {b['fileCount']-5} 个文件")

    total = sum(b['fileCount'] for b in books)
    print(f"\n共 {len(books)} 本书, {total} 个 .qd 文件")


def cmd_adb_pull(args):
    """从 Android 设备拉取 .qd 文件和数据库"""
    serial = _resolve_device(args.device)
    output = args.output or os.path.join(
        os.path.dirname(__file__), "..", "qd_files"
    )
    if not check_device():
        print("[!!] 未检测到 Android 设备")
        return

    print(f"=== 拉取 .qd 文件 → {output} ===")
    result = pull_device_files(output, device_serial=serial)
    print(f"  拉取完成: {result['qdFiles']} 个 .qd 文件, {result['databases']} 个数据库")
    for u in result.get('users', []):
        print(f"    [{u['userId']}]: {u['count']} 个文件")
    if result['total'] == 0:
        print("  未找到 .qd 文件")


def cmd_adb_extract(args):
    """从已 root 的 Android 设备直接提取解密参数（真机/模拟器均可用）"""
    serial = _resolve_device(args.device)
    print("=== ADB 参数提取 ===")
    if not check_device():
        print("[!!] 未检测到 Android 设备")
        return

    print("正在检查 root 权限...")
    if not check_root(device_serial=serial):
        print("[!!] root 不可用，请确认设备已 root 或使用模拟器\n")
        print("  模拟器默认有 root 权限，连接后重试即可")
        return

    print("正在从设备提取解密参数...")
    result = extract_params(device_serial=serial)

    print()
    qimei36 = result.get("qimei36", "")
    user_id = result.get("userId", "")
    pool_b64 = result.get("pool_b64", "")
    errors = result.get("errors", [])

    print(f"  QIMEI36: [{'OK' if qimei36 else '--'}] {qimei36 if qimei36 else '未提取'}")
    print(f"  userId:  [{'OK' if user_id else '--'}] {user_id if user_id else '未提取'}")
    print(f"  Pool:    [{'OK' if pool_b64 else '--'}] {pool_b64[:50] + '...' if pool_b64 else '未提取'}")

    if errors:
        print(f"\n[!] 部分参数提取失败:")
        for e in errors:
            print(f"   - {e}")

    # 保存到配置
    if qimei36 or user_id or pool_b64:
        cfg = load_config()
        if qimei36:
            cfg["qimei36"] = qimei36
        if user_id:
            cfg["userId"] = user_id
        if pool_b64:
            cfg["pool_b64"] = pool_b64
        save_config(cfg)
        print(f"\n[OK] 参数已保存到配置: {config_path()}")

        print("\n[提示] 参数已就绪，可执行以下操作:")
        print(f"   python -m qidian_save adb-pull{' -s ' + serial if serial else ''}  # 拉取 .qd 文件")
        print(f"   python -m qidian_save decrypt <目录>    # 上传解密")
    else:
        print("\n[!!] 未提取到任何参数，无法继续")


def cmd_adb_db(args):
    """查看从设备拉取的 SQLite 数据库内容"""
    search_dir = args.dir or os.path.join(
        os.path.dirname(__file__), "..", "qd_files"
    )
    search_path = Path(search_dir)

    if not search_path.exists():
        print(f"目录不存在: {search_path}")
        return

    # 找 SQLite 数据库
    dbs = list(search_path.rglob("*.qd")) + list(search_path.rglob("*.db"))
    sqlite_dbs = []
    for fp in dbs:
        try:
            hdr = fp.read_bytes()[:4]
            if hdr == b"SQLi" or fp.stat().st_size > 10000:
                sqlite_dbs.append(fp)
        except Exception:
            pass

    if not sqlite_dbs:
        print(f"在 {search_path} 下未找到 SQLite 数据库文件")
        return

    for fp in sorted(set(sqlite_dbs)):
        print(f"\n=== {fp.name} ({fp.stat().st_size}B) ===")
        info = inspect_database(str(fp))
        if "error" in info:
            print(f"  错误: {info['error']}")
            continue

        for table in info.get("tables", []):
            print(f"  [{table['name']}] {table['rowCount']} 行, 列: {', '.join(table['columns'][:8])}")
            if table["sample"]:
                for row in table["sample"][:3]:
                    print(f"    {' | '.join(row)}")
                if len(table["sample"]) > 3:
                    print(f"    ... 还有 {table['rowCount']-3} 行")

        if info.get("vipStats"):
            print(f"  VIP 分布: {info['vipStats']}")

def build_parser():
    p = argparse.ArgumentParser(prog="qidian-save", description="起点书籍本地保存工具")
    p.add_argument("--cookie-file", help="起点 Cookie JSON 文件路径")
    sub = p.add_subparsers(dest="command")

    p_login = sub.add_parser("login", help="GitHub Device Flow 登录")
    p_login.add_argument("--token", help="直接设置 JWT Token（跳过 OAuth）")
    p_login.set_defaults(func=cmd_login)

    p_search = sub.add_parser("search", help="搜索书籍")
    p_search.add_argument("keyword")
    p_search.set_defaults(func=cmd_search)

    p_cat = sub.add_parser("catalog", help="查看目录")
    p_cat.add_argument("book_id")
    p_cat.set_defaults(func=cmd_catalog)

    p_bookshelf = sub.add_parser("bookshelf", help="查看起点书架")
    p_bookshelf.set_defaults(func=cmd_bookshelf)

    p_backup = sub.add_parser("backup", help="备份书籍（需先起点扫码登录）")
    p_backup.add_argument("book_id")
    p_backup.add_argument("--start", type=int, default=1)
    p_backup.add_argument("--end", type=int, default=0)
    p_backup.add_argument("--output", "-o")
    p_backup.add_argument("--cookies-ref", help="已上传的起点 Cookie ref（跳过本地 Cookie 检测）")
    p_backup.set_defaults(func=cmd_backup)

    p_dec = sub.add_parser("decrypt", help="解密 .qd 文件（单文件或整个目录）")
    p_dec.add_argument("file", help=".qd 文件路径 或 包含 .qd 文件的目录")
    p_dec.add_argument("--qimei36", help="36位设备标识（默认从配置读取）")
    p_dec.add_argument("--user-id", help="起点用户 ID（默认从配置读取）")
    p_dec.add_argument("--pool-b64", help="Pool base64（默认从配置读取）")
    p_dec.add_argument("--output", "-o", help="输出路径（单文件模式）")
    p_dec.set_defaults(func=cmd_decrypt)

    p_usage = sub.add_parser("usage", help="查看用量")
    p_usage.set_defaults(func=cmd_usage)

    p_renew = sub.add_parser("renew-api-key", help="重新生成 API Key")
    p_renew.set_defaults(func=cmd_renew_api_key)

    p_qd_cfg = sub.add_parser("qd-config", help="查看/设置 .qd 解密配置")
    p_qd_cfg.add_argument("--set", help="设置配置项 (key=value)")
    p_qd_cfg.set_defaults(func=cmd_qd_config)

    p_adb_extract = sub.add_parser("adb-extract", help="从已 root 设备/模拟器直接提取解密参数")
    p_adb_extract.add_argument("--device", "-s", help="设备序列号（多设备时必填）")
    p_adb_extract.set_defaults(func=cmd_adb_extract)

    p_adb_scan = sub.add_parser("adb-scan", help="ADB 扫描设备上的 .qd 文件")
    p_adb_scan.add_argument("--device", "-s", help="设备序列号（多设备时必填）")
    p_adb_scan.set_defaults(func=cmd_adb_scan)

    p_adb_pull = sub.add_parser("adb-pull", help="从 ADB 设备拉取 .qd 文件")
    p_adb_pull.add_argument("--device", "-s", help="设备序列号（多设备时必填）")
    p_adb_pull.add_argument("--output", "-o", help="保存目录")
    p_adb_pull.set_defaults(func=cmd_adb_pull)

    p_adb_db = sub.add_parser("adb-db", help="查看已拉取的 SQLite 数据库")
    p_adb_db.add_argument("--dir", "-d", help="搜索目录（默认: qd_files/）")
    p_adb_db.set_defaults(func=cmd_adb_db)

    p_desk = sub.add_parser("desktop", help="启动桌面版")
    p_desk.set_defaults(func=cmd_desktop)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)

if __name__ == "__main__":
    main()
