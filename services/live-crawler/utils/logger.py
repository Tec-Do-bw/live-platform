# -*- coding: UTF-8 -*-
# @author: ylw
# @file: logger_func
# @time: 2024/1/15
# @desc:
from loguru import logger
import os
import datetime
import sys
from os.path import dirname, abspath, join

# 强制启用loguru颜色输出
os.environ["LOGURU_COLORS"] = "TRUE"
os.environ["LOGURU_FORCE_COLORS"] = "TRUE"

KNOWN_PLATFORMS = ('lazada', 'tiktok', 'shopee')

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file}:{line} - {message}"


class Logings:
    level = None  # 延迟初始化，避免循环依赖
    __instance = None
    _is_logger_added = False

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

        if not self._is_logger_added:  # 只有当logger还没有添加handler时才执行添加
            # 配置控制台输出，启用颜色
            logger.remove()  # 移除默认处理器
            logger.add(
                sys.stdout,  # 输出目标：标准输出（控制台）
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}:{line}</cyan> - <level>{message}</level>",
                # 日志格式，支持HTML标签着色
                level=Logings.level,  # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
                colorize=True,  # 启用颜色输出（控制台彩色显示）
                enqueue=True  # 异步写入日志，避免阻塞主线程
            )

            # 日志文件路径，使用 {time} 占位符，loguru会自动处理日期
            if not logging_name:
                # 默认日志文件名格式：logs/{time:YYYY-MM-DD}.logs
                self.logging_name = join(self.logpath, '{time:YYYY-MM-DD}.logs')
            else:
                # 自定义日志文件名
                self.logging_name = join(self.logpath, f'{logging_name}.logs')

            # 增加更详细的日志格式，包含文件名和行号，支持日期轮转
            logger.add(
                self.logging_name,  # 日志文件路径
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file}:{line} - {message}",  # 日志格式（纯文本，不含HTML标签）
                encoding='utf-8',  # 文件编码格式
                rotation='00:00',  # 日志轮转：每天凌晨0点创建新文件（也可用 "500 MB" 按大小轮转）
                retention='30 days',  # 日志保留期：30天后自动删除旧日志（也可用 "10" 保留最近10个文件）
                level=Logings.level,  # 日志级别：控制输出的最低级别
                diagnose=True,  # 诊断模式：True=显示变量值，False=不显示（调试时建议True，生产环境建议False）
                backtrace=True,  # 回溯追踪：True=显示完整调用栈，False=仅显示异常信息（调试时建议True）
                enqueue=True,  # 异步队列：True=多线程安全且不阻塞，False=同步写入
                colorize=True  # 文件着色：True=保留颜色代码（某些查看器支持），False=纯文本
            )

            # 按 crawl_type + platform 分离日志
            self._add_separated_handlers()

            self._is_logger_added = True

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
        logger.remove()
        cls._is_logger_added = False
        Logings()

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