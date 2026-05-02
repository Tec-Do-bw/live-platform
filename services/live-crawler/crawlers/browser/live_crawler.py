#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : live_crawler.py
# @Description: 直播数据采集爬虫工厂类 - 主调度器

from typing import List
from utils.logger import logger
from crawlers.browser.base import BaseLiveCrawler
from crawlers.browser.tiktok import TikTokLiveCrawler
from crawlers.browser.shopee import ShopeeLiveCrawler
from crawlers.browser.mx_tiktok import MxTikTokLiveCrawler
from crawlers.http.lazada import LazadaHttpCrawler


class LiveCrawler:
    """直播数据采集爬虫工厂类

    根据平台参数自动创建对应的爬虫实例，支持浏览器和 HTTP 双轨路由
    """

    # 浏览器采集平台映射表
    PLATFORM_CRAWLERS = {
        'tiktok': TikTokLiveCrawler,
        'shopee': ShopeeLiveCrawler,
    }

    # HTTP 采集平台映射表（优先级高于浏览器）
    HTTP_CRAWLERS: dict[str, type] = {
        'lazada': LazadaHttpCrawler,
    }

    def __new__(cls, platform: str = 'tiktok', browser_id: str = None, full_collection: bool = False,
                group_name: str = '', batch_id: str = '', crawl_type: str = 'history'):
        """工厂方法：根据platform创建对应的爬虫实例

        优先检查 HTTP_CRAWLERS，再检查 PLATFORM_CRAWLERS。

        Args:
            platform: 平台标识 ('tiktok', 'shopee', 'lazada' 等)
            browser_id: 指纹浏览器ID
            full_collection: 是否全量采集模式
            group_name: AdsPower分组名称（用于Shopee多国域名识别）
            batch_id: 批次ID
            crawl_type: 采集类型（'realtime' 或 'history'，仅 HTTP 爬虫使用）

        Returns:
            BaseLiveCrawler 或 BaseHttpCrawler 实例

        Raises:
            ValueError: 不支持的平台
        """
        # 优先检查 HTTP 爬虫
        if platform in cls.HTTP_CRAWLERS:
            crawler_class = cls.HTTP_CRAWLERS[platform]
            logger.info(f'通过工厂类创建 {platform} HTTP 爬虫实例 (全量采集: {full_collection}, crawl_type: {crawl_type})')
            return crawler_class(browser_id=browser_id, full_collection=full_collection,
                                 group_name=group_name, batch_id=batch_id, crawl_type=crawl_type)

        # 检查浏览器爬虫
        if platform not in cls.PLATFORM_CRAWLERS:
            supported = ', '.join(cls.get_supported_platforms())
            raise ValueError(f"不支持的平台: {platform}，支持的平台有: {supported}")

        # 获取对应的爬虫类
        crawler_class = cls.PLATFORM_CRAWLERS[platform]

        # 墨西哥 TikTok 路由：group_name 包含"墨西哥"时使用点击导航版本
        if platform == 'tiktok' and '墨西哥' in group_name:
            crawler_class = MxTikTokLiveCrawler
            logger.info(f'检测到墨西哥分组，使用 MxTikTokLiveCrawler')

        # 创建并返回实例（浏览器爬虫不传递 crawl_type）
        logger.info(f'通过工厂类创建 {platform} 平台爬虫实例 (全量采集: {full_collection})')
        return crawler_class(browser_id=browser_id, full_collection=full_collection, group_name=group_name, batch_id=batch_id)
    
    @classmethod
    def register_platform(cls, platform: str, crawler_class: type):
        """注册新的平台爬虫类
        
        Args:
            platform: 平台标识
            crawler_class: 爬虫类（必须继承BaseLiveCrawler）
        """
        if not issubclass(crawler_class, BaseLiveCrawler):
            raise TypeError(f"{crawler_class.__name__} 必须继承自 BaseLiveCrawler")
        
        cls.PLATFORM_CRAWLERS[platform] = crawler_class
        logger.info(f'已注册新平台: {platform} -> {crawler_class.__name__}')
    
    @classmethod
    def get_supported_platforms(cls) -> List[str]:
        """获取所有支持的平台列表（浏览器 + HTTP）

        Returns:
            List[str]: 平台标识列表
        """
        all_platforms = set(cls.PLATFORM_CRAWLERS.keys())
        all_platforms.update(cls.HTTP_CRAWLERS.keys())
        return sorted(all_platforms)


if __name__ == '__main__':
    # 测试代码
    logger.info(f'支持的平台: {LiveCrawler.get_supported_platforms()}')
    
    # 使用工厂类创建TikTok爬虫
    crawler = LiveCrawler(platform='shopee', browser_id='k16y6938',full_collection=True, group_name='马来西亚')
    result = crawler.start_crawl()
    logger.info(f'采集结果: {result}')
