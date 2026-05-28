"""HTTP 采集请求头构造工具。"""

from __future__ import annotations

from typing import Any


def build_headers(
    session: Any = None,
    *,
    cred: Any = None,
    origin: str = "https://shop.tiktok.com",
    referer: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """构造业务请求头，指纹字段从凭据派生。"""
    spec = getattr(cred, "fingerprint_spec", {}) if cred is not None else {}
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": spec.get("accept_language") or "en-US,en;q=0.9",
        "origin": origin,
        "referer": referer or origin,
    }

    if spec.get("user_agent"):
        headers["user-agent"] = spec["user_agent"]
    if spec.get("sec_ch_ua"):
        headers["sec-ch-ua"] = spec["sec_ch_ua"]
    if spec.get("sec_ch_ua_mobile"):
        headers["sec-ch-ua-mobile"] = spec["sec_ch_ua_mobile"]
    if spec.get("sec_ch_ua_platform"):
        headers["sec-ch-ua-platform"] = spec["sec_ch_ua_platform"]
    if extra:
        headers.update(extra)
    return headers
