"""
飞书 Webhook 通知服务
用于发送静态代理缺失告警等通知
"""
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from loguru import logger


class FeishuNotificationService:
    """飞书通知服务"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.FEISHU_WEBHOOK_URL

    async def send_message(self, content: str) -> bool:
        """
        发送飞书消息

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        payload = {
            "msg_type": "text",
            "content": {"text": content}
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                result = response.json()
                # 飞书返回 code=0 表示成功
                if result.get("code") == 0:
                    logger.info("飞书通知发送成功")
                    return True
                else:
                    logger.warning("飞书通知发送失败: {}", result)
                    return False
        except httpx.HTTPError as exc:
            logger.error("飞书通知请求失败: {}", exc)
            return False
        except Exception as exc:
            logger.error("飞书通知发送异常: {}", exc)
            return False

    async def notify_unsupported_country(
        self,
        country: str,
        media: str,
        profile_id: str
    ) -> bool:
        """
        发送静态代理不支持国家的通知

        Args:
            country: 国家代码
            media: 媒体类型
            profile_id: 浏览器 Profile ID

        Returns:
            是否发送成功
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = f"""⚠️ 静态代理缺失告警

国家: {country}
媒体: {media}
Profile ID: {profile_id}
时间: {now}

已自动使用24小时动态代理，请及时添加静态代理配置。"""

        return await self.send_message(content)


# 全局单例
notification_service = FeishuNotificationService()
