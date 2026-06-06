"""纯 API 调用封装 — 不包含任何业务逻辑"""
import os, zipfile, tempfile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Union


class ApiError(Exception):
    """API 返回的业务错误（非 2xx 响应）"""
    def __init__(self, status_code: int, message: str, url: str = ""):
        self.status_code = status_code
        self.message = message
        self.url = url
        parts = [f"HTTP {status_code}", message]
        if url:
            parts.append(url)
        super().__init__(": ".join(parts))


class QidianSaveClient:
    """qidian_save API 客户端

    Usage:
        client = QidianSaveClient("https://api.example.com")
        result = client.login_jwt("user@example.com", "password")
        client.set_token(result["access_token"])
    """

    def __init__(self, base_url: str, token: str = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        # 自动重试：网络错误 + HTTP 429/5xx，指数退避 1s/2s/4s
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        if token:
            self.set_token(token)

    def set_token(self, token: str):
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    @staticmethod
    def _raise_on_error(resp: requests.Response):
        """检查响应状态码，提取服务端错误消息"""
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error") or body.get("detail") or resp.reason
            except Exception:
                msg = resp.reason
            raise ApiError(resp.status_code, msg, url=resp.url)

    def _get(self, path: str, **kwargs) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", **kwargs, timeout=30)
        self._raise_on_error(resp)
        return resp.json()

    def _post(self, path: str, **kwargs) -> dict:
        resp = self.session.post(f"{self.base_url}{path}", **kwargs, timeout=30)
        self._raise_on_error(resp)
        return resp.json()

    def _post_form(self, path: str, data: dict) -> dict:
        """application/x-www-form-urlencoded POST（用于 /auth/jwt/login）"""
        resp = self.session.post(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        self._raise_on_error(resp)
        return resp.json()

    def _delete(self, path: str) -> dict:
        resp = self.session.delete(f"{self.base_url}{path}", timeout=30)
        self._raise_on_error(resp)
        return resp.json()

    def _patch(self, path: str, **kwargs) -> dict:
        resp = self.session.patch(f"{self.base_url}{path}", **kwargs, timeout=30)
        self._raise_on_error(resp)
        return resp.json()

    # ── Health ──

    def health_check(self) -> dict:
        """健康检查（免认证）"""
        return self._get("/api/health")

    # ── Auth: fastapi-users ──

    def register(self, email: str, password: str, username: str) -> dict:
        """注册新用户（免认证）"""
        return self._post("/auth/register", json={
            "email": email, "password": password, "username": username,
        })

    def login_jwt(self, email: str, password: str) -> dict:
        """邮箱+密码登录，返回 {"access_token": "...", "token_type": "bearer"}（免认证）

        注意：使用 application/x-www-form-urlencoded。

        Raises:
            ApiError: HTTP 400 时 detail 为 "LOGIN_BAD_CREDENTIALS"（密码错误）
                      或 "LOGIN_USER_NOT_ACTIVE"（账号未激活）
        """
        return self._post_form("/auth/jwt/login", {
            "username": email, "password": password,
        })

    def logout(self) -> dict:
        """登出（使当前 token 失效）"""
        return self._post("/auth/jwt/logout")

    def get_me(self) -> dict:
        return self._get("/users/me")

    def update_profile(self, username: str = None, avatar: str = None) -> dict:
        """更新当前用户信息（只传需要改的字段）"""
        body = {}
        if username is not None:
            body["username"] = username
        if avatar is not None:
            body["avatar"] = avatar
        return self._patch("/users/me", json=body)

    def forgot_password(self, email: str) -> dict:
        """发送密码重置邮件（免认证）"""
        return self._post("/auth/forgot-password", json={"email": email})

    def reset_password(self, token: str, password: str) -> dict:
        """使用重置令牌设置新密码（免认证）"""
        return self._post("/auth/reset-password", json={
            "token": token, "password": password,
        })

    # ── Backup ──

    def upload_qidian_cookies(self, cookies: dict) -> dict:
        """上传起点 Cookie 到服务端，返回 cookies_ref"""
        return self._post("/api/backup/cookies", json={"cookies": cookies})

    def start_backup(self, book_id: str, start: int = 1, end: int = 0,
                     cookies_ref: str = "", qidian_cookies: dict = None,
                     server_crawl: bool = True,
                     chapter_ids: list = None) -> dict:
        body = {"book_id": book_id, "start": start, "end": end,
                "cookies_ref": cookies_ref, "server_crawl": server_crawl}
        if qidian_cookies:
            body["qidian_cookies"] = qidian_cookies
        if chapter_ids:
            body["chapter_ids"] = chapter_ids
        return self._post("/api/backup/start", json=body)

    def get_task(self, task_id: int) -> dict:
        return self._get(f"/api/backup/{task_id}")

    def list_chapters(self, task_id: int) -> list:
        data = self._get(f"/api/backup/{task_id}/chapters")
        return data.get("chapters", [])

    def download_chapter(self, task_id: int, chapter_id: str, format: str = "text") -> Union[dict, str]:
        """下载章节内容

        Args:
            format: "text" 返回 {"decodedText": "..."}
                    "html" 返回原始 HTML 字符串
        """
        resp = self.session.get(
            f"{self.base_url}/api/backup/{task_id}/chapters/{chapter_id}",
            params={"format": format},
            timeout=30,
        )
        self._raise_on_error(resp)
        if format == "html":
            return resp.text
        return resp.json()

    def decode_chapter_zip(self, task_id: int, zip_data: bytes, cookies_str: str) -> bytes:
        """上传原始章节数据 zip，服务端解码后返回结果 zip

        Args:
            task_id: 备份任务 ID
            zip_data: 打包好的 zip 二进制数据（含 {chapterId}.json）
            cookies_str: JSON 序列化的 cookies 字符串

        Returns:
            解码结果的 zip 二进制数据

        Raises:
            ApiError: HTTP 400/404/413/429
        """
        resp = self.session.post(
            f"{self.base_url}/api/backup/{task_id}/decode-zip",
            files={"file": (f"chapters_{task_id}.zip", zip_data, "application/zip")},
            data={"cookies": cookies_str},
            timeout=300,
        )
        self._raise_on_error(resp)
        return resp.content

    def cleanup_task(self, task_id: int) -> dict:
        return self._delete(f"/api/backup/{task_id}")

    # ── .qd Decrypt — Zip workflow ──

    def decrypt_qd_zip(self, zip_path: str, qimei36: str, user_id: str,
                       pool_b64: str, output_path: str = None) -> dict:
        """上传 .qd 文件的 zip 压缩包到服务器，下载解密后的 zip

        Args:
            zip_path: .qd 文件的 zip 压缩包路径
            qimei36: 36 位设备标识
            user_id: 起点用户 ID
            pool_b64: base64 编码的密钥池
            output_path: 解密结果 zip 保存路径（默认自动生成）

        Returns:
            {"zip_path": str, "task_id": str | None}
        """
        if output_path is None:
            output_path = zip_path.rsplit(".", 1)[0] + "_decrypted.zip"

        with open(zip_path, "rb") as f:
            files = {"file": (os.path.basename(zip_path), f, "application/zip")}
            data = {"qimei36": qimei36, "userId": user_id, "poolB64": pool_b64}
            resp = self.session.post(
                f"{self.base_url}/api/decrypt/qd-zip",
                files=files, data=data, timeout=300,
            )
        self._raise_on_error(resp)

        task_id = resp.headers.get("X-Task-Id")

        with open(output_path, "wb") as f:
            f.write(resp.content)

        return {"zip_path": output_path, "task_id": task_id}

    def decrypt_qd(self, file_path: str, qimei36: str, user_id: str,
                   pool_b64: str) -> dict:
        """上传单个 .qd 文件到服务端解密（单文件模式，兼容旧版 API）

        Returns:
            {"decodedText": str, "taskId": int | None, ...}
        """
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/octet-stream")}
            data = {"qimei36": qimei36, "userId": user_id, "poolB64": pool_b64}
            resp = self.session.post(
                f"{self.base_url}/api/decrypt/qd",
                files=files, data=data, timeout=60,
            )
            self._raise_on_error(resp)
            return resp.json()

    # ── Usage ──

    # ── Announcements ──

    def get_announcements(self) -> list:
        """获取活跃公告列表"""
        data = self._get("/api/announcements")
        return data.get("announcements", [])

    # ── Usage ──

    def get_usage(self) -> dict:
        return self._get("/api/usage/today")
