"""起点公开 API 客户端 — 客户端直接调 m.qidian.com，不走 qidian_save 服务端"""
import json, re, time, base64, sys, os
from typing import Optional
import requests


# 终端日志（stderr，不干扰 stdout）
def log(msg: str):
    print(f"[qidian_client] {msg}", file=sys.stderr)


MOBILE_UA = ("Mozilla/5.0 (Linux; Android 11; Pixel 5) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0.0.0 Mobile Safari/537.36")

_SESSION = requests.Session()


def _mobile_get(url: str, params: dict = None, cookies: dict = None,
                max_retries: int = 2) -> Optional[requests.Response]:
    for attempt in range(max_retries):
        try:
            resp = _SESSION.get(url, params=params,
                headers={"User-Agent": MOBILE_UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                cookies=cookies or {}, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code == 200:
                return resp
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)  # 指数退避: 1s, 2s
    return None


def search_books(keyword: str, page: int = 1) -> list[dict]:
    """搜索书籍 — 直调 m.qidian.com/search"""
    log(f"搜索: keyword={keyword}, page={page}")
    resp = _mobile_get("https://m.qidian.com/search", {"kw": keyword, "page": page})
    if not resp:
        log("搜索: 无响应")
        return []
    log(f"搜索: HTTP {resp.status_code}, 响应体 {len(resp.text)} 字节")

    results = _parse_vite_page_context(resp.text)
    if not results:
        # Fallback: direct regex on HTML
        for m in re.finditer(
            r'"bookId":\s*(\d+)\s*,\s*"bookName":\s*"([^"]+)"\s*,\s*"authorName":\s*"([^"]+)"',
            resp.text
        ):
            results.append({"bookId": m.group(1), "bookName": m.group(2), "authorName": m.group(3)})

    log(f"搜索: 找到 {len(results)} 个结果")
    if not results:
        log(f"搜索: 响应前300字: {resp.text[:300]}")
    return results


def _parse_vite_page_context(html: str) -> list[dict]:
    """从 vite-plugin-ssr_pageContext 提取书籍列表（搜索/书架通用）

    搜索: pageContext.pageProps.pageData.bookInfo.records[] → {bid, bName, bAuth}
    书架: pageContext.pageProps.pageData.list[] → {bid, bName, bAuth}
    """
    m = re.search(r'<script id="vite-plugin-ssr_pageContext"[^>]*>(.*?)</script>',
                  html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        pd = (data.get("pageContext", {}).get("pageProps", {})
              .get("pageData", {}))
        # Try search result structure first
        records = pd.get("bookInfo", {}).get("records", [])
        if records:
            return [{
                "bookId": str(r["bid"]),
                "bookName": r.get("bName", ""),
                "authorName": r.get("bAuth", ""),
            } for r in records]
        # Then try bookshelf structure
        book_list = pd.get("list", [])
        if book_list:
            return [{
                "bookId": str(b["bid"]),
                "bookName": b.get("bName", ""),
                "authorName": b.get("bAuth", ""),
            } for b in book_list]
    except Exception:
        pass
    return []


def get_bookshelf(cookies: dict = None) -> list[dict]:
    """获取书架 — 直调 m.qidian.com/bookshelf/my/，需要已登录的 cookie"""
    log("获取书架")
    resp = _mobile_get("https://m.qidian.com/bookshelf/my/", cookies=cookies)
    if not resp:
        log("书架: 无响应")
        return []
    log(f"书架: HTTP {resp.status_code}, 响应体 {len(resp.text)} 字节")

    results = _parse_vite_page_context(resp.text)
    log(f"书架: 找到 {len(results)} 本书")
    if not results:
        # Check for redirect to login
        if resp.status_code in (301, 302) or "passport" in resp.text[:500]:
            log("书架: Cookie 可能已过期，返回登录页面")
        log(f"书架: 响应前300字: {resp.text[:300]}")
    return results


def get_book_info(book_id: str, cookies: dict = None) -> Optional[dict]:
    """获取书籍详情 — 直调 m.qidian.com/book/{id}/"""
    resp = _mobile_get(f"https://m.qidian.com/book/{book_id}/", cookies=cookies)
    if not resp:
        return None
    name_m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', resp.text)
    author_m = re.search(r'<meta[^>]*property="og:novel:author"[^>]*content="([^"]+)"', resp.text)
    if name_m:
        return {"bookId": book_id, "bookName": name_m.group(1),
                "authorName": author_m.group(1) if author_m else ""}
    return None


def get_catalog(book_id: str, cookies: dict = None) -> Optional[dict]:
    """获取目录 — 直调 m.qidian.com/book/{id}/catalog/

    同时获取书籍详情页的作者信息。
    """
    resp = _mobile_get(f"https://m.qidian.com/book/{book_id}/catalog/", cookies=cookies)
    if not resp:
        return None

    author_name = ""
    book_name = ""
    chapters = []
    total_chapters = 0

    m = re.search(r'<script id="vite-plugin-ssr_pageContext"[^>]*>(.*?)</script>',
                  resp.text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            pd = data.get("pageContext", {}).get("pageProps", {}).get("pageData", {})
            book_name = pd.get("bookName", "")
            total_chapters = pd.get("chapterTotalCnt", 0)
            for vol in pd.get("vs", []):
                for ch in vol.get("cs", []):
                    chapters.append({
                        "chapterId": str(ch["id"]),
                        "chapterName": ch.get("cN", ""),
                        "isVip": ch.get("sS", 0) != 1,
                        "isBuy": ch.get("isBuy", False),
                        "wordCount": ch.get("cnt", 0),
                    })
        except Exception:
            chapters = []

    # 作者信息不在目录页的 pageData 中，单独从书籍详情页获取
    if not author_name:
        author_name = _get_author_from_book_page(book_id, cookies)

    return {
        "bookName": book_name,
        "authorName": author_name,
        "totalChapters": total_chapters or len(chapters),
        "chapters": chapters,
    }


def _get_author_from_book_page(book_id: str, cookies: dict = None) -> str:
    """从书籍详情页 og:novel:author meta 提取作者名"""
    resp = _mobile_get(f"https://m.qidian.com/book/{book_id}/", cookies=cookies)
    if resp:
        m = re.search(r'<meta[^>]*property="og:novel:author"[^>]*content="([^"]+)"', resp.text)
        if m:
            return m.group(1)
    return ""


# ── 起点扫码登录（基于 ptlogin.yuewen.com JSONP API） ──

_RETURNURL = "https://www.qidian.com/loginSuccess?surl=https%3A%2F%2Fwww.qidian.com%2F"
_APP_ID = "10"
_AREA_ID = "1"

def _jsonp_parse(text: str) -> dict:
    """解析 JSONP 响应: callback({...}) → dict"""
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return {}

def _yuewen_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://passport.yuewen.com/",
    }

def get_qrcode() -> dict:
    """获取起点登录二维码 — 调 ptlogin.yuewen.com JSONP API"""
    try:
        s = requests.Session()
        s.headers.update(_yuewen_headers())

        log("请求 ptlogin.yuewen.com/login/qrcode...")
        cb = "jQuery" + str(int(time.time() * 1000))
        params = {
            "callback": cb, "appId": _APP_ID, "areaId": _AREA_ID,
            "source": "", "returnurl": _RETURNURL, "version": "",
            "imei": "", "qimei": "", "target": "iframe", "ticket": "1",
            "autotime": "30", "jumpdm": "yuewen", "ajaxdm": "yuewen",
            "auto": "1", "sdkversion": "", "method": "LoginV1.qrCodeCallback",
            "uuid": str(int(time.time())) + "_" + str(int(time.time() * 1000) % 1000000),
            "pageId": "qd_p_qidian", "bookId": "", "chapterId": "",
            "format": "jsonp", "_": str(int(time.time() * 1000)),
        }
        resp = s.get("https://ptlogin.yuewen.com/login/qrcode", params=params, timeout=30)
        log(f"QR 状态: {resp.status_code}, 长度: {len(resp.text)}")
        data = _jsonp_parse(resp.text)
        log(f"QR code: {data.get('code')}, keys: {list(data.keys())}")

        if data.get("code") != 0:
            return {"error": f"QR API 错误: {data}"}

        qr_data = data["data"]
        session_key = qr_data.get("sessionKey", "")
        image_b64 = qr_data.get("image", "")
        log(f"SessionKey: {'✅' if session_key else '❌'}")
        log(f"Image: {'✅' if image_b64 else '❌'} ({len(image_b64)} chars)")

        if image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        # 保存 session 供后续轮询使用
        get_qrcode._session = s
        get_qrcode._session_key = session_key

        return {"sessionKey": session_key, "imageBase64": image_b64}

    except Exception as e:
        import traceback
        log(f"异常: {traceback.format_exc()}")
        return {"error": str(e)}

# 存储 session 供 poll 使用
get_qrcode._session = None
get_qrcode._session_key = ""


def poll_qrcode(session_key: str, timeout: int = 120) -> Optional[dict]:
    """轮询二维码扫码状态 — 调 ptlogin.yuewen.com JSONP API

    Returns:
        None (等待中) 或 {"ywGuid": str, "ywKey": str, "ywOpenId": str}
    """
    s = getattr(get_qrcode, "_session", None) or requests.Session()
    if not hasattr(get_qrcode, "_session") or s is None:
        s.headers.update(_yuewen_headers())

    start = time.time()
    poll_count = 0

    while time.time() - start < timeout:
        poll_count += 1
        cb = "jQuery" + str(int(time.time() * 1000))
        params = {
            "callback": cb, "appId": _APP_ID, "areaId": _AREA_ID,
            "source": "", "returnurl": _RETURNURL, "version": "",
            "imei": "", "qimei": "", "target": "iframe", "ticket": "1",
            "autotime": "30", "jumpdm": "yuewen", "ajaxdm": "yuewen",
            "auto": "1", "sdkversion": "", "method": "LoginV1.qrCodeLoginCallback",
            "qrcode": session_key, "format": "jsonp",
            "_": str(int(time.time() * 1000)),
        }
        try:
            resp = s.get("https://ptlogin.yuewen.com/login/qrcodelogin",
                         params=params, timeout=10)
            data = _jsonp_parse(resp.text)
            code = data.get("code")
            log(f"[poll {poll_count}] code={code} raw={resp.text[:200]}")

            if code == 0:
                login_data = data["data"]
                log(f"扫码成功! ywguid={login_data.get('ywGuid', 'N/A')}")

                # sublogin — 用同一个 session 保证 cookie 连续
                return_url = login_data.get("returnUrl") or login_data.get("302url")
                if return_url:
                    s.get(return_url, timeout=30)
                else:
                    sub_params = {
                        "appId": _APP_ID, "areaId": _AREA_ID,
                        "returnurl": _RETURNURL, "target": "iframe",
                        "ticket": login_data["ticket"],
                        "autotime": "30", "jumpdm": "yuewen", "ajaxdm": "yuewen",
                        "auto": "1", "method": "LoginV1.qrCodeLoginCallback",
                        "format": "iframe",
                        "params": login_data.get("autoLoginSessionKey", ""),
                    }
                    s.get("https://ptlogin.qidian.com/login/sublogin",
                          params=sub_params, timeout=30)

                # 获取 _csrfToken
                for url in [
                    "https://m.qidian.com/bookshelf/my/",
                    "https://m.qidian.com/",
                ]:
                    try:
                        sr = s.get(url, headers={
                            "User-Agent": MOBILE_UA,
                            "Accept": "text/html",
                        }, timeout=15)
                        log(f"获取 Cookie 页面: {url} → {sr.status_code}")
                    except Exception:
                        pass

                cookies = {}
                for c in s.cookies:
                    cookies[c.name] = c.value
                log(f"Cookie 字段数: {len(cookies)}, 有 ywguid={'ywguid' in cookies}")

                return cookies

            elif code == -11019:
                scan_status = data.get("scanStatus", "0")
                if scan_status == "1":
                    log(f"[{poll_count}] 已扫码等待确认")
                else:
                    if poll_count % 5 == 0:
                        log(f"[{poll_count}] 等待扫码中...")
            else:
                log(f"[{poll_count}] 未知状态码: {code}, 完整响应: {resp.text[:300]}")

        except Exception as e:
            if poll_count % 5 == 0:
                log(f"[{poll_count}] 轮询异常: {e}")

        time.sleep(2)

    log("扫码超时")
    return None


# ── Cookie 持久化 ──

COOKIE_FILE = None  # 由 set_cookie_path 设置


def _default_cookie_dir() -> str:
    """获取默认 Cookie 存储目录（client 目录下的 data/）"""
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))


def set_cookie_path(path: str = None):
    """设置 Cookie 文件路径，不传参则使用默认路径"""
    global COOKIE_FILE
    if path:
        COOKIE_FILE = path
    else:
        COOKIE_FILE = os.path.join(_default_cookie_dir(), "qidian_cookies.json")


def _cookie_file() -> str:
    """获取当前 Cookie 文件路径（未设置时使用默认路径）"""
    if COOKIE_FILE:
        return COOKIE_FILE
    return os.path.join(_default_cookie_dir(), "qidian_cookies.json")


def load_cookies() -> dict:
    path = _cookie_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cookies(cookies: dict):
    path = _cookie_file()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows 不支持 0600，不影响功能


def get_chapter_data(book_id: str, chapter_id: str, cookies: dict = None) -> Optional[dict]:
    """获取单章原始加密数据（从移动端 SSR 页面提取）

    起点 /majax/chapter/getChapterInfo 已失效（始终返回 code=1），
    改用 SSR 页面 vite-plugin-ssr_pageContext JSON 提取。

    ⚠️ 边界角色：本函数仅做原始数据提取（从 SSR 页面拉取 chapterInfo），
    不涉及任何解密/解码。提取的 cES/content/css/randomFont/fkp/fixedFontUrl
    等原始字段将传给服务端 decode-zip API 进行实际解码。

    返回 decode-zip 输入格式：
        {chapterId, chapterName, cES, content, css, randomFont, fkp, fixedFontUrl}

    返回 None 表示未购买或网络异常。
    """
    url = f"https://m.qidian.com/chapter/{book_id}/{chapter_id}/"
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://m.qidian.com/",
    }
    for attempt in range(2):
        try:
            resp = _SESSION.get(url, headers=headers,
                                cookies=cookies or {}, timeout=20)
            if resp.status_code != 200:
                log(f"get_chapter_data HTTP {resp.status_code} ({book_id}/{chapter_id})")
                if attempt < 1:
                    time.sleep(1)
                    continue
                return None
            m = re.search(
                r'<script\s+id="vite-plugin-ssr_pageContext"[^>]*>(.*?)</script>',
                resp.text, re.DOTALL,
            )
            if not m:
                log(f"get_chapter_data 无 pageContext ({book_id}/{chapter_id})")
                return None
            data = json.loads(m.group(1))
            ci = (data.get("pageContext", {}).get("pageProps", {})
                  .get("pageData", {}).get("chapterInfo", {}))
            if not ci or not ci.get("chapterName"):
                log(f"get_chapter_data 无 chapterInfo ({book_id}/{chapter_id})")
                return None
            return {
                "chapterId": chapter_id,
                "chapterName": ci.get("chapterName", ""),
                "cES": ci.get("cES", 0),
                "content": ci.get("content", ""),
                "css": ci.get("css", ""),
                "randomFont": ci.get("randomFont", ""),
                "fkp": ci.get("fkp", ""),
                "fixedFontUrl": ci.get("fixedFontWoff2", "") or ci.get("fixedFontTtf", ""),
            }
        except requests.RequestException as e:
            log(f"get_chapter_data 异常: {e} ({book_id}/{chapter_id})")
            if attempt < 1:
                time.sleep(1)
                continue
            return None
        except (KeyError, ValueError, json.JSONDecodeError, re.error) as e:
            log(f"get_chapter_data 解析失败: {e} ({book_id}/{chapter_id})")
            return None
    return None
