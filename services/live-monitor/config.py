"""live-monitor 配置访问层（门面）。

所有业务配置统一从 Apollo 读取（唯一权威源）。
- 节点配置/代理池/流控参数: 读取点实时调用,享热更新,禁止存模块级常量
- 连接类配置（Redis/Kafka/MySQL/Holo）: 由调用方启动时读一次
仅 APOLLO_URL/APOLLOID/DEPLOY_ENV 走环境变量（见 core/apollo/__init__.py）。
"""
from __future__ import annotations

import json
import os
import socket

from core.apollo import APOLLO


# ========== 辅助函数 ==========
def _get_str(key: str, default: str = "") -> str:
    """获取字符串配置"""
    val = APOLLO.get_value(key, default_val=default)
    return default if val is None else str(val)


def _get_int(key: str, default: int, minimum: int | None = None) -> int:
    """获取整数配置，支持最小值约束"""
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


def _get_float(key: str, default: float, minimum: float | None = None) -> float:
    """获取浮点数配置，支持最小值约束"""
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


def _get_json(key: str, default: list | dict) -> list | dict:
    """获取 JSON 配置（自动解析 JSON 数组/对象字符串）"""
    raw = APOLLO.get_value(key, default_val=None)
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


# ========== 连接类配置（启动读一次）==========
def redis_config() -> dict[str, object]:
    """Redis 连接参数"""
    return {
        "host": _get_str("redis.host"),
        "port": _get_int("redis.port", 6379),
        "password": _get_str("redis.password") or None,
        "db": _get_int("redis.db", 0),
    }


def kafka_servers() -> list[str]:
    """Kafka broker 列表。值为逗号分隔字符串,取出即用,不再 eval"""
    raw = _get_str("kafka.servers")
    return [s.strip() for s in raw.split(",") if s.strip()]


def kafka_topic() -> str:
    """Kafka topic"""
    return _get_str("live_monitor.kafka.topic", "liveTs")


def mysql_config() -> dict[str, object]:
    """MySQL 连接参数"""
    return {
        "host": _get_str("mysql.host"),
        "port": _get_int("mysql.port", 3306),
        "user": _get_str("mysql.user"),
        "password": _get_str("mysql.password"),
        "database": _get_str("mysql.database"),
        "charset": "utf8mb4",
    }


def holo_config() -> dict[str, object]:
    """Holo 数据库连接参数（测试环境返回空字典）"""
    host = _get_str("holo.host")
    if not host:
        return {}

    return {
        "host": host,
        "port": _get_int("holo.port", 80),
        "dbname": _get_str("holo.dbname"),
        "user": _get_str("holo.user"),
        "password": _get_str("holo.password"),
    }


def oss_config() -> dict[str, str]:
    """阿里云 OSS 连接参数"""
    return {
        "endpoint": _get_str("oss.endpoint"),
        "bucket_name": _get_str("oss.bucket_name"),
        "access_key_id": _get_str("oss.access_key_id"),
        "access_key_secret": _get_str("oss.access_key_secret"),
    }


# ========== 节点配置（实时热更新）==========
def node_id() -> str:
    """节点标识（node1=主节点，node2=备节点）"""
    return _get_str("live_monitor.node_id", "node1")


def node_ip() -> str:
    """节点 IP（支持自动检测回退）"""
    configured = _get_str("live_monitor.node_ip").strip()
    if configured and configured != "127.0.0.1":
        return configured

    # 回退到自动检测
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip
    except Exception:
        return "127.0.0.1"


def priority() -> int:
    """节点优先级（主节点 100，备节点 50）"""
    return _get_int("live_monitor.priority", 100)


def backup_node_url() -> str:
    """备用节点 URL"""
    return _get_str("live_monitor.backup_node_url", "")


def is_primary_node() -> bool:
    """是否主节点"""
    return node_id() == "node1"


# ========== 代理配置（实时热更新）==========
def static_proxy_pool() -> list[str]:
    """静态代理池（300 IP，从 Apollo JSON 数组解析）"""
    return _get_json("live_monitor.proxy.static_pool", [])


def abroad_proxy_pool() -> list[str]:
    """海外代理池（从 Apollo JSON 数组解析）"""
    return _get_json("live_monitor.proxy.abroad_pool", [])


# ========== 功能配置（实时热更新）==========
def access_key_activation() -> str:
    """激活码密钥"""
    return _get_str("live_monitor.access_key_activation", "")


def api_host() -> str:
    """API 监听地址"""
    return _get_str("live_monitor.api.host", "0.0.0.0")


def api_port() -> int:
    """API 监听端口"""
    return _get_int("live_monitor.api.port", 8080)


def api_access_token() -> str:
    """API 访问 token"""
    return _get_str("live_monitor.api.access_token", "")


def detect_interval_seconds() -> int:
    """直播间状态检测间隔（秒）"""
    return _get_int("live_monitor.api.detect_interval_seconds", 60, minimum=10)


# ========== 调度器配置（实时热更新）==========
def scheduler_check_frequency() -> int:
    """定时任务检查频率（秒）"""
    return _get_int("live_monitor.scheduler.check_frequency", 180, minimum=60)


def scheduler_interval() -> int:
    """采集任务间隔（秒）"""
    return _get_int("live_monitor.scheduler.interval", 8, minimum=1)


def scheduler_consumer_thread_num() -> int:
    """消费者线程数"""
    return _get_int("live_monitor.scheduler.consumer_thread_num", 8, minimum=1)


# ========== 房间配置（实时热更新）==========
def room_max_number() -> int:
    """单次分配直播间数量上限"""
    return _get_int("live_monitor.room.max_number", 8, minimum=1)


def room_cut_live_number() -> int:
    """切片直播间数量"""
    return _get_int("live_monitor.room.cut_live_number", 10, minimum=1)


def redis_status_ttl_seconds() -> int:
    """Redis 直播状态 TTL（秒）"""
    return _get_int("live_monitor.redis_status_ttl_seconds", 900, minimum=60)


# ========== 环境判断（取代旧环境变量）==========
def is_test_env() -> bool:
    """判断是否为测试环境（取代旧环境变量）

    基于 DEPLOY_ENV 环境变量判断：
    - dev* / test* → 测试环境
    - PRO / prod* → 生产环境
    """
    cluster = os.environ.get("DEPLOY_ENV", "dev02").lower()
    return cluster.startswith("dev") or cluster.startswith("test")

# ========== 兼容旧 config.py 的静态配置 ==========
# 获取当前文件所在文件夹绝对路径
def get_current_directory():
    current_file_path = os.path.abspath(__file__)
    current_directory = os.path.dirname(current_file_path)
    return current_directory.replace("\\", '/')


# MCP配置
MCP_config = {
    "DEEPSEEK_API_KEY": ""
}

# 账号配置
account_config = {
    "ttUser": "paidaxing"
}

# 版本历史记录
version_history = [
    {
        "version": "v1.0.0",
        "releaseDate": "2025-04-27",
        "updates": [
            {
                "type": "feature",
                "items": [
                    "页面重构上线",
                    "添加直播间存在验证接口"
                ]
            },
            {
                "type": "improvement",
                "items": [
                    "优化直播间多次请求获取地址问题",
                    "加快响应50%"
                ]
            },
            {
                "type": "fix",
                "items": [
                    "修复账号风控问题"
                ]
            }
        ]
    }

]

# 初始浏览器调动配置设置
brower_config = {
    "Chromium": {
        "chrome_driver_path": "",  # 浏览器驱动driver路径,默认为空
        "initNum": 1,  # 启动浏览器数量,默认为1个浏览器
        "tabNum": 1,  # 每个浏览器打开的标签页数量，默认为1
        "isheadless": True,  # 是否无头模式，默认为否
        "proxyItem": [],  # 代理设置，默认为空
        "timeOuts": 15,  # 加载等待-默认为15秒
        "isincognito": False,  # 是否匿名无痕模式，默认为否
        "extensionPath": "",  # 加载插件路径，默认为空
        "downloadPath": "download"  # 文件下载保存地址,默认为download文件夹
    }
}

# 监听web url配置文件
requests_config = {'ShopeeLive': {'LiveRoomLink': {'addOPExec': '',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://my.shp.ee/mLYd9Av'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/shopeeInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': '',
                                                   'listenUrl': '',
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'TiktokLive': {'LiveRoomLink': {'addOPExec': 'TiktokLiveAddOP(OP,tabItem)',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://www.tiktok.com/@petersonslabbeauty/live'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/portInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': 'TiktokLiveUrl(taskParams)',
                                                   'listenUrl': ['user/room?aid=1988'],
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'LazadaLive': {'LiveRoomLink': {'addOPExec': '',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://s.lazada.com.my/s.Gl8c1'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/lazadaInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': '',
                                                   'listenUrl': '',
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'socket': {'CJ_version_data': {'addOPExec': '',
                                                  'doc': {
                                                      'defaultParams': {'user_type': {'type': 'string', 'value': '5'}},
                                                      'description': '获取版本对应的插件安装信息',
                                                      'docsLinks': [],
                                                      'endpoint': 'http://47.236.42.104:8081/CJ_version_data',
                                                      'headers': {},
                                                      'method': 'GET',
                                                      'responseFieldDescription': {}},
                                                  'generateRequestsUrl': '',
                                                  'listenUrl': '',
                                                  'mateUrl': '',
                                                  'parseFunc': '',
                                                  'saveFunc': ''},
                              'check_cj': {'addOPExec': '',
                                           'doc': {'defaultParams': {},
                                                   'description': '校验插件与直播间关系',
                                                   'docsLinks': [],
                                                   'endpoint': 'http://47.236.42.104:8081/get_check_CJ_data',
                                                   'headers': {},
                                                   'method': 'GET',
                                                   'responseFieldDescription': {}},
                                           'generateRequestsUrl': '',
                                           'listenUrl': '',
                                           'mateUrl': '',
                                           'parseFunc': '',
                                           'saveFunc': ''},
                              'socketOnlineUserID': {'addOPExec': '',
                                                     'doc': {'defaultParams': {},
                                                             'description': '获取当前链接的插件ID',
                                                             'docsLinks': [],
                                                             'endpoint': 'http://47.236.42.104:8080/socketOnlineUserID',
                                                             'headers': {},
                                                             'method': 'GET',
                                                             'responseFieldDescription': {}},
                                                     'generateRequestsUrl': '',
                                                     'listenUrl': '',
                                                     'mateUrl': '',
                                                     'parseFunc': '',
                                                     'saveFunc': ''}}}

# 爬虫数据需求池
data_need_pool = []
