"""Cookie 管理 API 路由，供 adspower-server 远程写入 Cookie。"""

import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from services.cookie_manager import save_cookies
from utils.logger import logger

router = APIRouter(prefix='/api', tags=['cookies'])

# Cookie API 访问令牌（从环境变量读取，默认值仅用于开发环境）
COOKIE_API_TOKEN = os.getenv("COOKIE_API_TOKEN", "sk-5eajkJEpzRQL4pvMpqxxoffm3hgFi7FCNDs2OXfWIJuOipvx")


class SaveCookieRequest(BaseModel):
    platform: str
    endpoint: str = ''
    cookies: dict = {}
    seller_id: str = ''
    venture: str = ''
    extra: dict = {}


@router.put('/cookies/{account_id}')
def upsert_cookie(account_id: str, req: SaveCookieRequest, x_api_token: str = Header(...)):
    """写入或更新 Cookie（upsert）

    需要在请求头中提供 X-API-Token 进行身份验证。
    """
    # 验证 API Token
    if x_api_token != COOKIE_API_TOKEN:
        logger.warning(f"Cookie API 访问被拒绝：无效的 token（account_id={account_id}）")
        raise HTTPException(status_code=403, detail="Invalid API token")

    try:
        extra = req.extra.copy()
        if req.seller_id:
            extra['seller_id'] = req.seller_id
        if req.venture:
            extra['venture'] = req.venture

        save_cookies(
            account_id=account_id,
            platform=req.platform,
            endpoint=req.endpoint,
            cookies=req.cookies,
            extra=extra,
        )
        return {'success': True}
    except Exception as e:
        logger.error('Cookie 保存失败: {}', e)
        raise HTTPException(status_code=500, detail=str(e))
