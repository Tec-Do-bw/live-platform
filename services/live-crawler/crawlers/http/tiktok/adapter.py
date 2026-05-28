"""TikTok HTTP 采集器适配层。"""

from __future__ import annotations

from datetime import datetime

from crawlers.http.tiktok.collector import _format_message, collect_tiktok
from services.data_reporter import send_api_request
from utils.credentials import load_credentials
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

    def start_crawl(self) -> dict:
        """执行 TikTok HTTP 采集并返回调度入口兼容的统计。"""
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
            cred = load_credentials(self.browser_id, platform="tiktok")
            cookies = cred.token_data if cred else {}
            for ok, item in collect_tiktok(self.browser_id, full=self.full_collection):
                if not ok:
                    result["error"] = item.get("data", {}).get("error", "unknown error")
                    continue

                result["apis_collected"] += 1
                message = _format_message(
                    item["url"],
                    item["request_body"],
                    item["response_body"],
                    cookies,
                    self.socket_user_id,
                )
                if send_api_request(
                    message,
                    platform=self.platform,
                    socket_user_id=self.socket_user_id,
                    timestamp=self.timestamp,
                ):
                    result["data_sent"] += 1

            result["success"] = result["error"] is None
        except LoginRequired as e:
            logger.warning(f"[{self.browser_id}] TikTok HTTP 登录态失效: {e}")
            result["login_status"] = False
            result["error"] = str(e)
        except Exception as e:
            logger.exception(f"[{self.browser_id}] TikTok HTTP 采集异常: {e}")
            result["error"] = str(e)
        finally:
            result["end_time"] = datetime.now().isoformat()

        return result
