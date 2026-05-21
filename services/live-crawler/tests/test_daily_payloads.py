"""测试 BrowserApi._generate_daily_payloads 和 _infer_timezone 时间计算逻辑

避免导入完整的 BrowserApi（依赖 pydantic_settings 等），
直接提取核心逻辑进行测试。
"""
import copy
import importlib.util
import sys
import types
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# ---- 从 BrowserApi 提取的核心逻辑（避免导入链问题） ----

TIMEZONE_MAP = {
    '新加坡': 'Asia/Singapore',
    '印尼': 'Asia/Jakarta',
    '泰国': 'Asia/Bangkok',
    '越南': 'Asia/Ho_Chi_Minh',
    '马来': 'Asia/Kuala_Lumpur',
    '菲律宾': 'Asia/Manila',
    '美国': 'America/New_York',
    '墨西哥': 'America/Mexico_City',
    '巴西': 'America/Sao_Paulo',
}


def infer_timezone(group_name: str) -> str:
    for keyword, tz in TIMEZONE_MAP.items():
        if keyword in group_name:
            return tz
    return 'Asia/Singapore'


def generate_daily_payloads(original_payload, timezone_str, full_collection, now_utc=None):
    """与 BrowserApi._generate_daily_payloads 逻辑一致，增加 now_utc 参数便于测试"""
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = ZoneInfo('Asia/Singapore')

    if now_utc:
        now_local = now_utc.astimezone(tz)
    else:
        now_local = datetime.now(tz)
    today_local = now_local.date()

    if full_collection:
        yesterday = today_local - timedelta(days=1)
        first_day = yesterday - timedelta(days=27)
        target_dates = []
        current = first_day
        while current <= yesterday:
            target_dates.append(current)
            current += timedelta(days=1)
    else:
        target_dates = [
            today_local - timedelta(days=1),
            today_local - timedelta(days=2),
            today_local - timedelta(days=3),
        ]

    payloads = []
    for target_date in target_dates:
        start_dt = datetime.combine(target_date - timedelta(days=1), datetime.min.time())
        start_dt_utc = start_dt.replace(tzinfo=timezone.utc)
        start_timestamp = int(start_dt_utc.timestamp())

        end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        end_dt_utc = end_dt.replace(tzinfo=timezone.utc)
        end_timestamp = int(end_dt_utc.timestamp())

        payload = copy.deepcopy(original_payload)
        payload['request']['params'][0]['time_selector'] = {
            "period": 2,
            "granularity": 11,
            "end_timestamp": end_timestamp,
            "start_timestamp": start_timestamp,
            "timezone_offset": "0"
        }
        payloads.append(payload)

    return payloads


def _load_tiktok_module():
    """最小化加载 tiktok 模块，避免真实浏览器与配置依赖。"""
    module_name = 'crawlers.browser.tiktok_for_test'
    if module_name in sys.modules:
        return sys.modules[module_name]

    # 伪造最小依赖，确保模块可导入
    fake_crawlers = types.ModuleType('crawlers')
    fake_crawlers.__path__ = []
    sys.modules['crawlers'] = fake_crawlers

    fake_browser = types.ModuleType('crawlers.browser')
    fake_browser.__path__ = []
    sys.modules['crawlers.browser'] = fake_browser

    fake_base = types.ModuleType('crawlers.browser.base')

    class DummyBaseLiveCrawler:
        def __init__(self, *args, **kwargs):
            pass

    fake_base.BaseLiveCrawler = DummyBaseLiveCrawler
    sys.modules['crawlers.browser.base'] = fake_base

    fake_logger_module = types.ModuleType('utils.logger')

    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def success(self, *args, **kwargs):
            pass

    fake_logger_module.logger = DummyLogger()
    sys.modules['utils.logger'] = fake_logger_module

    fake_ocr = types.ModuleType('ddddocr')

    class DummyDdddOcr:
        def __init__(self, *args, **kwargs):
            pass

    fake_ocr.DdddOcr = DummyDdddOcr
    sys.modules['ddddocr'] = fake_ocr

    module_path = Path(__file__).resolve().parents[1] / 'crawlers' / 'browser' / 'tiktok.py'
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ---- 测试用 Payload 模板 ----

MOCK_PAYLOAD = {
    "request": {
        "params": [{
            "time_selector": {
                "period": 2, "granularity": 11,
                "end_timestamp": 0, "start_timestamp": 0,
                "timezone_offset": "0"
            },
            "stats_types": [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213],
            "is_live_type": True
        }]
    },
    "version": "2"
}

# 固定时间：UTC 2026-03-10 04:00:00（北京时间 2026-03-10 12:00:00）
MOCK_NOW_UTC = datetime(2026, 3, 10, 4, 0, 0, tzinfo=timezone.utc)


def _ts(year, month, day):
    """UTC 时间戳快捷方法"""
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


# ---- 测试 _infer_timezone ----

class TestInferTimezone:
    def test_singapore(self):
        assert infer_timezone('新加坡团队-tiktok') == 'Asia/Singapore'

    def test_indonesia(self):
        assert infer_timezone('印尼团队-tiktok') == 'Asia/Jakarta'

    def test_usa(self):
        assert infer_timezone('美国团队-tiktok') == 'America/New_York'

    def test_default(self):
        assert infer_timezone('未知团队') == 'Asia/Singapore'


# ---- 测试 _generate_daily_payloads ----

class TestGenerateDailyPayloads:
    """测试 48 小时 UTC 窗口计算

    假设 UTC 2026-03-10 04:00:00
    - 新加坡 UTC+8 → 当地 2026-03-10 12:00 → today=3/10
    - 纽约 EST UTC-5 → 当地 2026-03-09 23:00 → today=3/9
    """

    def test_incremental_singapore(self):
        """新加坡增量：T-1=3/9, T-2=3/8, T-3=3/7"""
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'Asia/Singapore', False, MOCK_NOW_UTC
        )
        assert len(payloads) == 3

        # T-1 = 3/9: start=3/8 00:00 UTC, end=3/10 00:00 UTC
        ts = payloads[0]['request']['params'][0]['time_selector']
        assert ts['start_timestamp'] == _ts(2026, 3, 8)
        assert ts['end_timestamp'] == _ts(2026, 3, 10)

        # T-2 = 3/8: start=3/7 00:00 UTC, end=3/9 00:00 UTC
        ts = payloads[1]['request']['params'][0]['time_selector']
        assert ts['start_timestamp'] == _ts(2026, 3, 7)
        assert ts['end_timestamp'] == _ts(2026, 3, 9)

        # T-3 = 3/7: start=3/6 00:00 UTC, end=3/8 00:00 UTC
        ts = payloads[2]['request']['params'][0]['time_selector']
        assert ts['start_timestamp'] == _ts(2026, 3, 6)
        assert ts['end_timestamp'] == _ts(2026, 3, 8)

    def test_incremental_new_york(self):
        """纽约 EDT(UTC-4)，当地 3/10 00:00 → today=3/10
        增量：T-1=3/9, T-2=3/8, T-3=3/7
        """
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'America/New_York', False, MOCK_NOW_UTC
        )
        assert len(payloads) == 3

        # T-1 = 3/9: start=3/8 00:00 UTC, end=3/10 00:00 UTC
        ts = payloads[0]['request']['params'][0]['time_selector']
        assert ts['start_timestamp'] == _ts(2026, 3, 8)
        assert ts['end_timestamp'] == _ts(2026, 3, 10)

    def test_full_collection_singapore(self):
        """新加坡全量：近 28 天（2/10 到 3/9，共 28 条）"""
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'Asia/Singapore', True, MOCK_NOW_UTC
        )
        assert len(payloads) == 28

        # 第一条 2/10: start=2/9 00:00 UTC, end=2/11 00:00 UTC
        ts_first = payloads[0]['request']['params'][0]['time_selector']
        assert ts_first['start_timestamp'] == _ts(2026, 2, 9)
        assert ts_first['end_timestamp'] == _ts(2026, 2, 11)

        # 最后一条 3/9: start=3/8 00:00 UTC, end=3/10 00:00 UTC
        ts_last = payloads[-1]['request']['params'][0]['time_selector']
        assert ts_last['start_timestamp'] == _ts(2026, 3, 8)
        assert ts_last['end_timestamp'] == _ts(2026, 3, 10)

    def test_full_collection_new_york(self):
        """纽约全量：近 28 天，共 28 条"""
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'America/New_York', True, MOCK_NOW_UTC
        )
        assert len(payloads) == 28

    def test_payload_structure(self):
        """验证 Payload 结构：params 长度为 1，granularity 为 11"""
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'Asia/Singapore', False, MOCK_NOW_UTC
        )
        for p in payloads:
            assert len(p['request']['params']) == 1
            ts = p['request']['params'][0]['time_selector']
            assert ts['granularity'] == 11
            assert ts['period'] == 2
            assert ts['timezone_offset'] == "0"

    def test_original_payload_not_mutated(self):
        """验证原始 Payload 不被修改"""
        original = copy.deepcopy(MOCK_PAYLOAD)
        generate_daily_payloads(MOCK_PAYLOAD, 'Asia/Singapore', False, MOCK_NOW_UTC)
        assert MOCK_PAYLOAD == original

    def test_48h_window_width(self):
        """验证每个窗口宽度恰好 48 小时"""
        payloads = generate_daily_payloads(
            MOCK_PAYLOAD, 'Asia/Singapore', False, MOCK_NOW_UTC
        )
        for p in payloads:
            ts = p['request']['params'][0]['time_selector']
            assert ts['end_timestamp'] - ts['start_timestamp'] == 48 * 3600


class TestTikTokLiveListThreshold:
    def test_incremental_threshold_uses_three_days_ago_start(self):
        """增量模式应以账号时区前三天 00:00:00 作为直播过滤阈值"""
        tiktok_module = _load_tiktok_module()

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                base = datetime(2026, 3, 12, 12, 0, 0)
                if tz is not None:
                    return base.replace(tzinfo=tz)
                return base

        original_datetime = tiktok_module.datetime
        tiktok_module.datetime = FixedDateTime
        try:
            crawler = object.__new__(tiktok_module.TikTokLiveCrawler)
            crawler.full_collection = False
            crawler.processed_room_ids = set()
            crawler.batch_id = ''
            crawler.browser_id = 'test-browser'
            crawler.group_name = '印尼团队-tiktok'
            crawler._api_base_url = 'https://shop.tiktok.com'
            crawler._api_query_string = ''
            crawler._fetch_trend_chart_via_js = lambda room_id, headers: {'success': True}

            captured_room_ids = []

            class DummyLogger:
                def info(self, message, *args, **kwargs):
                    if isinstance(message, str) and '找到 ' in message and '直播间' in message:
                        captured_room_ids.append(message)

                def warning(self, *args, **kwargs):
                    pass

                def error(self, *args, **kwargs):
                    pass

            original_logger = tiktok_module.logger
            tiktok_module.logger = DummyLogger()
            try:
                response = {
                    'data': {
                        'segments': [{
                            'timed_lists': [{
                                'stats': [
                                    {
                                        'live_id': 'keep-room',
                                        'live_start_timestamp': int(datetime(2026, 3, 9, 0, 0, 0, tzinfo=timezone.utc).timestamp()),
                                        'live_end_timestamp': int(datetime(2026, 3, 9, 1, 0, 0, tzinfo=timezone.utc).timestamp()),
                                    },
                                    {
                                        'live_id': 'skip-room',
                                        'live_start_timestamp': int(datetime(2026, 3, 8, 22, 0, 0, tzinfo=timezone.utc).timestamp()),
                                        'live_end_timestamp': int(datetime(2026, 3, 8, 23, 59, 59, tzinfo=timezone.utc).timestamp()),
                                    },
                                ]
                            }]
                        }]
                    }
                }
                api_data = {
                    'url': 'https://shop.tiktok.com/api/v2/insights/creator/live/list?aid=1',
                    'headers': {},
                    'request': {
                        'request': {
                            'params': [{
                                'time_selector': {
                                    'base_timestamp': 1,
                                    'timezone_offset': 0,
                                },
                                'stats_types': [],
                            }]
                        }
                    }
                }

                crawler._handle_tiktok_live_list(response, api_data=api_data)
            finally:
                tiktok_module.logger = original_logger

            assert 'keep-room' in crawler.processed_room_ids
            assert 'skip-room' not in crawler.processed_room_ids
        finally:
            tiktok_module.datetime = original_datetime
