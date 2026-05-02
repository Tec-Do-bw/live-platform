#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""注入模拟监控数据，用于验证 monitor 前端面板

用法：cd live_dp && python scripts/mock_monitor_data.py
然后：python -m monitor.server
浏览器访问：http://localhost:8777
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor.tracker import CollectionMonitor

monitor = CollectionMonitor()

# ========== 批次 1：模拟一次正常采集 ==========
BATCH_1 = '2026-03-08_20:00'
monitor.start_batch(BATCH_1, 'scheduler')

# 账号 1：完整采集成功（2 个直播间，全部 trend 成功）
monitor.start_account(BATCH_1, 'k16w3t5d', '印尼团队-tiktok')
monitor.record_rooms(BATCH_1, 'k16w3t5d', [
    {
        'room_id': '7613870140707048210',
        'room_name': 'EARLY RAMADHAN SALE!',
        'live_start_ts': 1772742319,
        'live_end_ts': 1772815517,
        'duration': 73198,
        'cover_url': '',
        'revenue': '3651856',
        'currency_code': 'IDR',
        'direct_revenue': '3284068',
        'item_sold_cnt': 30,
        'view_cnt': 2222,
        'ctr': 0.141,
        'c_o': 0.086,
    },
    {
        'room_id': '7613495348485409544',
        'room_name': 'EARLY RAMADHAN SALE! Day 2',
        'live_start_ts': 1772655052,
        'live_end_ts': 1772730007,
        'duration': 74955,
        'cover_url': '',
        'revenue': '6194883',
        'currency_code': 'IDR',
        'direct_revenue': '4829454',
        'item_sold_cnt': 55,
        'view_cnt': 2478,
        'ctr': 0.150,
        'c_o': 0.108,
    },
])
monitor.record(BATCH_1, 'k16w3t5d', 'replay_info', status='success', response_size=5120)
monitor.record(BATCH_1, 'k16w3t5d', 'trend_gmv', room_id='7613870140707048210', status='success')
monitor.record(BATCH_1, 'k16w3t5d', 'trend_stats', room_id='7613870140707048210', status='success')
monitor.record(BATCH_1, 'k16w3t5d', 'trend_gmv', room_id='7613495348485409544', status='success')
monitor.record(BATCH_1, 'k16w3t5d', 'trend_stats', room_id='7613495348485409544', status='success')
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-12', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-13', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-14', 'live_stats', 'failed')
monitor.finish_account(BATCH_1, 'k16w3t5d', 'success')

# 账号 2：部分成功（3 个直播间，1 个 trend 失败）
monitor.start_account(BATCH_1, 'k1926s53', '马来团队-tiktok')
monitor.record_rooms(BATCH_1, 'k1926s53', [
    {
        'room_id': '7612001234567890001',
        'room_name': 'Skechers LIVE Sale',
        'live_start_ts': 1772740000,
        'live_end_ts': 1772780000,
        'duration': 40000,
        'cover_url': '',
        'revenue': '220985.33',
        'currency_code': 'MYR',
        'direct_revenue': '180000',
        'item_sold_cnt': 120,
        'view_cnt': 5600,
        'ctr': 1.14,
        'c_o': 0.005,
    },
    {
        'room_id': '7612001234567890002',
        'room_name': 'Flash Deal Friday',
        'live_start_ts': 1772650000,
        'live_end_ts': 1772690000,
        'duration': 40000,
        'cover_url': '',
        'revenue': '156000',
        'currency_code': 'MYR',
        'direct_revenue': '120000',
        'item_sold_cnt': 85,
        'view_cnt': 3200,
        'ctr': 0.98,
        'c_o': 0.004,
    },
    {
        'room_id': '7612001234567890003',
        'room_name': 'Weekend Special',
        'live_start_ts': 1772560000,
        'live_end_ts': 1772600000,
        'duration': 40000,
        'cover_url': '',
        'revenue': '89000',
        'currency_code': 'MYR',
        'direct_revenue': '72000',
        'item_sold_cnt': 45,
        'view_cnt': 1800,
        'ctr': 0.76,
        'c_o': 0.003,
    },
])
monitor.record(BATCH_1, 'k1926s53', 'replay_info', status='success', response_size=8192)
monitor.record(BATCH_1, 'k1926s53', 'trend_gmv', room_id='7612001234567890001', status='success')
monitor.record(BATCH_1, 'k1926s53', 'trend_stats', room_id='7612001234567890001', status='success')
monitor.record(BATCH_1, 'k1926s53', 'trend_gmv', room_id='7612001234567890002', status='success')
monitor.record(BATCH_1, 'k1926s53', 'trend_stats', room_id='7612001234567890002', status='success')
monitor.record(BATCH_1, 'k1926s53', 'trend_gmv', room_id='7612001234567890003', status='failed')
monitor.record(BATCH_1, 'k1926s53', 'trend_stats', room_id='7612001234567890003', status='failed')
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-12', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-13', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-14', 'live_stats', 'empty')
monitor.finish_account(BATCH_1, 'k1926s53', 'partial')

# 账号 3：登出失败
monitor.start_account(BATCH_1, 'k20abc99', '越南团队-tiktok')
monitor.finish_account(BATCH_1, 'k20abc99', 'login_failed')

monitor.finish_batch(BATCH_1)

# ========== 批次 2：模拟一次全量采集 ==========
BATCH_2 = '2026-03-08_04:00'
monitor.start_batch(BATCH_2, 'full')

monitor.start_account(BATCH_2, 'k16w3t5d', '印尼团队-tiktok')
monitor.record_rooms(BATCH_2, 'k16w3t5d', [
    {
        'room_id': '7610000000000000001',
        'room_name': 'Full Collection Test',
        'live_start_ts': 1772400000,
        'live_end_ts': 1772450000,
        'duration': 50000,
        'cover_url': '',
        'revenue': '1500000',
        'currency_code': 'IDR',
        'direct_revenue': '1200000',
        'item_sold_cnt': 15,
        'view_cnt': 900,
        'ctr': 0.12,
        'c_o': 0.07,
    },
])
monitor.record(BATCH_2, 'k16w3t5d', 'replay_info', status='success', response_size=3072)
monitor.record(BATCH_2, 'k16w3t5d', 'trend_gmv', room_id='7610000000000000001', status='success')
monitor.record(BATCH_2, 'k16w3t5d', 'trend_stats', room_id='7610000000000000001', status='success')
monitor.record_daily_stats(BATCH_2, 'k16w3t5d', '2026-03-07', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_2, 'k16w3t5d', '2026-03-08', 'live_stats', 'success')
monitor.finish_account(BATCH_2, 'k16w3t5d', 'success')

monitor.finish_batch(BATCH_2)

print('模拟数据注入完成!')
print(f'  批次 1: {BATCH_1} — 3 个账号（1 成功 / 1 部分 / 1 登出）')
print(f'  批次 2: {BATCH_2} — 1 个账号（全量采集）')
print()
print('启动服务：python -m monitor.server')
print('访问地址：http://localhost:8777')
