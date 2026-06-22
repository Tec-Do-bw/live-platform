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


class Logings:
    DEFAULT_LOG_NAME = 'default'
    level = 'INFO'
    console_level = 'INFO'  # 控制台输出等级
    file_level = 'INFO'    # 文件输出等级
    __instance = None
    _console_handler_id = None
    _file_handler_ids = {}
    _registered_log_names = set()

    DATE = '{time:YYYY-MM-DD}'
    LOG_DIR = join(dirname(dirname(abspath(__file__))), 'logs')
    logpath = LOG_DIR

    if not os.path.isdir(logpath):
        os.makedirs(logpath)

    # def __new__(cls, *args, **kwargs):
    #     if cls.__instance is None:
    #         cls.__instance = super(Logings, cls).__new__(cls, *args, **kwargs)
    #     return cls.__instance

    def __init__(self, logging_name=None, console_level=None, file_level=None, *args, **kwargs):
        if console_level:
            Logings.console_level = console_level
        if file_level:
            Logings.file_level = file_level

        self.log_label = logging_name.strip() if logging_name else self.DEFAULT_LOG_NAME
        Logings._registered_log_names.add(self.log_label)

        self.log_dir = self._prepare_log_dir(logging_name)
        self.log_file_pattern = os.path.join(self.log_dir, f"{self.DATE}.logs")
        self.logging_name = self.log_file_pattern

        self._ensure_console_handler()
        self._ensure_file_handler()

        self._logger = logger.bind(log_name=self.log_label)

    def _prepare_log_dir(self, logging_name):
        if logging_name:
            target_dir = os.path.join(self.logpath, logging_name)
            if not os.path.isdir(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            return target_dir
        return self.logpath

    @classmethod
    def _ensure_console_handler(cls):
        if cls._console_handler_id is not None:
            return

        logger.remove()  # 移除默认处理器
        cls._console_handler_id = logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}:{line}</cyan> - <level>{message}</level>",
            level=Logings.console_level,  # 使用控制台等级
            colorize=True,  # 显式启用颜色
            enqueue=True
        )

    def _ensure_file_handler(self):
        if self.log_label in Logings._file_handler_ids:
            return

        handler_id = logger.add(
            self.log_file_pattern,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file}:{line} - {message}",
            encoding='utf-8',
            rotation='00:00',  # 日志轮转：每天凌晨0点创建新文件（也可用 "500 MB" 按大小轮转）
            retention='30 days',
            backtrace=True,
            level=Logings.file_level,  # 使用文件等级
            diagnose=True,
            enqueue=True,
            colorize=True,
            filter=self._build_filter(self.log_label)
        )
        Logings._file_handler_ids[self.log_label] = handler_id

    @staticmethod
    def _build_filter(log_label):
        def _filter(record):
            return record["extra"].get("log_name", Logings.DEFAULT_LOG_NAME) == log_label
        return _filter

    @classmethod
    def _reset_logger_state(cls):
        cls._console_handler_id = None
        cls._file_handler_ids = {}

    @classmethod
    def _reinitialize_registered_loggers(cls):
        registered = list(cls._registered_log_names) or [cls.DEFAULT_LOG_NAME]
        # 先清空，重新实例化时会自动重新注册
        cls._registered_log_names = set(registered)
        for name in registered:
            if name == cls.DEFAULT_LOG_NAME:
                Logings()
            else:
                Logings(name)

    @property
    def get_level(self):
        """返回当前日志等级"""
        return self.level
    
    @classmethod
    def set_level(cls, level, console_level=None, file_level=None):
        """设置日志等级
        
        Args:
            level: 通用日志等级（向后兼容），可选 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
            console_level: 控制台输出等级
            file_level: 文件输出等级
        """
        cls.level = level
        if console_level:
            cls.console_level = console_level
        else:
            cls.console_level = level
        if file_level:
            cls.file_level = file_level
        else:
            cls.file_level = level
        logger.remove()  # 移除所有处理器
        cls._reset_logger_state()
        cls._reinitialize_registered_loggers()  # 重新初始化
    
    @classmethod
    def set_console_level(cls, level):
        """单独设置控制台输出等级
        
        Args:
            level: 控制台等级，可选 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        """
        cls.console_level = level
        logger.remove()  # 移除所有处理器
        cls._reset_logger_state()
        cls._reinitialize_registered_loggers()  # 重新初始化
    
    @classmethod
    def set_file_level(cls, level):
        """单独设置文件输出等级
        
        Args:
            level: 文件等级，可选 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        """
        cls.file_level = level
        logger.remove()  # 移除所有处理器
        cls._reset_logger_state()
        cls._reinitialize_registered_loggers()  # 重新初始化

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
        return self._logger


# logger = Logings().get_logger()


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
    #
    
    # ============ 示例 1: 基础用法 ============
    # 屏幕只显示 INFO 及以上，文件记录 DEBUG 及以上（默认配置）
    logs = Logings('bw')
    logger = logs.get_logger()
    
    logger.debug("DEBUG: 这条不会在屏幕显示，但会写入文件")
    logger.info("INFO: 这条既显示在屏幕，也写入文件")
    logger.warning("WARNING: 这条既显示在屏幕，也写入文件")
    logger.error("ERROR: 这条既显示在屏幕，也写入文件")
    
    # ============ 示例 2: 初始化时指定等级 ============
    # logs2 = Logings('test', console_level='WARNING', file_level='DEBUG')
    # logger2 = logs2.get_logger()
    # logger2.debug("DEBUG: 不显示")
    # logger2.info("INFO: 不显示")
    # logger2.warning("WARNING: 显示")
    
    # ============ 示例 3: 运行时修改等级 ============
    # Logings.set_console_level('WARNING')  # 只改变屏幕等级
    # logger.debug("DEBUG: 仍不显示")
    # logger.warning("WARNING: 现在显示")
    
    # ============ 示例 4: 同时修改两个等级 ============
    # Logings.set_level('INFO', console_level='WARNING', file_level='DEBUG')
    
    # ============ 示例 5: 单独修改文件等级 ============
    # Logings.set_file_level('INFO')  # 文件不记录DEBUG
    
    # ============ 推荐配置场景 ============
    # 场景 1: 生产环境 - 屏幕只显示WARNING，文件详细记录
    # Logings('prod', console_level='WARNING', file_level='DEBUG')
    
    # 场景 2: 开发环境 - 屏幕显示DEBUG，文件也记录DEBUG
    # Logings('dev', console_level='DEBUG', file_level='DEBUG')
    
    # 场景 3: 调试模式 - 屏幕显示DEBUG，文件只记录WARNING
    # Logings('debug', console_level='DEBUG', file_level='WARNING')