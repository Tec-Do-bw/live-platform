# -*- coding: utf-8 -*-
import re
import json
import random
import time
from utils.db_pool import db_pool
from utils.logger import Logings
from utils.downloader import Downloader, Task

logger = Logings().get_logger()


# 桌面 Chrome UA：直播页必须用桌面 UA，移动 UA 拿到的简化 HTML 无 SIGI_STATE
# 详见 docs/specs/tiktok-live-stream-url-fetch.md
UA_DESKTOP_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# 个人页/直播页通用请求头（小写头名 + priority + sec-ch-ua 结构，对齐 test.py）
# 仅 user-agent 不同：个人页用随机 iOS UA，直播页用桌面 Chrome UA
_BASE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


def get_random_ios_ua():
    """生成随机 iOS Safari UA（用于个人页请求，与 test.py 一致）"""
    ios_versions = [
        '15.0', '15.1', '15.2', '15.3', '15.4',
        '16.0', '16.1', '16.2', '16.3', '16.4',
        '17.0', '17.1', '17.2', '17.3'
    ]
    safari_versions = [
        '605.1.15', '604.1', '605.1', '606.1',
        '607.1', '608.1', '609.1'
    ]
    devices = ['iPhone', 'iPad', 'iPod']

    device = random.choice(devices)
    ios_version = random.choice(ios_versions)
    safari_version = random.choice(safari_versions)
    return (
        f"Mozilla/5.0 ({device}; CPU {device} OS {ios_version.replace('.', '_')} "
        f"like Mac OS X) AppleWebKit/{safari_version} (KHTML, like Gecko) "
        f"Version/{ios_version[:2]}.0 Mobile/15E148 Safari/{safari_version}"
    )


# 提取 handle 的正则
URL_HANDLE_RE = re.compile(r'/@([^/?#]+)')

# 直播页 SIGI_STATE 抽取
SIGI_RE = re.compile(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', re.S)

# 个人页 webapp.user-detail 抽取（与 test.py 一致）
USER_DETAIL_RE = re.compile(r'webapp\.user-detail":(.*?),"webapp')


class TiktokTool:
    def __init__(self, ipList=[], no_proxy=None):
        """
        TikTok工具类

        Args:
            ipList: IP代理列表
        """
        self.ipList = ipList
        # workers=2：个人页 + 直播页并发请求
        if no_proxy:
            self._downloader = Downloader(
                proxy=None,
                workers=2,
                timeout=10.0,
                max_retries=3,
            )
        else:
            self._downloader = Downloader(
                workers=2,
                timeout=10.0,
                max_retries=3,
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

    # ----- 请求头构造（严格对齐 test.py 风格） -----

    def _build_profile_headers(self):
        """个人页请求头，UA 使用随机 iOS（与 test.py 一致）"""
        return {**_BASE_HEADERS, "user-agent": get_random_ios_ua()}

    def _build_live_headers(self):
        """直播页请求头：UA 必须为桌面 Chrome，移动 UA 不含 SIGI_STATE"""
        return {**_BASE_HEADERS, "user-agent": UA_DESKTOP_CHROME}

    # ----- 解析辅助 -----

    def _extract_handle(self, url):
        """从 URL 抠出 handle，例如 /@xxx/live → xxx"""
        m = URL_HANDLE_RE.search(url)
        return m.group(1) if m else ""

    def _parse_profile_user(self, html_text):
        """从个人页 HTML 抽取 webapp.user-detail 中的 user 字段
        使用与 test.py 一致的正则定位再 json.loads
        """
        m = USER_DETAIL_RE.search(html_text)
        if not m:
            return None
        try:
            j_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        # statusCode != 0 表示用户不存在
        if j_data.get("statusCode") not in (0, None):
            return None
        return (j_data.get("userInfo") or {}).get("user") or None

    def _extract_stream_urls(self, stream_data_obj):
        """从 streamData / hevcStreamData 中提取 ({档位: flv_url}, common_dict)

        关键事实：pull_data.stream_data 是字符串，必须二次 json.loads。
        返回 tuple 第二个元素为 inner 的 common 字段（含 room_id），调用方可直接使用，
        避免对同一 stream_data 重复 json.loads。
        """
        if not stream_data_obj:
            return {}, {}
        inner_raw = (stream_data_obj.get("pull_data") or {}).get("stream_data")
        if not inner_raw:
            return {}, {}
        try:
            inner = json.loads(inner_raw)
        except json.JSONDecodeError:
            return {}, {}
        result = {}
        for quality, qv in (inner.get("data") or {}).items():
            flv = (qv or {}).get("main", {}).get("flv")
            if flv:
                result[quality] = flv
        return result, inner.get("common") or {}

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

    def _build_port_info(self, user, live_room, record_url, file_path):
        """合并达人数据 + 直播流数据为 port_info 结构

        Args:
            user: 个人页 webapp.user-detail 的 user 对象（必填）
            live_room: 直播页 SIGI_STATE.LiveRoom.liveRoomUserInfo.liveRoom（开播时存在）
            record_url: 原始请求 URL
            file_path: 本地保存路径标识
        """
        # 用户基础信息（始终存在）
        port_info = {
            "secUid": str(user.get("secUid") or ""),
            "uniqueId": str(user.get("uniqueId") or ""),
            "roomId": str(user.get("roomId") or ""),
            "signature": str(user.get("signature") or ""),
            "id": str(user.get("id") or ""),
            "nickname": str(user.get("nickname") or ""),
            "url": record_url,
            "filePath": file_path,
        }

        # 未开播：流字段留空，由 classify_tiktok_result 翻译为 code=2001
        if not live_room or live_room.get("status") != 2:
            port_info["flv_url"] = ""
            port_info["startTime"] = ""
            return port_info

        # 开播中：抽取 H264 + H265 多档位 FLV
        h264, h264_common = self._extract_stream_urls(live_room.get("streamData"))
        h265, _ = self._extract_stream_urls(live_room.get("hevcStreamData"))

        # play_urls：H265 优先（清晰度档位更全）+ H264 补充
        play_urls = []
        for tier in ("origin", "uhd_60", "hd_60", "hd", "sd", "ld", "ao"):
            if tier in h265 and h265[tier] not in play_urls:
                play_urls.append(h265[tier])
        for tier in ("hd", "ld", "ao"):
            if tier in h264 and h264[tier] not in play_urls:
                play_urls.append(h264[tier])

        # 首选 flv_url：H265 origin > H265 hd > H264 hd > 列表首位
        flv_url = (
            h265.get("origin") or h265.get("hd")
            or h264.get("hd") or (play_urls[0] if play_urls else "")
        )

        # 优先用 streamData 内 common.room_id（更可靠）
        room_id = h264_common.get("room_id")
        if room_id:
            port_info["roomId"] = str(room_id)

        port_info["flv_url"] = flv_url
        port_info["play_urls"] = play_urls
        port_info["startTime"] = str(live_room.get("startTime") or "")
        return port_info

    def get_tiktok_stream_data_requests(self, url, cookie_list):
        """采集流程：并发请求个人页 + 直播页，合并结果

        - Task 0: GET /@<handle>，抽 webapp.user-detail
        - Task 1: GET /@<handle>/live，抽 SIGI_STATE 中 LiveRoom 流地址
        - 合并字段为 port_info
        """
        try:
            handle = self._extract_handle(url)
            if not handle:
                return self._make_error(url, "URL 无法解析 handle")

            file_path = handle.replace(".", "_")

            # 并发请求：个人页 + 直播页同时发出
            profile_url = f"https://www.tiktok.com/@{handle}"
            live_url = f"https://www.tiktok.com/@{handle}/live"
            tasks = [
                Task(url=profile_url, task_id="profile", headers=self._build_profile_headers()),
                Task(url=live_url, task_id="live", headers=self._build_live_headers()),
            ]
            results = self._downloader.run(tasks)
            profile_result, live_result = results[0], results[1]

            # 解析个人页
            if not profile_result.success:
                logger.warning("请求个人页失败: %s | %s", profile_url, profile_result.error)
                return self._make_error(
                    url, f"请求个人页失败: {profile_result.error}",
                    profile_result.status_code,
                )

            user = self._parse_profile_user(profile_result.text)
            if not user:
                return {
                    "flv_url": "",
                    "roomId": "",
                    "message": "用户信息不存在",
                    "url": url,
                }

            # 解析直播页
            if not live_result.success:
                logger.warning("请求直播页失败: %s | %s", live_url, live_result.error)
                return self._build_port_info(user, None, url, file_path)

            sigi_match = SIGI_RE.search(live_result.text)
            if not sigi_match:
                return self._build_port_info(user, None, url, file_path)

            try:
                sigi = json.loads(sigi_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning("SIGI_STATE JSON 解析失败: %s", e)
                return self._make_error(url, f"页面解析失败: {e}")

            live_room_user_info = (
                (sigi.get("LiveRoom") or {}).get("liveRoomUserInfo") or {}
            )
            live_room = live_room_user_info.get("liveRoom") or {}

            live_user = live_room_user_info.get("user") or user
            return self._build_port_info(live_user, live_room, url, file_path)

        except Exception as e:
            logger.error("get_tiktok_stream_data_requests 异常: %s", e, exc_info=True)
            return self._make_error(url, f"采集内部异常: {e}")

    # 传入直播间地址，解析获取真实直播流地址信息
    def getLiveStreamInfo_requests(self, record_url, cookie_list, OP=None):
        try:
            return self.get_tiktok_stream_data_requests(url=record_url, cookie_list=cookie_list)
        except Exception as e:
            logger.error("getLiveStreamInfo_requests 异常: %s", e, exc_info=True)
            return {'flv_url': 'error', 'roomId': '', 'message': 'tk采集异常', 'filePath': ''}

if __name__ == '__main__':
    # 简易手动测试：少量代理样例即可
    ipList = [
        'senspower:T9u_SCK5Bezq@96.62.57.99:2333',
        'senspower:T9u_SCK5Bezq@96.62.57.98:2333',
        'senspower:T9u_SCK5Bezq@96.62.57.41:2333',
    ]
    tiktokTool = TiktokTool(ipList)

    times = []
    for i in range(2):
        start_time = time.time()
        try:
            # room_url = "https://www.tiktok.com/@greameofficialstore/live" #18岁禁止
            room_url = "https://www.tiktok.com/@sanjieyou/live" #正常
            # room_url = "https://www.tiktok.com/@koh.gen.do.my/live" #没有直播
            port_info = tiktokTool.getLiveStreamInfo_requests(room_url, ipList) or {}
            print(port_info)
        except Exception:
            print("解析错误", room_url)
        finally:
            cost = time.time() - start_time
            times.append(cost)
            print(f"耗时:{cost:.2f}")

    print(f"平均请求耗时: {sum(times) / len(times):.2f}秒")
    print(f"最长请求耗时: {max(times):.2f}秒")

