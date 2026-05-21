#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2026/03/02
# @Author     : XBW
# @File       : mx_tiktok.py
# @Description: 墨西哥地区 TikTok 直播数据采集爬虫（点击导航版本）

import json
import random
import time
from typing import Any
from datetime import datetime, timedelta, timezone as tz

from utils.logger import logger
from crawlers.browser.tiktok import TikTokLiveCrawler


class MxTikTokLiveCrawler(TikTokLiveCrawler):
    """墨西哥地区 TikTok 直播数据采集爬虫

    继承 TikTokLiveCrawler，覆写导航策略：
    shop.tiktok.com 下的页面优先使用侧边栏点击导航（而非直接 URL 跳转），
    解决墨西哥地区 URL 跳转问题。

    导航方法（_verify_navigation, _navigate_by_url, _navigate_by_click）
    和采集流程（visit_page_and_collect）均继承自父类，不再重复。
    """

    # shop 域名基础URL，首次点击导航前需确保在此域名下
    SHOP_BASE_URL = "https://shop.tiktok.com"

    # 墨西哥 URL 导航大概率偏移，减少无效重试
    URL_NAV_MAX_RETRY = 1

    # 详情页入口选择器模板，{room_id} 会被替换
    DETAIL_ENTRY_SELECTOR = "xpath://a[contains(@href, 'roomId={room_id}')]"
    DETAIL_WAIT = 'xpath://p[@class="text-neutral-text1 text-head-l"]'
    # 详情页返回按钮选择器
    DETAIL_BACK_SELECTOR = 'xpath://div[@class="zep-breadcrumb-item"]'

    # ==================== 导航策略覆写 ====================

    def _navigate_to_page(self, url: str) -> bool:
        """墨西哥策略：shop 页面优先使用点击导航

        与父类的区别：父类先尝试 URL 导航、失败后再点击恢复；
        墨西哥账号已知 URL 导航大概率偏移，因此直接跳过 URL 导航、
        优先点击。
        """
        if self._verify_navigation(url):
            return True
        if url in self.NAV_CLICK_MAP:
            return self._navigate_by_click(url)
        return self._navigate_by_url(url)

    # ==================== 详情页导航 ====================

    def _ensure_on_list_page(self) -> bool:
        """确保当前在直播列表页，若页面被反爬跳走则直接URL导航回来"""
        list_url = "https://shop.tiktok.com/streamer/compass/livestream-analytics/view"
        all_livestreams_ele = 'xpath://div[@class="zep-table-content-inner"]'

        # 已在列表页，直接检测列表容器是否存在
        if self._verify_navigation(list_url):
            if self.tab.ele(all_livestreams_ele, timeout=3):
                return True

        # 页面被跳走（反爬重定向）或列表未加载，直接URL导航回列表页
        logger.info('列表页状态异常，直接URL导航回列表页')
        self._navigate_by_click(list_url)
        loaded = self.tab.wait.eles_loaded(all_livestreams_ele, timeout=15)
        if not loaded:
            logger.warning('列表页加载超时')
            return False
        return True

    def _navigate_to_detail_page(self, room_id: str) -> bool:
        """从列表页点击进入直播详情页，需要确保稳定采集"""
        try:
            for i in range(3):
                # 每次重试前确保在列表页（应对反爬跳转）
                if not self._ensure_on_list_page():
                    logger.warning(f'无法回到列表页，跳过 room_id: {room_id}')
                    return False

                selector = self.DETAIL_ENTRY_SELECTOR.format(room_id=room_id)
                element = self.tab.ele(selector, timeout=5)
                if element:
                    self.tab.run_js('arguments[0].click();', element)
                    wait_flag = self.tab.wait.eles_loaded(self.DETAIL_WAIT, timeout=10)
                    if not wait_flag:
                        # 进入详情页失败，下一轮循环会调用 _ensure_on_list_page 重新回到列表页
                        logger.warning(f'进入详情页后未检测到目标元素，回退列表页重试 ({i+1}/3)')
                    else:
                        return True
                else:
                    logger.warning(f'未找到详情页入口元素 ({i+1}/3): {room_id}')

            logger.warning(f'点击进入详情页失败，已重试3次: {room_id}')
            return False
        except Exception as e:
            logger.error(f'点击进入详情页失败: {e}')
            return False

    def _navigate_back_from_detail(self) -> bool:
        """从详情页返回列表页

        三级回退：点击返回按钮 → 浏览器后退 → 直接URL导航
        """

        def click_100_view():
            try:
                dropdown = self.tab.ele('.zep-dropdown-button-button')
                if dropdown:
                    # 自动滚动直到该元素可见
                    dropdown.scroll.to_see()
                    dropdown.click()

                    option = self.tab.ele('text=View 100 Items')
                    if option:
                        # 针对下拉列表可能被遮挡的情况，直接执行 JS 点击
                        self.tab.run_js('arguments[0].click();', option)
            except Exception as e:
                pass
        if self.tab.url == 'https://shop.tiktok.com/streamer/compass/livestream-analytics/view':
            return True
        # 方式1：点击返回按钮
        if self.DETAIL_BACK_SELECTOR:
            try:
                back_btn = self.tab.ele(self.DETAIL_BACK_SELECTOR, timeout=5)
                if back_btn:
                    self.tab.run_js('arguments[0].click();', back_btn)
                    time.sleep(2)
                    click_100_view()
                    if 'detail' not in self.tab.url:
                        return True
            except Exception as e:
                logger.warning(f'点击返回按钮失败: {e}')

        # 方式2：浏览器后退
        try:
            self.tab.back()
            time.sleep(2)
            click_100_view()
            if 'detail' not in self.tab.url:
                return True
        except:
            pass

        # 方式3：直接导航回列表页
        list_url = "https://shop.tiktok.com/streamer/compass/livestream-analytics/view"
        return self._navigate_by_url(list_url)

    # ==================== 详情页采集逻辑（暂存） ====================

    def dp_handle_tiktok_live_list(self, response: Any, **kwargs: Any) -> None:
        # todo 该方法暂时保存起来 执行dp时候的逻辑
        """处理TikTok直播列表，通过点击进入详情页采集

        与父类逻辑相同，仅将直接URL导航改为点击进入+返回
        """

        def is_full_collection(d):
            params = d.get("request", {}).get("params", [])
            if not params:
                return False
            tsel = params[0].get("time_selector", {})
            stats = params[0].get("stats_types", [])
            return ("base_timestamp" in tsel and "timezone_offset" in tsel) or any(x in stats for x in [100, 101])

        try:
            # 过滤数据 只获取全量的数据接口
            request = kwargs.get("api_data", {}).get("request", {})
            if not is_full_collection(request):
                return
            # 解析响应
            if isinstance(response, str):
                if len(response) < 10000:
                    return
                response_json = json.loads(response)
            else:
                response_json = response

            # 提取直播间列表
            stats = response_json.get('data', {}).get('segments', [{}])[0] \
                .get('timed_lists', [{}])[0].get('stats', [])

            if not stats:
                return

            # 增量模式：基于账号时区计算前三天起始时间戳用于过滤
            if not self.full_collection:
                tz_offset_seconds = 0
                try:
                    params = request.get("request", {}).get("params", [])
                    if params:
                        tz_offset_seconds = params[0].get("time_selector", {}).get("timezone_offset", 0)
                        if isinstance(tz_offset_seconds, str):
                            tz_offset_seconds = int(tz_offset_seconds)
                except (ValueError, TypeError, IndexError):
                    pass

                account_tz = tz(timedelta(seconds=tz_offset_seconds))
                now = datetime.now(account_tz)
                three_days_ago = now - timedelta(days=3)
                three_days_ago_start = datetime(
                    three_days_ago.year, three_days_ago.month, three_days_ago.day,
                    0, 0, 0, tzinfo=account_tz
                )
                three_days_ago_timestamp = int(three_days_ago_start.timestamp())
                logger.info(
                    f'增量过滤：账号时区 UTC{tz_offset_seconds//3600:+d}，当地日期 {now.strftime("%Y-%m-%d")}，'
                    f'过滤 {three_days_ago.strftime("%Y-%m-%d")} 00:00:00 之前的直播间'
                )

            # 筛选直播间
            room_id_list = []
            for stat in stats:
                live_end_timestamp = stat.get('live_end_timestamp', 0)
                room_id = stat.get('live_id')

                if not room_id or live_end_timestamp == 0 or room_id in self.processed_room_ids:
                    continue

                if not self.full_collection:
                    if live_end_timestamp < three_days_ago_timestamp:
                        continue

                room_id_list.append(room_id)
                self.processed_room_ids.add(room_id)

            if room_id_list:
                mode_desc = '全部' if self.full_collection else '近三天的'
                logger.info(f'找到 {len(room_id_list)} 个{mode_desc}直播间，将依次点击进入详情页')

                # 依次点击进入详情页采集
                for i, room_id in enumerate(room_id_list):
                    logger.info(f'[{i + 1}/{len(room_id_list)}] 访问直播详情页: {room_id}')

                    try:
                        if self._navigate_to_detail_page(room_id):
                            # 在详情页上执行采集
                            self.visit_page_and_collect(self.tab.url)

                        # 返回列表页
                        self._navigate_back_from_detail()

                        time.sleep(random.randint(1, 3))
                    except Exception as e:
                        logger.error(f'访问直播详情页失败 {room_id}: {e}')
                        continue

        except Exception as e:
            logger.warning(f'处理TikTok直播列表失败: {e}')
