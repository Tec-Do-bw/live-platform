"""Shopee API 服务，用于查询店铺信息"""
import httpx
from loguru import logger
from typing import Optional

from app.config import get_shopee_seller_domain


class ShopeeApiService:
    """Shopee API 服务"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.client.headers.update(
            {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "priority": "u=0, i",
                "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Google Chrome\";v=\"134\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            }
        )

    async def get_shop_cb_option(self, country: str, shop_id: str) -> Optional[int]:
        """查询店铺的 cb_option（0=本土店，1=跨境店）

        Args:
            country: 国家代码（如 MY, ID, TH）
            shop_id: 店铺 ID

        Returns:
            0: 本土店
            1: 跨境店
            None: 查询失败或无数据
        """
        if not country or not shop_id:
            return None

        try:
            seller_domain = get_shopee_seller_domain(country).replace('seller.','')
            url = f"https://{seller_domain}/api/v4/shop/get_shop_detail"
            params = {"shopid": shop_id}

            logger.debug(f"查询 Shopee cb_option: {url}?shopid={shop_id}")
            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json().get("data", {})
            cb_option = data.get("cb_option")
            is_verified = data.get("is_shopee_verified", False)

            if cb_option is not None:
                # 跨境优选/Choice 走本土站（特殊隔离），将 cb_option 改写为 0
                if is_verified:
                    logger.info(f"店铺 {shop_id} 是跨境优选/Choice，改写 cb_option=1 -> 0（走本土站）")
                    return 0
                logger.info(f"店铺 {shop_id} cb_option={cb_option} ({'跨境' if cb_option == 1 else '本土'})")
                return int(cb_option)
            else:
                logger.warning(f"店铺 {shop_id} 响应中无 cb_option 字段")
                return None

        except httpx.HTTPStatusError as e:
            logger.warning(f"查询 cb_option HTTP 错误: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"查询 cb_option 异常: {e}")
            return None

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


# 全局单例
shopee_api_service = ShopeeApiService()


if __name__ == '__main__':
    async def main():
        cb_option = await shopee_api_service.get_shop_cb_option("my", "188678203")
        print(cb_option)

    import asyncio
    asyncio.run(main())