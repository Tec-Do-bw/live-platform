"""
定时调度任务 - 从 webSoctket/ALLSpider_Paidaxing.py 迁移
包含所有的T+1数据与GMV面板采集与模拟请求数据采集
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
from collections import defaultdict
from pathlib import Path
import pymysql
import requests
import json
import time
import asyncio
import websockets
from datetime import datetime, timedelta
from utils.logger import Logings


logger = Logings('mainSpider_requests').get_logger()

import psycopg

class HologresClient:
    """Hologres数据库客户端"""
    def __init__(self, host, port, dbname, user, password):
        if psycopg is None:
            raise ImportError("请先安装 psycopg: pip install psycopg")
        
        self.conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            keepalives=1,
            keepalives_idle=10,
            keepalives_interval=10,
            keepalives_count=5
        )

    def execute_sql_query(self, sql: str):
        """
        执行SQL查询并返回结果
        @param sql: 要执行的SQL查询语句
        @return: 查询结果列表
        """
        cur = self.conn.cursor()
        cur.execute(sql)
        if sql.find("select") != -1:
            result = cur.fetchall()
        else:
            self.conn.commit()
            result = 0
        cur.close()
        return result
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()


class WebSocketClient:
    """WebSocket客户端 - 用于与插件通信"""
    
    def __init__(self, user_id: str, url: str = 'ws://127.0.0.1:8081/ws/'):
        self.user_id = user_id
        self.uri = f"{url}{user_id}"
        self.websocket = None
        self.connected = False
        self.last_connect_time = 0
        self.reconnect_delay = 5  # 重连延迟（秒）

    async def connect(self):
        if self.connected:
            return True

        current_time = time.time()
        if current_time - self.last_connect_time < self.reconnect_delay:
            return False

        try:
            self.websocket = await websockets.connect(self.uri)
            self.connected = True
            self.last_connect_time = current_time
            logger.info(f"已连接到服务器用户ID: {self.user_id}")
            print(f"已连接到服务器用户ID: {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            print(f"连接失败: {e}")
            self.connected = False
            return False

    async def send_message(self, target_user_id: str, message):
        if not self.connected:
            if not await self.connect():
                logger.error("无法发送消息：未连接到服务器")
                print("无法发送消息：未连接到服务器")
                return

        try:
            if isinstance(message, dict) and "url" in message and "method" in message:
                message_data = {
                    **message,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "target_user_id": target_user_id
                }
                logger.info(f"发送API配置给用户 {target_user_id}: {message.get('url', 'unknown')}")
                print(f"发送API配置给用户 {target_user_id}: {message.get('url', 'unknown')}")
            elif isinstance(message, str):
                message_data = {
                    "url": message,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "target_user_id": target_user_id
                }
                logger.info(f"发送URL消息给用户 {target_user_id}: {message}")
                print(f"发送URL消息给用户 {target_user_id}: {message}")
            else:
                logger.warning(f"不支持的消息格式: {type(message)}")
                return

            await self.websocket.send(json.dumps(message_data, ensure_ascii=False))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            print(f"发送消息失败: {e}")
            self.connected = False

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("WebSocket连接已关闭")
            print("连接已关闭")


def group_messages_by_target(messages):
    """按target_id分组消息"""
    api_groups = defaultdict(list)
    values_groups = defaultdict(list)
    
    for msg in messages:
        target_id = msg["target_id"]
        if "api_config" in msg:
            api_groups[target_id].append(msg["api_config"])
        elif "values" in msg and isinstance(msg["values"], list):
            values_groups[target_id].extend(msg["values"])
        else:
            logger.warning(f"未知消息格式: {msg}")
            print(f"未知消息格式: {msg}")
    
    return dict(api_groups), dict(values_groups)


async def send_messages_for_target(client, target_id, api_configs, values, sleep_time):
    """为单个target_id发送消息"""
    for api_config in api_configs:
        await client.send_message(target_id, api_config)
        print(f"已发送API配置给 {target_id}, 等待{sleep_time}秒...")
        await asyncio.sleep(sleep_time)
    
    for value in values:
        await client.send_message(target_id, value)
        print(f"已发送消息给 {target_id}, 等待{sleep_time}秒...")
        await asyncio.sleep(sleep_time)


async def mainT1_GMV(messages, sleep_time=10):
    """通过WebSocket将消息发送给所有插件"""
    sender_id = "paidaxing"
    client = WebSocketClient(sender_id)
    
    try:
        if not await client.connect():
            logger.error("无法连接到WebSocket服务器")
            return
            
        api_groups, values_groups = group_messages_by_target(messages)
        all_targets = set(api_groups.keys()) | set(values_groups.keys())
        
        tasks = [
            asyncio.create_task(send_messages_for_target(
                client, target_id,
                api_groups.get(target_id, []),
                values_groups.get(target_id, []),
                sleep_time
            )) for target_id in all_targets
        ]
        
        await asyncio.gather(*tasks)
        logger.info("所有消息已发送完毕")
        print("所有消息已发送完毕")
        
    finally:
        await client.close()


def get_live_data_gmv(db_config, holo_db_config):
    """获取正在直播的直播间数据，并从Holo获取user_type"""
    mysql_result = []
    holo_client = None
    
    try:
        # 第一步：从MySQL获取直播间数据
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                sql = """
                select room_id,show_code,CJ_User_id from (
                select c.*,d.CJ_User_id FROM(
                select a.*,b.platform from (
                SELECT room_id,show_code from live_streaming_room_data where CAST(video_last_time AS SIGNED) > (UNIX_TIMESTAMP() - 300)) a
                left join live_streaming_room b 
                on 
                a.room_id = b.room_id and b.platform='tiktok'
                ) c
                left join 
                (SELECT room_id,room_name,CJ_User_id,room_url FROM live_streaming_gmv_data WHERE local_status = 1 and LENGTH(CJ_User_id)>0) d
                on c.room_id = d.room_id ) e where LENGTH(CJ_User_id)>0
                """
                cursor.execute(sql)
                mysql_result = cursor.fetchall()
        finally:
            connection.close()
        
        # 第二步：创建Holo客户端并获取user_type
        if mysql_result:
            try:
                holo_client = HologresClient(
                    host=holo_db_config['host'],
                    port=holo_db_config['port'],
                    dbname=holo_db_config['dbname'],
                    user=holo_db_config['user'],
                    password=holo_db_config['password']
                )
                logger.info("✅ Holo数据库连接成功")
                
                # 调用enrich函数添加user_type
                enriched_data = enrich_live_data_with_user_type(mysql_result, holo_client)
                return enriched_data
                
            except Exception as e:
                logger.error(f"Holo数据库连接或查询失败: {e}")
                # Holo查询失败，返回MySQL原始数据（不含user_type）
                logger.warning("将返回不含user_type的原始数据")
                return mysql_result
            finally:
                if holo_client:
                    try:
                        holo_client.close()
                    except:
                        pass
        
        return mysql_result
        
    except Exception as e:
        logger.error(f"获取直播间数据失败: {e}")
        print(f"数据库连接或查询出错: {e}")
        return []


def get_user_type_mapping(cj_user_ids, holo_client):
    """从Holo数据库获取CJ_User_id对应的user_type映射"""
    if not cj_user_ids:
        return {}
    
    try:
        # 构建IN查询条件
        cj_ids_str = "','".join(cj_user_ids)
        sql = f"""
        select socketuserid, user_type from (
            select socketuserid, user_type, 
                   row_number() over(partition by socketuserid order by update_time desc) as rn
            from ods_kafka_streamer_relate_data 
            where socketuserid in ('{cj_ids_str}') 
            and socketuserid != ''
        ) t where rn = 1
        """
        result = holo_client.execute_sql_query(sql)
        
        # 构建映射字典
        user_type_map = {}
        for row in result:
            user_type_map[row[0]] = row[1]
        
        return user_type_map
    except Exception as e:
        logger.error(f"从Holo获取user_type失败: {e}")
        return {}


def enrich_live_data_with_user_type(live_data, holo_client):
    """为直播间数据添加user_type字段"""
    if not live_data:
        return []
    
    # 提取所有CJ_User_id
    cj_user_ids = [row['CJ_User_id'] for row in live_data]
    
    # 获取user_type映射
    user_type_map = get_user_type_mapping(cj_user_ids, holo_client)
    
    # 添加user_type到结果中
    enriched_data = []
    for row in live_data:
        room_id = row['room_id']
        show_code = row['show_code']
        cj_user_id = row.get('CJ_User_id')
        user_type = user_type_map.get(cj_user_id, "unknown")  # 默认值为unknown
        enriched_data.append({
            "room_id": room_id,
            "show_code": show_code,
            "CJ_User_id": cj_user_id,
            "user_type": user_type
        })
    
    return enriched_data


def mainSpider_gmv(db_config, holo_db_config, istest=1):
    """GMV实时采集"""
    logger.info("🚀 GMV实时采集任务启动")
    
    messages = []
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "OfflineSpider", "config.json")
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"读取GMV配置失败: {e}")
        return
    
    if istest == 1:
        show_code = 7560603732498762516
        for item in config.get("GMV", []):
            for data_template in item.get("data_templates", []):
                api_config = {
                    "url": f'https://shop.tiktok.com/{item["endpoint"]}',
                    "method": item["method"],
                    "data": json.dumps(data_template).replace("PLACEHOLDER_ROOM_ID", str(show_code)),
                    "Referer": f'https://shop.tiktok.com/workbench/live/overview?room_id={show_code}',
                }
                messages.append({
                    "target_id": 'mZz6isdc',
                    "api_config": api_config
                })
    else:
        live_streaming_room_data = get_live_data_gmv(db_config, holo_db_config)
        for roomDict in live_streaming_room_data:
            show_code = roomDict['show_code']
            cj_user_id = roomDict['CJ_User_id']
            user_type = roomDict.get('user_type', 'unknown')
            if user_type != 'unknown' and int(user_type) == 6.0: #这里有些是等于88 fuck
                for item in config.get("GMV", []):
                    for data_template in item.get("data_templates", []):
                        api_config = {
                            "url": f'https://shop.tiktok.com/{item["endpoint"]}',
                            "method": item["method"],
                            "data": json.dumps(data_template).replace("PLACEHOLDER_ROOM_ID", str(show_code)),
                            "Referer": f'https://shop.tiktok.com/workbench/live/overview?room_id={show_code}',
                        }
                        messages.append({
                            "target_id": cj_user_id,
                            "api_config": api_config
                        })
            else:
                for roomDict in live_streaming_room_data:
                    liveUrl = "https://shop.tiktok.com/workbench/live/overview?room_id="+roomDict['show_code']
                    messages.append({"target_id": roomDict['CJ_User_id'], "values": [liveUrl]})

    logger.info(f"GMV采集消息总数: {len(messages)}")
    asyncio.run(mainT1_GMV(messages, sleep_time=random.randint(10, 15)))
    logger.info("✅ GMV实时采集任务完成")


def get_live_data_cookies(db_config):
    """获取近两天的cookie"""
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                today = datetime.today()
                yesterday = today - timedelta(days=1)
                today_formatted = today.strftime('%Y-%m-%d')
                yesterday_formatted = yesterday.strftime('%Y-%m-%d')
                day_before_yesterday = today - timedelta(days=2)
                day_before_yesterday_formatted = day_before_yesterday.strftime('%Y-%m-%d')

                getLiveChectsql = f"""
                    select CJ_user_id,cookies,requests,api_name from(
                        select *,ROW_NUMBER() over(PARTITION by CJ_user_id  order by  `timesTamp` desc) k from 
                        (select CJ_user_id,cookies,requests,timesTamp,api_name from 
                        live_account_data_info 
                        where  (`timesTamp` like '%{today_formatted}%' or `timesTamp` like '%{yesterday_formatted}%' or `timesTamp` like '%{day_before_yesterday_formatted}%')
                        and length(cookies)>5 and  LENGTH(cj_user_id)>0  and requests not like '%98001002%'  and cookies like '%sessionid%') a
                        ) b where k=1 and cookies like '%sessionid%'
                """
                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        logger.error(f"获取cookie数据失败: {e}")
        return []


def get_media_user_id(db_config, num=2):
    """获取满足条件的media_user_id与插件ID的关系"""
    if int(num) < 2:
        num = 2
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
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
        logger.error(f"获取media_user_id失败: {e}")
        return []


def get_user_id_mapping(db_config):
    """userID_CJID_mediaUser_id 映射关系"""
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                mappingSql = """select media_user_id,user_id,cj_user_id from  live_tiktok_media_user_id_mapping"""
                cursor.execute(mappingSql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        logger.error(f"获取用户映射失败: {e}")
        return []


def mapping_info_func(mapping_info):
    """构造映射关系"""
    mapping_info_dict = {}
    for i in mapping_info:
        mapping_info_dict[i["media_user_id"]] = i["user_id"]
    return mapping_info_dict


def getArgs2(db_config):
    """清洗参数"""
    mapping_info = get_user_id_mapping(db_config)
    mapping_info_dict = mapping_info_func(mapping_info)
    Sql_data = get_live_data_cookies(db_config)
    argsList = list()
    cj_IDList = []
    
    for data in Sql_data:
        tmp_Ck = {}
        try:
            cookiesInit = json.loads(data["cookies"])
            responseInit = json.loads(data["requests"])
            CJ_user_id = data["CJ_user_id"]

            responseInit_json = json.loads(responseInit.get("response"))
            ctData = responseInit_json.get("data", "")
            
            if "creator_id" in str(ctData):
                creator_id = ctData.get("segments")[0].get("filter").get("creator_id", "")
                tmp_Ck["user_id"] = mapping_info_dict.get(creator_id)
                tmp_Ck["user_name"] = ""
            else:
                tmp_Ck["user_id"] = ctData.get("user_id", "")
                tmp_Ck["user_name"] = ctData.get("user_name", "")
            tmp_Ck["api_name"] = data["api_name"]
            tmp_Ck["CJ_user_id"] = CJ_user_id
        except:
            continue
            
        for i_1 in cookiesInit:
            if i_1["name"] == "msToken":
                tmp_Ck["msToken"] = i_1["value"]
            if i_1["name"] == "sessionid":
                tmp_Ck["sessionid"] = i_1["value"]
            if "sessionid" in tmp_Ck.keys() and "msToken" in tmp_Ck.keys():
                break
        
        tmp_Ck["full_cookies"] = cookiesInit

        if tmp_Ck["CJ_user_id"] not in cj_IDList:
            cj_IDList.append(tmp_Ck["CJ_user_id"])
            argsList.append(tmp_Ck)
    return argsList


def upload_data(CJ_user_id, requestContent, cookies_dict=None):
    """上传数据到后端"""
    # 从requestContent中提取cookies信息，如果没有则使用默认值
    if cookies_dict is None and "init_account_info" in requestContent.get("extra", {}):
        cookies_dict = requestContent["extra"]["init_account_info"].get("cookies", {})
    
    # 将cookies字典转换为字符串格式
    if isinstance(cookies_dict, (dict, list)):
        cookies_str = json.dumps(cookies_dict)
    else:
        cookies_str = "requestsSpider"
    logger.info(f"上传ck数据到后端,内容为: {cookies_str}")
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
    }

    post_url = "https://www.livelabstar.com/live/v1.0/data/info/send"
    headers = {
        "accessToken": "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF",
        "Content-Type": "application/json"
    }

    response = requests.post(url=post_url, headers=headers, json=body)
    print(f"响应状态码提交自己网站: {response.status_code}")
    print(f"响应内容交自己网站: {response.text}")


def get_prams_time(num=1):
    """获取时间参数列表"""
    from datetime import timezone
    tz_offset = timezone(timedelta(hours=8))
    result = []

    for i in range(1, num + 1):
        today = datetime.now(tz_offset)
        target_date = today - timedelta(days=i)
        target_datetime = target_date.replace(hour=8, minute=0, second=0, microsecond=0)
        timestamp = int(target_datetime.timestamp())
        result.append({
            'start_time': str(timestamp - 86400),
            'end_time': str(timestamp + 86400),
            'target_date': target_date.strftime('%Y-%m-%d')
        })
    return result


def generate_date_list(num):
    """根据num数量生成日期列表，从当前日期往前推"""
    data_list = []
    today = datetime.now().date()
    for i in range(num):
        end_date = today - timedelta(days=i)
        start_date = end_date - timedelta(days=1)
        data_list.append({
            'start': start_date.strftime('%Y-%m-%dT00:00:00'),
            'end': end_date.strftime('%Y-%m-%dT00:00:00')
        })
    return data_list


def getData(init_account_info):
    """关键指标"""
    cookies = init_account_info.get("cookies")
    start_time = init_account_info.get("start_time")
    end_time = init_account_info.get("end_time")
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Pragma': 'no-cache',
        'Referer': 'https://shop.tiktok.com/streamer/compass/livestream-analytics/view',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    }
    
    json_data = {
        'request': {
            'params': [{
                'time_selector': {"period": 2, "granularity": 11, "end_timestamp": int(end_time),
                                  "start_timestamp": int(start_time), "timezone_offset": "0"},
                'stats_types': [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213],
                'is_live_type': True,
            }],
        },
        'version': '2',
    }
    
    response = requests.post(
        'https://shop.tiktok.com/api/v2/insights/creator/live/stats?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance',
        cookies=cookies, headers=headers, json=json_data,
    )
    
    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v2/insights/creator/live/stats?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_data_overview(init_account_info):
    """数据概览"""
    cookies = init_account_info.get("cookies")
    start_time = init_account_info.get("start_time")
    end_time = init_account_info.get("end_time")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Referer': 'https://shop.tiktok.com/streamer/compass/data-overview/view',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }

    json_data = {
        "request": {
            "params": [{
                "time_selector": {"period": 2, "granularity": 11, "end_timestamp": end_time,
                                  "start_timestamp": start_time, "timezone_offset": "0"},
                "stats_types": [100, 101, 121, 11, 21, 130, 301, 302, 353, 351]
            }]
        },
        "version": "2"
    }

    response = requests.post(
        'https://shop.tiktok.com/api/v2/insights/creator/live/stats?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        cookies=cookies, headers=headers, json=json_data,
    )
    
    json_data["user_id"] = init_account_info.get("user_id")
    json_data["user_name"] = init_account_info.get("user_name")
    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v2/insights/creator/live/stats?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_account_info(init_account_info):
    """账号信息获取"""
    cookies = init_account_info.get("cookies")
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://shop.tiktok.com/streamer/live/product/dashboard',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }

    params = {'version': '1'}
    response = requests.get(
        'https://shop.tiktok.com/api/v1/streamer_desktop/account_info/get',
        params=params, cookies=cookies, headers=headers,
    )
    
    params["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v1/streamer_desktop/account_info/get',
        "params": params,
        "extra": params
    }
    return requestContent


def get_live_list(init_account_info):
    """直播列表"""
    cookies = init_account_info.get("cookies")
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Referer': 'https://shop.tiktok.com/streamer/compass/livestream-analytics/view',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }

    json_data = {
        'request': {
            'params': [{
                'time_selector': {
                    'period': 33,
                    'granularity': 32,
                    'base_timestamp': str(int(time.time())),
                    'timezone_offset': 25200,
                },
                'list_control': {
                    'rules': [{'direction': 2, 'field': 'LIVE_LIST_LIVE_START_TIMESTAMP'}],
                    'pagination': {'size': 500, 'page': 0},
                },
                'stats_types': [10, 15, 11, 12, 13, 14, 80, 88, 95, 86, 96, 90, 72, 70, 20, 25, 29, 40, 21, 50, 41, 42, 100, 101, 62, 61],
            }],
        },
        'version': '2',
    }

    response = requests.post(
        'https://shop.tiktok.com/api/v2/insights/creator/live/list?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        cookies=cookies, headers=headers, json=json_data,
    )
    
    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v2/insights/creator/live/list?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_product_list(init_account_info, dt):
    """商品列表"""
    cookies = init_account_info.get("cookies")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Referer': 'https://shop.tiktok.com/streamer/compass/product-analysis/view',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    }

    json_data = {
        'request': {
            'params': [{
                'stats_types': [80, 100, 40, 1, 2],
                'filter': {'search_input': '', 'country_code': []},
                'list_control': {
                    'rules': [{'direction': 2, 'field': 'CREATOR_PRODUCT_ANALYTICS_LIST_REVENUE'}],
                    'pagination': {'size': 50, 'page': 0},
                },
                'time_descriptor': {
                    'granularity': 'all',
                    'start': dt['start'],
                    'end': dt['end'],
                    'timezone_offset': 25200,
                },
            }],
        },
        'version': '3',
    }

    response = requests.post(
        'https://shop.tiktok.com/api/v3/insights/creator/product/analytics/list?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F140.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        cookies=cookies, headers=headers, json=json_data,
    )
    
    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v3/insights/creator/product/analytics/list?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F140.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_trend_chart(init_account_info):
    """获取表现趋势"""
    cookies = init_account_info.get("cookies")
    room_id = init_account_info.get("room_id")
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Referer': f'https://shop.tiktok.com/workbench/live/overview?room_id={room_id}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    
    json_data = {
        'request': {
            'room_filter': {'room_id': room_id, 'is_content_type': 1},
            'stats_types': [20, 11],
        },
    }
    
    response = requests.post(
        'https://shop.tiktok.com/api/v1/insights/workbench/live/detail/trend/chart?app_name=i18n_ecom_shop&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&vertical=3',
        cookies=cookies, headers=headers, json=json_data,
    )
    
    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://shop.tiktok.com/api/v1/insights/workbench/live/detail/trend/chart?app_name=i18n_ecom_shop&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F139.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&vertical=3',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_live_chart(init_account_info):
    """直播间详情-内容分析-直播趋势"""
    cookies = init_account_info.get("cookies")
    room_id = init_account_info.get("room_id")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://shop.tiktok.com',
        'Referer': f'https://shop.tiktok.com/streamer/compass/livestream-analytics/view/detail?roomId={room_id}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    }

    json_data = {
        'request': {
            'room_filter': {'room_id': room_id, 'query_online': False},
            'stats_types': [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40],
            'granularity': 1,
        },
    }

    response = requests.post(
        'https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart?user_language=zh-CN&locale=zh-Hans&aid=253642&app_name=i18n_ecom_alliance&device_id=0&device_platform=web&cookie_enabled=true&screen_width=2560&screen_height=1440&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+(Windows+NT+10.0%3B+Win64%3B+x64)+AppleWebKit%2F537.36+(KHTML,+like+Gecko)+Chrome%2F140.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&page_scene=0',
        cookies=cookies, headers=headers, json=json_data,
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
    """直播录像数据/直播回放数据"""
    cookies = init_account_info.get("cookies")
    headers = {
        'accept': '*/*',
        'origin': 'https://livecenter.tiktok.com',
        'referer': 'https://livecenter.tiktok.com/',
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
    
    response = requests.get(
        'https://webcast.tiktok.com/webcast/room/replay/info/',
        params=json_data, cookies=cookies, headers=headers, timeout=15
    )

    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://webcast.tiktok.com/webcast/room/replay/info/',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_live_replay_highlight(init_account_info):
    """直播高光时刻"""
    cookies = init_account_info.get("cookies")
    room_id = init_account_info.get("room_id")
    
    headers = {
        'accept': '*/*',
        'content-type': 'application/json',
        'origin': 'https://livecenter.tiktok.com',
        'referer': 'https://livecenter.tiktok.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    }
    
    json_data = {'room_ids': str(room_id), 'scene': 4, 'get_result_by': 0}

    response = requests.post(
        'https://webcast.tiktok.com/webcast/anchor/live_fragment/list/?aid=304449&device_platform=web_pc&tz_name=Asia%2FShanghai&webcast_language=zh-tw',
        cookies=cookies, headers=headers, json=json_data, timeout=15
    )

    json_data["init_account_info"] = init_account_info
    requestContent = {
        "response": response.text,
        "url": 'https://webcast.tiktok.com/webcast/anchor/live_fragment/list/?aid=304449&device_platform=web_pc&tz_name=Asia%2FShanghai&webcast_language=zh-tw',
        "params": json_data,
        "extra": json_data
    }
    return requestContent


def get_New_cj_user_id():
    """获取新增的插件ID(新安装插件ID，初次采集) 当天/前一天有过连接的插件ID"""
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    today_date = datetime.now().strftime("%Y%m%d")
    log_dir = Path(__file__).parent.parent.parent / "webSoctket" / "socketLog"
    log_yesterday_path = os.path.join(log_dir, f"socket_{yesterday_date}.log")
    log_today_path = os.path.join(log_dir, f"socket_{today_date}.log")

    cj_user_ids = set()

    # 读取昨天的日志文件
    try:
        with open(log_yesterday_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '] [' in line:
                    json_part = line.split('] [', 1)[1].rstrip(']')
                    if json_part:
                        try:
                            json_data = eval('[' + json_part + ']')
                            for item in json_data:
                                if isinstance(item, dict) and 'cjUserId' in item:
                                    cj_user_ids.add(item['cjUserId'])
                        except:
                            continue
    except FileNotFoundError:
        logger.warning(f"昨天的日志文件不存在: {log_yesterday_path}")
    except Exception as e:
        logger.error(f"读取昨天日志文件出错: {e}")

    # 读取今天的日志文件
    try:
        with open(log_today_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '] [' in line:
                    json_part = line.split('] [', 1)[1].rstrip(']')
                    if json_part:
                        try:
                            json_data = eval('[' + json_part + ']')
                            for item in json_data:
                                if isinstance(item, dict) and 'cjUserId' in item:
                                    cj_user_ids.add(item['cjUserId'])
                        except:
                            continue
    except FileNotFoundError:
        logger.warning(f"今天的日志文件不存在: {log_today_path}")
    except Exception as e:
        logger.error(f"读取今天日志文件出错: {e}")

    return list(cj_user_ids)


def get_gmv_data_CJID(db_config):
    """取出映射种子表gmv_data表中但不存在live_api_collect_data_monitoring_log接口数据表中的插件ID"""
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                collect_date = datetime.now().strftime("%Y-%m-%d")
                sql = f"""
                     SELECT room_id, room_name, CJ_User_id, room_url
                    FROM live_streaming_gmv_data
                    WHERE local_status = 1
                        AND LENGTH(CJ_User_id) > 0
                        AND platform = 'tiktok'
                        AND CJ_User_id NOT IN (
                                SELECT cj_user_id
                                FROM live_api_collect_data_monitoring_log
                                WHERE collect_date = '{collect_date}'
                                    AND message_cnt_1d = 0
                            )
                """
                cursor.execute(sql)
                result_init = cursor.fetchall()
                return list(result_init)
        finally:
            connection.close()
    except Exception as e:
        logger.error(f"获取GMV数据CJID失败: {e}")
        return []


def get_gmv_data_CJID_all(db_config):
    """取出所有GMV表中的插件ID"""
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                sql = """
                     SELECT CJ_User_id FROM live_streaming_gmv_data 
                     WHERE local_status = 1 and LENGTH(CJ_User_id)>0 and platform = 'tiktok' 
                """
                cursor.execute(sql)
                result_init = cursor.fetchall()
                return list(result_init)
        finally:
            connection.close()
    except Exception as e:
        logger.error(f"获取所有GMV CJID失败: {e}")
        return []


def get_spider_crawled_CJID(db_config):
    """查找今天已记录但数据量为0的插件ID和API接口（需要重新采集）"""
    try:
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                collect_date = datetime.now().strftime("%Y-%m-%d")
                sql = f"""
                    SELECT cj_user_id, api_name, message_cnt_1d
                    FROM live_api_collect_data_monitoring_log
                    WHERE collect_date = '{collect_date}'
                    AND message_cnt_1d = 0
                    AND CJ_User_id IN (
                            SELECT CJ_User_id
                            FROM live_streaming_gmv_data
                            WHERE local_status = 1
                            AND LENGTH(CJ_User_id) > 0
                        )
                """
                cursor.execute(sql)
                result_init = cursor.fetchall()
                return list(result_init)
        finally:
            connection.close()
    except Exception as e:
        logger.error(f"获取已爬取CJID失败: {e}")
        return []


def API_map(db_config):
    """接口映射,生成需要采集的任务列表"""
    with_cj_user_id = get_gmv_data_CJID(db_config)
    with_cj_user_id_crawled = get_spider_crawled_CJID(db_config)

    TT_api_List = [
        "https://livecenter.tiktok.com/replay",
        "https://shop.tiktok.com/streamer/compass/livestream-analytics/view",
        "https://shop.tiktok.com/streamer/compass/product-analysis/view"
    ]

    def tmp_tt_map_api(i_Key):
        if i_Key in ["商品分析"]:
            return "https://shop.tiktok.com/streamer/compass/product-analysis/view"
        elif i_Key in ["录像高光", "直播录像列表"]:
            return "https://livecenter.tiktok.com/replay"
        elif i_Key in ["数据概览-关键指标"]:
            return "https://shop.tiktok.com/streamer/compass/data-overview/view"
        elif i_Key in ["直播分析-关键指标", "关键指标", "直播间列表", "直播间详情-关键指标",
                       "直播间详情-内容分析-直播趋势", "直播间详情-商品分析-商品列表", 
                       "直播间详情-商品分析-成交趋势", "直播间详情-流量分析-流量趋势", 
                       "直播间详情-流量分析-流量转化", "直播间详情-用户画像", "账号信息"]:
            return "https://shop.tiktok.com/streamer/compass/livestream-analytics/view"
        else:
            return None

    initDict = {}

    # 不在接口表中的且在gmv_data表中的插件
    for item_user in with_cj_user_id:
        initDict[item_user["CJ_User_id"]] = TT_api_List

    # 还未获取到数据的插件ID
    for cjApi in with_cj_user_id_crawled:
        if not initDict.get(cjApi["cj_user_id"], ''):
            initDict[cjApi["cj_user_id"]] = []
        api_url = tmp_tt_map_api(cjApi['api_name'])
        if api_url and api_url not in initDict[cjApi["cj_user_id"]]:
            initDict[cjApi["cj_user_id"]].append(api_url)

    # 当天与前一天的所有链接过的插件ID且不存在于gmv_data种子表中的CJ加入采集
    new_cj_user_id = get_New_cj_user_id()
    with_cj_user_id_All = get_gmv_data_CJID_all(db_config)
    with_cj_user_id_All_CJID = [i["CJ_User_id"] for i in with_cj_user_id_All]
    
    for i in new_cj_user_id:
        if i not in with_cj_user_id_All_CJID:
            initDict[i] = TT_api_List

    return initDict


def mainSpider_T1(db_config, istest=1):
    """T+1插件数据采集"""
    logger.info("🚀 T+1插件采集任务启动")
    
    try:
        all_need_crawled = API_map(db_config)
        messages = []
        
        for cj_user_id, api_list in all_need_crawled.items():
            messages.append({"target_id": cj_user_id, "values": api_list})

        logger.info(f"T+1采集消息总数: {len(messages)}")
        print(f'len(messages)-->{len(messages)}')
        
        asyncio.run(mainT1_GMV(messages, sleep_time=300))
        logger.info("✅ T+1插件采集任务完成")
        
    except Exception as e:
        logger.error(f"T+1插件采集任务失败: {e}")
        raise


def mainSpider_requests(db_config, num=3, is_test_env=True):
    """基本信息采集（requests模拟请求）"""
    logger.info("🚀 基本信息采集任务启动")
    
    try:
        All_cookies = getArgs2(db_config)
        logger.info(f"获取到{len(All_cookies)}个账号cookie")
        print(f'All_cookies-->{All_cookies}')
        print(f'len(All_cookies)-->{len(All_cookies)}')

        for s in All_cookies:
            sessionid = s.get("sessionid", "")
            if not sessionid:
                logger.warning(f"没有获取到sessionid: {s}")
                print(f"没有获取到sessionid--->{s}")
                continue
                
            msToken = s["msToken"]
            full_cookies = s.get("full_cookies")
            init_account_info = {
                "cookies": {'sessionid': sessionid, 'msToken': msToken},
                "user_id": s["user_id"],
                "user_name": s["user_name"]
            }

            # 关键指标
            res_time_list = get_prams_time(num)
            for t_time in res_time_list[::-1]:
                print(f't_time-->{t_time}')
                init_account_info["start_time"] = t_time.get("start_time")
                init_account_info["end_time"] = t_time.get("end_time")
                
                try:
                    requestContent = getData(init_account_info)
                except Exception as e:
                    logger.error(f"关键指标采集失败-->{e}")
                    requestContent = "0"

                logger.debug({"api_name": "关键指标", "requestContent": len(str(requestContent)),
                           "init_account_info": init_account_info, "CJ_user_id": s["CJ_user_id"]})

                logger.info(f"requestContent关键指标-->{len(str(requestContent))}")
                upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)
                time.sleep(2)

            # 账号信息
            if s["api_name"] != "账号信息":
                try:
                    requestContent = get_account_info(init_account_info)
                except Exception as e:
                    logger.error(f"账号信息采集失败: {e}")
                    requestContent = "0"

                logger.debug({"api_name":"账号信息","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":s["CJ_user_id"]})
                logger.info(f"账号信息数据长度: {len(str(requestContent))}")
                upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)
                time.sleep(2)

            # 数据概览
            res_time_list = get_prams_time(num)
            for t_time in res_time_list[::-1]:
                init_account_info["start_time"] = t_time.get("start_time")
                init_account_info["end_time"] = t_time.get("end_time")
                
                try:
                    requestContent = get_data_overview(init_account_info)
                except Exception as e:
                    logger.error(f"数据概览采集失败: {e}")
                    requestContent = "0"

                logger.debug({"api_name":"数据概览","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":s["CJ_user_id"]})
                logger.info(f"数据概览数据长度: {len(str(requestContent))}")
                upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)
                time.sleep(3)

            # 商品列表
            data_list = generate_date_list(num)
            for dt in data_list:
                try:
                    requestContent = get_product_list(init_account_info, dt)
                except Exception as e:
                    logger.error(f"商品列表采集失败: {e}")
                    requestContent = "0"

                logger.debug({"api_name":"商品列表","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":s["CJ_user_id"]})
                logger.info(f"商品列表数据长度: {len(str(requestContent))}")
                upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)
                time.sleep(3)

            # 直播列表
            try:
                requestContent = get_live_list(init_account_info)
            except Exception as e:
                logger.error(f"直播列表采集失败: {e}")
                requestContent = "0"
                
            logger.debug({"api_name":"直播列表","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":s["CJ_user_id"]})
            logger.info(f"直播列表数据长度: {len(str(requestContent))}")
            upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)
            time.sleep(2)

            # 直播录像与对应的高光时刻数据
            try:
                requestContent = get_live_replay(init_account_info)
            except Exception as e:
                logger.error(f"直播录像采集失败: {e}")
                requestContent = "0"

            logger.debug({"api_name":"直播录像数据","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":s["CJ_user_id"]})
            logger.info(f"直播录像数据长度: {len(str(requestContent))}")
            upload_data(s["CJ_user_id"], requestContent, cookies_dict=full_cookies)

            # 高光时刻
            try:
                kafkaDataInit = json.loads(requestContent["response"])
                replays = kafkaDataInit["data"]["replays"]
                
                today = datetime.today()
                day_before_yesterday = today - timedelta(days=2)
                day_before_yesterday_midnight = day_before_yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                day_before_yesterdayTime = int(day_before_yesterday_midnight.timestamp())
                
                roomidList = [
                    item.get("id") for item in replays 
                    if item.get("id") and int(item.get("start_time")) >= day_before_yesterdayTime
                ]

                for roomid in roomidList:
                    init_account_info_highlight = {
                        "cookies": init_account_info["cookies"],
                        "room_id": roomid,
                        "user_id": init_account_info["user_id"],
                        "user_name": init_account_info["user_name"]
                    }
                    
                    try:
                        requestContent_highlight = get_live_replay_highlight(init_account_info_highlight)
                    except Exception as e:
                        logger.error(f"高光时刻采集失败: {e}")
                        requestContent_highlight = "0"
                        
                    logger.debug({"api_name":"直播高光时刻","requestContent":len(str(requestContent_highlight)),"init_account_info":init_account_info_highlight,"CJ_user_id":s["CJ_user_id"]})
                    logger.info(f"直播高光时刻数据长度: {len(str(requestContent_highlight))}")
                    upload_data(s["CJ_user_id"], requestContent_highlight, cookies_dict=full_cookies)
                    
            except Exception as e:
                logger.error(f"处理高光时刻失败: {e}")

        # 初始化插件ID与token身份信息的映射
        # 表现趋势,这个接口与场次有关系，与时间无关，单独采集
        SSS_dict = {}
        for s in All_cookies:
            SSS_dict[s["CJ_user_id"]] = s

        room_id_list = get_media_user_id(db_config, num)
        for room_item in room_id_list:
            if str(room_item["CJ_User_id"]) == "None":
                continue

            if room_item["CJ_User_id"] in SSS_dict.keys():
                cj_user_id_key = room_item["CJ_User_id"]
                full_cookies = SSS_dict[cj_user_id_key].get("full_cookies")
                init_account_info = {
                    "cookies": {
                        'sessionid': SSS_dict[room_item["CJ_User_id"]]["sessionid"],
                        'msToken': SSS_dict[room_item["CJ_User_id"]]["msToken"]
                    },
                    "room_id": room_item["show_code"],
                    "CJ_user_id": SSS_dict[room_item["CJ_User_id"]]["CJ_user_id"]
                }

                # 获取表现趋势
                try:
                    requestContent = get_trend_chart(init_account_info)
                except Exception as e:
                    logger.error(f"表现趋势采集失败: {e}")
                    requestContent = "0"

                logger.debug({"api_name":"表现趋势","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":init_account_info["CJ_user_id"]})
                print(f"表现趋势数据长度: {len(str(requestContent))}")
                upload_data(init_account_info["CJ_user_id"], requestContent, cookies_dict=full_cookies)

                # 直播间详情-内容分析-直播趋势
                try:
                    requestContent = get_live_chart(init_account_info)
                except Exception as e:
                    logger.error(f"直播趋势采集失败: {e}")
                    requestContent = "0"

                logger.debug({"api_name":"直播间详情-内容分析-直播趋势","requestContent":len(str(requestContent)),"init_account_info":init_account_info,"CJ_user_id":init_account_info["CJ_user_id"]})
                logger.debug(f"直播趋势数据长度: {len(str(requestContent))}")
                upload_data(init_account_info["CJ_user_id"], requestContent, cookies_dict=full_cookies)

            time.sleep(2)

        logger.info("✅ 基本信息采集任务完成")
        
    except Exception as e:
        logger.error(f"基本信息采集任务失败: {e}")
        raise



if __name__ == '__main__':
    import config
    is_test_env = config.is_test_env()  # True: 测试环境, False: 生产环境

    def init_database_config(istest=1):
        """初始化数据库配置（已迁移到 Apollo，config 门面）"""
        try:
            # MySQL 连接参数（cursorclass 为 pymysql 专用，门面不含，此处补上）
            db_config = {
                **config.mysql_config(),
                'cursorclass': pymysql.cursors.DictCursor,
            }
            # 仅生产环境初始化 Holo 配置
            if not config.is_test_env():
                holo_db_config = config.holo_config()
            else:
                holo_db_config = {}

            return db_config, holo_db_config
        except Exception as e:
            logger.error(f"数据库配置初始化失败: {e}", exc_info=True)
            raise
    db_config, holo_db_config = init_database_config(is_test_env)

    mainSpider_requests(db_config, num=3, is_test_env=is_test_env)
