"""
日志配置模块
使用 loguru 进行日志记录，支持按日切割
"""
import os
import sys

from loguru import logger

from app.config import settings


def _get_log_dir() -> str:
    """获取日志目录路径"""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_logger() -> None:
    """
    配置 loguru 日志
    - 控制台输出
    - 文件输出，按日切割
    """
    log_level = settings.LOG_LEVEL.upper()
    log_dir = _get_log_dir()
    log_file = os.path.join(log_dir, "app_{time:YYYY-MM}.log")

    # 移除默认 handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # 添加文件输出，按日切割
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 month",
        retention=None,
        encoding="utf-8",
        enqueue=True,  # 异步写入，提高性能
    )


# 应用启动时自动配置日志
setup_logger()
