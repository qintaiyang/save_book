"""Helpers for the server-credential advanced backup workflow."""

from __future__ import annotations

from .api_client import ApiError


def _detail_error_code(detail) -> str:
    if isinstance(detail, dict):
        nested = detail.get("detail")
        if isinstance(nested, dict):
            return str(nested.get("error") or "")
        return str(detail.get("error") or "")
    return ""


def _detail_text(detail) -> str:
    if isinstance(detail, dict):
        text = detail.get("error") or detail.get("detail") or ""
        return str(text)
    return str(detail or "")


def format_advanced_backup_error(error: Exception | str) -> str:
    """Return a user-facing message for expected advanced-backup API failures."""
    if isinstance(error, ApiError):
        status = error.status_code
        detail = error.message
        code = _detail_error_code(detail)
        text = _detail_text(detail)
    else:
        status = 0
        detail = None
        code = ""
        text = str(error)

    if status == 403:
        if code == "advanced_backup_disabled":
            return "高级备份未开放，请稍后再试。"
        if code == "advanced_backup_not_allowed":
            return "当前账号无权限使用高级备份，请确认会员计划或联系管理员。"
        return "当前账号无权限使用高级备份。"

    if status == 503:
        if code == "advanced_backup_credentials_missing":
            return "服务端高级备份凭据未配置，请稍后再试。"
        if code == "advanced_backup_credentials_invalid":
            return "服务端高级备份凭据不可用，请稍后再试。"
        return "高级备份服务暂不可用，请稍后再试。"

    if status == 429:
        if isinstance(detail, dict) and {"limit", "used", "remaining"}.issubset(detail):
            return (
                "高级备份额度不足: "
                f"已用 {detail.get('used')}/{detail.get('limit')}, "
                f"剩余 {detail.get('remaining')}。"
            )
        if text:
            return text
        return "请求过于频繁或额度不足，请稍后再试。"

    if status == 409:
        return text or "任务尚未完成，请稍后刷新状态后再下载。"

    return text or str(error)
