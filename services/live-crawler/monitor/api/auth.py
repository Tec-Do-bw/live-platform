"""共享 API 鉴权依赖。"""

from fastapi import Header, HTTPException

from core.config import Settings


API_TOKEN = Settings.COOKIE_API_CONFIG.get("token", "")


def require_cookie_api_token(x_api_token: str = Header(default="")) -> None:
    """校验下游内网接口的 X-API-Token。"""
    if not API_TOKEN or x_api_token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid API token")
