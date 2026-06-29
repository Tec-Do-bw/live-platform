#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time:2020.09.12
# @author:xhrg
# @email:634789257@qq.com

import hashlib
import sys
import socket
import logging
import os

import urllib.request
from urllib.error import HTTPError
from urllib import parse

version = sys.version_info.major

# 定义常量
CONFIGURATIONS = "configurations"
NOTIFICATION_ID = "notificationId"
NAMESPACE_NAME = "namespaceName"


def http_request(url, timeout, headers={}):
    try:
        request = urllib.request.Request(url, headers=headers)
        res = urllib.request.urlopen(request, timeout=timeout)
        body = res.read().decode("utf-8")
        return res.code, body
    except HTTPError as e:
        if e.code == 304:
            # logging.getLogger(__name__).warning("http_request error,code is 304, maybe you should check secret")
            return 304, None
        # logging.getLogger(__name__).warning("http_request error,code is %d, msg is %s", e.code, e.msg)
        raise e


def url_encode(params):
    return parse.urlencode(params)


def makedirs_wrapper(path):
    os.makedirs(path, exist_ok=True)


# 对时间戳，uri，秘钥进行加签
def signature(timestamp, uri, secret):
    import hmac
    import base64
    string_to_sign = '' + timestamp + '\n' + uri
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(hmac_code).decode()


def url_encode_wrapper(params):
    return url_encode(params)


def no_key_cache_key(namespace, key):
    return "{}{}{}".format(namespace, len(namespace), key)


# 返回是否获取到的值，不存在则返回None
def get_value_from_dict(namespace_cache, key):
    if namespace_cache:
        kv_data = namespace_cache.get(CONFIGURATIONS)
        if kv_data is None:
            return None
        if key in kv_data:
            return kv_data[key]
    return None


def init_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 53))
        ip = s.getsockname()[0]
        return ip
    finally:
        s.close()
    return ""
