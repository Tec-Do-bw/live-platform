"""TikTok HTTP 采集器适配层。"""

from __future__ import annotations

from datetime import datetime

from crawlers.http.tiktok.collector import _format_message, collect_tiktok, setup_session
from services.data_reporter import send_api_request
from services.login_callback import send_login_callback
from utils.logger import logger
from utils.types import LoginRequired


class TikTokHttpCollector:
    """暴露 start_crawl() 的薄适配器，内部转调 collect_tiktok()。"""

    platform = "tiktok"

    def __init__(
        self,
        browser_id: str,
        full_collection: bool = False,
        group_name: str = "",
        batch_id: str = "",
        crawl_type: str = "history",
    ):
        self.browser_id = browser_id
        self.socket_user_id = browser_id
        self.full_collection = full_collection
        self.group_name = group_name
        self.batch_id = batch_id
        self.crawl_type = crawl_type
        self.timestamp = int(datetime.now().timestamp())
        # 标记本轮是否触发了登出即时恢复（对齐浏览器版 BaseLiveCrawler._login_recovery）
        self._login_recovery = False

    def _report(self, item: dict, cookies: dict) -> bool:
        """格式化单条采集结果并上报，返回是否上报成功。"""
        message = _format_message(
            item["url"],
            item["request_body"],
            item["response_body"],
            cookies,
            self.socket_user_id,
        )
        return send_api_request(
            message,
            platform=self.platform,
            socket_user_id=self.socket_user_id,
            timestamp=self.timestamp,
        )

    def start_crawl(self) -> dict:
        """执行 TikTok HTTP 采集并返回调度入口兼容的统计。

        流程：先验证登录态 → 发 success 回调（内部检测 logout→login 即时恢复）
        → 据恢复标记决定本轮 full → 进入数据采集主体。
        登录态失效时抛 LoginRequired，转为 logout 回调并写登出事件。
        """
        result = {
            "platform": self.platform,
            "browser_id": self.browser_id,
            "success": False,
            "pages_visited": 0,
            "apis_collected": 0,
            "data_sent": 0,
            "login_status": True,
            "error": None,
            "start_time": datetime.now().isoformat(),
            "login_recovery": False,
            "crawler_mode": "http",
        }

        try:
            # 1. 验证登录态（凭据缺失/失效在此抛出，由下方 except 捕获）
            cred, session, login_result = setup_session(self.browser_id)
            try:
                cookies = cred.token_data

                # 2. 验证通过 → 发 success 回调，内部检测 logout→login 即时恢复
                callback = send_login_callback(
                    browser_id=self.browser_id,
                    platform=self.platform,
                    group_name=self.group_name,
                    login_status="success",
                )
                if callback.get("login_recovery"):
                    self._login_recovery = True
                    self.full_collection = True
                    logger.info(
                        f"[{self.browser_id}] TikTok HTTP 登出即时恢复触发，本轮切换为全量采集"
                    )

                # 3. 上报 account_info（验证阶段已请求，复用结果）
                result["apis_collected"] += 1
                if self._report(login_result, cookies):
                    result["data_sent"] += 1

                # 4. 进入数据采集主体（用最终决定的 full，注入已建会话避免重复验证）
                for ok, item in collect_tiktok(
                    self.browser_id,
                    full=self.full_collection,
                    cred=cred,
                    session=session,
                    login_result=login_result,
                ):
                    if not ok:
                        result["error"] = item.get("data", {}).get("error", "unknown error")
                        continue

                    result["apis_collected"] += 1
                    if self._report(item, cookies):
                        result["data_sent"] += 1
            finally:
                session.close()

            result["login_recovery"] = self._login_recovery
            result["success"] = result["error"] is None
        except LoginRequired as e:
            logger.warning(f"[{self.browser_id}] TikTok HTTP 登录态失效: {e}")
            # 登出 → 发 logout 回调并写登出事件，供下一轮登出恢复全量判定
            send_login_callback(
                browser_id=self.browser_id,
                platform=self.platform,
                group_name=self.group_name,
                login_status="logout",
                reason=str(e),
            )
            result["login_status"] = False
            result["error"] = str(e)
        except Exception as e:
            logger.exception(f"[{self.browser_id}] TikTok HTTP 采集异常: {e}")
            result["error"] = str(e)
        finally:
            result["end_time"] = datetime.now().isoformat()

        return result
