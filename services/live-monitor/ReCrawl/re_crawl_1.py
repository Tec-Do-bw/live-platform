#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/10/23 下午7:54
# @Author     : XBW
# @File       : re_crawl_1.py
# @Description: 重采（1：直播趋势数据,2:直播回放数据）
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from utils.logger import Logings
Logings.file_level = 'DEBUG'
logger = Logings('re_crawl').get_logger()
import pymysql
import requests
import json
import time
from datetime import datetime,timedelta
from utils.serverTool import fetch_apollo_config



# 获取需要重采的数据及对应的最新cookie信息
def get_live_data_cookies_with_show_codes(db_config):
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 获取近10天的日期范围用于cookies查询
                date_conditions = []
                for i in range(10):
                    date = (datetime.today() - timedelta(days=i)).strftime('%Y-%m-%d')
                    date_conditions.append(f"`timesTamp` LIKE '%{date}%'")
                date_condition_sql = " OR ".join(date_conditions)

                # 关联查询：需要重采的数据 + 最新的cookie信息
                getLiveChectsql = f"""
SELECT 
    final.CJ_user_id,
    final.media_user_id,
    final.show_codes_by_type,
    final.data_type,
    final.cookies,
    final.requests,
    final.api_name
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY CJ_user_id, data_type ORDER BY `timesTamp` DESC) AS k
    FROM (
        SELECT DISTINCT
            map.cj_user_id AS CJ_user_id,
            uncol.media_user_id,
            uncol.show_codes AS show_codes_by_type,
            uncol.data_type,
            acc.cookies,
            acc.requests,
            acc.api_name,
            acc.timesTamp
        FROM (
            -- 需要重采的数据（按media_user_id和data_type分组，分别聚合show_code）
            SELECT
                media_user_id,
                data_type,
                GROUP_CONCAT(DISTINCT show_code) AS show_codes
            FROM
                uncollected_data_records
            WHERE
                local_status = 1 
                AND platform = 'tiktok'
            GROUP BY
                media_user_id,
                data_type
        ) uncol
        INNER JOIN live_tiktok_media_user_id_mapping map
            ON uncol.media_user_id COLLATE utf8mb4_general_ci = map.media_user_id COLLATE utf8mb4_general_ci
        INNER JOIN live_account_data_info acc
            ON map.cj_user_id COLLATE utf8mb4_general_ci = acc.CJ_user_id COLLATE utf8mb4_general_ci
        WHERE
            ({date_condition_sql})
            AND LENGTH(acc.cookies) > 5
            AND LENGTH(acc.CJ_user_id) > 0
            AND acc.requests NOT LIKE '%98001002%'
            AND acc.cookies LIKE '%sessionid%'
    ) a
) final
WHERE 
    final.k = 1
    AND final.cookies LIKE '%sessionid%'
                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()
                print(f"从数据库查询到 {len(result)} 条需要重采的数据（含cookie和show_codes）")
                return result
        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
        return []


# 获取满足条件的media_user_id与插件ID的关系
def get_media_user_id(db_config, num=2):
    # 强制取最近3天的场次ID
    if int(num) < 2:
        num = 2
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 获取满足条件的media_user_id与插件ID的关系
                getLiveChectsql = f"""
                    SELECT e.*,d.CJ_User_id,DATE_FORMAT(
                    CONVERT_TZ(
                        FROM_UNIXTIME(e.updateTime),
                        'UTC',
                        'Asia/Shanghai'
                    ),
                    '%Y-%m-%d %H:%i:%s'
                ) AS beijing_datetime
            FROM (select * from live.live_show_info where CAST(updateTime as SIGNED) >UNIX_TIMESTAMP() - 86400 * {num})  e
            LEFT JOIN (
                SELECT room_id, CJ_User_id, media_user_id 
                FROM (
                    SELECT 
                        a.room_id,
                        a.CJ_User_id,
                        b.media_user_id 
                    FROM (
                        SELECT * 
                        FROM live_streaming_gmv_data 
                        WHERE local_status = 1 
                        AND platform = 'tiktok'
                    ) a
                    LEFT JOIN live_streaming_room b 
                        ON a.room_id = b.room_id 
                        AND b.local_status = 1
                ) c 
                WHERE LENGTH(c.CJ_User_id) > 0
            ) d 
            ON e.media_user_id = d.media_user_id  COLLATE utf8mb4_general_ci 
                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
        return []


# userID_CJID_mediaUser_id 映射关系
def get_user_id_mapping(db_config):
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 获取满足条件的media_user_id与插件ID的关系
                mappingSql = """select media_user_id,user_id,cj_user_id from  live_tiktok_media_user_id_mapping"""
                cursor.execute(mappingSql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
        return []


# 构造映射关系
def mapping_info_func(mapping_info):
    mapping_info_dict = {}
    for i in mapping_info:
        mapping_info_dict[i["media_user_id"]] = i["user_id"]
        mapping_info_dict[i["user_id"]] = i["media_user_id"]
    return mapping_info_dict


# 清洗参数（简化版：直接使用SQL关联后的数据）
def getCrawlIds(db_config):
    mapping_info = get_user_id_mapping(db_config)
    mapping_info_dict = mapping_info_func(mapping_info)
    
    # 直接获取关联好的数据（已包含show_codes和cookies）
    Sql_data = get_live_data_cookies_with_show_codes(db_config)
    
    argsList = list()
    for data in Sql_data:
        try:
            cookiesInit = json.loads(data["cookies"])
            responseInit = json.loads(data["requests"])
            CJ_user_id = data["CJ_user_id"]
            media_user_id = data["media_user_id"]  # SQL已返回
            show_codes = data["show_codes_by_type"]  # SQL已返回
            data_type = data["data_type"]  # SQL已返回

            responseInit_json = json.loads(responseInit.get("response"))
            ctData = responseInit_json.get("data", "")
            
            # 提取 user_id 和 user_name
            if "creator_id" in str(ctData):
                user_id = mapping_info_dict.get(media_user_id, "")
                user_name = ""
            else:
                user_id = ctData.get("user_id", "")
                user_name = ctData.get("user_name", "")
            
            # 提取 cookies
            msToken = ""
            sessionid = ""
            for i_1 in cookiesInit:
                if i_1["name"] == "msToken":
                    msToken = i_1["value"]
                if i_1["name"] == "sessionid":
                    sessionid = i_1["value"]
                if msToken and sessionid:
                    break
            
            # 构建返回数据
            if sessionid:
                argsList.append({
                    "CJ_user_id": CJ_user_id,
                    "user_id": user_id,
                    "media_user_id": media_user_id,
                    "user_name": user_name,
                    "msToken": msToken,
                    "sessionid": sessionid,
                    "api_name": data["api_name"],
                    "show_codes": show_codes,  # 来自SQL直接返回
                    "data_type": data_type,  # 来自SQL直接返回（1:直播趋势, 2:直播回放）
                    "full_cookies": cookiesInit
                })
        except Exception as e:
            print(f"解析数据出错: {e}, 跳过该条数据")
            continue
    
    print(f"成功解析的数据数量: {len(argsList)}")
    return argsList

# ✅ ✅ ✅ ✅ 模拟请求映射与清洗相关-start ✅ ✅ ✅ ✅ ✅
# 上传数据到后端
def upload_data(CJ_user_id, requestContent, cookies_dict=None):
    """上传数据到后端"""
    # 从requestContent中提取cookies信息，如果没有则使用默认值
    if cookies_dict is None and "init_account_info" in requestContent.get("extra", {}):
        cookies_dict = requestContent["extra"]["init_account_info"].get("cookies", {})

    # 将cookies字典转换为字符串格式
    if isinstance(cookies_dict, (dict,list)):
        cookies_str = json.dumps(cookies_dict)
    else:
        cookies_str = "requestsSpider"

    body = {
        "params": requestContent["params"],
        "cookies": cookies_str,
        "fromUrl": requestContent["url"],
        "extra": json.dumps(requestContent["extra"]),
        "sign": "8K38u50d4c9c2c7ba8efc59689uhd",
        "userType": 88,
        "updateTime": int(time.time() * 1000),
        "request": {"response": requestContent["response"], "url": requestContent["url"]},
        "socketUserId": CJ_user_id,
    };

    logger.debug('body-->%s'%body)
    post_url = "https://www.livelabstar.com/live/v1.0/data/info/send"

    headers = {
        "accessToken": "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF",
        "Content-Type": "application/json"
    }

    # 发送 POST 请求
    response = requests.post(
        url=post_url,
        headers=headers,
        json=body
    )

    # 打印响应状态码和内容（原JS中没有处理响应，这里添加基础处理）
    logger.success(f"响应状态码提交自己网站: {response.status_code}")




# 直播间详情-内容分析-直播趋势
def get_live_chart(init_account_info,room_id):
    cookies = init_account_info.get("cookies")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Pragma': 'no-cache',
        'Referer': f'https://shop.tiktok.com/streamer/compass/livestream-analytics/view/detail?roomId={room_id}',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'request-start-time': '1758185768966',
        'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }

    json_data = {
        'request': {
            'room_filter': {
                'room_id': room_id,
                'query_online': False,
            },
            'stats_types': [
                3,
                20,
                341,
                21,
                22,
                12,
                16,
                23,
                50,
                51,
                40,
            ],
            'granularity': 1,
        },
    }

    response = requests.post(
        'https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F140.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        cookies=cookies,
        headers=headers,
        json=json_data,
    )

    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F140.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_live_replay(init_account_info):
    cookies = init_account_info.get("cookies")
    headers = {
        'accept': '*/*',
        'accept-language': 'zh-CN,zh;q=0.9',
        'cache-control': 'no-cache',
        'origin': 'https://livecenter.tiktok.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://livecenter.tiktok.com/',
        'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    }
    json_data = {
        'aid': "304449",
        'app_name': 'tiktok_live_center',
        'count': '20',
        'device_platform': 'web_pc',
        'need_suffix': 'True',
        'offset': '0',
        'webcast_language': 'zh-tw',
    }
    response = requests.get('https://webcast.tiktok.com/webcast/room/replay/info/', params=json_data, cookies=cookies,
                            headers=headers, timeout=15)

    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://webcast.tiktok.com/webcast/room/replay/info/',
        "params": json_data,
        "extra": json_data
    }
    return requestContent



def run(db_config):
    items = getCrawlIds(db_config)
    # print(items)
    # sys.exit(0)
    # with open('1.json', 'r', encoding='utf-8') as f:
    #     items = json.load(f)
    for node in items:
        sessionid = node.get("sessionid","")
        if not sessionid:
            print("没有获取到sessionid--->",node)
            continue
        msToken = node["msToken"]
        full_cookies = node.get("full_cookies")
        # 根据 data_type 进行不同的处理
        if node['data_type'] == 2:
            init_account_info = {
                "cookies": {
                    'sessionid': sessionid,
                    'msToken': msToken
                },
                "user_id": node["user_id"],
                "user_name": node["user_name"]
            }
            # data_type = 2: 直播回放数据
            try:
                requestContent = get_live_replay(init_account_info)
            except Exception as e:
                print("error-->", e)
                requestContent = "0"

            upload_data(node["CJ_user_id"], requestContent, cookies_dict=full_cookies)
            logger.info(f"requestContent直播录像数据-->数据上报成功{node['media_user_id']}")
            
        elif node['data_type'] == 1:
            init_account_info = {
                "cookies": {
                    'sessionid': sessionid,
                    'msToken': msToken
                },
                "CJ_user_id": node["CJ_user_id"]
            }
            # data_type = 1: 直播趋势数据（需要按 show_code 循环采集）
            for show_code in node['show_codes'].split(","):
                init_account_info["room_id"] = show_code
                # 直播间详情-内容分析-直播趋势
                try:
                    requestContent = get_live_chart(init_account_info, show_code)
                except Exception as e:
                    print("error-->", e)
                    requestContent = "0"
                upload_data(node["CJ_user_id"], requestContent, cookies_dict=full_cookies)
                time.sleep(5)
                logger.info(f"requestContent直播间详情-内容分析-直播趋势 数据上报成功--->{node['media_user_id']}\t{show_code}")
        else:
            print("没有匹配到数据类型--->", node)
        
        time.sleep(5)
    print('数据补采完成')







if __name__ == '__main__':
    istest = 0
    config_data = fetch_apollo_config(istest)
    # 数据库连接配置
    db_config = {
        'host': config_data["devSqlHost"],
        'port': int(config_data["devSqlPort"]),
        'user': config_data["devSqlUser"],
        'password': config_data["devSqlPassword"],
        'database': config_data['database'],
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
    run(db_config)