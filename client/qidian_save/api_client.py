"""纯 API 调用封装 — 不包含任何业务逻辑"""
import os, zipfile, tempfile
import requests
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
        dc = client.login_github_device_code()
        result = client.login_github_poll_token(dc["device_code"])
        client.set_token(result["token"])
    """

    def __init__(self, base_url: str, token: str = None, api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        if token:
            self.set_token(token)
        if api_key:
            self.set_api_key(api_key)

    def set_token(self, token: str):
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def set_api_key(self, api_key: str):
        self.session.headers.update({"X-API-Key": api_key})

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

    def _delete(self, path: str) -> dict:
        resp = self.session.delete(f"{self.base_url}{path}", timeout=30)
        self._raise_on_error(resp)
        return resp.json()

    # ── Auth: GitHub Device Flow ──

    def login_github_device_code(self) -> dict:
        """Step 1: 发起 GitHub Device Flow，返回 device_code + user_code + verification_uri"""
        return self._post("/api/auth/github/device-code")

    def login_github_poll_token(self, device_code: str) -> dict:
        """Step 2/3: 轮询 GitHub 登录状态

        Returns:
            {"status": "pending"|"slow_down"|"expired"|"denied"|"success",
             "token": str?, "user": dict?, "interval": int?, "error": str?}
        """
        return self._post("/api/auth/github/poll-token", json={"device_code": device_code})

    # ── Auth: legacy ──

    def login(self, provider: str, code: str) -> dict:
        return self._post("/api/auth/login", json={"provider": provider, "code": code})

    def get_me(self) -> dict:
        return self._get("/api/auth/me")

    def renew_api_key(self) -> dict:
        """重新生成 API Key"""
        return self._post("/api/auth/api-key/regenerate")

    # ── Backup ──

    def upload_qidian_cookies(self, cookies: dict) -> dict:
        """上传起点 Cookie 到服务端，返回 cookies_ref"""
        return self._post("/api/backup/cookies", json={"cookies": cookies})

    def start_backup(self, book_id: str, start: int = 1, end: int = 0,
                     cookies_ref: str = "", qidian_cookies: dict = None) -> dict:
        body = {"book_id": book_id, "start": start, "end": end,
                "cookies_ref": cookies_ref}
        if qidian_cookies:
            body["qidian_cookies"] = qidian_cookies
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
