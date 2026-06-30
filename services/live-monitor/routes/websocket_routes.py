#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/10/23 下午4:39
# @Author     : XBW
# @File       : websocket_routes.py
# @Description: 等待插件完全更新完才可以打开该路由 ，目前该ws路由还是单起一个服务

import os
import logging
from fastapi import APIRouter, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import requests
import asyncio
import queue
from typing import Dict
from datetime import datetime
from kafka import KafkaProducer
import json
import sys
import os

# 导入工具函数
import config
from check_cj_data import check_CJ_data

# ========== 节点配置（已迁移到 Apollo，config 门面）==========
NODE_ID = config.node_id()
NODE_IP = config.node_ip()
PRIORITY = config.priority()
BACKUP_NODE_URL = config.backup_node_url()

# 创建路由器（不使用prefix，保持原有路由地址）
router = APIRouter()

# 设置日志级别
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.WARNING)

# 用户任务队列字典，每个用户有自己的队列
user_task_queues: Dict[str, queue.Queue] = {}


# 获取日志目录路径
def get_log_dir():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "socketLog")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return log_dir


# 保存socket客户端连接日志
def save_socket_cli_log(data):
    current_date = datetime.now().strftime("%Y%m%d")
    log_dir = get_log_dir()
    log_filename = f"socket_{current_date}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(log_filepath, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {data}\n")
    except Exception as e:
        print(f"写入socket日志失败: {e}")


# kafka相关操作
class KafkaHelper:
    def __init__(self):
        try:
            # Kafka broker 列表已迁移到 Apollo（config 门面），无需 eval
            kafka_server = config.kafka_servers()
            self.producer = KafkaProducer(
                bootstrap_servers=kafka_server,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        except Exception as e:
            print("出现错误", e)
            self.producer = None

    # 数据推到kafka
    def sendToKafka(self, data, topic_name=''):
        if self.producer:
            self.producer.send(topic_name, value=data)
            self.producer.flush()  # 确保所有消息都被发送到Kafka服务器,flush()会阻塞直到所有未完成的消息请求都发送完成


# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_times: Dict[str, datetime] = {}
        self.client_ips: Dict[str, str] = {}  # 添加IP地址记录

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            # 获取客户端IP地址
            client_ip = websocket.client.host if websocket.client else "unknown"
            self.active_connections[user_id] = websocket
            self.connection_times[user_id] = datetime.now()
            self.client_ips[user_id] = client_ip
            print(f"用户 {user_id} 已连接，IP地址: {client_ip}")

        if user_id not in user_task_queues:
            user_task_queues[user_id] = queue.Queue()

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.connection_times:
            del self.connection_times[user_id]
        if user_id in self.client_ips:
            del self.client_ips[user_id]
        if user_id in user_task_queues:
            del user_task_queues[user_id]
        print(f"用户 {user_id} 已断开连接")

    async def get_connected_users(self):
        """返回当前连接的用户"""
        return list(self.active_connections.keys())

    def get_user_ip(self, user_id: str) -> str:
        """获取用户的IP地址"""
        return self.client_ips.get(user_id, "unknown")


# 创建全局连接管理器实例
manager = ConnectionManager()

# 创建全局Kafka实例（将在app启动时初始化）
pushKfk = None


# 后台任务：每3分钟打印一次连接的用户
async def print_connected_users():
    # ✅ 从环境变量读取备用节点地址
    backup_node_url = BACKUP_NODE_URL
    
    while True:
        try:
            connected_users = await manager.get_connected_users()
            if connected_users:
                connection_status = []
                disconnected_users = []  # 记录需要清理的用户

                for user in connected_users:
                    # 仅依据内存中的连接表做统计，不主动发送 ping，也不因异常清理
                    websocket = manager.active_connections.get(user)
                    if websocket:
                        connection_status.append({
                            "cjUserId": user,
                            "connectTime": str(int(datetime.now().timestamp() * 1000)),
                            "clientIP": manager.get_user_ip(user)
                        })
                    else:
                        disconnected_users.append(user)

                # 清理已断开的连接
                for user in disconnected_users:
                    manager.disconnect(user)
                    print(f"已清理断开连接的用户: {user}")

                if connection_status:
                    print(f"当前连接数量为: {len(connection_status)}")
                    save_socket_cli_log(connection_status)
                    if pushKfk:
                        pushKfk.sendToKafka(connection_status, topic_name='streamer_cj_user_notify')
                    
                    # ✅ 新增：同步日志到备节点
                    try:
                        requests.post(
                            f"{backup_node_url}/sync_log",
                            json={"log_type": "socket", "data": connection_status},
                            timeout=3
                        )
                    except Exception as e:
                        # 备节点不可用时忽略错误，不影响主流程
                        pass
                else:
                    print("当前没有活跃连接")
        except Exception as e:
            print(f"检查连接用户时出错: {e}")
        await asyncio.sleep(60)


# WebSocket端点
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    client_ip = manager.get_user_ip(user_id)
    disconnection_logged = False  # 添加断开连接日志标志

    try:
        while True:
            try:
                # 接收消息
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                # 处理心跳ping消息
                if isinstance(data, dict) and data.get('type') == 'ping':
                    # 响应pong消息
                    await websocket.send_json({
                        "type": "pong",
                        "userId": user_id,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    print(f"💓 响应用户 {user_id}(IP: {client_ip}) 的心跳")
                    continue
                
                print(f"📨 收到来自用户 {user_id}(IP: {client_ip}) 的消息: {data}")

                # 转发消息给目标用户
                target_user_id = data.get('target_user_id')
                if target_user_id and target_user_id in manager.active_connections:
                    target_websocket = manager.active_connections[target_user_id]
                    target_ip = manager.get_user_ip(target_user_id)
                    try:
                        await target_websocket.send_json(data)
                        print(f"消息已转发给用户 {target_user_id}(IP: {target_ip})")
                    except Exception as e:
                        print(f"转发消息给用户 {target_user_id}(IP: {target_ip}) 失败: {e}")
                        manager.disconnect(target_user_id)

                # 检查用户的任务队列
                if user_id in user_task_queues:
                    try:
                        sendData = user_task_queues[user_id].get_nowait()
                        message = {
                            "url": sendData,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        await websocket.send_json(message)
                        print(f"消息已发送给用户 {user_id}(IP: {client_ip}): {message}")
                    except queue.Empty:
                        pass
                    except Exception as e:
                        print(f"发送队列消息给用户 {user_id}(IP: {client_ip}) 失败: {e}")
                        break

            except asyncio.TimeoutError:
                # 接收超时，继续循环
                continue
            except WebSocketDisconnect:
                if not disconnection_logged:
                    print(f"用户 {user_id}(IP: {client_ip}) 主动断开连接")
                    disconnection_logged = True
                break
            except Exception as e:
                if not disconnection_logged:
                    print(f"处理用户 {user_id}(IP: {client_ip}) 消息时出错: {e}")
                    disconnection_logged = True
                break

    except Exception as e:
        if not disconnection_logged:
            print(f"WebSocket Error for user {user_id}(IP: {client_ip}): {e}")
            disconnection_logged = True
    finally:
        # 确保只打印一次断开连接信息
        if not disconnection_logged:
            print(f"用户 {user_id}(IP: {client_ip}) 连接已关闭")
            disconnection_logged = True

        manager.disconnect(user_id)
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/health")
def health_check():
    """
    健康检查端点（插件和定时调度脚本都会调用此接口判断服务器是否可用）
    ✅ 从环境变量自动读取节点配置
    """
    return {
        "code": 200,
        "status": "healthy",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "connections": len(manager.active_connections),
        "node_id": NODE_ID,
        "priority": PRIORITY,
        "node_ip": NODE_IP
    }


@router.post("/sync_log")
async def sync_log(request: Request):
    """接收其他节点同步的日志"""
    try:
        body = await request.json()
        log_type = body.get("log_type", "socket")
        log_data = body.get("data", [])
        
        if log_type == "socket":
            for item in log_data:
                save_socket_cli_log(item)
        
        return {"code": 200, "message": "日志同步成功"}
    except Exception as e:
        return {"code": 500, "message": f"日志同步失败: {e}"}

# 获取最新socket链接有哪些
@router.get("/socketOnlineUserID")
def socketOnlineUserID(num: str = Query("1", description="推送的条数")):
    num = int(num)
    dateNow = datetime.now().strftime("%Y%m%d")
    log_dir = get_log_dir()
    log_filepath = os.path.join(log_dir, f"socket_{dateNow}.log")
    
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            endList = list()
            for line in f.readlines():
                endList.append(list(eval(line[21:])))
        returnList = endList[-num:] if len(endList) >= num else endList
        return {"code": 200, "message": "sucess", "data": returnList}
    except FileNotFoundError:
        return {"code": 404, "message": "日志文件不存在", "data": []}
    except Exception as e:
        return {"code": 500, "message": f"读取日志失败: {e}", "data": []}


@router.get("/get_check_CJ_data")
def get_check_CJ_data_route():
    """获取CJ数据检查结果"""
    # 环境判断已迁移到 Apollo 引导变量 DEPLOY_ENV（config.is_test_env）
    data = check_CJ_data(config.is_test_env())
    return {"code": 200, "message": "sucess", "data": data}


@router.get("/CJListenUrl")
async def CJListenUrl():
    """
    返回需要监听的url列表
    """
    listen_url_list = list()
    config_data = {
        "TT": {
            "listen_url": ["api/v2/insights/creator/live/stats",
                           "api/v2/insights/creator/live/list",
                           "api/v1/insights/creator/liveroom/recap/core/stats",
                           "api/v1/insights/creator/liveroom/recap/product/list",
                           "api/v1/insights/workbench/live/detail/core/stats",
                           "api/v1/insights/creator/liveroom/recap/trend/chart",
                           "api/v1/insights/creator/liveroom/recap/viewer/source/stats",
                           "webcast/room/replay/info/?aid=304449",
                           "api/v1/streamer_desktop/account_info/get",
                           "api/v2/insights/creator/info",
                           "api/v3/insights/workbench/live/detail/source/new", #tk接口改为v3
                           "api/v1/insights/workbench/live/detail/room/info",
                           "api/v1/insights/workbench/live/detail/trend/chart",
                           "api/v3/insights/creator/product/analytics/list"],
            "topic_name": "onecollect_plugin_data_AdsGoogle"
        },
        "shopee": {
            "listen_url": [
                "api/supply/lm/sellercenter/overview/v2",
                "api/supply/lm/sellercenter/metricTrend/v2",
                "api/supply/lm/sellercenter/userDemographics",
                "api/supply/lm/sellercenter/realtime/sessionList",
                "api/supply/lm/sellercenter/productsList/v2",
                "api/supply/sellercenter/video/v2/overview",
                "api/supply/sellercenter/video/v2/metricTrend",
                "api/supply/sellercenter/video/v2/demographics",
                "api/supply/sellercenter/video/v2/videolist",
                "api/supply/sellercenter/video/v2/productlist",
                "api/supply/lm/sellercenter/productsList/v2"
            ],
            "topic_name": "onecollect_plugin_data_AdsGoogle"
        },
    }

    for item in config_data.values():
        for listen_url in item.get("listen_url", []):
            listen_url_list.append(listen_url)

    print("listen_url_list--->", listen_url_list)

    return listen_url_list


# 初始化函数，在应用启动时调用
def init_websocket_routes():
    """初始化WebSocket路由所需的全局资源"""
    global pushKfk
    pushKfk = KafkaHelper()
    print("✅ WebSocket路由模块已初始化")
    return pushKfk


# 启动后台任务的函数
def start_background_tasks():
    """启动后台任务"""
    return asyncio.create_task(print_connected_users())

