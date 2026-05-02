#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置示例文件
展示如何配置多个浏览器账号和平台
"""

# 示例：配置多个TikTok账号
ADSPOWER_CONFIG_EXAMPLE = {
    "api_url": "http://127.0.0.1:54345",
    "browsers": [
        # TikTok账号1
        {
            "browser_id": "tt_account_1",
            "platform": "TT",
            "enabled": True,
        },
        # TikTok账号2
        {
            "browser_id": "tt_account_2",
            "platform": "TT",
            "enabled": True,
        },
        # Shopee账号（预留）
        {
            "browser_id": "shopee_account_1",
            "platform": "shopee",
            "enabled": False,  # 暂不启用
        },
    ]
}

# 示例：配置多个采集时间点
SCHEDULER_CONFIG_EXAMPLE = {
    "enabled": True,
    "cron_config": {
        # 每天凌晨4点执行
        "hour": "4",
        "minute": "0",
        # 如需每天执行两次，可配置为: "hour": "4,16"
    },
    "task_timeout": 2,  # 2小时超时
    "max_retries": 3,
    "retry_delay": 300,  # 5分钟后重试
}

# 示例：配置告警（飞书机器人）
ALERT_CONFIG_EXAMPLE = {
    "enabled": True,
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK_ID",
    "alert_types": {
        "login_failed": True,   # 账号登出告警
        "crawl_failed": True,   # 采集失败告警
        "task_timeout": True,   # 任务超时告警
    }
}

