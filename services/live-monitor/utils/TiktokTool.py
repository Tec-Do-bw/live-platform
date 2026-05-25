# -*- coding: utf-8 -*-
import re
import json
import random
import time
import execjs
import queue
from utils.db_pool import db_pool
from utils.logger import Logings
from utils.downloader import Downloader, Task

logger = Logings().get_logger()


class TiktokTool:
    def __init__(self, ipList=[], no_proxy=None):
        """
        TikTok工具类

        Args:
            ipList: IP代理列表
        """
        self.ipList = ipList
        if no_proxy:
            self._downloader = Downloader(
                proxy=None,
                workers=1,
                timeout=10.0,
                max_retries=3,
                headers={"Sec-Fetch-Site": "same-origin"},
            )
        else:
            self._downloader = Downloader(
                workers=1,
                timeout=10.0,
                max_retries=3,
                headers={"Sec-Fetch-Site": "same-origin"},
            )

        self.All_country = ['CN', 'US', 'CA', 'FR', 'GB', 'DE', 'ES', 'IT', 'RU', 'AU', 'UA', 'AR', 'MX', 'BR', 'TR',
                            'CO',
                            'ZA', 'CL', 'TH', 'VN', 'MY', 'MM', 'IN', 'ID', 'SG', 'PH', 'BD', 'JP', 'KR', 'PK', 'SA',
                            'UZ',
                            'PY', 'EC', 'AT', 'CZ', 'DK', 'PL', 'PE', 'LT', 'SE', 'HU', 'BG', 'IL', 'AE', 'SD', 'RO',
                            'QA',
                            'NG', 'NL', 'NP', 'KZ', 'GH', 'EG', 'UG', 'ZM', 'KE', 'FI', 'NO', 'CH', 'MG', 'NZ', 'PT',
                            'GR',
                            'IE', 'DZ', 'MN', 'LK', 'TN', 'AF', 'AL', 'AD', 'AO', 'AG', 'AM', 'AZ', 'BS', 'BH', 'BB',
                            'BY',
                            'BE', 'BZ', 'BJ', 'BT', 'BO', 'BW', 'BN', 'BF', 'BI', 'KH', 'CM', 'CV', 'CF', 'TD', 'CG',
                            'CK',
                            'CR', 'CI', 'HR', 'CU', 'DJ', 'TL', 'SV', 'GQ', 'EE', 'ET', 'FJ', 'GA', 'GM', 'PS', 'GE',
                            'GD',
                            'GT', 'GN', 'GW', 'GY', 'HT', 'HN', 'IS', 'IQ', 'IR', 'JM', 'JO', 'KI', 'KW', 'KG', 'LA',
                            'LV',
                            'LB', 'LS', 'LR', 'LY', 'LI', 'LU', 'MK', 'MW', 'MV', 'ML', 'MH', 'MR', 'MU', 'FM', 'MD',
                            'MC',
                            'MA', 'MZ', 'NA', 'NR', 'NI', 'NE', 'NU', 'OM', 'PW', 'PA', 'PG', 'RW', 'LC', 'ST', 'SN',
                            'RS',
                            'SC', 'SL', 'SK', 'SI', 'SB', 'SO', 'SS', 'SR', 'SZ', 'SY', 'TJ', 'TZ', 'TG', 'TO', 'TV',
                            'UY',
                            'VE', 'YE', 'ZW', 'DO', 'BA']

    # 获取动态cookies列表
    def get_cookie_list(self,
                        getLiveCookiessql="SELECT cookies FROM live_account_info where cookies like '%true%'  order by id desc limit 20"):
        """
        从数据库获取cookie列表（使用连接池）

        Args:
            getLiveCookiessql: 查询SQL语句

        Returns:
            cookies字符串列表
        """
        try:
            # ✅ 使用连接池查询
            dd = db_pool.execute_query(getLiveCookiessql)

            if not dd:
                logger.warning("未查询到任何cookies记录")
                return []

            cookies_string_list = []
            for d in dd:
                try:
                    # 处理cookie数据
                    cookiesArgsList = eval(d[0].replace("true", "True").replace("false", "False"))
                    cookie = {}
                    for i in cookiesArgsList:
                        cookie[i['name']] = i['value']
                    cookies_string = '; '.join([f"{key}={value}" for key, value in cookie.items()])
                    if cookies_string not in cookies_string_list:
                        cookies_string_list.append(cookies_string)
                except Exception as parse_error:
                    logger.error(f"解析单条cookie失败: {parse_error}")
                    continue

            logger.info(f"成功获取cookies列表 | 数量={len(cookies_string_list)}")
            return cookies_string_list

        except Exception as e:
            logger.error(f"获取动态cookies列表时出错: {e}", exc_info=True)
            return []

    def get_cookies_dict(self, cookies_str):
        # 将cookies字符串转换为字典
        cookies_dict = {}
        for item in cookies_str.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                cookies_dict[key.strip()] = value.strip()

        return cookies_dict

    def _extract_json_from_html(self, html_str, script_id="SIGI_STATE"):
        """从HTML指定script标签中提取JSON数据"""
        try:
            pattern = f'<script id="{script_id}" type="application/json">(.*?)</script>'
            json_str = re.findall(pattern, html_str, re.DOTALL)[0]
            return json.loads(json_str)
        except Exception:
            return None

    def _parse_user_detail(self, json_data, record_url):
        """解析用户个人信息（webapp.user-detail），返回与parse_json_data一致的字段结构"""
        if not json_data:
            return {"flv_url": "", "roomId": "", "message": "页面解析失败", "url": record_url}

        user_detail = (json_data.get("__DEFAULT_SCOPE__") or {}).get("webapp.user-detail")
        if not user_detail or not user_detail.get("userInfo"):
            return {"flv_url": "", "roomId": "", "message": "用户信息不存在", "url": record_url}

        user = user_detail["userInfo"].get("user", {})

        try:
            filePath = re.compile("@(.*?)/live").findall(record_url)[0].replace(".", "_")
        except (IndexError, AttributeError):
            filePath = ""

        return {
            "flv_url": "",
            "startTime": "",
            "secUid": str(user.get("secUid", "")),
            "uniqueId": str(user.get("uniqueId", "")),
            "roomId": str(user.get("roomId", "")),
            "signature": str(user.get("signature", "")),
            "id": str(user.get("id", "")),
            "nickname": str(user.get("nickname", "")),
            "url": record_url,
            "filePath": filePath,
        }
    def _make_error(self, url, message, status_code=None):
        """构造统一的错误返回字典，保持与正常结果结构一致。"""
        msg = f"{message} (HTTP {status_code})" if status_code else message
        return {
            "flv_url": "error",
            "roomId": "",
            "message": msg,
            "filePath": "",
            "url": url,
        }

    def get_tiktok_stream_data_requests(self, url, cookie_list):
        try:
            # 请求直播页，Referer 设为实际 URL
            task = Task(url=url, headers={"Referer": url})
            result = self._downloader.fetch_one(task)

            if not result.success:
                logger.warning("请求直播页失败: %s | %s", url, result.error)
                return self._make_error(url, f"请求直播页失败: {result.error}", result.status_code)

            html_str = result.text
            json_data = self._extract_json_from_html(html_str)

            # SIGI_STATE 中有 LiveRoom → 解析直播流信息
            if json_data and json_data.get("LiveRoom"):
                return self.parse_json_data(json_data, url)

            # 无直播 → 请求个人主页获取用户基本信息
            profile_url = url.replace("/live", "")
            profile_task = Task(url=profile_url, headers={"Referer": profile_url})
            profile_result = self._downloader.fetch_one(profile_task)

            if not profile_result.success:
                logger.warning("请求个人页失败: %s | %s", profile_url, profile_result.error)
                return self._make_error(url, f"请求个人页失败: {profile_result.error}", profile_result.status_code)

            profile_data = self._extract_json_from_html(
                profile_result.text, "__UNIVERSAL_DATA_FOR_REHYDRATION__"
            )
            return self._parse_user_detail(profile_data, url)

        except Exception as e:
            logger.error("get_tiktok_stream_data_requests 异常: %s", e, exc_info=True)
            return self._make_error(url, f"采集内部异常: {e}")


    def parse_json_data(self, json_data, record_url):
        port_info = {}

        if json_data.get("LiveRoom", ''):
            liveRoomUserInfo = json_data.get("LiveRoom", '').get("liveRoomUserInfo")
            liveRoom = liveRoomUserInfo.get("liveRoom")
            startTime = liveRoom.get("startTime")
            port_info["startTime"] = str(startTime)

            try:
                stream_data = liveRoom.get("streamData").get("pull_data").get("stream_data")
            except:
                port_info["flv_url"] = "error"
            try:
                json_data2 = json.loads(stream_data)
                flv_url = json_data2.get("data").get("origin").get("main").get("flv")
                if str(liveRoom["status"]) == '2':
                    port_info["flv_url"] = flv_url
                else:
                    port_info["flv_url"] = ''
            except:
                port_info["flv_url"] = ""
            user = liveRoomUserInfo.get("user")
            port_info["secUid"] = str(user.get("secUid"))
            port_info["uniqueId"] = str(user.get("uniqueId"))
            port_info["roomId"] = str(user.get("roomId"))
            port_info["signature"] = str(user.get("signature"))
            port_info["id"] = str(user.get("id"))
            port_info["nickname"] = str(user.get("nickname"))
            port_info["url"] = record_url
            filePath = re.compile("@(.*?)/live").findall(record_url)[0].replace(".", "_")
            port_info["filePath"] = filePath
            return port_info

        else:
            port_info = {"flv_url": "", "roomId": "", "message": "直播间不存在", "url": record_url}
            return port_info

    # 传入直播间地址，解析获取真实直播流地址信息
    def getLiveStreamInfo_requests(self, record_url, cookie_list, OP=None):
        json_data = 0
        # 尝试直接解密获取
        try:
            json_data = self.get_tiktok_stream_data_requests(url=record_url, cookie_list=cookie_list)
            return json_data
        except Exception as e:
            print("getLiveStreamInfo_requests11111111:e-->", e)
            return {'flv_url': 'error', 'roomId': '', 'message': 'tk采集异常', 'filePath': ''}

if __name__ == '__main__':
    import queue

    tabItemQ = queue.Queue()
    ipList = ['senspower:T9u_SCK5Bezq@96.62.57.99:2333', 'senspower:T9u_SCK5Bezq@96.62.57.98:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.41:2333', 'senspower:T9u_SCK5Bezq@96.62.57.38:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.37:2333', 'senspower:T9u_SCK5Bezq@96.62.57.35:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.34:2333', 'senspower:T9u_SCK5Bezq@96.62.57.33:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.31:2333', 'senspower:T9u_SCK5Bezq@96.62.57.25:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.24:2333', 'senspower:T9u_SCK5Bezq@96.62.57.226:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.187:2333', 'senspower:T9u_SCK5Bezq@96.62.57.18:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.130:2333', 'senspower:T9u_SCK5Bezq@96.62.57.129:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.128:2333', 'senspower:T9u_SCK5Bezq@96.62.57.127:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.124:2333', 'senspower:T9u_SCK5Bezq@96.62.57.112:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.111:2333', 'senspower:T9u_SCK5Bezq@96.62.57.108:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.107:2333', 'senspower:T9u_SCK5Bezq@96.62.57.105:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.99:2333', 'senspower:T9u_SCK5Bezq@96.62.151.66:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.249:2333', 'senspower:T9u_SCK5Bezq@96.62.151.228:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.218:2333', 'senspower:T9u_SCK5Bezq@96.62.151.217:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.216:2333', 'senspower:T9u_SCK5Bezq@96.62.151.215:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.214:2333', 'senspower:T9u_SCK5Bezq@96.62.151.211:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.210:2333', 'senspower:T9u_SCK5Bezq@96.62.151.21:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.184:2333', 'senspower:T9u_SCK5Bezq@96.62.151.182:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.130:2333', 'senspower:T9u_SCK5Bezq@96.62.151.128:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.239:2333', 'senspower:T9u_SCK5Bezq@96.62.149.238:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.237:2333', 'senspower:T9u_SCK5Bezq@96.62.149.236:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.234:2333', 'senspower:T9u_SCK5Bezq@96.62.149.233:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.231:2333', 'senspower:T9u_SCK5Bezq@96.62.149.23:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.229:2333', 'senspower:T9u_SCK5Bezq@96.62.149.222:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.186:2333', 'senspower:T9u_SCK5Bezq@96.62.149.159:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.158:2333', 'senspower:T9u_SCK5Bezq@96.62.149.157:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.156:2333', 'senspower:T9u_SCK5Bezq@96.62.149.155:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.153:2333', 'senspower:T9u_SCK5Bezq@96.62.149.152:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.151:2333', 'senspower:T9u_SCK5Bezq@96.62.149.150:2333',
              'senspower:T9u_SCK5Bezq@96.62.10.10:2333', 'senspower:T9u_SCK5Bezq@95.135.223.246:2333',
              'senspower:T9u_SCK5Bezq@95.135.104.30:2333', 'senspower:T9u_SCK5Bezq@95.135.104.17:2333',
              'senspower:T9u_SCK5Bezq@95.134.80.5:2333', 'senspower:T9u_SCK5Bezq@95.134.80.15:2333',
              'senspower:T9u_SCK5Bezq@95.134.79.143:2333', 'senspower:T9u_SCK5Bezq@95.134.202.9:2333',
              'senspower:T9u_SCK5Bezq@95.134.202.13:2333', 'senspower:T9u_SCK5Bezq@94.241.137.48:2333',
              'senspower:T9u_SCK5Bezq@94.241.137.47:2333', 'senspower:T9u_SCK5Bezq@94.241.137.27:2333',
              'senspower:T9u_SCK5Bezq@94.241.137.138:2333', 'senspower:T9u_SCK5Bezq@94.241.136.97:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.196:2333', 'senspower:T9u_SCK5Bezq@94.241.136.167:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.16:2333', 'senspower:T9u_SCK5Bezq@94.241.136.152:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.146:2333', 'senspower:T9u_SCK5Bezq@93.114.88.84:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.82:2333', 'senspower:T9u_SCK5Bezq@93.114.88.62:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.57:2333', 'senspower:T9u_SCK5Bezq@93.114.88.43:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.236:2333', 'senspower:T9u_SCK5Bezq@93.114.88.214:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.123:2333', 'senspower:T9u_SCK5Bezq@93.114.88.118:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.106:2333', 'senspower:T9u_SCK5Bezq@88.216.247.99:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.31:2333', 'senspower:T9u_SCK5Bezq@82.29.99.225:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.22:2333', 'senspower:T9u_SCK5Bezq@82.29.99.21:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.162:2333', 'senspower:T9u_SCK5Bezq@82.29.99.142:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.107:2333', 'senspower:T9u_SCK5Bezq@82.29.7.91:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.68:2333', 'senspower:T9u_SCK5Bezq@82.29.7.65:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.36:2333', 'senspower:T9u_SCK5Bezq@82.29.7.250:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.233:2333', 'senspower:T9u_SCK5Bezq@82.29.7.202:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.19:2333', 'senspower:T9u_SCK5Bezq@82.29.7.189:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.163:2333', 'senspower:T9u_SCK5Bezq@82.29.7.154:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.143:2333', 'senspower:T9u_SCK5Bezq@82.29.7.13:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.123:2333', 'senspower:T9u_SCK5Bezq@82.29.7.119:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.114:2333', 'senspower:T9u_SCK5Bezq@82.29.7.111:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.110:2333', 'senspower:T9u_SCK5Bezq@82.29.7.101:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.10:2333', 'senspower:T9u_SCK5Bezq@82.29.68.47:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.37:2333', 'senspower:T9u_SCK5Bezq@82.29.68.35:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.25:2333', 'senspower:T9u_SCK5Bezq@82.29.68.241:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.168:2333', 'senspower:T9u_SCK5Bezq@82.29.55.9:2333',
              'senspower:T9u_SCK5Bezq@82.29.55.175:2333', 'senspower:T9u_SCK5Bezq@82.29.150.35:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.254:2333', 'senspower:T9u_SCK5Bezq@82.29.150.192:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.187:2333', 'senspower:T9u_SCK5Bezq@82.29.150.155:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.102:2333', 'senspower:T9u_SCK5Bezq@68.64.156.94:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.5:2333', 'senspower:T9u_SCK5Bezq@68.64.156.44:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.3:2333', 'senspower:T9u_SCK5Bezq@68.64.156.242:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.222:2333', 'senspower:T9u_SCK5Bezq@68.64.156.208:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.176:2333', 'senspower:T9u_SCK5Bezq@68.64.156.141:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.121:2333', 'senspower:T9u_SCK5Bezq@68.64.156.107:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.10:2333', 'senspower:T9u_SCK5Bezq@66.93.30.58:2333',
              'senspower:T9u_SCK5Bezq@45.207.128.202:2333', 'senspower:T9u_SCK5Bezq@45.207.128.116:2333',
              'senspower:T9u_SCK5Bezq@45.196.195.15:2333', 'senspower:T9u_SCK5Bezq@45.194.24.74:2333',
              'senspower:T9u_SCK5Bezq@45.192.239.8:2333', 'senspower:T9u_SCK5Bezq@45.192.239.46:2333',
              'senspower:T9u_SCK5Bezq@45.192.238.12:2333', 'senspower:T9u_SCK5Bezq@38.30.200.61:2333',
              'senspower:T9u_SCK5Bezq@38.213.58.170:2333', 'senspower:T9u_SCK5Bezq@38.213.253.128:2333',
              'senspower:T9u_SCK5Bezq@38.213.252.214:2333', 'senspower:T9u_SCK5Bezq@38.213.139.158:2333',
              'senspower:T9u_SCK5Bezq@38.213.122.216:2333', 'senspower:T9u_SCK5Bezq@31.59.187.65:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.60:2333', 'senspower:T9u_SCK5Bezq@31.59.187.58:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.5:2333', 'senspower:T9u_SCK5Bezq@31.59.187.245:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.216:2333', 'senspower:T9u_SCK5Bezq@31.59.187.199:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.180:2333', 'senspower:T9u_SCK5Bezq@31.59.187.135:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.92:2333', 'senspower:T9u_SCK5Bezq@31.59.113.9:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.89:2333', 'senspower:T9u_SCK5Bezq@31.59.113.57:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.52:2333', 'senspower:T9u_SCK5Bezq@31.59.113.43:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.40:2333', 'senspower:T9u_SCK5Bezq@31.59.113.245:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.239:2333', 'senspower:T9u_SCK5Bezq@31.59.113.236:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.185:2333', 'senspower:T9u_SCK5Bezq@31.59.113.182:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.174:2333', 'senspower:T9u_SCK5Bezq@31.59.113.169:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.134:2333', 'senspower:T9u_SCK5Bezq@31.59.113.130:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.85:2333', 'senspower:T9u_SCK5Bezq@31.59.112.68:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.233:2333', 'senspower:T9u_SCK5Bezq@31.59.112.220:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.213:2333', 'senspower:T9u_SCK5Bezq@31.59.112.202:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.166:2333', 'senspower:T9u_SCK5Bezq@31.59.112.103:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.47:2333', 'senspower:T9u_SCK5Bezq@31.57.133.236:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.194:2333', 'senspower:T9u_SCK5Bezq@31.57.133.180:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.155:2333', 'senspower:T9u_SCK5Bezq@31.56.201.84:2333',
              'senspower:T9u_SCK5Bezq@31.56.201.68:2333', 'senspower:T9u_SCK5Bezq@31.56.201.177:2333',
              'senspower:T9u_SCK5Bezq@31.56.201.115:2333', 'senspower:T9u_SCK5Bezq@217.147.165.167:2333',
              'senspower:T9u_SCK5Bezq@217.147.165.154:2333', 'senspower:T9u_SCK5Bezq@217.147.165.128:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.5:2333', 'senspower:T9u_SCK5Bezq@209.213.202.45:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.233:2333', 'senspower:T9u_SCK5Bezq@209.213.202.230:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.224:2333', 'senspower:T9u_SCK5Bezq@209.213.202.222:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.211:2333', 'senspower:T9u_SCK5Bezq@209.213.202.198:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.193:2333', 'senspower:T9u_SCK5Bezq@209.213.202.187:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.174:2333', 'senspower:T9u_SCK5Bezq@209.213.202.14:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.105:2333', 'senspower:T9u_SCK5Bezq@195.86.51.38:2333',
              'senspower:T9u_SCK5Bezq@195.86.30.56:2333', 'senspower:T9u_SCK5Bezq@195.86.30.30:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.246:2333', 'senspower:T9u_SCK5Bezq@192.200.211.245:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.240:2333', 'senspower:T9u_SCK5Bezq@192.200.211.236:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.233:2333', 'senspower:T9u_SCK5Bezq@188.209.143.81:2333',
              'senspower:T9u_SCK5Bezq@188.209.143.187:2333', 'senspower:T9u_SCK5Bezq@172.121.61.89:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.86:2333', 'senspower:T9u_SCK5Bezq@172.121.61.85:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.84:2333', 'senspower:T9u_SCK5Bezq@172.121.61.82:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.81:2333', 'senspower:T9u_SCK5Bezq@172.121.61.80:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.63:2333', 'senspower:T9u_SCK5Bezq@172.121.61.58:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.48:2333', 'senspower:T9u_SCK5Bezq@172.121.61.47:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.245:2333', 'senspower:T9u_SCK5Bezq@172.121.61.154:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.119:2333', 'senspower:T9u_SCK5Bezq@172.121.53.47:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.46:2333', 'senspower:T9u_SCK5Bezq@172.121.53.45:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.43:2333', 'senspower:T9u_SCK5Bezq@172.121.53.41:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.246:2333', 'senspower:T9u_SCK5Bezq@172.121.53.220:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.149:2333', 'senspower:T9u_SCK5Bezq@172.121.53.148:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.146:2333', 'senspower:T9u_SCK5Bezq@172.121.53.145:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.144:2333', 'senspower:T9u_SCK5Bezq@172.121.53.140:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.14:2333', 'senspower:T9u_SCK5Bezq@172.121.53.102:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.39:2333', 'senspower:T9u_SCK5Bezq@172.120.245.37:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.36:2333', 'senspower:T9u_SCK5Bezq@172.120.245.35:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.34:2333', 'senspower:T9u_SCK5Bezq@172.120.245.32:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.31:2333', 'senspower:T9u_SCK5Bezq@172.120.245.3:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.220:2333', 'senspower:T9u_SCK5Bezq@172.120.245.160:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.141:2333', 'senspower:T9u_SCK5Bezq@167.148.104.79:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.76:2333', 'senspower:T9u_SCK5Bezq@167.148.104.72:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.54:2333', 'senspower:T9u_SCK5Bezq@167.148.104.254:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.252:2333', 'senspower:T9u_SCK5Bezq@167.148.104.225:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.182:2333', 'senspower:T9u_SCK5Bezq@167.148.104.172:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.151:2333', 'senspower:T9u_SCK5Bezq@154.83.108.43:2333',
              'senspower:T9u_SCK5Bezq@154.83.108.215:2333', 'senspower:T9u_SCK5Bezq@151.242.8.187:2333',
              'senspower:T9u_SCK5Bezq@151.242.121.64:2333', 'senspower:T9u_SCK5Bezq@149.87.190.232:2333',
              'senspower:T9u_SCK5Bezq@149.87.172.196:2333', 'senspower:T9u_SCK5Bezq@149.87.172.100:2333',
              'senspower:T9u_SCK5Bezq@149.51.127.23:2333', 'senspower:T9u_SCK5Bezq@104.234.185.96:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.38:2333', 'senspower:T9u_SCK5Bezq@104.234.185.251:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.243:2333', 'senspower:T9u_SCK5Bezq@104.234.185.237:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.234:2333', 'senspower:T9u_SCK5Bezq@104.234.185.23:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.214:2333', 'senspower:T9u_SCK5Bezq@104.234.185.191:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.183:2333', 'senspower:T9u_SCK5Bezq@104.234.185.173:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.160:2333', 'senspower:T9u_SCK5Bezq@104.234.185.157:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.116:2333']
    tiktokTool = TiktokTool(ipList)

    import time

    times = []  # 用于保存每次请求耗时

    for i in range(2):
        start_time = time.time()
        try:
            # room_url = "https://www.tiktok.com/@greameofficialstore/live" #18岁禁止
            room_url = "https://www.tiktok.com/@balabalaclothes/live" #正常
            # room_url = "https://www.tiktok.com/@koh.gen.do.my/live" #没有直播
            port_info = tiktokTool.getLiveStreamInfo_requests(room_url, ipList, tabItemQ) or {}
            print(port_info)
        except:
            print("解析错误", room_url)
        finally:
            cost = time.time() - start_time
            times.append(cost)
            print(f"耗时:{cost:.2f}")

    # 统计平均耗时和最大耗时
    avg_time = sum(times) / len(times)
    max_time = max(times)

    print(f"平均请求耗时: {avg_time:.2f}秒")
    print(f"最长请求耗时: {max_time:.2f}秒")

    # 多线程测试
    # import time
    # from concurrent.futures import ThreadPoolExecutor, as_completed
    #
    # # 假设你的 tiktokTool, ipList, tabItemQ 已经在上方定义完毕
    # room_url = "https://www.tiktok.com/@daddy.mockingbird/live"
    # times = []
    #
    #
    # # 1. 把单次请求的逻辑封装成一个函数
    # def fetch_stream_data(url):
    #     start_time = time.time()
    #     try:
    #         port_info = tiktokTool.getLiveStreamInfo_requests(url, ipList, tabItemQ) or {}
    #         print(port_info)
    #     except Exception as e:
    #         print("解析错误", url, e)
    #     finally:
    #         cost = time.time() - start_time
    #         print(f"耗时:{cost:.2f}")
    #         return cost  # 返回耗时用于后续统计
    #
    #
    # # 2. 使用线程池进行并发请求
    # # max_workers 是并发的线程数，你可以根据你的代理池大小和目标网站的限制来调整 (比如 10 到 20)
    # max_workers = 1
    # print(f"开始并发请求，线程数: {max_workers}...")
    #
    # with ThreadPoolExecutor(max_workers=max_workers) as executor:
    #     # 提交 100 个任务到线程池
    #     futures = [executor.submit(fetch_stream_data, room_url) for _ in range(200)]
    #
    #     # 获取结果 (as_completed 会在任务完成时立刻生成结果)
    #     for future in as_completed(futures):
    #         cost = future.result()
    #         times.append(cost)
    #
    # # 3. 统计平均耗时和最大耗时
    # if times:
    #     avg_time = sum(times) / len(times)
    #     max_time = max(times)
    #
    #     print(f"总计完成请求数: {len(times)}")
    #     print(f"平均请求耗时: {avg_time:.2f}秒")
    #     print(f"最长请求耗时: {max_time:.2f}秒")
    # else:
    #     print("未能记录到任何有效数据。")
