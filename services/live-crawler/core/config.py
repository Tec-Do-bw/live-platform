#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置文件 - 根据环境自动选择配置"""

import os

from .config_base import BaseConfig, DevConfig, ProConfig


def get_settings() -> BaseConfig:
    """根据环境变量获取对应的配置实例"""
    app_env = os.getenv("APP_ENV", "dev").lower()

    if app_env == "pro":
        return ProConfig()
    if app_env == "dev":
        return DevConfig()
    return DevConfig()


# 创建全局配置实例
Settings = get_settings()

# 为了保持向后兼容，导出Settings类
__all__ = ["Settings", "get_settings"]