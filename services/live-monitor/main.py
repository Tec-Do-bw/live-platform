import queue
import asyncio
import requests
from fastapi import FastAPI, Request
from fastapi import Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import uvicorn
import os
from dotenv import load_dotenv
from parseMian import *

# ✅ 加载 .env 文件中的环境变量
load_dotenv()
from utils.Tools import ProducerTask, spiderLogWrite, get_current_directory
from base import OperateHelper
from config import brower_config
from starlette.middleware.sessions import SessionMiddleware
import secrets
import importlib
from utils.api_response import (
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
)


def get_requests_config():
    config_module = importlib.import_module('config')
    importlib.reload(config_module)
    return config_module.requests_config


from urllib.parse import unquote
import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
import pymysql
import signal
import sys

# ✅ 导入日志系统
from utils.logger import Logings

logger = Logings().get_logger()

# ✅ 导入数据库连接池
from utils.db_pool import db_pool

# ✅ 全局锁保护 all_Live_Room_dict，防止并发竞态条件
room_dict_lock = threading.Lock()

# ✅ 调度器线程监控相关变量
scheduler_thread = None  # 调度器线程引用
scheduler_last_heartbeat = 0  # 最后心跳时间

# ✅ 导入额外的定时任务调度器
try:
    from start_scheduler import main as start_scheduler_main

    SCHEDULER_AVAILABLE = False
    logger.warning("暂时不做旧模板采集功能,GMV/T+1/基本信息采集任务将不可用")
except ImportError:
    logger.warning("start_scheduler 模块未找到，GMV/T+1/基本信息采集任务将不可用")
    SCHEDULER_AVAILABLE = False

# 导入路由
from routes.docs import router as docs_router
from routes.activation import router as activation_router
from routes.websocket_routes import router as websocket_router, start_background_tasks, manager
from utils.serverTool import fetch_apollo_config
from utils.TiktokTool import TiktokTool
from utils.ShopeeTool import ShopeeTool
from utils.LazadaTool import LazadaTool
from get_tt_Cookies import getCookies
from check_cj_data import check_CJ_data

# ✅ ✅ ✅ ✅ 以下是基础配置相关设置 ✅ ✅ ✅ ✅ ✅ 

# ========== 节点配置（主备部署）==========
# ⚠️ 部署时需要修改以下参数
# 主机1: NODE_ID='node1', NODE_IP='47.237.6.199', PRIORITY=100
# 主机2: NODE_ID='node2', NODE_IP='47.236.42.104', PRIORITY=50

NODE_ID = os.environ.get('NODE_ID', 'node1')  # 节点ID
NODE_IP = os.environ.get('NODE_IP', '127.0.0.1')  # 节点IP
PRIORITY = int(os.environ.get('PRIORITY', '100'))  # 节点优先级
BACKUP_NODE_URL = os.environ.get('BACKUP_NODE_URL', '')  # 备用节点URL
ISTEST = int(os.environ.get('ISTEST', '1'))

logger.info(f"节点配置 | NODE_ID={NODE_ID}, NODE_IP={NODE_IP}, PRIORITY={PRIORITY}, BACKUP_NODE_URL={BACKUP_NODE_URL}")
OP = None


# 使用lifespan替代on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    task = start_background_tasks()
    yield
    # 关闭时执行
    logger.info("=" * 60)
    logger.info("🛑 程序正在关闭，清理资源...")
    logger.info("=" * 60)

    # 取消后台任务
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # ✅ 关闭数据库连接池
    try:
        if db_pool:
            logger.info("正在关闭数据库连接池...")
            db_pool.close()
            logger.info("✅ 数据库连接池已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接池时出错: {e}", exc_info=True)

    logger.info("🎉 资源清理完成，程序已安全退出")


# 创建 FastAPI 实例对象
app = FastAPI(lifespan=lifespan)

# 添加会话中间件，用于用户认证
app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_hex(32),  # 使用随机生成的密钥
    session_cookie="sensortower_session",  # 会话cookie名称
    max_age=86400,  # 会话有效期，单位为秒，这里设置为24小时
)

# 注册路由
app.include_router(docs_router)
app.include_router(activation_router)
# app.include_router(websocket_router)


# 配置静态文件服务
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 解决跨域问题（浏览器插件也需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 路由：修复代理路径
@app.middleware("http")
async def fix_proxy_path(request: Request, call_next):
    # 获取原始路径并解码
    raw_path = unquote(request.scope["path"])  # 解码 %3A 等符号

    # 匹配类似 "http://domain:port/sensortower/data" 的路径
    if "http://" in raw_path or "https://" in raw_path:
        # 使用正则提取正确的路径部分
        match = re.search(r'http[s]?://[^/]+(/.*)', raw_path)
        if match:
            corrected_path = match.group(1)
            request.scope["path"] = corrected_path  # 修改请求路径
    # 继续处理请求
    response = await call_next(request)
    return response


# 心跳接口（保留兼容性）
@app.get("/check_status")
def check_status():
    return {"code": 200, "message": "live-spider-API-V2-boss-server is running"}


# 健康检查接口（主备架构专用）
@app.get("/health")
def health_check():
    """
    健康检查端点（主备节点通过此接口判断服务器状态）
    返回节点信息、连接数和房间数
    """
    return {
        "code": 200,
        "status": "healthy",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "node_id": NODE_ID,
        "priority": PRIORITY,
        "node_ip": NODE_IP,
        "room_count": len(all_Live_Room_dict) if 'all_Live_Room_dict' in globals() else 0,
        "ws_connections": len(manager.active_connections),
    }


# ✅ ✅ ✅ ✅ 以下是核心框架逻辑 ✅ ✅ ✅ ✅ ✅

# 离线脚本执行状态字典
offline_script_config_dict = {}

# 甲方爸爸需求池：任务队列
taskQ = queue.Queue()


# HR招聘专员：哨兵巡视是否有牛马离职或者逃岗(因为意外情况或者人为因素导致浏览器关闭)
def sentryTabItem(args):
    tabItemQ = args[0]
    browserObjList = args[1]
    # 判断如果有离线或者挂掉的浏览器进程，则需要重启
    # print("browserObjList-->",browserObjList)
    while True:
        new_browserObjList, result = OP.sentryItem(browserObjList)
        # 判断从tabItemQ队列中取出的tab标签页对象，不在新的浏览器对象列表中，则抛弃
        # 在消费者线程中进行对比，这里只做全局赋值
        new_obj_tabs_list = list()
        for new_browserObj in new_browserObjList:
            new_obj_tabs_list.extend(new_browserObj["tabs"])
        # global All_tabs_list
        All_tabs_list = new_obj_tabs_list

        # 对于新加的tab标签页，需要添加入tabItemQ队列中
        for rs in result:
            tabItemQ.put(rs)
        # 检测完毕后，用新的new_browserObjList替换旧的browserObjList
        browserObjList = new_browserObjList
        # print("All_tabs_list-->",All_tabs_list)
        # print("len(All_tabs_list)",str(len(All_tabs_list)))

        # ✅ 离线脚本运行检测与启动 ✅
        # 动态读取离线脚本配置
        taskList = []
        # 读取离线脚本配置文件
        try:
            offline_config_path = os.path.join(os.path.dirname(__file__), "OfflineSpider", "offlineConfig.json")
            with open(offline_config_path, "r", encoding="utf-8") as f:
                offline_config = json.load(f)

            # 创建一个临时集合来跟踪当前配置中的有效脚本
            current_active_scripts = set()

            # 处理配置信息
            current_time = datetime.now()
            current_hour = current_time.hour  # 获取当前小时数值

            for platform, scripts in offline_config.items():
                for script in scripts:
                    script_name = script.get("script", "")
                    status = script.get("status", 0)  # 0表示禁用，1表示启用
                    cycle_time = script.get("cycleTime", 86400)  # 默认24小时执行一次
                    start_time = script.get("start_time", "")  # 获取start_time
                    script_key = f"{platform}_{script_name}"

                    # 如果脚本启用状态为1
                    if status == 1:
                        # 将当前活跃脚本添加到跟踪集合
                        current_active_scripts.add(script_key)

                        # 如果脚本不在字典中，则添加
                        if script_key not in offline_script_config_dict:
                            offline_script_config_dict[script_key] = {
                                "lastRunTime": None
                            }

                        last_run_time = offline_script_config_dict[script_key].get("lastRunTime")

                        # 检查是否满足执行条件
                        should_run = False

                        # 如果脚本从未运行或已经超过周期时间
                        if not last_run_time or (current_time - last_run_time).total_seconds() >= cycle_time:
                            # 如果存在start_time，需要检查当前小时是否匹配
                            if start_time:
                                # 将start_time转换为整数进行比较
                                try:
                                    start_hour = int(start_time)
                                    if current_hour == start_hour:
                                        should_run = True
                                except ValueError:
                                    # 如果start_time不是有效的整数，则忽略此条件
                                    should_run = True
                            else:
                                # 如果没有start_time，只需满足周期条件
                                should_run = True

                            # 如果满足所有执行条件，添加到待执行任务列表
                            if should_run:
                                taskList.append({
                                    "argsInfo": platform,
                                    "script": script_name
                                })

                                # 更新脚本状态启动时间
                                offline_script_config_dict[script_key] = {
                                    "lastRunTime": current_time
                                }
                                # 每次启动脚本，写入日志，作为分析页面
                                log_file_path = os.path.join(os.path.dirname(__file__), "OfflineSpider",
                                                             "crawl_log.log")
                                # 检查日志文件大小，如果超过5MB则重命名并创建新文件
                                if os.path.exists(log_file_path) and os.path.getsize(
                                        log_file_path) > 5 * 1024 * 1024:  # 5MB
                                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                                    log_dir = os.path.dirname(log_file_path)
                                    log_filename = os.path.basename(log_file_path)
                                    new_log_path = os.path.join(log_dir,
                                                                f"{os.path.splitext(log_filename)[0]}_{timestamp}.log")
                                    os.rename(log_file_path, new_log_path)
                                    # 创建新的日志文件
                                    with open(log_file_path, "w", encoding="utf-8") as f:
                                        pass
                                current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logContent = f"[{current_datetime}]" + "--->" + f"[{script_name}]" + " is start!"
                                spiderLogWrite(logContent, log_file_path=log_file_path)
                    else:
                        # 如果脚本状态为0且在字典中存在，则从字典中移除
                        if script_key in offline_script_config_dict:
                            del offline_script_config_dict[script_key]

            # 清理字典中不再活跃的脚本
            keys_to_remove = [key for key in offline_script_config_dict.keys() if key not in current_active_scripts]
            for key in keys_to_remove:
                del offline_script_config_dict[key]

        except Exception as e:
            logger.error(f"读取离线脚本配置文件失败: {e}", exc_info=True)

        # 执行满足条件的离线脚本
        if len(taskList) > 0:
            for argsInfo in taskList:
                producer_thread = threading.Thread(target=ProducerTask, args=(argsInfo,))
                producer_thread.daemon = True
                producer_thread.start()

        # 等待下次检测
        # print("当前离线脚本状态-->",offline_script_config_dict)
        # print('等待下次检测',str(datetime.now().strftime("%H:%M:%S")))
        time.sleep(300)


# 不存在(错误的直播间)的直播间
def get_error_room_url():
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    error_url_path = os.path.join(current_dir, "errorUrl.txt")
    with open(error_url_path, "r", encoding="utf-8") as f:
        live_error_room_url = [line.strip() for line in f]
    return live_error_room_url


def _check_error_url(mate_url: str, platform: str) -> dict | None:
    """检查 URL 是否在已知错误列表中，命中则返回标准错误响应"""
    try:
        error_urls = get_error_room_url()
        if mate_url in error_urls:
            return error_response(
                code=4041,
                reason=ErrorReason.ROOM_NOT_FOUND,
                detail="命中已知错误链接列表",
                platform=platform,
                mate_url=mate_url,
            )
    except FileNotFoundError:
        pass
    return None


# 获取TT直播间信息
@app.post("/liveRoom/portInfo")
async def portInfo(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="tiktok", mate_url=""
        ))

    err_resp = _check_error_url(mateUrl, "tiktok")
    if err_resp:
        return JSONResponse(content=err_resp)

    cookie_list = tiktokTool.get_cookie_list()
    tiktok_no_proxy = TiktokTool(ipList)
    raw = tiktok_no_proxy.getLiveStreamInfo_requests(mateUrl, cookie_list, OP)

    outcome = classify_tiktok_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="tiktok", mate_url=mateUrl
    ))


# 获取虾皮直播间信息（校验使用）
@app.post("/liveRoom/shopeeInfo")
async def get_shopee_live_info(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="shopee", mate_url=""
        ))

    logger.info(f"接收到Shopee直播间请求 | url={mateUrl}")

    err_resp = _check_error_url(mateUrl, "shopee")
    if err_resp:
        return JSONResponse(content=err_resp)

    try:
        raw = shopeeTool.get_shopee_live_info(mateUrl, proxy=False)
        logger.info(f"成功获取Shopee直播间信息 | url={mateUrl}")
    except Exception as e:
        logger.error(f"获取Shopee直播间失败 | url={mateUrl} error={e}", exc_info=True)
        raw = None

    outcome = classify_shopee_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="shopee", mate_url=mateUrl
    ))


# 获取lazada直播间信息（校验使用）
@app.post("/liveRoom/lazadaInfo")
async def get_lazadalive_info(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="lazada", mate_url=""
        ))

    logger.info(f"接收到lazada直播间请求 | url={mateUrl}")

    try:
        raw = lazadaTool.get_lazada_live_info(mateUrl, proxy=False)
        logger.info(f"成功获取lazada直播间信息 | url={mateUrl}")
    except Exception as e:
        logger.error(f"获取lazada直播间失败 | url={mateUrl} error={e}", exc_info=True)
        raw = None

    outcome = classify_lazada_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="lazada", mate_url=mateUrl
    ))



@app.get("/getCookies")
def getCookiesMian():
    cookiesList = getCookies()
    return {"code": 200, "message": "success", "data": cookiesList}


# 注意：/socketOnlineUserID 和 /get_check_CJ_data 路由已迁移到 routes/websocket_routes.py


# ========== 主备节点数据同步接口 ==========

@app.post("/sync_room_dict")
async def sync_room_dict(request: Request):
    """
    接收主节点同步的直播间状态数据
    备节点通过此接口接收主节点的 all_Live_Room_dict
    """
    try:
        body = await request.json()
        room_dict = body.get("room_dict", {})
        timestamp = body.get("timestamp", 0)
        source_node_id = body.get("node_id", "unknown")

        # 只有备节点才接收数据同步
        if NODE_ID != 'node1':
            global all_Live_Room_dict
            all_Live_Room_dict = room_dict
            logger.info(f"[数据同步] 接收到主节点 {source_node_id} 的房间数据 | 数量={len(room_dict)}")

        return {"code": 200, "message": "同步成功", "received_count": len(room_dict)}
    except Exception as e:
        logger.error(f"[数据同步] 房间数据同步失败: {e}", exc_info=True)
        return {"code": 500, "message": f"同步失败: {e}"}


@app.post("/sync_offline_scripts")
async def sync_offline_scripts(request: Request):
    """
    接收主节点同步的离线脚本状态
    备节点通过此接口接收主节点的 offline_script_config_dict
    """
    try:
        body = await request.json()
        offline_scripts = body.get("offline_scripts", {})
        timestamp = body.get("timestamp", 0)
        source_node_id = body.get("node_id", "unknown")

        # 只有备节点才接收数据同步
        if NODE_ID != 'node1':
            global offline_script_config_dict
            offline_script_config_dict = offline_scripts
            logger.info(f"[数据同步] 接收到主节点 {source_node_id} 的离线脚本状态 | 数量={len(offline_scripts)}")

        return {"code": 200, "message": "同步成功", "received_count": len(offline_scripts)}
    except Exception as e:
        logger.error(f"[数据同步] 离线脚本同步失败: {e}", exc_info=True)
        return {"code": 500, "message": f"同步失败: {e}"}

    # 客户端获取当前可用的房间接口


@app.post("/get_roominfo")
async def get_roominfo(request: Request):
    body = await request.json()
    # 获取当前秒级时间戳
    current_timestamp = int(time.time())

    # 从body中获取ip
    ip = body.get("ip", "")

    logger.debug(f"客户端请求房间 | IP={ip} 当前房间数={len(all_Live_Room_dict)}")

    selected_room = None
    
    # ✅ 加锁保护，确保"查找-更新"操作的原子性，防止并发竞态条件
    with room_dict_lock:
        for room_id, room_info in all_Live_Room_dict.items():
            status_update_time = room_info.get("status_update_time")
            allocation_status = room_info.get("allocation_status")
            live_info = room_info.get("live_info")

            # 检查是否满足条件：当前时间戳大于status_update_time 5分钟(300秒)，且allocation_status=0,且当前是正在直播的直播间
            if (current_timestamp > (int(status_update_time) + 300)) and str(allocation_status) == "0" and len(
                    live_info.get("flv_url", "")) > 0:
                logger.info(f"找到可分配房间 | room_id={room_id} url={room_info.get('room_url')}")

                selected_room = room_info.copy()  # 复制对象以返回
                selected_room["room_id"] = room_id  # 添加room_id到返回对象中
                
                # ✅ 立即设置 allocation_status="1"（关键修复！）
                # 防止其他并发请求也获取到同一房间
                all_Live_Room_dict[room_id]["allocation_status"] = "1"
                all_Live_Room_dict[room_id]["status_update_time"] = current_timestamp
                all_Live_Room_dict[room_id]["ip"] = ip
                
                logger.info(f"✅ 房间分配成功 | room_id={room_id} IP={ip}  url={room_info.get('room_url')}")
                break

    # 如果找到满足条件的对象，返回该对象；否则返回空
    if selected_room:
        logger.info(f"房间分配成功 | room_id={selected_room['room_id']} IP={ip}")
        response = {"code": 200, "message": "获取成功", "data": selected_room}
    else:
        logger.debug(f"暂无可用房间 | IP={ip}")
        response = {"code": 200, "message": "暂无可用房间", "data": {}}
    return JSONResponse(content=response)


# 接收上报信息、3分钟上报一次
@app.post("/report_roominfo")
async def report_roominfo(request: Request):
    body = await request.json()
    # 获取当前时间戳
    current_timestamp = int(time.time())

    # 用于收集allocation_status更新为0的room_id
    released_room_ids = []

    logger.debug(f"接收到客户端上报 | 房间数={len(body)}")

    # ✅ 加锁保护，确保状态更新的一致性
    with room_dict_lock:
        # 遍历body中的数据
        for room_id, room_info in body.items():
            status_update_time = room_info.get("status_update_time", 0)

            # 只要上报了，说明客户端在线，直接更新状态
            if room_id in all_Live_Room_dict:
                all_Live_Room_dict[room_id]["status_update_time"] = current_timestamp
                all_Live_Room_dict[room_id]["allocation_status"] = "1"
                logger.debug(f"房间状态更新 | room_id={room_id} status=1 (正常上报)")
            else:
                # 如果房间不在all_Live_Room_dict中（可能被后台移除），则通知客户端停止
                released_room_ids.append(room_id)

    response = {"code": 200, "message": "上报成功", "released_rooms": released_room_ids}
    return JSONResponse(content=response)


"""
    1. 获取数据库中所有待检测的直播间
    2. 更新all_Live_Room_dict(新增新添加的直播间)
    3. 删除all_Live_Room_dict中不存在于新查询中的对象(已经不在监控的移除)
"""


def select_Info():
    sql = "select room_id,room_url,allocation_status from live_streaming_room where local_status = 1 "

    logger.info(f"开始从数据库同步直播间列表 | database={database}")

    # ✅ 直接使用连接池查询
    result = db_pool.execute_query(sql)
    # 处理数据库查询结果，更新all_Live_Room_dict
    if result:
        # ✅ 加锁保护：更新all_Live_Room_dict
        with room_dict_lock:
            # 获取当前result中的room_id列表
            current_room_ids = set()
            # result = [('15eaf18d772d4113ba6ab298581d438d', 'https://ph.shp.ee/DT7Tpev', '0')]
            for row in result:
                room_id, room_url, allocation_status = row
                current_room_ids.add(room_id)

                # ✅ 如果room_id不存在于all_Live_Room_dict中，则添加
                if room_id not in all_Live_Room_dict:
                    all_Live_Room_dict[room_id] = {
                        "room_url": room_url,
                        "allocation_status": "0",
                        "status_update_time": 0,
                        "ip": "",
                        "live_info": {}
                    }
                    logger.debug(f"新增监控房间 | room_id={room_id} url={room_url}")

            # ✅ 删除all_Live_Room_dict中不存在于新result中的对象(已经不在监控的移除)
            keys_to_remove = []
            for room_id in all_Live_Room_dict.keys():
                if room_id not in current_room_ids:
                    keys_to_remove.append(room_id)

            for room_id in keys_to_remove:
                del all_Live_Room_dict[room_id]
                logger.info(f"移除监控房间 | room_id={room_id}")

    # print("更新后的all_Live_Room_dict:", all_Live_Room_dict)
    logger.info(f"数据库同步完成 | 当前监控房间数={len(all_Live_Room_dict)}")


"""
循环校验直播间是否正在直播
# 取出所有cookies,监控列表中取出所有未直播的直播间,进行直播检测
"""


def check_single_room(room_id, room_url, cookie_list, live_error_room_url):
    """
    检查单个直播间状态的函数（用于多线程调用）
    
    Args:
        room_id: 房间ID
        room_url: 房间URL
        cookie_list: Cookie列表
        live_error_room_url: 错误房间URL列表
        
    Returns:
        tuple: (room_id, port_info, success)
    """
    if room_url in live_error_room_url:
        return room_id, None, False
        
    try:
        # ✅ 这里判断是虾皮还是tiktok,以后可能还有别的平台都是这里添加
        if "shp" in room_url and "tiktok" not in room_url:
            port_info = shopeeTool.get_shopee_live_info(room_url)
            play_urls = port_info.get("play_urls", []) or []
            logger.debug(f"Shopee房间检测完成 | room_id={room_id} 直播={len(play_urls) > 0}")
        elif "tiktok" in room_url:
            port_info = tiktokTool.getLiveStreamInfo_requests(room_url, cookie_list, OP) or {}
            flv_url = port_info.get("flv_url", "")
            logger.debug(f"TikTok房间检测完成 | room_id={room_id} 直播={len(flv_url) > 0}")
        else:
            raise Exception("不支持的直播平台")
        
        return room_id, port_info, True
    except Exception as e:
        logger.error(f"检测房间失败 | room_id={room_id} error={e}")
        return room_id, None, False


def check_live_status(cookie_list):
    print("开始校验直播间是否正在直播")
    current_time = int(time.time())
    
    # ✅ 加锁保护：收集初始数据
    with room_dict_lock:
        # 除了上报修改状态也需要服务端定时自检测状态(防止客户端上次上报结束后直接挂掉情况，导致服务端一直是allocation_status=1 的情况)
        for room_id, info in all_Live_Room_dict.items():
            # 这里阈值放宽，认为超过5分钟没有任何上报为挂掉
            if int(info.get("status_update_time", 0)) + 300 < current_time and info.get("allocation_status") == "1":
                all_Live_Room_dict[room_id]["allocation_status"] = "0"
                logger.info(f"🔓 房间已释放（自检超时）| room_id={room_id}")

        # 当前没有采集的直播间
        to_check_room_ids = []
        for room_id, info in all_Live_Room_dict.items():
            if str(info.get("allocation_status")) == "0" and int(info.get("status_update_time", 0)) + 180 < current_time:
                to_check_room_ids.append(room_id)
    
    # 开始遍历监控当前未采集的直播间信息，进行更新live_info，当live_info中存在直播真实链接信息的时候就会被获取采集
    logger.info(f"待检查直播间数量为：{len(to_check_room_ids)}")
    
    if len(to_check_room_ids) == 0:
        logger.info(f"=== 本轮检测完成 | 总房间数={len(all_Live_Room_dict)} | 无需检查房间 ===")
        return
    
    live_error_room_url = get_error_room_url()
    
    # ✅ 使用多线程并发检查直播间
    # 设置线程池大小（建议10-20个线程，避免过多并发请求）
    max_workers = min(3, len(to_check_room_ids))
    success_count = 0
    fail_count = 0
    check_results = {}  # 存储检查结果
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有检查任务
        future_to_room = {}
        for room_id in to_check_room_ids:
            # ✅ 释放锁后再访问 all_Live_Room_dict（不加锁，因为只是读）
            room_info = all_Live_Room_dict.get(room_id)
            if not room_info:
                continue
            
            room_url = room_info.get("room_url")
            future = executor.submit(check_single_room, room_id, room_url, cookie_list, live_error_room_url)
            future_to_room[future] = room_id
        
        # 处理完成的任务
        for future in as_completed(future_to_room):
            room_id = future_to_room[future]
            try:
                # ✅ 添加180秒超时，防止单个任务阻塞整个线程池
                returned_room_id, port_info, success = future.result(timeout=180)
                if success and port_info:
                    check_results[returned_room_id] = port_info
                    success_count += 1
                else:
                    fail_count += 1
            except TimeoutError:
                logger.error(f"⚠️ 检测房间超时(60s) | room_id={room_id}")
                fail_count += 1
            except Exception as e:
                logger.error(f"处理检测结果失败 | room_id={room_id} error={e}")
                fail_count += 1
    
    # ✅ 释放锁后的网络IO完成，现在加锁更新结果
    with room_dict_lock:
        for room_id, port_info in check_results.items():
            if room_id in all_Live_Room_dict:
                all_Live_Room_dict[room_id]["live_info"] = port_info
    
    # 统计当前正在采集的房间数
    collecting_count = 0
    for room_info in all_Live_Room_dict.values():
        if str(room_info.get("allocation_status")) == "1" and room_info.get("status_update_time") + 4*60 > current_time:
            collecting_count += 1
    
    logger.info(f"=== 本轮检测完成 | 总房间数={len(all_Live_Room_dict)} | 采集中={collecting_count} | 检查={len(to_check_room_ids)} | 成功={success_count} | 失败={fail_count} ===")


# ✅ 信号处理器：捕获终止信号，优雅关闭浏览器
def signal_handler(signum, frame):
    """
    处理 SIGINT (Ctrl+C) 和 SIGTERM 信号
    确保浏览器进程被正确关闭
    """
    logger.info("=" * 60)
    logger.info(f"🛑 接收到终止信号 ({signum})，正在清理资源...")
    logger.info("=" * 60)

    try:
        if db_pool:
            logger.info("正在关闭数据库连接池...")
            db_pool.close()
            logger.info("✅ 数据库连接池已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接池时出错: {e}", exc_info=True)

    logger.info("🎉 资源清理完成，程序退出")
    sys.exit(0)


def start_select_info_scheduler(ISTEST):
    """
    启动定时任务,每5分钟执行一次select_Info
    ✅ 支持主备切换：只有主节点执行任务，备节点监控主节点健康状态
    ✅ 支持数据同步：主节点每次执行后同步数据到备节点
    ✅ 支持线程健康监控：更新心跳时间，支持外部监控线程存活状态
    """
    global scheduler_thread, scheduler_last_heartbeat, scheduler_execution_count

    def scheduler():
        global scheduler_last_heartbeat, scheduler_execution_count

        logger.info("🚀 定时调度器已启动")

        # 主备切换相关变量
        primary_failed_count = 0
        max_failed_count = 3
        is_primary = (NODE_ID == 'node1')

        while True:
            try:
                # ✅ 更新心跳时间
                scheduler_last_heartbeat = int(time.time())
                
                # ========== 主备切换逻辑 ==========
                should_execute = is_primary  # 默认主节点执行

                # 如果是备节点，需要检查主节点健康状态
                if not is_primary and BACKUP_NODE_URL:
                    try:
                        response = requests.get(
                            f"{BACKUP_NODE_URL}/health",
                            timeout=3
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if data.get("code") == 200:
                                # 主节点健康
                                if primary_failed_count > 0:
                                    logger.info("[定时任务] 主节点已恢复，备节点停止执行")
                                primary_failed_count = 0
                                should_execute = False
                            else:
                                primary_failed_count += 1
                        else:
                            primary_failed_count += 1
                    except Exception as e:
                        primary_failed_count += 1
                        logger.warning(
                            f"[定时任务] 主节点健康检查失败 ({primary_failed_count}/{max_failed_count}): {e}")

                    # 连续失败3次，备节点接管
                    if primary_failed_count >= max_failed_count:
                        should_execute = True
                        if primary_failed_count == max_failed_count:
                            logger.warning(f"✅ [定时任务] 主节点故障，备节点 {NODE_ID} 接管任务执行")
                            webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/99d1046a-b872-448c-80eb-5dca6b816916"
                            data = {
                                "msg_type": "text",
                                "content": {
                                    "text": f"🚨 系统异常告警\n\n主节点爬虫服务异常，请手动重启\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                }
                            }
                            response = requests.post(webhook_url, json=data)

                # ========== 执行任务或待命 ==========
                if should_execute:
                    logger.info(f"[定时任务] 节点 {NODE_ID} 开始执行...")

                    try:
                        cookie_list = tiktokTool.get_cookie_list(getLiveCookiessql)
                        logger.info(f"Cookie池刷新成功 | 数量={len(cookie_list)}")
                    except Exception as e:
                        logger.error(f"获取Cookie列表出错: {e}", exc_info=True)
                        cookie_list = []  # 使用空列表继续执行

                    try:
                        select_Info()
                    except Exception as e:
                        logger.error(f"执行select_Info检查出错: {e}", exc_info=True)
                    try:
                        check_live_status(cookie_list)
                    except Exception as e:
                        logger.error(f"执行check_live_status检查出错: {e}", exc_info=True)

                    # ========== 主节点数据同步到备节点 ==========
                    if is_primary and BACKUP_NODE_URL:
                        try:
                            # 同步房间数据
                            requests.post(
                                f"{BACKUP_NODE_URL}/sync_room_dict",
                                json={
                                    "room_dict": all_Live_Room_dict,
                                    "timestamp": int(time.time()),
                                    "node_id": NODE_ID
                                },
                                timeout=5
                            )

                            # 同步离线脚本状态
                            requests.post(
                                f"{BACKUP_NODE_URL}/sync_offline_scripts",
                                json={
                                    "offline_scripts": offline_script_config_dict,
                                    "timestamp": int(time.time()),
                                    "node_id": NODE_ID
                                },
                                timeout=5
                            )
                            logger.info(f"[数据同步] 已同步数据到备节点 | 房间数={len(all_Live_Room_dict)}")
                        except Exception as e:
                            # 数据同步失败不影响主流程
                            logger.warning(f"[数据同步] 同步失败（不影响主流程）: {e}")
                else:
                    # 备节点待命
                    if datetime.now().minute % 5 == 0:  # 每5分钟输出一次日志
                        logger.info(f"[定时任务] 备节点 {NODE_ID} 待命中... (主节点正常运行)")

            except Exception as e:
                logger.error(f"定时任务执行出错: {e}", exc_info=True)

            logger.info("⏰ 等待下次检测（5分钟后）")
            # ✅ 分段 sleep，每30秒更新一次心跳，防止长时间 sleep 期间被误判为死亡
            for _ in range(10):  # 5分钟 = 300秒 = 10 * 30秒
                scheduler_last_heartbeat = int(time.time())
                time.sleep(30)

    scheduler_thread = threading.Thread(target=scheduler, daemon=True)
    scheduler_thread.start()
    scheduler_last_heartbeat = int(time.time())
    logger.info("✅ 定时调度器线程已启动")


def start_scheduler_monitor():
    """
    启动调度器线程监控
    ✅ 每2分钟检查一次，心跳超时10分钟判定为死亡并自动重启
    """
    def monitor():
        logger.info("🔍 调度器监控线程已启动")
        
        while True:
            time.sleep(120)  # 每2分钟检查一次
            
            try:
                heartbeat_age = int(time.time()) - scheduler_last_heartbeat
                thread_alive = scheduler_thread is not None and scheduler_thread.is_alive()
                
                # 心跳超时10分钟（600秒）或线程死亡则重启
                if not thread_alive or heartbeat_age > 600:
                    reason = "线程已死亡" if not thread_alive else f"心跳超时({heartbeat_age}秒)"
                    logger.error(f"🚨 调度器异常 | {reason} | 正在重启...")
                    
                    # 发送飞书告警
                    try:
                        webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/99d1046a-b872-448c-80eb-5dca6b816916"
                        requests.post(webhook_url, json={
                            "msg_type": "text",
                            "content": {"text": f"🚨 实时直播流监控调度器异常\n节点: {NODE_ID}\n原因: {reason}\n操作: 自动重启"}
                        }, timeout=5)
                    except:
                        pass
                    
                    start_select_info_scheduler(ISTEST)
                    logger.info("✅ 调度器线程已重启")
                    
            except Exception as e:
                logger.error(f"调度器监控出错: {e}")
    
    threading.Thread(target=monitor, daemon=True).start()
    logger.info("✅ 调度器监控线程已启动")



# 获取所有直播间状态信息的路由
@app.get("/get_all_rooms")
def get_all_rooms(request: Request):
    """
    获取所有直播间的状态信息
    返回 all_Live_Room_dict，包括采集状态、房间URL、直播信息等
    """
    current_time = int(time.time())
    
    # 计算当前正在采集的房间数
    collecting_count = 0
    for room_info in all_Live_Room_dict.values():
        # ✅ 检查是否正在采集（allocation_status=1 且4分钟内有上报）
        if str(room_info.get("allocation_status", "0")) == "1" and \
           int(room_info.get("status_update_time", 0)) + 240 > current_time:
            collecting_count += 1
    
    # ✅ 构建响应数据（移到循环外）
    response_data = {
        'code': 200,
        'message': 'success',
        'data': {
            'total_rooms': len(all_Live_Room_dict),
            'collecting_rooms': collecting_count,
            'available_rooms': len(all_Live_Room_dict) - collecting_count,
            'rooms': all_Live_Room_dict.copy()
        }
    }
    
    logger.info(f"获取房间状态 | 总数={len(all_Live_Room_dict)} | 采集中={collecting_count} | 可用={len(all_Live_Room_dict) - collecting_count}")
    return JSONResponse(content=response_data)



# 资本家
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 liveSpider_Serverv2 正在启动...")
    logger.info("=" * 60)

    # ✅ 注册信号处理器（确保 Ctrl+C 时能优雅关闭浏览器）
    signal.signal(signal.SIGINT, signal_handler)
    # Windows 平台可能不支持 SIGTERM，需要条件注册
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    logger.info("✅ 信号处理器已注册")

    # 初始化操作类
    OP = OperateHelper(brower_config, useType="Chromium")

    # ###############以下是真正服务####################
    logger.info("获取Apollo配置...")
    config_data = fetch_apollo_config(ISTEST)
    # print(config_data)
    getLiveCookiessql = "SELECT cookies FROM live_account_info where cookies like '%true%'  order by id desc limit 20"
    host = config_data.get("devSqlHost")
    user = config_data.get("devSqlUser")
    password = config_data.get("devSqlPassword")
    database = config_data.get("database")
    port = int(config_data.get("devSqlPort"))

    # ✅ 初始化数据库连接池（不打印密码）
    logger.info(f"初始化数据库连接池 | host={host} database={database} port={port}")

    try:
        db_pool.initialize(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            max_connections=10,
            min_cached=2
        )
        logger.info("✅ 数据库连接池初始化成功")
    except Exception as e:
        logger.error(f"数据库连接池初始化失败: {e}", exc_info=True)
        import sys

        sys.exit(1)

    # ✅ 代理池配置
    try:
        if ISTEST == 1:
            ipList = ['senspower:T9u_SCK5Bezq@31.59.112.68:2333','senspower:T9u_SCK5Bezq@82.29.150.155:2333','senspower:T9u_SCK5Bezq@31.59.112.103:2333','senspower:T9u_SCK5Bezq@31.59.112.85:2333','senspower:T9u_SCK5Bezq@82.29.150.35:2333','senspower:T9u_SCK5Bezq@82.29.150.254:2333','senspower:T9u_SCK5Bezq@31.59.112.233:2333','senspower:T9u_SCK5Bezq@82.29.150.192:2333','senspower:T9u_SCK5Bezq@31.59.112.166:2333','senspower:T9u_SCK5Bezq@31.59.112.202:2333','senspower:T9u_SCK5Bezq@31.59.112.220:2333','senspower:T9u_SCK5Bezq@82.29.150.187:2333','senspower:T9u_SCK5Bezq@82.29.150.102:2333','senspower:T9u_SCK5Bezq@31.59.112.213:2333','senspower:T9u_SCK5Bezq@167.148.104.151:2333','senspower:T9u_SCK5Bezq@167.148.104.72:2333','senspower:T9u_SCK5Bezq@167.148.104.79:2333','senspower:T9u_SCK5Bezq@167.148.104.252:2333','senspower:T9u_SCK5Bezq@167.148.104.54:2333','senspower:T9u_SCK5Bezq@167.148.104.182:2333','senspower:T9u_SCK5Bezq@167.148.104.172:2333','senspower:T9u_SCK5Bezq@167.148.104.76:2333','senspower:T9u_SCK5Bezq@167.148.104.254:2333','senspower:T9u_SCK5Bezq@167.148.104.225:2333','senspower:T9u_SCK5Bezq@199.182.96.180:2333','senspower:T9u_SCK5Bezq@199.182.96.171:2333','senspower:T9u_SCK5Bezq@199.182.96.95:2333','senspower:T9u_SCK5Bezq@199.182.96.132:2333','senspower:T9u_SCK5Bezq@199.182.96.155:2333','senspower:T9u_SCK5Bezq@199.182.96.31:2333','senspower:T9u_SCK5Bezq@199.182.96.28:2333','senspower:T9u_SCK5Bezq@199.182.96.46:2333','senspower:T9u_SCK5Bezq@199.182.96.59:2333','senspower:T9u_SCK5Bezq@199.182.96.220:2333','senspower:T9u_SCK5Bezq@199.182.96.249:2333','senspower:T9u_SCK5Bezq@199.182.96.55:2333','senspower:T9u_SCK5Bezq@199.182.96.13:2333','senspower:T9u_SCK5Bezq@172.121.61.57:2333','senspower:T9u_SCK5Bezq@172.121.61.119:2333','senspower:T9u_SCK5Bezq@172.121.61.154:2333','senspower:T9u_SCK5Bezq@172.120.245.229:2333','senspower:T9u_SCK5Bezq@172.121.61.47:2333','senspower:T9u_SCK5Bezq@172.120.245.3:2333','senspower:T9u_SCK5Bezq@172.121.61.48:2333','senspower:T9u_SCK5Bezq@172.121.61.86:2333','senspower:T9u_SCK5Bezq@172.121.61.8:2333','senspower:T9u_SCK5Bezq@172.120.245.187:2333','senspower:T9u_SCK5Bezq@172.120.245.65:2333','senspower:T9u_SCK5Bezq@172.121.61.146:2333','senspower:T9u_SCK5Bezq@172.121.53.220:2333','senspower:T9u_SCK5Bezq@172.121.53.147:2333','senspower:T9u_SCK5Bezq@172.121.53.246:2333','senspower:T9u_SCK5Bezq@172.121.53.91:2333','senspower:T9u_SCK5Bezq@172.121.53.161:2333','senspower:T9u_SCK5Bezq@172.121.53.4:2333','senspower:T9u_SCK5Bezq@172.120.245.211:2333','senspower:T9u_SCK5Bezq@172.120.245.160:2333','senspower:T9u_SCK5Bezq@172.120.245.121:2333','senspower:T9u_SCK5Bezq@172.120.245.141:2333','senspower:T9u_SCK5Bezq@172.120.245.87:2333','senspower:T9u_SCK5Bezq@172.121.53.14:2333','senspower:T9u_SCK5Bezq@172.121.53.122:2333','senspower:T9u_SCK5Bezq@172.121.53.47:2333','senspower:T9u_SCK5Bezq@172.121.61.237:2333','senspower:T9u_SCK5Bezq@172.120.245.223:2333','senspower:T9u_SCK5Bezq@172.121.53.176:2333','senspower:T9u_SCK5Bezq@172.120.245.240:2333','senspower:T9u_SCK5Bezq@172.121.61.43:2333','senspower:T9u_SCK5Bezq@172.121.61.63:2333','senspower:T9u_SCK5Bezq@172.120.245.220:2333','senspower:T9u_SCK5Bezq@172.121.53.178:2333','senspower:T9u_SCK5Bezq@172.121.53.123:2333','senspower:T9u_SCK5Bezq@172.120.245.118:2333','senspower:T9u_SCK5Bezq@172.121.61.58:2333','senspower:T9u_SCK5Bezq@172.121.61.250:2333','senspower:T9u_SCK5Bezq@172.121.61.245:2333','senspower:T9u_SCK5Bezq@172.121.53.254:2333','senspower:T9u_SCK5Bezq@172.121.53.102:2333','senspower:T9u_SCK5Bezq@172.120.245.173:2333','senspower:T9u_SCK5Bezq@96.62.57.90:2333','senspower:T9u_SCK5Bezq@96.62.151.62:2333','senspower:T9u_SCK5Bezq@96.62.149.229:2333','senspower:T9u_SCK5Bezq@96.62.151.66:2333','senspower:T9u_SCK5Bezq@96.62.149.252:2333','senspower:T9u_SCK5Bezq@96.62.151.130:2333','senspower:T9u_SCK5Bezq@96.62.151.99:2333','senspower:T9u_SCK5Bezq@96.62.151.182:2333','senspower:T9u_SCK5Bezq@96.62.149.159:2333','senspower:T9u_SCK5Bezq@96.62.57.84:2333','senspower:T9u_SCK5Bezq@96.62.149.186:2333','senspower:T9u_SCK5Bezq@96.62.149.68:2333','senspower:T9u_SCK5Bezq@96.62.151.128:2333','senspower:T9u_SCK5Bezq@96.62.149.94:2333','senspower:T9u_SCK5Bezq@96.62.57.187:2333','senspower:T9u_SCK5Bezq@96.62.151.228:2333','senspower:T9u_SCK5Bezq@96.62.151.125:2333','senspower:T9u_SCK5Bezq@96.62.149.15:2333','senspower:T9u_SCK5Bezq@96.62.149.156:2333','senspower:T9u_SCK5Bezq@96.62.151.184:2333','senspower:T9u_SCK5Bezq@96.62.151.147:2333','senspower:T9u_SCK5Bezq@96.62.149.63:2333','senspower:T9u_SCK5Bezq@96.62.149.23:2333','senspower:T9u_SCK5Bezq@96.62.149.33:2333','senspower:T9u_SCK5Bezq@96.62.149.231:2333','senspower:T9u_SCK5Bezq@96.62.149.46:2333','senspower:T9u_SCK5Bezq@96.62.57.226:2333','senspower:T9u_SCK5Bezq@96.62.149.40:2333','senspower:T9u_SCK5Bezq@96.62.151.249:2333','senspower:T9u_SCK5Bezq@96.62.149.222:2333','senspower:T9u_SCK5Bezq@96.62.151.21:2333','senspower:T9u_SCK5Bezq@96.62.151.142:2333','senspower:T9u_SCK5Bezq@68.64.159.78:2333','senspower:T9u_SCK5Bezq@68.64.159.74:2333','senspower:T9u_SCK5Bezq@68.64.159.68:2333','senspower:T9u_SCK5Bezq@68.64.159.128:2333','senspower:T9u_SCK5Bezq@68.64.159.18:2333','senspower:T9u_SCK5Bezq@68.64.159.48:2333','senspower:T9u_SCK5Bezq@68.64.159.72:2333','senspower:T9u_SCK5Bezq@68.64.159.217:2333','senspower:T9u_SCK5Bezq@68.64.159.15:2333','senspower:T9u_SCK5Bezq@68.64.159.84:2333','senspower:T9u_SCK5Bezq@68.64.159.178:2333','senspower:T9u_SCK5Bezq@68.64.159.119:2333','senspower:T9u_SCK5Bezq@68.64.159.156:2333','senspower:T9u_SCK5Bezq@68.64.159.124:2333','senspower:T9u_SCK5Bezq@68.64.159.76:2333','senspower:T9u_SCK5Bezq@68.64.159.93:2333','senspower:T9u_SCK5Bezq@68.64.159.136:2333','senspower:T9u_SCK5Bezq@68.64.159.218:2333','senspower:T9u_SCK5Bezq@68.64.159.172:2333','senspower:T9u_SCK5Bezq@68.64.159.89:2333','senspower:T9u_SCK5Bezq@68.64.159.45:2333','senspower:T9u_SCK5Bezq@68.64.159.79:2333','senspower:T9u_SCK5Bezq@68.64.159.12:2333','senspower:T9u_SCK5Bezq@68.64.159.38:2333','senspower:T9u_SCK5Bezq@216.231.43.109:2333','senspower:T9u_SCK5Bezq@216.231.42.140:2333','senspower:T9u_SCK5Bezq@216.231.45.207:2333','senspower:T9u_SCK5Bezq@216.231.44.191:2333','senspower:T9u_SCK5Bezq@216.231.40.79:2333','senspower:T9u_SCK5Bezq@216.231.43.43:2333','senspower:T9u_SCK5Bezq@216.231.42.193:2333','senspower:T9u_SCK5Bezq@216.231.45.68:2333','senspower:T9u_SCK5Bezq@216.231.43.247:2333','senspower:T9u_SCK5Bezq@216.231.43.143:2333','senspower:T9u_SCK5Bezq@216.231.43.181:2333','senspower:T9u_SCK5Bezq@149.52.118.151:2333','senspower:T9u_SCK5Bezq@149.52.118.128:2333','senspower:T9u_SCK5Bezq@149.52.118.74:2333','senspower:T9u_SCK5Bezq@149.52.118.150:2333','senspower:T9u_SCK5Bezq@149.52.118.248:2333','senspower:T9u_SCK5Bezq@149.52.118.205:2333','senspower:T9u_SCK5Bezq@149.52.118.113:2333','senspower:T9u_SCK5Bezq@149.52.118.220:2333','senspower:T9u_SCK5Bezq@149.52.118.133:2333','senspower:T9u_SCK5Bezq@149.52.118.6:2333','senspower:T9u_SCK5Bezq@149.52.118.18:2333','senspower:T9u_SCK5Bezq@149.52.118.194:2333','senspower:T9u_SCK5Bezq@149.52.118.124:2333','senspower:T9u_SCK5Bezq@149.40.69.69:2333','senspower:T9u_SCK5Bezq@149.40.83.188:2333','senspower:T9u_SCK5Bezq@149.40.71.30:2333','senspower:T9u_SCK5Bezq@149.40.71.40:2333','senspower:T9u_SCK5Bezq@149.40.69.74:2333','senspower:T9u_SCK5Bezq@149.40.71.16:2333','senspower:T9u_SCK5Bezq@149.40.71.149:2333','senspower:T9u_SCK5Bezq@149.40.83.13:2333','senspower:T9u_SCK5Bezq@149.40.69.184:2333','senspower:T9u_SCK5Bezq@149.40.83.200:2333','senspower:T9u_SCK5Bezq@149.40.71.98:2333','senspower:T9u_SCK5Bezq@149.40.83.163:2333','senspower:T9u_SCK5Bezq@149.40.83.194:2333','senspower:T9u_SCK5Bezq@149.40.71.155:2333','senspower:T9u_SCK5Bezq@149.40.83.96:2333','senspower:T9u_SCK5Bezq@149.40.71.146:2333','senspower:T9u_SCK5Bezq@149.40.69.124:2333','senspower:T9u_SCK5Bezq@149.40.69.89:2333','senspower:T9u_SCK5Bezq@149.40.69.84:2333','senspower:T9u_SCK5Bezq@149.40.71.203:2333','senspower:T9u_SCK5Bezq@149.40.83.161:2333','senspower:T9u_SCK5Bezq@149.40.83.178:2333','senspower:T9u_SCK5Bezq@149.40.71.243:2333','senspower:T9u_SCK5Bezq@149.40.71.251:2333','senspower:T9u_SCK5Bezq@149.40.69.202:2333','senspower:T9u_SCK5Bezq@149.40.69.105:2333','senspower:T9u_SCK5Bezq@149.40.71.234:2333','senspower:T9u_SCK5Bezq@149.40.69.157:2333','senspower:T9u_SCK5Bezq@149.40.83.156:2333','senspower:T9u_SCK5Bezq@149.40.83.124:2333','senspower:T9u_SCK5Bezq@149.40.71.170:2333','senspower:T9u_SCK5Bezq@149.40.83.88:2333','senspower:T9u_SCK5Bezq@149.40.71.3:2333','senspower:T9u_SCK5Bezq@149.40.71.197:2333','senspower:T9u_SCK5Bezq@149.40.69.58:2333','senspower:T9u_SCK5Bezq@149.40.83.17:2333','senspower:T9u_SCK5Bezq@149.40.71.201:2333','senspower:T9u_SCK5Bezq@149.40.69.60:2333','senspower:T9u_SCK5Bezq@149.40.83.133:2333','senspower:T9u_SCK5Bezq@149.40.71.69:2333','senspower:T9u_SCK5Bezq@149.40.69.125:2333','senspower:T9u_SCK5Bezq@149.40.71.229:2333','senspower:T9u_SCK5Bezq@149.40.69.104:2333','senspower:T9u_SCK5Bezq@149.40.69.101:2333','senspower:T9u_SCK5Bezq@149.40.83.205:2333','senspower:T9u_SCK5Bezq@149.40.71.74:2333','senspower:T9u_SCK5Bezq@149.40.83.74:2333','senspower:T9u_SCK5Bezq@149.40.83.231:2333','senspower:T9u_SCK5Bezq@149.40.69.223:2333','senspower:T9u_SCK5Bezq@149.40.83.114:2333','senspower:T9u_SCK5Bezq@149.40.71.103:2333','senspower:T9u_SCK5Bezq@149.40.83.244:2333','senspower:T9u_SCK5Bezq@149.40.69.117:2333','senspower:T9u_SCK5Bezq@149.40.69.113:2333','senspower:T9u_SCK5Bezq@149.40.83.216:2333','senspower:T9u_SCK5Bezq@149.40.83.246:2333','senspower:T9u_SCK5Bezq@149.40.83.67:2333','senspower:T9u_SCK5Bezq@149.40.83.137:2333','senspower:T9u_SCK5Bezq@149.40.71.96:2333','senspower:T9u_SCK5Bezq@149.40.69.149:2333','senspower:T9u_SCK5Bezq@149.40.83.33:2333','senspower:T9u_SCK5Bezq@149.40.69.186:2333','senspower:T9u_SCK5Bezq@149.40.71.65:2333','senspower:T9u_SCK5Bezq@149.40.83.228:2333','senspower:T9u_SCK5Bezq@149.40.69.239:2333','senspower:T9u_SCK5Bezq@149.40.69.52:2333','senspower:T9u_SCK5Bezq@149.40.69.119:2333','senspower:T9u_SCK5Bezq@149.40.71.249:2333','senspower:T9u_SCK5Bezq@149.40.69.88:2333','senspower:T9u_SCK5Bezq@149.40.71.39:2333','senspower:T9u_SCK5Bezq@149.40.71.54:2333','senspower:T9u_SCK5Bezq@149.40.69.39:2333','senspower:T9u_SCK5Bezq@149.40.71.147:2333','senspower:T9u_SCK5Bezq@149.40.69.254:2333','senspower:T9u_SCK5Bezq@149.40.71.178:2333','senspower:T9u_SCK5Bezq@149.40.69.220:2333','senspower:T9u_SCK5Bezq@149.40.69.11:2333','senspower:T9u_SCK5Bezq@149.40.69.42:2333','senspower:T9u_SCK5Bezq@149.40.69.138:2333','senspower:T9u_SCK5Bezq@149.40.83.183:2333','senspower:T9u_SCK5Bezq@149.40.69.128:2333','senspower:T9u_SCK5Bezq@149.40.83.77:2333','senspower:T9u_SCK5Bezq@149.40.69.146:2333','senspower:T9u_SCK5Bezq@149.40.69.139:2333','senspower:T9u_SCK5Bezq@149.40.83.44:2333','senspower:T9u_SCK5Bezq@149.40.71.28:2333','senspower:T9u_SCK5Bezq@149.40.83.247:2333','senspower:T9u_SCK5Bezq@149.40.71.184:2333','senspower:T9u_SCK5Bezq@149.40.69.4:2333','senspower:T9u_SCK5Bezq@149.40.83.232:2333','senspower:T9u_SCK5Bezq@149.40.71.211:2333','senspower:T9u_SCK5Bezq@149.40.69.13:2333','senspower:T9u_SCK5Bezq@149.40.69.44:2333','senspower:T9u_SCK5Bezq@149.40.69.79:2333','senspower:T9u_SCK5Bezq@192.200.211.246:2333','senspower:T9u_SCK5Bezq@192.200.211.240:2333','senspower:T9u_SCK5Bezq@192.200.211.233:2333','senspower:T9u_SCK5Bezq@192.200.211.245:2333','senspower:T9u_SCK5Bezq@192.200.211.236:2333']
        else:
            ipList = eval(config_data.get("ipList"))
        logger.info(f"代理池配置成功 | 数量={len(ipList)}")
    except Exception as e:
        logger.warning(f"获取ipList配置失败: {e}")
        ipList = []

    # ✅ 初始化线程安全的直播间状态字典
    all_Live_Room_dict = dict()

    # ✅ 初始化工具类（不再传递conn参数）
    tiktokTool = TiktokTool(ipList)
    shopeeTool = ShopeeTool(ipList)
    lazadaTool = LazadaTool(ipList)
    logger.info("✅ 工具类初始化完成")

    # ✅ 启动定时任务（房间检测和离线脚本监控）
    start_select_info_scheduler(ISTEST)

    # ✅ 启动调度器健康监控线程
    start_scheduler_monitor()

    # ✅ 启动额外的定时任务调度器（GMV/T+1/基本信息采集）
    if SCHEDULER_AVAILABLE:
        logger.info("📋 启动ws定时推送分发任务，运行派大星插件获数中...")
        scheduler_thread = threading.Thread(target=start_scheduler_main, daemon=True)
        scheduler_thread.start()
        logger.info("✅ 派大星推送任务插件已启动")
    else:
        logger.warning("⚠️ 跳过额外定时任务配置（start_scheduler模块不可用）")

    # ✅ 初始化 WebSocket 路由
    # from routes.websocket_routes import init_websocket_routes
    # init_websocket_routes(ISTEST)
    # logger.info("✅ WebSocket 路由已初始化")

    logger.info("=" * 60)
    logger.info("🎉 所有组件初始化完成，启动Web服务器...")
    logger.info(f"📡 服务地址: http://{NODE_IP}:8080")
    logger.info(f"🔗 健康检查: http://{NODE_IP}:8080/health")
    logger.info(f"📋 节点信息: {NODE_ID} (优先级: {PRIORITY})")
    logger.info("=" * 60)

    # ✅ 启动Web服务器（包含所有功能：API + WebSocket + 所有定时任务）
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
