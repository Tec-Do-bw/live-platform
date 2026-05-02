#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/21 上午11:21
# @Author     : XBW
# @File       : 虾皮直播回放获取.py
# @Description: 
import requests


headers = {
    "User-Agent": "language=zh-Hans app_type=1 platform=native_ios appver=34929 os_ver=14.2.0 Cronet/102.0.5005.61",
    "content-type": "application/json",
    "accept-language": "en-US,en"
}
# url = "https://live.shopee.sg/api/v1/shop_page/live/replay_list"
# params = {
#     "offset": "0",
#     "limit": "50",
#     "uid": "1218661031"
# }

url = "https://live.shopee.com.my/api/v1/shop_page/live/replay_list"
params = {
    "offset": "0",
    "limit": "3",
    "uid": "1618800797"
}


response = requests.get(url, headers=headers, params=params)

print(response.text)
print(response)

url = "https://live.shopee.com.my/api/v1/replay/3001468"
response = requests.get(url, headers=headers,)

print(response.text)
print(response)
#
# response = requests.get(url, headers=headers,)
#
# print(response.text)
# print(response)