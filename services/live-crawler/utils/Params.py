#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# 用于存放项目及模块相关的参数信息
import datetime
import random
import time
import uuid
import os
__all__ = [
    'Params',
]


class Params(object):

    # 请求错误重试相关参数（重试次数，重试最小等待时间，重试最大等待时间）
    retry_num = 3
    retry_time_min = 1000
    retry_time_max = 3000

    # requests 超时，休眠等设置
    time_out = 10

    request_delay_list = [x / 10 for x in range(10, 19, 1)]
    request_delay_random = random.choice(request_delay_list)

    # 当前时间戳
    timestamp = int(time.time() * 1000)
    timestamp_normal = int(time.time())

    # 代理地址
    proxy_url = "http://api.xiequ.cn/VAD/GetIp.aspx?act=get&num=1&time=30&plat=0&re=0&type=2&so=1&ow=1&spl=1&addr=&db=1"

    # 一些常见的 ua 参数信息(测试使用，推荐使用fake_useragent)
    ua_list = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.193 Mobile Safari/537.36",
        "Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1",
        "Mozilla/5.0 (Linux; Android 7.0; SM-G892A Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/67.0.3396.87 Mobile Safari/537.36",
    ]

    # 随机 ua 的设置
    # ua_random = str(UserAgent().chrome)

    # splash_url = "http://123.56.16.57:8050"
    splash_url = "http://192.168.99.100:8050"

    scrapy_splash_wait = '2'

    heimao_index_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0',
        'Accept': 'text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://tousu.sina.com.cn/',
    }
    heimao_domain = "https://tousu.sina.com.cn/"
    pengpai_domain = "http://www.thepaper.cn"

    # heimao_filter_table = "heimao_filter"
    # heimao_saved_file = "heimao"
    # pengpai_filter_table = "heimao_filter"
    # pengpai_saved_file = "heimao"
    filter_table = "complaint_filter"
    saved_file = "complaint"

    history_time = (datetime.datetime.now() + datetime.timedelta(days=-1)).strftime("%Y-%m-%d")
    curr_time = (datetime.datetime.now() + datetime.timedelta(days=0)).strftime("%Y-%m-%d")
    before_yesterday_time = (datetime.datetime.now() + datetime.timedelta(days=-2)).strftime("%Y-%m-%d")
    @staticmethod
    def snapchat_index_headers():
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'apollographql-client-name': 'adsMgr',
            'apollographql-client-version': '672d611e',
            # 'authorization': f'Bearer {token}',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://ads.snapchat.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://ads.snapchat.com/',
            'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'x-application': '87947032-5fbd-46a7-ba60-073ca8efefbb',
            "x-client-trace-id": f"{uuid.uuid4()},rst:{int(time.time() * 1000)}"  # 每次都不不一样
        }
        return headers

    @staticmethod
    def Joybug_headers():
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": "https://biu6ihvvco.feishu.cn/",
            "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Google Chrome\";v=\"134\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        }
        return headers


if __name__ == '__main__':
    from pprint import pprint
    print('随机等待时间为：', Params.request_delay_random)
    pprint(Params.snapchat_index_headers())

