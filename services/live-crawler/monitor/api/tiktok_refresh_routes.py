"""TikTok 凭据刷新 API 路由，供 adspower-server 登录成功后远程触发。

登录态人工投屏复登后,adspower-server 调用本接口立即刷新该账号的
account_credentials(query_string/cookies/creator_id),确保复登及时生效,
不必等每日 cron。
"""

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from cookie_keeper.tiktok_refresher import TikTokRefresher
from core.config import Settings
from utils.logger import logger

router = APIRouter(prefix='/api', tags=['tiktok'])

# 复用 Cookie API 的访问令牌(与 cookie_routes 同源,adspower-server 已持有)
TIKTOK_API_TOKEN = Settings.COOKIE_API_CONFIG.get("token", "")


class RefreshTikTokRequest(BaseModel):
    """刷新 TikTok 凭据请求体。"""

    account_id: str
    group_name: str = ''
    proxy: str = ''


@router.post('/refresh_tiktok_credential')
async def refresh_tiktok_credential(req: RefreshTikTokRequest, x_api_token: str = Header(...)):
    """刷新单个 TikTok 账号的 HTTP 采集凭据。

    需要在请求头中提供 X-API-Token 进行身份验证。
    refresh_account 会开浏览器并阻塞约 15-30s,放线程池执行避免阻塞事件循环。
    """
    if x_api_token != TIKTOK_API_TOKEN:
        logger.warning(f"TikTok 刷新 API 访问被拒绝：无效的 token（account_id={req.account_id}）")
        raise HTTPException(status_code=403, detail="Invalid API token")

    if not req.account_id:
        raise HTTPException(status_code=400, detail="account_id 不能为空")

    logger.info(f"[{req.account_id}] 收到 TikTok 凭据刷新请求 group_name={req.group_name}")
    try:
        refresher = TikTokRefresher()
        ok = await run_in_threadpool(
            refresher.refresh_account,
            req.account_id,
            req.group_name,
            req.proxy,
        )
        return {"success": ok, "account_id": req.account_id}
    except Exception as e:
        logger.exception(f"[{req.account_id}] TikTok 凭据刷新接口异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))
