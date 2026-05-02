#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/14 上午11:56
# @Author     : XBW
# @File       : slider_demo.py
# @Description: 

# !/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : tiktok.py
# @Description: TikTok平台直播数据采集爬虫

import json
import time
import random
import requests
import ddddocr
from typing import Any, Dict, List
from datetime import datetime, timedelta
from webdriver.browserapi import BrowserApi
from utils.logger import logger
from DrissionPage import Chromium, ChromiumOptions



class SildderCrawler():
    """TikTok平台直播数据采集爬虫"""

    def __init__(self):
        # co = ChromiumOptions().auto_port()
        # co.set_argument('--start-maximized')  # 设置启动时最大化
        # driver = Chromium(addr_or_opts=co)
        self.driver = BrowserApi.get_driver('k16w7jdu')
        self.tab = self.driver.latest_tab
        self.ocr =  ddddocr.DdddOcr(det=False, ocr=False)


    def get_platform_name(self) -> str:
        """返回TikTok平台标识"""
        return 'tiktok'

    def visit_page_and_collect(self, url: str) -> Dict[str, Any]:
        """访问TikTok页面并收集数据

        Args:
            url: 页面URL

        Returns:
            Dict: 页面采集结果
        """
        # 1. 访问页面
        self.tab.set.cookies.clear()
        self.tab.clear_cache()
        self.tab.get(url)
        time.sleep(5)
        logger.info(f'TikTok页面加载中...')
        # 2.5 检测并处理滑块验证码
        self._detect_and_handle_slider()


    def _handle_tiktok_live_list(self, response: Any) -> None:
        """处理TikTok直播列表，自动打开昨天的直播详情页

        Args:
            response: API响应数据
        """
        try:
            # 解析响应
            if isinstance(response, str):
                if len(response) < 10000:  # 响应太小，跳过
                    return
                response_json = json.loads(response)
            else:
                response_json = response

            # 提取直播间列表
            stats = response_json.get('data', {}).get('segments', [{}])[0] \
                .get('timed_lists', [{}])[0].get('stats', [])

            if not stats:
                return

            # 计算昨天的时间戳
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
            yesterday_timestamp = int(yesterday_start.timestamp())

            # 筛选昨天开始的直播
            room_id_list = []
            for stat in stats:
                live_start_timestamp = stat.get('live_start_timestamp', 0)
                live_end_timestamp = stat.get('live_end_timestamp', 0)
                room_id = stat.get('live_id')

                # 过滤无效、正在直播或已处理的直播间
                if not room_id or live_end_timestamp == 0 or room_id in self.processed_room_ids:
                    continue

                if live_start_timestamp >= yesterday_timestamp:
                    room_id_list.append(room_id)
                    self.processed_room_ids.add(room_id)

            if room_id_list:
                logger.info(f'找到 {len(room_id_list)} 个昨天的直播间，将依次访问详情页')

                # 依次访问直播详情页
                for i, room_id in enumerate(room_id_list):
                    detail_url = f"https://shop.tiktok.com/streamer/compass/livestream-analytics/view/detail?roomId={room_id}"
                    logger.info(f'[{i + 1}/{len(room_id_list)}] 访问直播详情页: {room_id}')

                    try:
                        # 访问详情页并采集
                        self.visit_page_and_collect(detail_url)

                        # 间隔30秒，避免请求过快
                        if i < len(room_id_list) - 1:
                            time.sleep(30)
                    except Exception as e:
                        logger.error(f'访问直播详情页失败 {room_id}: {e}')
                        continue

        except Exception as e:
            logger.warning(f'处理TikTok直播列表失败: {e}')

    def _detect_and_handle_slider(self) -> bool:
        """检测并处理滑块验证码

        Returns:
            bool: 是否成功处理滑块
        """
        try:
            # 最多尝试5次滑块验证
            for attempt in range(1, 6):
                # 检测页面是否存在滑块
                if not self._check_slider_exists():
                    logger.debug('页面中未检测到滑块验证码')
                    return False

                logger.info(f'第 {attempt}/5 次尝试滑块验证')

                # 获取滑块距离
                distance = self._get_slider_distance()

                logger.info(f'计算出滑块滑动距离: {distance}px')

                # 执行滑块操作
                if self._perform_slider_action(distance):
                    logger.success('滑块验证成功！')
                    return True
                else:
                    logger.warning(f'第 {attempt} 次尝试：滑块验证失败，准备重试...')
                    time.sleep(2)

            logger.error('滑块验证超过最大尝试次数，未能通过')
            return False

        except Exception as e:
            logger.error(f'处理滑块验证异常: {e}')
            return False

    def _check_slider_exists(self) -> bool:
        """检查页面中是否存在滑块验证码

        Returns:
            bool: 页面中是否存在滑块
        """
        try:
            self.tab.wait.eles_loaded('xpath://*[@class="sc-eNQAEJ dhEdIP"]',timeout=5)
            # 检查是否存在滑块容器
            slider_container = self.tab.ele('xpath://*[@id="captcha-verify-image"]', timeout=2)
            if not slider_container:
                return False
            self.background_url = self.tab.ele('xpath://*[@id="captcha-verify-image"]', timeout=2).attr('src')

            # 检查是否存在滑块按钮
            slider_button = self.tab.ele('xpath://*[@class="sc-eNQAEJ dhEdIP"]', timeout=2)
            if not slider_button:
                return False
            self.target_url = self.tab.ele('xpath://*[@id="captcha-verify-image"]/../img[2]', timeout=2).attr('src')
            logger.debug(f'背景图片\t{self.background_url}\n 目标图片\t{self.target_url}')
            return True

        except Exception as e:
            logger.debug(f'检查滑块是否存在时出错: {e}')
            return False

    def _get_slider_distance(self) -> int:
        """获取滑块需要滑动的距离

        Returns:
            int: 滑动距离（像素），如果获取失败返回None
        """
        try:
            background_response = requests.get(self.background_url)
            target_response = requests.get(self.target_url)

            ocr_result = self.ocr.slide_match(target_response.content, background_response.content)

            # 转换坐标
            x = int(ocr_result['target'][0])
            # 根据原始图片宽度(550px)转换为实际滑块宽度(340px)
            distance = int(int(x) / 550 * 340) - 5

            return distance
        except Exception as e:
            logger.error(f'获取滑块距离异常: {e}')
            return None

    def _perform_slider_action(self, distance: int) -> bool:
        """执行滑块操作，模拟用户滑动

        Args:
            distance: 滑块需要滑动的距离

        Returns:
            bool: 是否成功滑动
        """
        try:
            element = 'xpath://*[@class="sc-eNQAEJ dhEdIP"]'
            ele = self.tab.ele(element)
            ele.drag(distance,  random.randint(-2, 2),random.uniform(0.5,1.5))
            #
            #
            #
            # distance = [distance]
            # # 按住滑块
            # self.tab.actions.hold(element)
            # time.sleep(random.uniform(0.001, 0.003))
            # # 按轨迹移动
            # for x in distance:
            #     self.tab.actions.move(x, random.randint(-2, 2))  # y 方向随机微小抖动
            #     # time.sleep(random.uniform(0.001, 0.003))  # 每步移动间隔
            #
            # # 松开滑块
            # time.sleep(random.uniform(0.01, 0.03))
            # self.tab.actions.release()

            # 检查是否验证成功（检查滑块是否消失）
            try:
                slider = self.tab.ele('xpath://*[@id="captcha_container"]', timeout=2)
                if not slider:
                    logger.success('滑块已消失，验证成功')
                    return True
            except:
                logger.success('滑块已消失，验证成功')
                return True

            logger.warning('滑块仍然存在，验证可能未成功')
            return False

        except Exception as e:
            logger.error(f'执行滑块操作异常: {e}')
            return False

    def get_geetest_tracks(self, distance):
        def ease_out_expo(sep):
            if sep == 1:
                return 1
            else:
                return 1 - pow(2, -10 * sep)

        plus = []
        # 记录count次滑块位置信息
        count = int(distance / 4)
        for i in range(count):
            s = round(ease_out_expo(i / count) * distance)
            plus.append(round(s))
        return plus


if __name__ == '__main__':
    crawler = SildderCrawler()
    for i in range(10):
        crawler.visit_page_and_collect('https://www.tiktok.com/shop')