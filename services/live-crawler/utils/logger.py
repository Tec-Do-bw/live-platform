# -*- coding: UTF-8 -*-
# @author: ylw
# @file: logger_func
# @time: 2024/1/15
# @desc:
from loguru import logger
import os
import sys
from os.path import dirname, abspath, join
from pathlib import Path

# 强制启用loguru颜色输出
os.environ["LOGURU_COLORS"] = "TRUE"
os.environ["LOGURU_FORCE_COLORS"] = "TRUE"

KNOWN_PLATFORMS = ('lazada', 'tiktok', 'shopee')

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file}:{line} - {message}"


class Logings:
    level = None  # 延迟初始化，避免循环依赖
    __instance = None
    _is_logger_added = False
    service_name = os.getenv('LIVE_CRAWLER_LOG_SERVICE', 'app')

    LOG_DIR = join(dirname(dirname(abspath(__file__))), 'logs')
    logpath = LOG_DIR

    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(Logings, cls).__new__(cls, *args, **kwargs)
        return cls.__instance

    def __init__(self, logging_name=None, *args, **kwargs):
        # 延迟初始化日志级别（统一从 core.config.Settings.LOG_LEVEL 读取，
        # 导入失败时降级为 INFO 兜底，确保 logger 自身可独立工作）
        if Logings.level is None:
            try:
                from core.config import Settings
                Logings.level = Settings.LOG_LEVEL
            except Exception:
                Logings.level = 'INFO'

        if not Logings._is_logger_added:  # 只有当logger还没有添加handler时才执行添加
            self._setup_handlers(logging_name=logging_name)

    @classmethod
    def configure(cls, service_name: str, log_dir: str | Path | None = None) -> None:
        """按启动入口重新配置日志落点。"""
        cls.service_name = service_name
        if log_dir is not None:
            cls.LOG_DIR = str(log_dir)
            cls.logpath = str(log_dir)
        os.makedirs(cls.logpath, exist_ok=True)
        logger.remove()
        cls._is_logger_added = False
        Logings()

    def _setup_handlers(self, logging_name=None):
        """配置控制台、入口文件和 realtime 分离文件 handler。"""
        logger.remove()  # 移除默认处理器
        logger.add(
            sys.stdout,  # 输出目标：标准输出（控制台）
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}:{line}</cyan> - <level>{message}</level>",
            level=Logings.level,  # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
            colorize=True,  # 启用颜色输出（控制台彩色显示）
            enqueue=True  # 异步写入日志，避免阻塞主线程
        )

        if logging_name:
            self.logging_name = join(self.logpath, f'{logging_name}.logs')
        else:
            service_dir = join(self.logpath, 'services', self.service_name)
            os.makedirs(service_dir, exist_ok=True)
            self.logging_name = join(service_dir, '{time:YYYY-MM-DD}.logs')

        # 普通入口日志排除 realtime，避免 Lazada 实时采集污染 history/入口日志。
        logger.add(
            self.logging_name,
            format=LOG_FORMAT,
            encoding='utf-8',
            rotation='00:00',
            retention='30 days',
            level=Logings.level,
            diagnose=True,
            backtrace=True,
            enqueue=True,
            colorize=True,
            filter=lambda record: record["extra"].get("crawl_type") != "realtime",
        )

        # 按 crawl_type + platform 分离日志
        self._add_separated_handlers()

        Logings._is_logger_added = True

    def _add_separated_handlers(self):
        """为实时采集按平台添加分离日志 handler"""
        for p in KNOWN_PLATFORMS:
            sub_dir = join(self.logpath, 'realtime', p)
            if not os.path.isdir(sub_dir):
                os.makedirs(sub_dir)

        for p in KNOWN_PLATFORMS:
            logger.add(
                join(self.logpath, 'realtime', p, '{time:YYYY-MM-DD}.logs'),
                format=LOG_FORMAT, encoding='utf-8', rotation='00:00',
                retention='30 days', level=Logings.level, enqueue=True,
                filter=lambda record, _p=p: (
                    record["extra"].get("crawl_type") == "realtime"
                    and record["extra"].get("platform") == _p
                ),
            )

    @property
    def get_level(self):
        """返回当前日志等级"""
        return self.level

    @classmethod
    def set_level(cls, level):
        """设置日志等级"""
        cls.level = level
        cls.configure(cls.service_name)

    @staticmethod
    def format_context(**kwargs):
        """格式化上下文信息

        Args:
            **kwargs: 键值对形式的上下文信息，如 credit_code='xxx', uuid='yyy'

        Returns:
            str: 格式化后的上下文字符串，如 "信用代码=xxx, uuid=yyy"
        """
        return ", ".join([f"{k.replace('_', ' ')}={v}" for k, v in kwargs.items() if v])

    def get_logger(self):
        return logger


logger = Logings().get_logger()

__all__ = [
    'logger',
    'Logings'
]

if __name__ == '__main__':
    # logs = Logings()
    #
    #
    # def func(a, b):
    #     return a / b
    #
    #
    # def my(z, c):
    #     try:
    #         func(z, c)
    #     except ZeroDivisionError:
    #         logs.exception('...........')
    #
    #
    # my(5, 0)

    logs = Logings()
    print(logs.get_level)  # 将打印 'INFO'

    # 测试不同级别的日志
    logger.debug("这是一条调试信息")
    logger.info("这是一条信息")
    logger.warning("这是一条警告")
    logger.error("这是一条错误信息")
    logger.critical("这是一条严重错误信息")

    # 测试带上下文的日志
    context = Logings.format_context(credit_code="91440101XXXXXX", uuid="abc-123", record_no="R001")
    logger.info(f"数据处理完成: {context}")
