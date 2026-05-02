#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2026/4/21 上午11:32
# @Author     : XBW
# @File       : lazda_cookie_activity.py
# @Description: 测试 Lazada 采集需要的关键 cookie 活性
#
# 测试 sellercenter 端和 LazLive 端的 cookie 活性，
# 通过逐个剔除 cookie 字段来确定哪些是必需的。
#
# 使用方式：填入有效的 cookie 和代理信息后直接运行。

import hashlib
import json
import time
from datetime import datetime

import requests

# ============================================================
# 配置区：填入你要测试的 cookie 和代理
# ============================================================

PROXY = {
    "http": "socks5://c822ee15:2169010a@75.kookeey.info:27240",
    "https": "socks5://c822ee15:2169010a@75.kookeey.info:27240",
}

# 国家域名，可选: co.th, com.my, co.id, vn, sg, com.ph
COUNTRY_DOMAIN = "co.th"

# 全量 cookie（从浏览器抓包获取，sellercenter 和 LazLive 共享同一浏览器会话）
ALL_COOKIES = {
    "cna": "NNBoInM/qnUCAS/2pJUtEAnT",
    "t_fv": "1776411188851",
    "t_uid": "6fmYKAYleJpRP3U57aqJify8sZISianI",
    "lzd_cid": "df44ceb5-8099-4b23-8561-6d9864b90d0a",
    "_tb_token_": "57beefd559b8e",
    "JSID": "115fea090cd2f5f961f5cc4831e92ded",
    "TID": "1a1de23d0cb20a57508ebc30fe84070d",
    "CSRFT": "ef018a3e31e73",
    "lwrid": "AgGdmlvaokfs0sJNBpPoX39uI7qt",
    "asc_seller_mp_type": "ASC_V2",
    "_lang": "zh_CN",
    "asc_uid": "101446560219",
    "asc_uid.sig": "xZmGELX_NMncRtbv2oeNodFtZRKeY67kL9BXM0NBuS4",
    "asc_uid_enc": "MTAxNDQ2NTYwMjE5",
    "asc_uid_enc.sig": "jRZZUpWWHbtbB5cbWYLNb8X-w9PBLBiRp5xfaWqTVLg",
    "xlly_s": "1",
    "lwrtk": "AAIEaedahoNh4p3IstyPPfBSLxHfHdoHZPe5CgscUpTle6P7PhdXrok=",
    "lzd_sid": "1d07b33d5e2828d4f7a1e9b72ceea36a",
    "_m_h5_tk": "764c1e53c280547320b945b4aaa5fbef_1776769085545",
    "_m_h5_tk_enc": "9cc8c063da0b6696fd652a9ffd26cd63",
    "t_sid": "2vO0nrfNQ278eI2ZwvCUtyub97EZdE0H",
    "utm_channel": "NA",
    "epssw": "12*m6yDVGwGGIEI2FohIGGh7LSHVJ32HLZE9o3hrsX04UTzlGGG4UGhMsh72LLOpxCTM0GGwTpwAFsCEq0kmyG6bus0ck2uabvLm6j8cR4Uxf9rkB4hlXlTLukbP9tT8yhhxw4_2m8nvCDMZgZofZp65QvXmyGXsOpuJGItsr6qnnumlDGtLGGIpqLlJp0YKwK235kNVb8jCjDWitR3TJZiBAMOss8iGh5OwbJ4IGGGGtR4EJtIbImFGwGGGfV1GR761GBtcGcxm3xdJX8smQy295kdsUQWihDFUi3vtQp2KYZm6sKR78yB2c7K9tMVWEQvgENX1knwwMAyXq-yfEkiAuje6vXkcoL10vazOzHLa0..",
    "isg": "BK2tf164uOvusFw-UnbzNOgYvEknCuHcQKF7OO-y6cSzZs0Yt1rxrPs4UCKAXfmU",
    "tfstk": "g1JIHw4EUy4Q6qiKyyoafOE1eFWWAckqNusJm3eU29Bdy8TMWBSr-DA52E-PwTl3aTsWzNJF83QzVF6HQByP82XW2EWSuqkq3HxhdT3qukZOKQBR2Y7-_6BsllGxuqkqQXEOF2g2YdSp_1IlWMI89an1BijAeMB8ec_OViV8JUB-fcsPm8U8pJFTBiSReaLRectOSg6RvUB-fhQG2byg-GyGSHiJSKj9MubBvNw8edhhOZtLa8eJCM1BxHQ60nJ1A6_ANu2_TpLw2pJhsfVNEhRXPQLog5XB2BBd0HDQCtKp_LswU0P5JhJ6Xp1_0--wbBX9pIZ8eh6CJEvdsyg1kpx9nOCZHmt9Ie-HC3r-eG8VWHvdFxncd9QdCGvrSJQW6QpFtT4Ku6xJ1FsCHguL3ZG6S7Z1i8s1uci_Z7joyT0wTeyGX6IGbYnsfSSC9Gj1uci_Z7fdjGR-fcNVA"
}

# sellercenter 端 UA 和 headers
SC_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "th,en-US;q=0.9,en;q=0.8",
    "bx-v": "2.5.36",
    "referer": f"https://sellercenter.lazada.{COUNTRY_DOMAIN}/ba/livemonitor",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}

# LazLive 端 headers
LIVE_HEADERS = {
    "accept": "application/json",
    "accept-language": "th,en-US;q=0.9,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded",
    "origin": f"https://live.lazada.{COUNTRY_DOMAIN}",
    "referer": f"https://live.lazada.{COUNTRY_DOMAIN}/",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
}

REGION_MAP = {
    'co.th': 'LAZADA_TH',
    'com.my': 'LAZADA_MY',
    'co.id': 'LAZADA_ID',
    'vn': 'LAZADA_VN',
    'sg': 'LAZADA_SG',
    'com.ph': 'LAZADA_PH',
}


# ============================================================
# 工具函数
# ============================================================

def _calc_mtop_sign(token: str, t: str, app_key: str, data: str) -> str:
    """计算 mtop 签名：md5(token & t & appKey & data)"""
    raw = f'{token}&{t}&{app_key}&{data}'
    return hashlib.md5(raw.encode()).hexdigest()


def _check_response(resp: requests.Response, is_mtop: bool = False) -> dict:
    """检查响应，判断登录态是否有效"""
    result = {"status_code": resp.status_code, "is_valid": False, "message": ""}

    if resp.status_code != 200:
        result["message"] = f"HTTP {resp.status_code}"
        return result

    try:
        data = resp.json()
    except Exception:
        result["message"] = "响应非 JSON"
        return result

    if is_mtop:
        ret = data.get("ret", [])
        if any("SUCCESS" in r for r in ret):
            result["is_valid"] = True
            result["message"] = "登录态有效"
        else:
            result["message"] = f"mtop 失败: {ret}"
    else:
        code = data.get("code")
        if code == 0:
            result["is_valid"] = True
            result["message"] = "登录态有效"
        else:
            result["message"] = f"BA 接口失败: code={code}, msg={data.get('msg', '')}"

    return result


def _test_cookie_keys(cookies: dict, send_fn, label: str):
    """通用的逐个剔除 cookie 测试逻辑

    Args:
        cookies: 全量 cookie 字典
        send_fn: 发送请求函数，接收 cookie 字典，返回 _check_response 的结果
        label: 端口名称（用于打印）
    """
    print("=" * 60)
    print(f"【{label} Cookie 活性测试】")
    print("=" * 60)

    # Step 1: 全量 cookie 基线测试
    print("\n[1] 全量 cookie 基线测试...")
    try:
        baseline = send_fn(cookies)
        print(f"    状态码: {baseline['status_code']}")
        print(f"    结果: {baseline['message']}")
    except Exception as e:
        print(f"    请求异常: {e}")
        return None

    if not baseline["is_valid"]:
        print(f"\n    ⚠ 全量 cookie 已失效，无法进行关键 cookie 测试")
        return None

    # Step 2: 逐个剔除
    print(f"\n[2] 逐个剔除 cookie 测试关键字段...")
    print("-" * 60)

    critical = []
    optional = []

    for key in list(cookies.keys()):
        if not cookies[key]:
            continue

        test_cookies = {k: v for k, v in cookies.items() if k != key}
        try:
            result = send_fn(test_cookies)
            if result["is_valid"]:
                optional.append(key)
                print(f"    {key:25s} -> 可选（去掉后仍正常）")
            else:
                critical.append(key)
                print(f"    {key:25s} -> 关键！（去掉后失败: {result['message']}）")
        except Exception as e:
            critical.append(key)
            print(f"    {key:25s} -> 关键！（去掉后异常: {e}）")

        time.sleep(0.5)

    # 汇总
    print("\n" + "=" * 60)
    print(f"【{label} 测试结果汇总】")
    print(f"  关键 cookie ({len(critical)}): {critical}")
    print(f"  可选 cookie ({len(optional)}): {optional}")
    print("=" * 60)

    return {"critical": critical, "optional": optional}


# ============================================================
# 测试函数
# ============================================================

def test_sellercenter_cookie_activity(cookies: dict = None, proxy: dict = None):
    """测试 sellercenter 端 cookie 活性

    测试接口：realtime/key/detailV2.json（BA 实时大屏数据，无需额外参数）
    """
    cookies = cookies or ALL_COOKIES
    proxy = proxy or PROXY
    url = (
        f"https://sellercenter.lazada.{COUNTRY_DOMAIN}"
        "/ba/sycm/lazada/faas/dashboard/key/overviewV2.json"
    )
    params = {
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}

    def _send(ck: dict) -> dict:
        resp = requests.get(url, headers=SC_HEADERS, cookies=ck,params=params, proxies=proxy, timeout=15)
        return _check_response(resp, is_mtop=False)

    return _test_cookie_keys(cookies, _send, "Sellercenter 端")


def test_marketing_center_cookie_activity(cookies: dict = None, proxy: dict = None):
    """测试营销中心接口 cookie 活性（接口 1.1 类型）

    测试接口：mtop.lazada.live.data.seller.metrics（GET，需要 mtop 签名）
    这些接口虽然属于 Sellercenter 营销中心，但走的是 acs-m 域名的 mtop 网关，
    需要 _m_h5_tk 签名，与 LazLive 接口类似。
    """
    cookies = cookies or ALL_COOKIES
    proxy = proxy or PROXY

    api = "mtop.lazada.live.data.seller.metrics"
    url = f"https://acs-m.lazada.{COUNTRY_DOMAIN}/h5/{api}/1.0/"
    region_id = REGION_MAP.get(COUNTRY_DOMAIN, 'LAZADA_TH')

    def _send(ck: dict) -> dict:
        # 构造请求数据（查询单日数据）
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        data_obj = {
            "period": "day",
            "dateRange": f"{yesterday}|{yesterday}"
        }
        data_str = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)

        # 计算 mtop 签名
        m_h5_tk = ck.get('_m_h5_tk', '')
        token = m_h5_tk.split('_')[0] if m_h5_tk else ''
        t = str(int(time.time() * 1000))
        sign = _calc_mtop_sign(token, t, '4272', data_str)

        params = {
            'jsv': '2.6.1',
            'appKey': '4272',
            't': t,
            'sign': sign,
            'v': '1.0',
            'timeout': '30000',
            'H5Request': 'true',
            'url': api,
            'x-i18n-language': 'en',
            'api': api,
            'type': 'originaljson',
            'dataType': 'json',
            'valueType': 'original',
            'x-i18n-regionID': region_id,
            'data': data_str,  # GET 请求，data 放在 query string
        }

        resp = requests.get(url, headers=LIVE_HEADERS, cookies=ck,
                            params=params, proxies=proxy, timeout=15)
        return _check_response(resp, is_mtop=True)

    return _test_cookie_keys(cookies, _send, "营销中心（mtop）")


def test_lazlive_cookie_activity(cookies: dict = None, proxy: dict = None):
    """测试 LazLive 端 cookie 活性

    测试接口：mtop.lazada.live.querylivesbystatus（POST，需要 mtop 签名）
    签名依赖 _m_h5_tk cookie，剔除该 cookie 时签名会失败，说明它是关键的。
    """
    cookies = cookies or ALL_COOKIES
    proxy = proxy or PROXY

    api = "mtop.lazada.live.querylivesbystatus"
    url = f"https://acs-m.lazada.{COUNTRY_DOMAIN}/h5/{api}/1.0/"
    region_id = REGION_MAP.get(COUNTRY_DOMAIN, 'LAZADA_TH')

    def _send(ck: dict) -> dict:
        # 每次请求都重新计算签名（因为 _m_h5_tk 可能被剔除）
        data_obj = {
            "_timezone": -7,
            "pageNum": 1,
            "pageSize": 10,
            "roomStatus": "Notice,Online,End,History",
            "orderByRoomStatus": "Notice,Online,End,History",
        }
        data_str = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)

        m_h5_tk = ck.get('_m_h5_tk', '')
        token = m_h5_tk.split('_')[0] if m_h5_tk else ''
        t = str(int(time.time() * 1000))
        sign = _calc_mtop_sign(token, t, '4272', data_str)

        params = {
            'jsv': '2.6.1',
            'appKey': '4272',
            't': t,
            'sign': sign,
            'v': '1.0',
            'timeout': '30000',
            'H5Request': 'true',
            'url': api,
            'type': 'originaljson',
            'method': 'POST',
            'api': api,
            'dataType': 'json',
            'valueType': 'original',
            'x-i18n-regionID': region_id,
        }
        post_data = {'data': data_str}

        resp = requests.post(url, headers=LIVE_HEADERS, cookies=ck,
                             params=params, data=post_data,
                             proxies=proxy, timeout=15)
        return _check_response(resp, is_mtop=True)

    return _test_cookie_keys(cookies, _send, "LazLive 端")


# ============================================================
# Cookie 刷新接口探测
# ============================================================

def discover_cookie_refresh_endpoints(cookies: dict = None, proxy: dict = None):
    """探测哪些 Lazada 接口会刷新（续命）关键 cookie

    原理：
        访问各种 Lazada 页面和 API 接口，抓取响应头中的 Set-Cookie，
        记录哪些接口会返回新的 JSID、lzd_sid、_m_h5_tk 等关键 cookie。

    返回：
        字典，key 为 cookie 名称，value 为会刷新该 cookie 的接口列表
    """
    cookies = cookies or ALL_COOKIES
    proxy = proxy or PROXY

    # 关键 cookie 列表（根据前面测试结果）
    critical_cookies = {
        "JSID",           # Sellercenter 端关键
        "lzd_sid",        # LazLive 端关键
        "_m_h5_tk",       # LazLive 端关键（mtop 签名）
        "_m_h5_tk_enc",   # LazLive 端关键
    }

    # 待测试的接口列表（页面 + API）
    test_targets = [
        # Sellercenter 主站页面
        {
            "name": "Sellercenter 首页",
            "url": f"https://sellercenter.lazada.{COUNTRY_DOMAIN}/",
            "method": "GET",
            "headers": SC_HEADERS,
        },
        {
            "name": "Sellercenter BA 实时大屏",
            "url": f"https://sellercenter.lazada.{COUNTRY_DOMAIN}/ba/livemonitor",
            "method": "GET",
            "headers": SC_HEADERS,
        },
        {
            "name": "Sellercenter BA Dashboard",
            "url": f"https://sellercenter.lazada.{COUNTRY_DOMAIN}/ba/dashboard",
            "method": "GET",
            "headers": SC_HEADERS,
        },
        # Sellercenter API 接口
        {
            "name": "BA realtime/key/detailV2",
            "url": (
                f"https://sellercenter.lazada.{COUNTRY_DOMAIN}"
                "/ba/sycm/lazada/faas/realtime/key/detailV2.json"
            ),
            "method": "GET",
            "headers": SC_HEADERS,
        },
        {
            "name": "BA dashboard/key/overviewV2",
            "url": (
                f"https://sellercenter.lazada.{COUNTRY_DOMAIN}"
                "/ba/sycm/lazada/faas/dashboard/key/overviewV2.json"
            ),
            "method": "GET",
            "headers": SC_HEADERS,
        },
        # LazLive 主站页面
        {
            "name": "LazLive 首页",
            "url": f"https://live.lazada.{COUNTRY_DOMAIN}/",
            "method": "GET",
            "headers": LIVE_HEADERS,
        },
        {
            "name": "LazLive 直播间列表页",
            "url": f"https://live.lazada.{COUNTRY_DOMAIN}/live/list",
            "method": "GET",
            "headers": LIVE_HEADERS,
        },
        # LazLive mtop 接口
        {
            "name": "mtop.lazada.live.querylivesbystatus",
            "url": f"https://acs-m.lazada.{COUNTRY_DOMAIN}/h5/mtop.lazada.live.querylivesbystatus/1.0/",
            "method": "POST",
            "headers": LIVE_HEADERS,
            "build_params": True,  # 需要动态构造 mtop 参数
        },
        {
            "name": "mtop.lazada.live.data.seller.metrics",
            "url": f"https://acs-m.lazada.{COUNTRY_DOMAIN}/h5/mtop.lazada.live.data.seller.metrics/1.0/",
            "method": "GET",
            "headers": LIVE_HEADERS,
            "build_params": True,
        },
    ]

    def _build_mtop_params(api_name: str, method: str):
        """构造 mtop 接口参数"""
        if "querylivesbystatus" in api_name:
            data_obj = {
                "_timezone": -7,
                "pageNum": 1,
                "pageSize": 10,
                "roomStatus": "Notice,Online,End,History",
                "orderByRoomStatus": "Notice,Online,End,History",
            }
        elif "seller.metrics" in api_name:
            data_obj = {"_timezone": -7}
        else:
            data_obj = {}

        data_str = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)
        m_h5_tk = cookies.get('_m_h5_tk', '')
        token = m_h5_tk.split('_')[0] if m_h5_tk else ''
        t = str(int(time.time() * 1000))
        sign = _calc_mtop_sign(token, t, '4272', data_str)

        region_id = REGION_MAP.get(COUNTRY_DOMAIN, 'LAZADA_TH')
        params = {
            'jsv': '2.6.1',
            'appKey': '4272',
            't': t,
            'sign': sign,
            'v': '1.0',
            'timeout': '30000',
            'H5Request': 'true',
            'url': api_name.split('/')[-1],
            'type': 'originaljson',
            'api': api_name.split('/')[-1],
            'dataType': 'json',
            'valueType': 'original',
            'x-i18n-regionID': region_id,
        }

        if method == "POST":
            params['method'] = 'POST'
            post_data = {'data': data_str}
            return params, post_data
        else:
            params['data'] = data_str
            return params, None

    print("=" * 70)
    print("【Lazada Cookie 刷新接口探测】")
    print("=" * 70)
    print(f"目标：找到会刷新关键 cookie 的接口")
    print(f"关键 cookie: {', '.join(critical_cookies)}\n")

    # 记录结果：{cookie_name: [endpoint_names]}
    refresh_map = {ck: [] for ck in critical_cookies}

    for idx, target in enumerate(test_targets, 1):
        name = target["name"]
        url = target["url"]
        method = target["method"]
        headers = target["headers"]

        print(f"[{idx}/{len(test_targets)}] 测试: {name}")
        print(f"    URL: {url[:80]}...")

        try:
            # 构造请求
            if target.get("build_params"):
                params, post_data = _build_mtop_params(target["name"], method)
                if method == "POST":
                    resp = requests.post(
                        url, headers=headers, cookies=cookies,
                        params=params, data=post_data,
                        proxies=proxy, timeout=15, allow_redirects=True
                    )
                else:
                    resp = requests.get(
                        url, headers=headers, cookies=cookies,
                        params=params, proxies=proxy, timeout=15, allow_redirects=True
                    )
            else:
                if method == "POST":
                    resp = requests.post(
                        url, headers=headers, cookies=cookies,
                        proxies=proxy, timeout=15, allow_redirects=True
                    )
                else:
                    resp = requests.get(
                        url, headers=headers, cookies=cookies,
                        proxies=proxy, timeout=15, allow_redirects=True
                    )

            # 检查响应头中的 Set-Cookie
            set_cookies = resp.headers.get("Set-Cookie", "")
            if not set_cookies:
                # 有些服务器用小写
                set_cookies = resp.headers.get("set-cookie", "")

            if set_cookies:
                # 解析 Set-Cookie（可能有多个，用逗号或分号分隔）
                # 简单处理：检查是否包含关键 cookie 名称
                found_cookies = []
                for ck_name in critical_cookies:
                    if ck_name in set_cookies:
                        found_cookies.append(ck_name)
                        refresh_map[ck_name].append(name)

                if found_cookies:
                    print(f"    ✓ 会刷新: {', '.join(found_cookies)}")
                else:
                    print(f"    - 有 Set-Cookie，但不包含关键 cookie")
            else:
                print(f"    - 无 Set-Cookie")

        except Exception as e:
            print(f"    ✗ 请求失败: {e}")

        time.sleep(0.5)  # 避免请求过快

    # 汇总结果
    print("\n" + "=" * 70)
    print("【探测结果汇总】")
    print("=" * 70)

    for ck_name in critical_cookies:
        endpoints = refresh_map[ck_name]
        if endpoints:
            print(f"\n{ck_name}:")
            for ep in endpoints:
                print(f"  - {ep}")
        else:
            print(f"\n{ck_name}: ⚠ 未找到会刷新该 cookie 的接口")

    print("\n" + "=" * 70)
    print("【使用建议】")
    print("=" * 70)
    print("1. 如果某个 cookie 有对应的刷新接口，定期调用该接口即可续命")
    print("2. 如果没有找到刷新接口，可能需要：")
    print("   - 访问更多页面（如用户中心、设置页等）")
    print("   - 模拟浏览器完整的登录流程")
    print("   - 使用 AdsPower 浏览器保持会话活跃")
    print("=" * 70)

    return refresh_map


# ============================================================
# Session 过期监控
# ============================================================

def monitor_session_expiry(
    sc_cookies: dict = None,
    live_cookies: dict = None,
    proxy: dict = None,
    interval_minutes: int = 30,
    max_hours: int = 24,
):
    """定时轮询监控 session 过期时间

    Args:
        sc_cookies: sellercenter 端关键 cookie（至少包含 JSID）
        live_cookies: LazLive 端关键 cookie（至少包含 lzd_sid, _m_h5_tk, _m_h5_tk_enc）
        proxy: 代理配置
        interval_minutes: 轮询间隔（分钟）
        max_hours: 最大监控时长（小时），超过后自动停止

    功能：
        - 每隔 interval_minutes 分钟探测一次两个端口
        - 记录时间戳和结果
        - 当任一端口失效时报告失效时间
        - 按 Ctrl+C 可随时停止
    """
    sc_cookies = sc_cookies or {"JSID": ALL_COOKIES.get("JSID", "")}
    live_cookies = live_cookies or {
        "lzd_sid": ALL_COOKIES.get("lzd_sid", ""),
        "_m_h5_tk": ALL_COOKIES.get("_m_h5_tk", ""),
        "_m_h5_tk_enc": ALL_COOKIES.get("_m_h5_tk_enc", ""),
    }
    proxy = proxy or PROXY

    # 构造请求函数
    sc_url = (
        f"https://sellercenter.lazada.{COUNTRY_DOMAIN}"
        "/ba/sycm/lazada/faas/dashboard/key/overviewV2.json"
    )
    params = {
        "dateRange": "2026-04-07|2026-04-07",
        "dateType": "day"
    }

    def _check_sc():
        try:
            resp = requests.get(sc_url, headers=SC_HEADERS, cookies=sc_cookies,params=params,
                                proxies=proxy, timeout=15)
            return _check_response(resp, is_mtop=False)
        except Exception as e:
            return {"status_code": 0, "is_valid": False, "message": f"异常: {e}"}

    api = "mtop.lazada.live.querylivesbystatus"
    live_url = f"https://acs-m.lazada.{COUNTRY_DOMAIN}/h5/{api}/1.0/"
    region_id = REGION_MAP.get(COUNTRY_DOMAIN, 'LAZADA_TH')

    def _check_live():
        try:
            data_obj = {
                "_timezone": -7,
                "pageNum": 1,
                "pageSize": 10,
                "roomStatus": "Notice,Online,End,History",
                "orderByRoomStatus": "Notice,Online,End,History",
            }
            data_str = json.dumps(data_obj, separators=(',', ':'), ensure_ascii=False)

            m_h5_tk = live_cookies.get('_m_h5_tk', '')
            token = m_h5_tk.split('_')[0] if m_h5_tk else ''
            t = str(int(time.time() * 1000))
            sign = _calc_mtop_sign(token, t, '4272', data_str)

            params = {
                'jsv': '2.6.1',
                'appKey': '4272',
                't': t,
                'sign': sign,
                'v': '1.0',
                'timeout': '30000',
                'H5Request': 'true',
                'url': api,
                'type': 'originaljson',
                'method': 'POST',
                'api': api,
                'dataType': 'json',
                'valueType': 'original',
                'x-i18n-regionID': region_id,
            }
            post_data = {'data': data_str}

            resp = requests.post(live_url, headers=LIVE_HEADERS, cookies=live_cookies,
                                 params=params, data=post_data,
                                 proxies=proxy, timeout=15)
            return _check_response(resp, is_mtop=True)
        except Exception as e:
            return {"status_code": 0, "is_valid": False, "message": f"异常: {e}"}

    # 开始监控
    print("=" * 70)
    print("【Lazada Session 过期监控】")
    print("=" * 70)
    print(f"轮询间隔: {interval_minutes} 分钟")
    print(f"最大监控时长: {max_hours} 小时")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("按 Ctrl+C 停止监控\n")

    start_time = time.time()
    max_duration = max_hours * 3600
    interval_seconds = interval_minutes * 60
    check_count = 0

    sc_expired = False
    live_expired = False
    sc_expire_time = None
    live_expire_time = None

    try:
        while True:
            check_count += 1
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elapsed = (time.time() - start_time) / 3600

            print(f"[检查 #{check_count}] {now} (已运行 {elapsed:.1f} 小时)")

            # 检查 sellercenter
            if not sc_expired:
                sc_result = _check_sc()
                if sc_result["is_valid"]:
                    print(f"  ✓ Sellercenter: 正常 (HTTP {sc_result['status_code']})")
                else:
                    sc_expired = True
                    sc_expire_time = now
                    print(f"  ✗ Sellercenter: 失效！{sc_result['message']}")
            else:
                print(f"  - Sellercenter: 已失效（于 {sc_expire_time}）")

            # 检查 LazLive
            if not live_expired:
                live_result = _check_live()
                if live_result["is_valid"]:
                    print(f"  ✓ LazLive: 正常 (HTTP {live_result['status_code']})")
                else:
                    live_expired = True
                    live_expire_time = now
                    print(f"  ✗ LazLive: 失效！{live_result['message']}")
            else:
                print(f"  - LazLive: 已失效（于 {live_expire_time}）")

            # 如果两个都失效了，停止监控
            if sc_expired and live_expired:
                print("\n" + "=" * 70)
                print("【监控结束：两个端口均已失效】")
                print(f"  Sellercenter 失效时间: {sc_expire_time}")
                print(f"  LazLive 失效时间: {live_expire_time}")
                print("=" * 70)
                break

            # 检查是否超过最大监控时长
            if time.time() - start_time > max_duration:
                print("\n" + "=" * 70)
                print(f"【监控结束：已达到最大监控时长 {max_hours} 小时】")
                if not sc_expired:
                    print("  Sellercenter: 仍然有效")
                if not live_expired:
                    print("  LazLive: 仍然有效")
                print("=" * 70)
                break

            # 等待下一次检查
            print(f"  下次检查: {interval_minutes} 分钟后\n")
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("【监控已手动停止】")
        print(f"运行时长: {(time.time() - start_time) / 3600:.1f} 小时")
        if sc_expired:
            print(f"  Sellercenter 失效时间: {sc_expire_time}")
        else:
            print("  Sellercenter: 监控期间一直有效")
        if live_expired:
            print(f"  LazLive 失效时间: {live_expire_time}")
        else:
            print("  LazLive: 监控期间一直有效")
        print("=" * 70)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "monitor":
            # 监控模式：python lazda_cookie_activity.py monitor [间隔分钟] [最大小时]
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            max_hours = int(sys.argv[3]) if len(sys.argv) > 3 else 24

            # 只使用关键 cookie
            sc_critical = {"JSID": ALL_COOKIES.get("JSID", "")}
            live_critical = {
                "lzd_sid": ALL_COOKIES.get("lzd_sid", ""),
                "_m_h5_tk": ALL_COOKIES.get("_m_h5_tk", ""),
                "_m_h5_tk_enc": ALL_COOKIES.get("_m_h5_tk_enc", ""),
            }

            monitor_session_expiry(
                sc_cookies=sc_critical,
                live_cookies=live_critical,
                interval_minutes=interval,
                max_hours=max_hours,
            )

        elif mode == "discover":
            # 探测模式：python lazda_cookie_activity.py discover
            print("提示：此模式会访问多个 Lazada 页面和接口，请确保 cookie 有效\n")
            discover_cookie_refresh_endpoints()

        elif mode == "marketing":
            # 营销中心单独测试：python lazda_cookie_activity.py marketing
            print("Lazada 营销中心接口 Cookie 活性测试")
            print("请确保已填入有效的 cookie 和代理信息\n")
            marketing_result = test_marketing_center_cookie_activity()

        else:
            print(f"未知模式: {mode}")
            print("可用模式：")
            print("  - 默认（无参数）：测试 cookie 活性")
            print("  - monitor [间隔分钟] [最大小时]：监控 session 过期")
            print("  - discover：探测哪些接口会刷新 cookie")

    else:
        # 默认模式：测试 cookie 活性
        print("Lazada Cookie 活性测试")
        print("请确保已填入有效的 cookie 和代理信息\n")
        print("可用模式：")
        print("  - python lazda_cookie_activity.py           # 测试所有接口 cookie 活性")
        print("  - python lazda_cookie_activity.py monitor   # 监控 session 过期")
        print("  - python lazda_cookie_activity.py discover  # 探测刷新接口")
        print("  - python lazda_cookie_activity.py marketing # 单独测试营销中心接口\n")

        # 测试三组接口
        sc_result = test_sellercenter_cookie_activity()
        print("\n\n")
        marketing_result = test_marketing_center_cookie_activity()
        print("\n\n")
        live_result = test_lazlive_cookie_activity()
