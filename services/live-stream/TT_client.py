import requests
import threading
import time
import uvicorn
from fastapi import FastAPI
import subprocess
import socket
import oss2
import os
import shutil
from kafka import KafkaProducer
import json
from datetime import datetime
import hashlib
from loguru import logger
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable
import re

# 配置日志
logger.add(
    "logs/ffmpeg_stream_{time:YYYY-MM-DD}.log",
    rotation="100 MB",
    retention="7 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    encoding="utf-8"
)

app = FastAPI()


# ========== FFmpeg 稳定推流模块 ==========
class StreamStatus(Enum):
    """推流状态枚举"""
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class StreamConfig:
    """推流配置"""
    # 最大重试次数
    max_retries: int = 5
    # 重试间隔(秒)
    retry_interval: int = 3
    # 重试间隔递增因子
    retry_backoff: float = 1.5
    # 最大重试间隔(秒)
    max_retry_interval: int = 30
    # 分析时长(微秒) - FFmpeg分析输入流的时长
    analyzeduration: int = 5000000  # 5秒
    # 探测大小(字节) - FFmpeg探测输入流的数据量
    probesize: int = 10000000  # 10MB
    # 心跳检测间隔(秒)
    heartbeat_interval: int = 30
    # 无数据超时(秒) - 连续多久没有新文件生成则认为断流
    no_data_timeout: int = 60


class FFmpegStreamManager:
    """FFmpeg直播推流管理器 - 实现稳定可靠的推流"""

    def __init__(self, config: StreamConfig = None):
        self.config = config or StreamConfig()
        self.status = StreamStatus.IDLE
        self.process: Optional[subprocess.Popen] = None
        self.retry_count = 0
        self.current_retry_interval = self.config.retry_interval
        self.last_file_time = 0
        self.total_reconnects = 0
        self.stream_start_time = 0
        self._stop_flag = False
        self._lock = threading.Lock()

    def build_ffmpeg_command(self, live_url: str, output_filename: str, segment_time: int = 8,
                             platform: str = "tiktok") -> list:
        """
        构建优化的FFmpeg命令 (FFmpeg 8.0+ 完整优化版)

        关键参数说明:
        - reconnect系列: 启用自动重连机制
        - rw_timeout: 读写超时(微秒)
        - fflags: +genpts 生成时间戳, +discardcorrupt 丢弃损坏的包
        - max_delay: 最大解复用延迟
        - platform: 平台类型，支持 "tiktok" 和 "shopee"，针对不同平台使用不同参数
        """
        command = [
            'ffmpeg',
            # ===== 全局参数 =====
            '-y',  # 覆盖输出文件
            '-loglevel', 'warning',
            '-stats',
        ]

        # ===== 根据平台设置不同的超时和缓冲参数 =====
        if platform == "shopee":
            # Shopee 平台优化参数：更短的超时，更大的缓冲，更好的帧率处理
            rw_timeout = '8000000'  # 8秒读写超时（更快检测卡顿）
            max_muxing_queue_size = '9999'  # 更大的复用队列
            logger.debug(f"使用 Shopee 平台优化参数")
        else:
            # TikTok 默认参数
            rw_timeout = '15000000'  # 15秒读写超时
            max_muxing_queue_size = '1024'  # 默认队列大小

        # ===== HTTP/HTTPS 完整重连参数 (FFmpeg 8.0 全支持) =====
        if live_url.startswith('http://') or live_url.startswith('https://'):
            command.extend([
                # 基础重连
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '5',
                # 网络错误时重连
                '-reconnect_on_network_error', '1',
                # HTTP错误时重连 (4xx/5xx)
                '-reconnect_on_http_error', '4xx,5xx',
                # 读写超时 (根据平台不同)
                '-rw_timeout', rw_timeout,
            ])

        # ===== 输入分析参数 =====
        command.extend([
            '-analyzeduration', str(self.config.analyzeduration),
            '-probesize', str(self.config.probesize),
            # +genpts: 生成时间戳
            # +discardcorrupt: 丢弃损坏的包
            # +igndts: 忽略DTS时间戳问题
            '-fflags', '+genpts+discardcorrupt+igndts',
            # 最大解复用延迟 (微秒)
            '-max_delay', '5000000',
        ])

        # ===== 输入源 =====
        command.extend(['-i', live_url])

        # ===== 编码参数 =====
        command.extend([
            '-c:v', 'copy',
            '-c:a', 'copy',
            # 避免时间戳问题
            '-avoid_negative_ts', 'make_zero',
            # 复制未知流
            '-copy_unknown',
            # 映射所有流
            '-map', '0',
            # 设置复用队列大小（防止Shopee帧率卡顿）
            '-max_muxing_queue_size', max_muxing_queue_size,
        ])

        # ===== 分段输出参数 =====
        command.extend([
            '-f', 'segment',
            '-segment_time', str(segment_time),
            '-reset_timestamps', '1',
            # 强制关键帧对齐
            '-break_non_keyframes', '0',
        ])

        # ===== 输出文件 =====
        command.append(output_filename)

        return command

    def _parse_ffmpeg_progress(self, line: str) -> dict:
        """解析FFmpeg输出获取推流进度信息"""
        info = {}

        # 匹配 frame=  123 fps= 30 q=-1.0 size=    1234kB time=00:00:05.00 bitrate=2000.0kbits/s
        patterns = {
            'frame': r'frame=\s*(\d+)',
            'fps': r'fps=\s*([\d.]+)',
            'size': r'size=\s*([\d.]+\w+)',
            'time': r'time=\s*([\d:.]+)',
            'bitrate': r'bitrate=\s*([\d.]+\w+/s)',
            'speed': r'speed=\s*([\d.]+)x'
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, line)
            if match:
                info[key] = match.group(1)

        return info

    def _monitor_ffmpeg_output(self, process: subprocess.Popen, room_id: str):
        """监控FFmpeg输出，实时记录日志并检测帧率异常"""
        low_fps_count = 0  # 连续低帧率计数
        try:
            for line in iter(process.stderr.readline, b''):
                if self._stop_flag:
                    break

                line_str = line.decode('utf-8', errors='ignore').strip()
                if not line_str:
                    continue

                # 解析进度信息
                if 'frame=' in line_str or 'size=' in line_str:
                    progress = self._parse_ffmpeg_progress(line_str)
                    if progress:
                        # 帧率监控：检测低帧率异常（可能导致视频卡顿）
                        fps_str = progress.get('fps', '0')
                        try:
                            fps = float(fps_str)
                            if fps < 5:  # FPS低于5时告警
                                low_fps_count += 1
                                if low_fps_count >= 3:  # 连续3次低帧率才告警
                                    logger.warning(f"[{room_id}] 帧率异常: FPS={fps}, 可能存在卡顿")
                                    low_fps_count = 0  # 重置计数，避免频繁告警
                            else:
                                low_fps_count = 0  # 帧率正常，重置计数
                        except (ValueError, TypeError):
                            pass

                # 检测错误和警告
                elif 'error' in line_str.lower():
                    # logger.error(f"[{room_id}] FFmpeg错误: {line_str}")
                    pass
                elif 'warning' in line_str.lower():
                    # logger.warning(f"[{room_id}] FFmpeg警告: {line_str}")
                    pass
                elif 'Connection refused' in line_str or 'Connection timed out' in line_str:
                    # logger.error(f"[{room_id}] 网络连接问题: {line_str}")
                    pass
                elif 'End of file' in line_str or 'Input/output error' in line_str:
                    logger.warning(f"[{room_id}] 直播流结束或IO错误: {line_str}")
                    pass

        except Exception as e:
            logger.error(f"[{room_id}] 监控FFmpeg输出异常: {e}")

    def _check_stream_health(self, output_dir: str) -> bool:
        """
        检查推流健康状态
        通过检测是否持续生成新的TS文件来判断
        """
        try:
            if not os.path.exists(output_dir):
                return False

            ts_files = [f for f in os.listdir(output_dir) if f.endswith('.ts')]
            if not ts_files:
                return True  # 刚开始可能还没有文件

            # 获取最新文件的修改时间
            latest_time = 0
            for f in ts_files:
                file_path = os.path.join(output_dir, f)
                mtime = os.path.getmtime(file_path)
                if mtime > latest_time:
                    latest_time = mtime

            # 如果最新文件超过超时时间没有更新，认为推流异常
            if latest_time > 0:
                elapsed = time.time() - latest_time
                if elapsed > self.config.no_data_timeout:
                    logger.warning(f"推流健康检查: {elapsed:.1f}秒未生成新文件")
                    return False

            return True

        except Exception as e:
            logger.error(f"检查推流健康状态异常: {e}")
            return True  # 异常时默认返回健康

    def start_stream(self, live_url: str, output_filename: str, output_dir: str,
                     segment_time: int = 8, room_id: str = "unknown",
                     on_status_change: Callable = None, platform: str = "tiktok") -> subprocess.Popen:
        """
        启动推流，带自动重连机制

        参数:
        - live_url: 直播源地址
        - output_filename: 输出文件名模板
        - output_dir: 输出目录
        - segment_time: 分段时长(秒)
        - room_id: 房间ID(用于日志)
        - on_status_change: 状态变化回调函数
        - platform: 平台类型 ("tiktok" 或 "shopee")

        返回: subprocess.Popen 进程对象
        """
        self._stop_flag = False
        self.stream_start_time = time.time()
        self.retry_count = 0
        self.current_retry_interval = self.config.retry_interval

        def update_status(new_status: StreamStatus):
            self.status = new_status
            if on_status_change:
                on_status_change(new_status, room_id)
            logger.info(f"[{room_id}] 推流状态变更: {new_status.value}")

        while not self._stop_flag and self.retry_count <= self.config.max_retries:
            try:
                update_status(StreamStatus.CONNECTING if self.retry_count == 0 else StreamStatus.RECONNECTING)

                # 构建FFmpeg命令（根据平台使用不同参数）
                command = self.build_ffmpeg_command(live_url, output_filename, segment_time, platform)
                logger.info(f"[{room_id}] 启动FFmpeg推流 (重试次数: {self.retry_count}, 平台: {platform})")
                logger.debug(f"[{room_id}] FFmpeg命令: {' '.join(command)}")

                # 启动进程，捕获stderr用于监控
                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=1
                )

                # 启动输出监控线程
                monitor_thread = threading.Thread(
                    target=self._monitor_ffmpeg_output,
                    args=(self.process, room_id),
                    daemon=True
                )
                monitor_thread.start()

                update_status(StreamStatus.STREAMING)
                # 注意：这里不能立即重置 retry_count，否则会陷入"启动->失败->重置->启动"的死循环
                # self.retry_count = 0
                self.current_retry_interval = self.config.retry_interval

                # 主循环：监控进程状态和推流健康
                last_health_check = time.time()
                run_start_time = time.time()
                has_reset_retry = False

                while not self._stop_flag:
                    # 检查进程是否退出
                    if self.process.poll() is not None:
                        exit_code = self.process.returncode
                        logger.warning(f"[{room_id}] FFmpeg进程退出, 退出码: {exit_code}")
                        break

                    # 稳定运行检查：如果运行超过60秒，才认为是一次成功的连接，重置重试计数
                    if not has_reset_retry and (time.time() - run_start_time > 60):
                        self.retry_count = 0
                        has_reset_retry = True
                        logger.info(f"[{room_id}] 推流稳定运行超过60秒，重置重试计数器")

                    # 定期健康检查
                    current_time = time.time()
                    if current_time - last_health_check >= self.config.heartbeat_interval:
                        last_health_check = current_time

                        if not self._check_stream_health(output_dir):
                            logger.warning(f"[{room_id}] 推流健康检查失败，准备重连")
                            self.process.terminate()
                            self.process.wait(timeout=5)
                            break
                        else:
                            # logger.debug(f"[{room_id}] 推流健康检查通过")
                            pass

                    time.sleep(1)

                # 如果是主动停止，退出循环
                if self._stop_flag:
                    update_status(StreamStatus.STOPPED)
                    break

            except Exception as e:
                logger.error(f"[{room_id}] 推流异常: {e}")

            # 重连逻辑
            self.retry_count += 1
            self.total_reconnects += 1

            if self.retry_count <= self.config.max_retries:
                logger.info(f"[{room_id}] 等待 {self.current_retry_interval}秒 后进行第 {self.retry_count} 次重连...")
                time.sleep(self.current_retry_interval)

                # 指数退避
                self.current_retry_interval = min(
                    self.current_retry_interval * self.config.retry_backoff,
                    self.config.max_retry_interval
                )
            else:
                logger.error(f"[{room_id}] 达到最大重试次数 {self.config.max_retries}，停止推流")
                update_status(StreamStatus.FAILED)

        return self.process

    def stop_stream(self, room_id: str = "unknown"):
        """安全停止推流"""
        self._stop_flag = True

        if self.process:
            try:
                logger.info(f"[{room_id}] 正在停止推流...")
                self.process.terminate()
                self.process.wait(timeout=10)
                logger.info(f"[{room_id}] 推流已停止")
            except subprocess.TimeoutExpired:
                logger.warning(f"[{room_id}] 推流进程终止超时，强制杀死")
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.error(f"[{room_id}] 停止推流异常: {e}")

        self.status = StreamStatus.STOPPED

    def get_stream_stats(self) -> dict:
        """获取推流统计信息"""
        return {
            "status": self.status.value,
            "retry_count": self.retry_count,
            "total_reconnects": self.total_reconnects,
            "uptime": time.time() - self.stream_start_time if self.stream_start_time else 0
        }


# ========== 主备节点配置 ==========
PRIMARY_NODE_URL = os.environ.get('PRIMARY_NODE_URL', 'http://47.236.42.104:8080')
BACKUP_NODE_URL = os.environ.get('BACKUP_NODE_URL', 'http://47.237.6.199:8080')  # 备用节点URL


# 心跳接口
@app.get("/check_status")
def read_root():
    return {"code": 200, "message": "live-spider-API-V2-client is running"}


def md5_encrypt(string):
    # 创建一个md5哈希对象
    md5_hash = hashlib.md5()
    # 更新哈希对象的字节数据
    md5_hash.update(string.encode('utf-8'))
    # 返回十六进制的哈希值
    return md5_hash.hexdigest()


# ========== 主备节点请求函数 ==========
def request_with_fallback(method, endpoint, json_data=None, timeout=5):
    """
    发送请求到主节点，如果失败则尝试备用节点

    参数:
    - method: 请求方法 ('post' 或 'get')
    - endpoint: 端点路径 (如 '/get_roominfo')
    - json_data: 请求数据
    - timeout: 请求超时时间

    返回: 响应对象，如果两个节点都失败则返回 None
    """
    nodes = [PRIMARY_NODE_URL]
    if BACKUP_NODE_URL:
        nodes.append(BACKUP_NODE_URL)

    for node_url in nodes:
        try:
            url = f"{node_url}{endpoint}"

            if method.lower() == 'post':
                response = requests.post(url, json=json_data, timeout=timeout)
            else:
                response = requests.get(url, json=json_data, timeout=timeout)

            response.raise_for_status()
            return response

        except Exception as e:
            logger.error(f"请求失败 {node_url}{endpoint}: {e}")
            if node_url != nodes[-1]:  # 不是最后一个节点，继续尝试下一个
                logger.info(f"正在尝试备用节点...")
            else:
                logger.error(f"所有节点都已尝试，请求失败")
                return None

    return None


 # apollo获取配置
def fetch_apollo_config(istest=0):
    APOLLO_URL = str(os.environ.get('APOLLO_URL')).strip()
    APOLLOID = str(os.environ.get('APOLLOID')).strip()

    # 判断是不是测试环境
    if 'develop' in APOLLO_URL:
        istest = 1

    # if istest == 1:
    #     APOLLO_URL = 'http://dev-apollo.tec-develop.com'

    if istest != 1:
        # http://10.225.17.67:30080（windows机子需要单独做映射）
        if os.name == 'nt':
            APOLLO_URL = 'http://10.225.17.67:30080'

    APOLLOID = 'live-spider'

    if istest == 1:
        url = "{}/configs/{}/dev01/application".format(str(APOLLO_URL), str(APOLLOID))
        print("测试环境", url)
    else:
        url = "{}/configs/{}/PRO/application".format(str(APOLLO_URL), str(APOLLOID))
        print("生产环境", url)

    # 配置你的 Apollo 服务详情
    config_data = {}
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查响应是否成功
        config_data = response.json()
    except Exception as e:
        print(f"获取apollo配置失败: {e}")

    if config_data:
        configurations = config_data["configurations"]
        return configurations
    else:
        return {}



# 获取当前文件所在文件夹绝对路径
def get_current_directory():
    current_file_path = os.path.abspath(__file__)
    current_directory = os.path.dirname(current_file_path)
    return current_directory.replace("\\", '/')


# 清空指定文件夹
def ensure_folder_empty(folder_path):
    # 如果文件夹不存在，则创建文件夹
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        logger.info(f"文件夹 {folder_path} 不存在，已创建。")
    else:
        # 如果文件夹存在，则清空文件夹
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logger.error(f'删除文件 {file_path} 时出错: {e}')
        logger.info(f"文件夹 {folder_path} 已清空。")


# 统计指定文件夹下每个子文件夹中的文件数量
def count_files_in_subdirectories(folder_path="", iscount=False):
    """
    统计指定文件夹下每个子文件夹中的文件数量。

    参数:
    folder_path (str): 文件夹路径

    返回:
    dict: 以子文件夹名称为键，子文件夹中文件数量为值的字典
    """
    result = {}
    if folder_path == "":
        folder_path = get_current_directory() + '/video'

    # 检查文件夹是否存在
    if not os.path.exists(folder_path):
        logger.warning(f"文件夹 {folder_path} 不存在")
        return result

    # 遍历文件夹中的每个子文件夹
    for entry in os.listdir(folder_path):
        subfolder_path = os.path.join(folder_path, entry)
        # 检查是否为子文件夹
        if os.path.isdir(subfolder_path):
            file_count = 0
            # 遍历子文件夹中的每个文件
            for subentry in os.listdir(subfolder_path):
                subentry_path = os.path.join(subfolder_path, subentry)
                # 检查是否为文件
                if os.path.isfile(subentry_path):
                    file_count += 1
            # 超过3个认为开始积压视频了
            if not iscount:
                if file_count >= 4:
                    result[entry] = file_count
            else:
                result[entry] = file_count
    return result


# kafka相关操作
class KafkaHelper:
    def __init__(self, istest=1):
        configurations = fetch_apollo_config(istest)
        kafka_server = list(eval(configurations["kafkaPro"]))
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_server,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )

    # 数据推到kafka
    def sendToKafka(self, data, topic_name='liveTs'):
        self.producer.send(topic_name, value=data)
        self.producer.flush()


# 阿里云OSS相关操作
class AiyunOBSHelper:
    def __init__(self, istest=1):
        configurations = fetch_apollo_config(istest)
        # print("configurations-->",configurations)
        self.endpoint = configurations['endpoint']
        self.bucket_name = configurations['bucket_name']
        self.access_key_id = configurations['access_key_id']
        self.access_key_secret = configurations['access_key_secret']

        # 创建Bucket实例
        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)

    # 上传文件,返回在线链接
    def upload_file(self, local_file_path, periodOfValidity=86400 * 180):
        local_file_path = local_file_path.replace("\\", '/')
        object_name = 'realtime-video/' + local_file_path.split('/')[-1]
        try:
            self.bucket.put_object_from_file(object_name, local_file_path)
            # print(f"文件 {local_file_path} 已成功上传至 {object_name}")
            # 生成一个预签名的URL，有效期为10天
            url = self.bucket.sign_url('GET', object_name, periodOfValidity)
            return url
        except Exception as e:
            logger.error(f"上传失败: {e}")
            return None


# 文件与视频文件相关操作
class FileHelper:
    def __init__(self, folder_path=""):
        self.folder_path = folder_path

    # 读取文件夹下所有文件
    def list_files_in_directory(self, directory):
        # 获取文件夹下所有文件
        try:
            files = os.listdir(directory)
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.error(f"读取目录失败: {directory}, 错误: {e}")
            return []

        # 过滤出文件（排除文件夹）
        files = [f for f in files if os.path.isfile(os.path.join(directory, f))]

        # 过滤掉切割产物文件（文件名格式如 xxx_00000.00001.ts，包含多个数字段）
        # 切割产物特征：文件名最后部分是 NNNNN.MMMMM.ts 格式
        def is_cut_product(filename):
            """判断是否为切割产物文件"""
            if not filename.endswith('.ts'):
                return False
            # 获取文件名（不含扩展名）的最后部分
            name_without_ext = filename[:-3]  # 去掉 .ts
            parts = name_without_ext.split('_')
            if len(parts) < 2:
                return False
            last_part = parts[-1]  # 如 "00000.00001" 或 "00000"
            # 如果最后部分包含点号且点号两边都是数字，则是切割产物
            if '.' in last_part:
                segments = last_part.split('.')
                if len(segments) == 2 and segments[0].isdigit() and segments[1].isdigit():
                    return True
            return False

        def is_file_ready(filepath):
            """检查文件是否已完成写入（修改时间超过2秒）"""
            try:
                mtime = os.path.getmtime(filepath)
                # 文件修改时间超过2秒才认为写入完成
                return (time.time() - mtime) > 2
            except Exception:
                return False

        # 过滤掉切割产物和正在写入的文件
        ready_files = []
        for f in files:
            if is_cut_product(f):
                continue
            filepath = os.path.join(directory, f)
            if is_file_ready(filepath):
                ready_files.append(f)

        # 按照文件名排序
        sorted_files = sorted(ready_files)
        # 排除最后一个文件（可能还在被FFmpeg写入）
        if len(sorted_files) > 1:
            return sorted_files[:-1]
        else:
            return []

    # 额外切割大的视频，返回视频，与视频链接
    def cutBigFile(self, input_video_path, segment_duration):
        # 切割后视频文件地址
        output_directory, output_filename = os.path.split(input_video_path)
        stdPath = str(output_filename.split(".")[0] + '.%00005d.ts')
        output_pattern = output_directory + '/' + stdPath
        command = [
            'ffmpeg',
            '-i', input_video_path,
            '-c', 'copy',
            '-segment_time', str(segment_duration),
            '-f', 'segment',
            output_pattern
        ]

        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            logger.error(f"视频切割失败: {e}")
            return []
        # 获取切割后的视频文件路径地址列表
        output_files = [
            os.path.join(output_directory, f)
            for f in os.listdir(output_directory)
            if f.startswith(output_filename.split(".")[0]) and len(f.split(".")) > 2
        ]
        return output_files

    # 传入本地视频路径，返回视频基础信息
    def parse_video_Info(self, port_info):

        # 基础信息
        data = {
            "roomID": port_info["roomId"],
            "room_id": port_info["room_id"],
            "roomName": port_info["filePath"],
            "intervalTime": port_info["interval"],
            "local_file_path": port_info["File"],
            "createTime": port_info["CreatTime"],
            "init_startTime": port_info["init_startTime"],
        }

        file_stat = os.stat(data["local_file_path"])
        data["st_size"] = round(file_stat.st_size / (1024 * 1024), 2)  # 视频大小
        data["videoStartTime"] = str(int(file_stat.st_ctime))  # 视频开始时间
        data["videoEndTime"] = str(int(file_stat.st_mtime))  # 视频结束时间
        if data["videoEndTime"] == data["videoStartTime"]:
            data["videoEndTime"] = str(int(data["videoStartTime"]) + 8)
        data["intervalTime"] = int(data["videoEndTime"]) - int(data["videoStartTime"])

        data["batchID"] = port_info["roomId"]
        data["UserID"] = port_info["id"]

        data["videoIndex"] = str(int(data["local_file_path"].split('_')[-1].split(".")[0]))
        # del data["local_file_path"]
        return data

    # 传入本地视频路径，返回视频基础信息
    def parse_video_Info_shopee(self, port_info):
        # print("port_info222-->",port_info)
        # 基础信息
        data = {
            "roomID": port_info["room_id"],
            "room_id": port_info["session"]["room_id"],
            "roomName": port_info["session"]["username"],
            "intervalTime": port_info["interval"],
            "local_file_path": port_info["File"],
            "createTime": port_info["CreatTime"],
            "init_startTime": port_info["init_startTime"],
        }

        file_stat = os.stat(data["local_file_path"])
        data["st_size"] = round(file_stat.st_size / (1024 * 1024), 2)  # 视频大小
        data["videoStartTime"] = str(int(file_stat.st_ctime))  # 视频开始时间
        data["videoEndTime"] = str(int(file_stat.st_mtime))  # 视频结束时间
        if data["videoEndTime"] == data["videoStartTime"]:
            data["videoEndTime"] = str(int(data["videoStartTime"]) + 8)
        data["intervalTime"] = int(data["videoEndTime"]) - int(data["videoStartTime"])

        data["batchID"] = port_info["session"]["session_id"]
        data["UserID"] = port_info["session"]["uid"]
        data["shop_id"] = port_info["session"]["shop_id"]
        data["nickname"] = port_info["session"]["nickname"]
        data["member_cnt"] = port_info["session"]["member_cnt"]
        data["like_cnt"] = port_info["session"]["like_cnt"]
        data["start_time"] = port_info["session"]["start_time"]
        data["viewer_count"] = port_info["session"]["viewer_count"]
        data["chatroom_id"] = port_info["session"]["chatroom_id"]

        data["videoIndex"] = str(int(data["local_file_path"].split('_')[-1].split(".")[0]))
        # del data["local_file_path"]
        return data

    # 情况2:处理进程阻塞不释放导致的大文件问题
    def parse_video_Info2(self, data2, big_file_path):
        file_stat = os.stat(big_file_path)
        videoStartTime = str(
            int(file_stat.st_ctime) + int(data2["intervalTime"]) * int(data2["local_file_path"].split(".")[-2]))
        data2["videoStartTime"] = str(videoStartTime)  # 视频开始时间
        data2["videoEndTime"] = str(int(videoStartTime) + int(data2["intervalTime"]))  # 视频结束时间
        data2["st_size"] = round(file_stat.st_size / (1024 * 1024), 2)
        # corollashoes_th_1752982646_00000.00002.ts
        meta_index_video = data2["local_file_path"].split('_')[-1].split(".")
        # ['00000', '00002', 'ts']
        data2["videoIndex"] = str(str(int(meta_index_video[0])) + '.' + str(int(meta_index_video[1])))
        return data2

    def cleanup_stale_files(self, directory, max_age_seconds=1800):
        """
        清理过时的临时文件

        参数:
        - directory: 要清理的目录
        - max_age_seconds: 文件最大存活时间(秒)，默认30分钟

        返回: 清理的文件数量
        """
        cleaned_count = 0
        try:
            if not os.path.exists(directory):
                return 0

            current_time = time.time()
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                try:
                    if os.path.isfile(filepath):
                        # 检查文件修改时间
                        mtime = os.path.getmtime(filepath)
                        age = current_time - mtime
                        if age > max_age_seconds:
                            os.remove(filepath)
                            cleaned_count += 1
                            logger.warning(f"清理过时文件: {filepath} (存在{int(age)}秒)")
                except PermissionError:
                    logger.debug(f"文件被占用，跳过清理: {filepath}")
                except Exception as e:
                    logger.error(f"清理文件失败: {filepath}, 错误: {e}")

        except Exception as e:
            logger.error(f"清理目录失败: {directory}, 错误: {e}")

        return cleaned_count


# 入kafaka 格式矫正
class MainHelper:
    def __init__(self, topic_name='liveTs', istest=1):
        self.FileHelperObj = FileHelper()
        self.AliYOBSHelperObj = AiyunOBSHelper(istest)
        self.KafkaHelperObj = KafkaHelper(istest)
        self.topic_name = topic_name

        # 文件处理状态追踪 (防止重复处理)
        self._processing_files = set()  # 正在处理中的文件路径
        self._processed_files = set()  # 已成功处理的文件路径
        self._processed_lock = threading.Lock()  # 线程安全锁
        self._last_cleanup_time = time.time()  # 上次清理时间

    def _cleanup_processed_files(self):
        """定期清理已处理文件记录，防止内存泄漏（每30分钟清理一次）"""
        current_time = time.time()
        if current_time - self._last_cleanup_time > 1800:  # 30分钟
            with self._processed_lock:
                # 清空已处理记录（因为30分钟前的文件肯定已经不存在了）
                old_count = len(self._processed_files)
                self._processed_files.clear()
                self._last_cleanup_time = current_time
                if old_count > 0:
                    logger.info(f"清理已处理文件记录: 清除 {old_count} 条记录")

    def _is_file_processing_or_processed(self, file_path: str) -> bool:
        """检查文件是否正在处理或已处理"""
        with self._processed_lock:
            return file_path in self._processing_files or file_path in self._processed_files

    def _mark_file_processing(self, file_path: str):
        """标记文件为正在处理"""
        with self._processed_lock:
            self._processing_files.add(file_path)

    def _mark_file_completed(self, file_path: str, success: bool):
        """标记文件处理完成"""
        with self._processed_lock:
            self._processing_files.discard(file_path)
            if success:
                self._processed_files.add(file_path)

    # 数据入kafka
    def toKafkaLiveData(self, port_info):
        video_local_path = port_info['output_dir_init']

        # 定期清理已处理文件记录
        self._cleanup_processed_files()

        # 定期清理过时文件（每次调用时检查，清理超过30分钟的文件）
        # 这可以防止因为各种异常导致的文件积压
        self.FileHelperObj.cleanup_stale_files(video_local_path, max_age_seconds=1800)

        # 检查文件积压情况
        try:
            all_files = [f for f in os.listdir(video_local_path) if os.path.isfile(os.path.join(video_local_path, f))]
            if len(all_files) > 50:
                logger.error(f"严重文件积压: {video_local_path} 有 {len(all_files)} 个文件待处理!")
            elif len(all_files) > 20:
                logger.warning(f"文件积压警告: {video_local_path} 有 {len(all_files)} 个文件待处理")
        except Exception:
            pass

        file_paths = self.FileHelperObj.list_files_in_directory(video_local_path)

        update_file_list = list()
        for File in file_paths:
            try:
                full_path = video_local_path + '/' + File

                # 检查文件是否已在处理中或已处理完成，防止重复处理
                if self._is_file_processing_or_processed(full_path):
                    logger.debug(f"跳过已处理/处理中的文件: {File}")
                    continue

                # 标记为正在处理
                self._mark_file_processing(full_path)

                port_info["File"] = full_path
                # 先获取基础信息(这里需要判断是哪个平台的，TT还是shopee)
                if 'session_id' in port_info.get("session", {}).keys() and 'shop_id' in port_info.get("session",
                                                                                                      {}).keys():
                    data = self.FileHelperObj.parse_video_Info_shopee(port_info)
                else:
                    data = self.FileHelperObj.parse_video_Info(port_info)

                # 判断是否为长视频
                if data["intervalTime"] > 12:
                    # print("视频时长超过10秒,需要切割视频")
                    cutVideolist = self.FileHelperObj.cutBigFile(data["local_file_path"], 8)

                    # 只有切割成功才处理
                    if cutVideolist:
                        # 遍历分割后的视频
                        for catFile in cutVideolist:
                            data2 = data.copy()

                            data2["local_file_path"] = catFile.replace('\\', "/")
                            data2["_original_file_path"] = full_path  # 追踪原始文件路径
                            data2["intervalTime"] = 8
                            data2_end = self.FileHelperObj.parse_video_Info2(data2, data["local_file_path"])
                            update_file_list.append(data2_end)

                        # 切割成功后删除原始长视频
                        try:
                            logger.debug(f"移除长视频--> {data['local_file_path']}")
                            os.remove(data["local_file_path"])
                        except PermissionError as e:
                            logger.warning(f"长视频文件被占用，稍后重试删除: {data['local_file_path']}")
                        except FileNotFoundError:
                            logger.debug(f"长视频文件已不存在: {data['local_file_path']}")
                        except Exception as e:
                            logger.error(f"删除长视频文件失败: {data['local_file_path']}, 错误: {e}")
                    else:
                        # 切割失败，取消处理标记，下次再处理
                        logger.warning(f"视频切割失败，跳过: {data['local_file_path']}")
                        self._mark_file_completed(full_path, False)


                else:
                    # print("视频时长不超过10秒,不需要切割视频")
                    data["_original_file_path"] = full_path  # 追踪原始文件路径
                    update_file_list.append(data)
            except Exception as e:
                logger.error(f"处理文件失败: {File}, 错误: {e}")
                # 处理失败，取消处理标记，下次可以重试
                self._mark_file_completed(full_path, False)
                continue

        # print("update_file_list--->",update_file_list)
        # # # 上传视频
        for item in update_file_list:
            local_file_path = item["local_file_path"]
            original_file_path = item.get("_original_file_path", local_file_path)  # 用于追踪原始文件

            # 检查文件是否存在
            if not os.path.exists(local_file_path):
                logger.warning(f"文件不存在，跳过上传: {local_file_path}")
                self._mark_file_completed(original_file_path, False)
                continue

            # 上传到OSS
            AliYUrl = self.AliYOBSHelperObj.upload_file(local_file_path)

            # 上传失败处理
            if AliYUrl is None:
                logger.warning(f"上传失败，保留文件稍后重试: {local_file_path}")
                self._mark_file_completed(original_file_path, False)  # 标记为未完成，下次可以重试
                continue

            item["videoUrl"] = AliYUrl
            item["uniID"] = md5_encrypt(AliYUrl)

            # 删除本地文件
            delete_success = False
            try:
                logger.debug(f"移除--> {local_file_path}")
                os.remove(local_file_path)
                delete_success = True
            except PermissionError:
                logger.warning(f"文件被占用，稍后删除: {local_file_path}")
                # 文件被占用但上传成功，仍然发送kafka（但标记为已处理防止重复）
                delete_success = True  # 上传成功就算处理成功
            except FileNotFoundError:
                logger.debug(f"文件已被删除: {local_file_path}")
                delete_success = True
            except Exception as e:
                logger.error(f"删除文件失败: {local_file_path}, 错误: {e}")
                delete_success = True  # 上传成功就算处理成功

            # 标记文件处理完成
            self._mark_file_completed(original_file_path, delete_success)

            # 从item中删除本地路径
            del item["local_file_path"]
            if "_original_file_path" in item:
                del item["_original_file_path"]

            try:
                # 这里需要区分是TT还是shopee(历史遗留原因导致字段没有对齐，需要判断,虾皮对应字段更多)
                if 'shop_id' in item.keys():
                    update_item = item.copy()
                else:
                    item["roomID"] = item["room_id"]
                    update_item = item.copy()
                    del item["room_id"]
                    del item["init_startTime"]
                    del item["st_size"]

                self.KafkaHelperObj.sendToKafka(item, topic_name=self.topic_name)
                logger.info(f"上传data---> {item}")
                try:
                    online_room_list[update_item["room_id"]]["status_update_time"] = int(time.time())
                    online_room_list[update_item["room_id"]]["ip"] = socket.gethostbyname(socket.gethostname())
                except Exception as e:
                    # 存在资源占用情况，但不影响最终结果，所以不抛出异常处理
                    pass

            except Exception as e:
                logger.error(f"发送Kafka异常--> {e}")


def ProducerTask(port_info_init):
    """
    直播推流生产者任务 - 优化版本

    特性:
    - 自动重连机制
    - 网络自适应
    - 详细日志记录
    - 健康检查
    """
    port_info = port_info_init.get("live_info")
    room_id = port_info_init["room_id"]

    # 获取当前文件所在文件夹路径
    directory = get_current_directory()
    # 保存单独文件夹名
    filePath = port_info["filePath"]
    # 输出文件名前缀、没有就创建文件夹,如果有则清空文件夹
    output_dir_init = "{}/video/{}".format(directory, filePath)

    ensure_folder_empty(output_dir_init)
    # 指定输出视频文件夹地址
    port_info["output_dir_init"] = output_dir_init
    port_info["room_id"] = room_id
    port_info["interval"] = 8
    port_info["init_startTime"] = port_info["startTime"]

    live_url = port_info["flv_url"]
    CreatTime = str(int(time.time()))

    port_info["CreatTime"] = CreatTime

    # 视频文件保存地址
    output_filename = output_dir_init + '/' + filePath + '_' + CreatTime + '_%00005d.ts'

    # 判断平台类型 (根据 session 中是否包含 shop_id 来区分)
    platform = "shopee" if 'shop_id' in port_info.get("session", {}) else "tiktok"

    logger.info(f"[{room_id}] 开始推流任务")
    logger.info(f"[{room_id}] 直播源: {live_url}")
    logger.info(f"[{room_id}] 输出目录: {output_dir_init}")
    logger.info(f"[{room_id}] 平台类型: {platform}")

    # 创建推流配置
    stream_config = StreamConfig(
        max_retries=5,  # 最大重试5次
        retry_interval=3,  # 初始重试间隔3秒
        retry_backoff=1.5,  # 重试间隔递增因子
        max_retry_interval=30,  # 最大重试间隔30秒
        analyzeduration=5000000,  # 5秒分析时长
        probesize=10000000,  # 10MB探测大小
        heartbeat_interval=30,  # 30秒心跳检测
        no_data_timeout=60  # 60秒无数据超时
    )

    # 创建推流管理器
    stream_manager = FFmpegStreamManager(config=stream_config)

    # 状态变更回调
    def on_status_change(status: StreamStatus, rid: str):
        """推流状态变更时更新在线列表"""
        try:
            if rid in online_room_list:
                online_room_list[rid]["stream_status"] = status.value
                online_room_list[rid]["status_update_time"] = int(time.time())
        except Exception as e:
            logger.error(f"[{rid}] 更新状态失败: {e}")

    # 启动上传处理线程
    upload_stop_flag = threading.Event()

    def upload_worker():
        """后台上传工作线程"""
        while not upload_stop_flag.is_set():
            try:
                MainHelperObj.toKafkaLiveData(port_info)
            except Exception as e:
                # logger.error(f"[{room_id}] 上传处理异常: {e}")
                logger.error(f"[{room_id}] 上传处理异常: {e}")
            time.sleep(1)

    upload_thread = threading.Thread(target=upload_worker, daemon=True)
    upload_thread.start()

    try:
        # 启动推流 (带自动重连，传递平台参数)
        process = stream_manager.start_stream(
            live_url=live_url,
            output_filename=output_filename,
            output_dir=output_dir_init,
            segment_time=port_info["interval"],
            room_id=room_id,
            on_status_change=on_status_change,
            platform=platform
        )

        # 推流结束后的统计
        stats = stream_manager.get_stream_stats()
        logger.info(f"[{room_id}] 推流任务结束, 统计信息: {stats}")

    except KeyboardInterrupt:
        logger.info(f"[{room_id}] 收到中断信号，停止推流")
        stream_manager.stop_stream(room_id)
    except Exception as e:
        logger.error(f"[{room_id}] 推流任务异常退出: {e}")
    finally:
        # 停止上传线程
        upload_stop_flag.set()
        upload_thread.join(timeout=5)

        # 最后一次上传处理
        try:
            MainHelperObj.toKafkaLiveData(port_info)
        except Exception as e:
            logger.error(f"[{room_id}] 最终上传处理异常: {e}")

        # 关键修改：任务结束后，从在线列表中移除该房间
        # 防止已停止采集的任务继续上报心跳，导致服务端误判
        if room_id in online_room_list:
            try:
                del online_room_list[room_id]
                logger.info(f"[{room_id}] 采集结束，已从在线列表中移除")
            except Exception as e:
                logger.error(f"[{room_id}] 移除房间失败: {e}")

        logger.info(f"[{room_id}] 推流任务清理完成")

    # 如果没有达到服务器承载上线数据liveRoomNumber，每次获取一个房间信息


def get_room_info(liveRoomNumber=4):
    """获取房间信息的函数"""
    current_room_count = len(online_room_list)
    if current_room_count < liveRoomNumber:
        for i in range(liveRoomNumber - current_room_count):
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
                response = request_with_fallback('post', '/get_roominfo', json_data={"ip": local_ip})

                if response is None:
                    logger.warning("无法从任何节点获取房间信息")
                    continue

                live_room_info = response.json()
                if live_room_info["data"] and live_room_info["data"]["room_id"] not in online_room_list.keys():
                    online_room_list[live_room_info["data"]["room_id"]] = live_room_info["data"]
                    # 初次获取更新状态为最新时间与1，防止第一次按照为0上报信息
                    online_room_list[live_room_info["data"]["room_id"]]["allocation_status"] = 1
                    online_room_list[live_room_info["data"]["room_id"]]["status_update_time"] = int(time.time())

                    logger.info(f"获取到新房间: {live_room_info['data']}")
                    # 每次获取到新的直播间进行启动一条新的监控线程
                    port_info_init = live_room_info["data"]
                    # ProducerTask(port_info_init)
                    producer_thread = threading.Thread(target=ProducerTask, args=(port_info_init,))
                    producer_thread.daemon = False
                    producer_thread.start()

                    # 如果已经达到目标数量，提前退出(差几个直播间就获取几次)
                    if len(online_room_list.keys()) >= liveRoomNumber:
                        break
            except Exception as e:
                logger.error(f"获取房间信息时出错: {e}")


# 定时上报功能
def report_room_info(online_room_list):
    """定时上报房间信息"""
    if len(online_room_list) > 0:
        try:
            logger.info(f"上报房间信息: {online_room_list}")
            response = request_with_fallback('post', '/report_roominfo', json_data=online_room_list)

            if response is None:
                logger.warning("无法从任何节点上报房间信息")
                return

            released_room_ids = response.json().get("released_rooms", [])
            for room_id in released_room_ids:
                if room_id in online_room_list:
                    del online_room_list[room_id]
                    logger.info(f"释放房间: {room_id}")
        except Exception as e:
            logger.error(f"上报房间信息时出错: {e}")


# 获取房间信息与上报定时任务
def start_get_room_scheduler(liveRoomNumber):
    """启动定时任务,每3分钟执行一次get_room_info"""

    def scheduler():
        while True:
            try:
                # 优先上报保活，防止获取新任务耗时过长导致超时
                report_room_info(online_room_list)
                get_room_info(liveRoomNumber)

            except Exception as e:
                logger.error(f"执行get_room_info时出错: {e}")
            time.sleep(180)  # 3分钟 = 180秒


    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info(f"{now} get_room_info定时任务已启动，每3分钟执行一次")


if __name__ == "__main__":
    # 确保日志目录存在
    log_dir = os.path.join(get_current_directory(), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        logger.info(f"创建日志目录: {log_dir}")

    istest = 0
    config_apollo = fetch_apollo_config(istest)
    topic_name = config_apollo.get("topic_name", "liveTs")
    liveRoomNumber = int(config_apollo.get("cutliveNumber",4))
    MainHelperObj = MainHelper(topic_name=topic_name)
    online_room_list = dict()

    logger.info("=" * 50)
    logger.info("FFmpeg直播推流客户端启动")
    logger.info(f"配置: topic_name={topic_name}, liveRoomNumber={liveRoomNumber}")
    logger.info("=" * 50)

    # 启动主进程
    start_get_room_scheduler(liveRoomNumber)

    # 保持主线程运行，防止程序直接退出
    uvicorn.run(app, host="0.0.0.0", port=8080)

