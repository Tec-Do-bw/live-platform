"""Lazada HTTP 采集器单元测试。"""

import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from crawlers.http.base import ApiSequence
from crawlers.http.lazada import (
    API_TYPE_BA_KEY_OVERVIEW,
    API_TYPE_BA_PRODUCT_PERF_REVENUE,
    API_TYPE_BA_PRODUCT_PERF_VISITOR,
    API_TYPE_BA_TRAFFIC_SOURCE,
    API_TYPE_LIVE_LIST,
    API_TYPE_REALTIME_DETAIL,
    API_TYPE_ROOM_METRICS,
    API_TYPE_SELLER_METRICS,
    API_TYPE_SELLER_PRODUCT_ROOMS,
    API_TYPE_SELLER_PRODUCTS,
    LAZADA_COUNTRY_MAP,
    LAZADA_TIMEZONE_MAP,
    LIVE_API_TYPES,
    SELLERCENTER_API_TYPES,
    LazadaHttpCrawler,
)
from downloader import DownloadResult, Task


# ------------------------------------------------------------------
# 测试 mtop 签名计算（任务 8.1）
# ------------------------------------------------------------------

def test_calc_mtop_sign():
    """测试 mtop 签名计算（固定输入验证输出）。"""
    token = 'abc123'
    t = '1000'
    app_key = '4272'
    data = '{"a":1}'

    expected = hashlib.md5(f'{token}&{t}&{app_key}&{data}'.encode()).hexdigest()
    actual = LazadaHttpCrawler._calc_mtop_sign(token, t, app_key, data)

    assert actual == expected


def test_calc_mtop_sign_compact_json():
    """测试 data 必须是紧凑 JSON。"""
    token = 'abc'
    t = '1000'
    app_key = '4272'
    data_dict = {'a': 1, 'b': 2}

    # 紧凑 JSON
    data_compact = json.dumps(data_dict, separators=(',', ':'))
    sign = LazadaHttpCrawler._calc_mtop_sign(token, t, app_key, data_compact)

    # 验证签名基于紧凑格式
    expected = hashlib.md5(f'{token}&{t}&{app_key}&{data_compact}'.encode()).hexdigest()
    assert sign == expected


# ------------------------------------------------------------------
# 测试国家域名映射和时区映射（任务 8.2）
# ------------------------------------------------------------------

def test_country_domain_mapping():
    """测试国家域名映射覆盖 6 个国家（中英文各 6 个 = 12 条）。"""
    assert len(LAZADA_COUNTRY_MAP) == 12
    # 英文
    assert LAZADA_COUNTRY_MAP['thailand'] == 'co.th'
    assert LAZADA_COUNTRY_MAP['malaysia'] == 'com.my'
    assert LAZADA_COUNTRY_MAP['indonesia'] == 'co.id'
    assert LAZADA_COUNTRY_MAP['vietnam'] == 'vn'
    assert LAZADA_COUNTRY_MAP['singapore'] == 'sg'
    assert LAZADA_COUNTRY_MAP['philippines'] == 'com.ph'
    # 中文
    assert LAZADA_COUNTRY_MAP['泰国'] == 'co.th'
    assert LAZADA_COUNTRY_MAP['马来'] == 'com.my'
    assert LAZADA_COUNTRY_MAP['印尼'] == 'co.id'
    assert LAZADA_COUNTRY_MAP['越南'] == 'vn'
    assert LAZADA_COUNTRY_MAP['新加坡'] == 'sg'
    assert LAZADA_COUNTRY_MAP['菲律宾'] == 'com.ph'


def test_timezone_mapping():
    """测试时区映射覆盖所有域名。"""
    assert len(LAZADA_TIMEZONE_MAP) == 6
    assert LAZADA_TIMEZONE_MAP['co.th'] == 7
    assert LAZADA_TIMEZONE_MAP['com.my'] == 8
    assert LAZADA_TIMEZONE_MAP['co.id'] == 7
    assert LAZADA_TIMEZONE_MAP['vn'] == 7
    assert LAZADA_TIMEZONE_MAP['sg'] == 8
    assert LAZADA_TIMEZONE_MAP['com.ph'] == 8


# ------------------------------------------------------------------
# 测试日期范围计算（任务 8.3）
# ------------------------------------------------------------------

def test_date_range_incremental():
    """测试增量模式返回 7 天。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    dates = crawler._get_date_range(is_full=False)
    assert len(dates) == 7


def test_date_range_full():
    """测试全量模式返回 30 天。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    dates = crawler._get_date_range(is_full=True)
    assert len(dates) == 30


def test_date_range_timezone():
    """测试日期按国家时区计算。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='thailand-lazada')
    assert crawler.country_domain == 'co.th'

    # 获取当地今天
    today = crawler._get_country_today()
    utc_now = datetime.utcnow()
    expected_offset = 7  # UTC+7

    # 验证时区偏移
    diff_hours = (today - utc_now).total_seconds() / 3600
    assert abs(diff_hours - expected_offset) < 1  # 允许 1 小时误差


# ------------------------------------------------------------------
# 测试 build_api_sequence() 生成的 ApiSequence 结构
# ------------------------------------------------------------------

@patch('crawlers.http.lazada._get_cookies')
def test_build_api_sequence_both_cookies_valid(mock_get_cookies):
    """测试双端口 Cookie 均有效时的序列生成。"""
    mock_get_cookies.side_effect = lambda aid, plat, ep: (
        {'cookie1': 'value1'} if ep == 'sellercenter' else
        {'_m_h5_tk': 'token123_1234567890', 'cookie2': 'value2'}
    )

    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    cookies = crawler.get_cookies()
    sequences = crawler.build_api_sequence(cookies, is_full=False)

    # 历史模式：1.1 + 1.2 + 1.3 + 1.4 + 1.5 + 12 个 BA + 3.1 = 18 个序列
    assert len(sequences) == 18
    assert all(isinstance(s, ApiSequence) for s in sequences)
    assert len(crawler.skipped_api_types) == 0


@patch('crawlers.http.lazada._get_cookies')
def test_build_api_sequence_sellercenter_missing(mock_get_cookies):
    """测试 sellercenter Cookie 缺失时跳过对应序列。"""
    mock_get_cookies.side_effect = lambda aid, plat, ep: (
        None if ep == 'sellercenter' else
        {'_m_h5_tk': 'token123_1234567890', 'cookie2': 'value2'}
    )

    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    cookies = crawler.get_cookies()
    sequences = crawler.build_api_sequence(cookies, is_full=False)

    # 只有 3.1 一个序列
    assert len(sequences) == 1
    assert sequences[0].api_type == API_TYPE_LIVE_LIST
    assert set(crawler.skipped_api_types) == SELLERCENTER_API_TYPES


@patch('crawlers.http.lazada._get_cookies')
def test_build_api_sequence_live_missing(mock_get_cookies):
    """测试 live Cookie 缺失时跳过对应序列。"""
    mock_get_cookies.side_effect = lambda aid, plat, ep: (
        {'cookie1': 'value1'} if ep == 'sellercenter' else None
    )

    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    cookies = crawler.get_cookies()
    sequences = crawler.build_api_sequence(cookies, is_full=False)

    # 17 个 sellercenter 序列，无 live 序列
    assert len(sequences) == 17
    assert set(crawler.skipped_api_types) == LIVE_API_TYPES


@patch('crawlers.http.lazada._get_cookies')
def test_api_type_coverage(mock_get_cookies):
    """测试序列覆盖所有 18 个阶段 1 api_type（不含 3.2）。"""
    mock_get_cookies.side_effect = lambda aid, plat, ep: (
        {'cookie1': 'value1'} if ep == 'sellercenter' else
        {'_m_h5_tk': 'token123_1234567890', 'cookie2': 'value2'}
    )

    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    cookies = crawler.get_cookies()
    sequences = crawler.build_api_sequence(cookies, is_full=False)

    api_types = {s.api_type for s in sequences}
    expected = (SELLERCENTER_API_TYPES | LIVE_API_TYPES) - {API_TYPE_ROOM_METRICS}
    assert api_types == expected


# ------------------------------------------------------------------
# 测试分页续页逻辑
# ------------------------------------------------------------------

def test_needs_next_page_mtop_full_page():
    """测试 mtop 分页：total 大于已采集数→续页。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    result = {
        'api_type': API_TYPE_SELLER_PRODUCT_ROOMS,
        'data': {'data': {}, 'total': 250},
    }
    assert crawler._needs_next_page_mtop(result, page_num=1) is True


def test_needs_next_page_mtop_partial_page():
    """测试 mtop 分页：total 等于已采集数→终止。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    result = {
        'api_type': API_TYPE_SELLER_PRODUCT_ROOMS,
        'data': {'data': {}, 'total': 100},
    }
    assert crawler._needs_next_page_mtop(result, page_num=1) is False


def test_needs_next_page_mtop_max_pages():
    """测试 mtop 分页：达到最大页数→终止。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    result = {
        'api_type': API_TYPE_SELLER_PRODUCT_ROOMS,
        'data': {'data': {}, 'total': 1500},
    }
    assert crawler._needs_next_page_mtop(result, page_num=10) is False


def test_needs_next_page_mtop_live_list():
    """测试 3.1 接口分页：totalCount 在 data.data 层（字符串类型）。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    result = {
        'api_type': API_TYPE_LIVE_LIST,
        'data': {'data': {'totalCount': '250'}},
    }
    assert crawler._needs_next_page_mtop(result, page_num=1) is True
    assert crawler._needs_next_page_mtop(result, page_num=3) is False


def test_needs_next_page_mtop_no_total():
    """测试 mtop 分页：缺少 total 字段→安全降级不翻页。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    result = {
        'api_type': API_TYPE_SELLER_PRODUCT_ROOMS,
        'data': {'data': {}},
    }
    assert crawler._needs_next_page_mtop(result, page_num=1) is False


# ------------------------------------------------------------------
# 测试 _extract_live_uuids() 和 on_completed 回调
# ------------------------------------------------------------------

def test_extract_live_uuids_dict_format():
    """测试从对象格式 liveInfoDTOs 提取 liveUuid。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    results = [
        {
            'api_type': API_TYPE_LIVE_LIST,
            'data': {
                'data': {
                    'data': {
                        'liveInfoDTOs': {
                            'End': [{'liveUuid': 'uuid1'}],
                            'History': [{'liveUuid': 'uuid2'}],
                            'Online': [{'liveUuid': 'uuid3'}],
                        }
                    }
                }
            },
        }
    ]
    uuids = crawler._extract_live_uuids(results)
    # 历史模式：只提取 End + History
    assert set(uuids) == {'uuid1', 'uuid2'}


def test_extract_live_uuids_realtime():
    """测试实时模式只提取 Online 状态。"""
    crawler = LazadaHttpCrawler(
        browser_id='test', group_name='singapore-lazada', crawl_type='realtime'
    )
    results = [
        {
            'api_type': API_TYPE_LIVE_LIST,
            'data': {
                'data': {
                    'data': {
                        'liveInfoDTOs': {
                            'End': [{'liveUuid': 'uuid1'}],
                            'Online': [{'liveUuid': 'uuid2'}],
                        }
                    }
                }
            },
        }
    ]
    uuids = crawler._extract_live_uuids(results)
    assert uuids == ['uuid2']


def test_extract_live_uuids_empty():
    """测试无 liveUuid 时返回空列表。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    results = [
        {
            'api_type': API_TYPE_LIVE_LIST,
            'data': {'data': {'data': {'liveInfoDTOs': {}}}},
        }
    ]
    assert crawler._extract_live_uuids(results) == []


@patch('crawlers.http.lazada._get_cookies')
def test_seq_live_list_on_completed(mock_get_cookies):
    """测试 3.1 序列的 on_completed 回调构造 3.2 Task。"""
    mock_get_cookies.side_effect = lambda aid, plat, ep: (
        {'cookie1': 'value1'} if ep == 'sellercenter' else
        {'_m_h5_tk': 'token123_1234567890', 'cookie2': 'value2'}
    )

    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    cookies = crawler.get_cookies()
    seq = crawler._seq_live_list(cookies['live'], is_full=False)

    assert seq.on_completed is not None

    # 模拟 3.1 结果
    results = [
        {
            'api_type': API_TYPE_LIVE_LIST,
            'data': {
                'data': {
                    'data': {
                        'liveInfoDTOs': {
                            'End': [{'liveUuid': 'uuid1'}, {'liveUuid': 'uuid2'}],
                        }
                    }
                }
            },
        }
    ]
    dep_tasks = seq.on_completed(results)
    assert len(dep_tasks) == 2
    assert all(t.meta['api_type'] == API_TYPE_ROOM_METRICS for t in dep_tasks)


# ------------------------------------------------------------------
# 测试 parse_response()
# ------------------------------------------------------------------

def test_parse_response_success_sellercenter():
    """测试 sellercenter 接口成功解析（code=0）。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    task = Task(url='http://example.com', meta={'api_type': API_TYPE_SELLER_METRICS})
    result = DownloadResult(
        task=task, success=True,
        text='{"code": 0, "data": {"metrics": []}, "success": true}',
    )
    parsed = crawler.parse_response(result)
    assert parsed is not None
    assert parsed['api_type'] == API_TYPE_SELLER_METRICS


def test_parse_response_success_mtop():
    """测试 mtop 接口成功解析（ret 包含"调用成功"）。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    task = Task(url='http://example.com', meta={'api_type': API_TYPE_LIVE_LIST})
    result = DownloadResult(
        task=task, success=True,
        text='{"ret": ["SUCCESS::调用成功"], "data": {"liveInfoDTOs": []}, "v": "1.0"}',
    )
    parsed = crawler.parse_response(result)
    assert parsed is not None
    assert parsed['api_type'] == API_TYPE_LIVE_LIST


def test_parse_response_request_failed():
    """测试请求失败返回 None。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    task = Task(url='http://example.com', meta={'api_type': API_TYPE_SELLER_METRICS})
    result = DownloadResult(task=task, success=False, error='Network error')
    assert crawler.parse_response(result) is None


def test_parse_response_json_decode_error():
    """测试 JSON 解析失败返回 None。"""
    crawler = LazadaHttpCrawler(browser_id='test', group_name='singapore-lazada')
    task = Task(url='http://example.com', meta={'api_type': API_TYPE_SELLER_METRICS})
    result = DownloadResult(task=task, success=True, text='invalid json')
    assert crawler.parse_response(result) is None


# ------------------------------------------------------------------
# 测试中文分组名解析
# ------------------------------------------------------------------

def test_parse_country_domain_chinese():
    """测试中文分组名解析。"""
    assert LazadaHttpCrawler(browser_id='test', group_name='新加坡团队-lazada').country_domain == 'sg'
    assert LazadaHttpCrawler(browser_id='test', group_name='马来团队-lazada').country_domain == 'com.my'
    assert LazadaHttpCrawler(browser_id='test', group_name='泰国团队-lazada').country_domain == 'co.th'

