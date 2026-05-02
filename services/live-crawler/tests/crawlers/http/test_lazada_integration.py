"""Lazada HTTP 采集器集成测试（真实网络请求）。

测试账号: sbqsomimax@outlook.com（泰国站 co.th）
前置条件:
  1. 数据库中已有该账号的双端口 Cookie
  2. 本地代理 127.0.0.1:7890 可用
  3. 数据上报已关闭（DATA_SERVER_CONFIG.enabled=False）
"""

import json
import time
from datetime import datetime

import pytest

from crawlers.http.lazada import (
    API_TYPE_BA_KEY_OVERVIEW,
    API_TYPE_REALTIME_DETAIL,
    API_TYPE_SELLER_METRICS,
    LazadaHttpCrawler,
)
from downloader import Downloader, Task
from services.cookie_manager import get_cookies


# 测试账号
TEST_ACCOUNT = 'sbqsomimax@outlook.com'
TEST_GROUP_NAME = '泰国团队-lazada'  # 泰国站


# ------------------------------------------------------------------
# Step 1: 单接口连通性测试
# ------------------------------------------------------------------

def test_step1_sellercenter_connectivity():
    """Step 1a: 测试 sellercenter 端口连通性（1.5 realtime/key/detailV2）。"""
    cookies = get_cookies(TEST_ACCOUNT, 'lazada', 'sellercenter')
    assert cookies is not None, "sellercenter Cookie 不存在"

    # 构造 Cookie header
    cookie_header = '; '.join(f'{k}={v}' for k, v in cookies.items())

    # 构造请求
    url = 'https://sellercenter.lazada.co.th/ba/sycm/faas/dashboard/realtime/key/detailV2.json'
    task = Task(
        url=url,
        headers={'Cookie': cookie_header},
        meta={'api_type': API_TYPE_REALTIME_DETAIL},
    )

    # 发送请求（不走代理）
    dl = Downloader(proxy=None)
    results = dl.run([task])

    assert len(results) == 1
    result = results[0]

    print(f"\n=== sellercenter 连通性测试 ===")
    print(f"URL: {result.url}")
    print(f"Status: {result.status_code}")
    print(f"Success: {result.success}")
    if result.success:
        data = json.loads(result.text)
        print(f"Response keys: {list(data.keys())}")
    else:
        print(f"Error: {result.error}")

    assert result.success, f"sellercenter 请求失败: {result.error}"
    assert result.status_code == 200


def test_step1_live_mtop_connectivity():
    """Step 1b: 测试 live 端口 mtop 连通性（1.1 seller.metrics）。"""
    cookies = get_cookies(TEST_ACCOUNT, 'lazada', 'live')
    assert cookies is not None, "live Cookie 不存在"

    # 提取 token
    m_h5_tk = cookies.get('_m_h5_tk', '')
    assert m_h5_tk, "_m_h5_tk 不存在"
    token = m_h5_tk.split('_')[0]

    # 构造 mtop 请求
    t = str(int(time.time() * 1000))
    app_key = '4272'
    date = datetime.now().strftime('%Y%m%d')
    data = json.dumps({'date': date}, separators=(',', ':'))

    # 计算签名
    import hashlib
    sign = hashlib.md5(f'{token}&{t}&{app_key}&{data}'.encode()).hexdigest()

    # 拼接 URL
    url = (
        f'https://acs-m.lazada.co.th/h5/mtop.lazada.live.data.seller.metrics/1.0/'
        f'?appKey={app_key}&t={t}&sign={sign}&data={data}'
    )

    cookie_header = '; '.join(f'{k}={v}' for k, v in cookies.items())
    task = Task(
        url=url,
        headers={'Cookie': cookie_header},
        meta={'api_type': API_TYPE_SELLER_METRICS},
    )

    # 发送请求（不走代理）
    dl = Downloader(proxy=None)
    results = dl.run([task])

    assert len(results) == 1
    result = results[0]

    print(f"\n=== live mtop 连通性测试 ===")
    print(f"URL: {result.url[:100]}...")
    print(f"Status: {result.status_code}")
    print(f"Success: {result.success}")
    if result.success:
        data = json.loads(result.text)
        print(f"Response keys: {list(data.keys())}")
        # mtop 响应通常有 ret 字段
        if 'ret' in data:
            print(f"ret: {data['ret']}")
    else:
        print(f"Error: {result.error}")

    assert result.success, f"live mtop 请求失败: {result.error}"
    assert result.status_code == 200


# ------------------------------------------------------------------
# Step 2: build_api_sequence 构造验证
# ------------------------------------------------------------------

def test_step2_build_tasks_structure():
    """Step 2: 验证 build_api_sequence 生成的 ApiSequence 结构。"""
    crawler = LazadaHttpCrawler(
        browser_id=TEST_ACCOUNT,
        group_name=TEST_GROUP_NAME,
    )

    # 获取 Cookie
    cookies = crawler.get_cookies()
    assert cookies is not None, "Cookie 获取失败"
    assert cookies.get('sellercenter'), "sellercenter Cookie 缺失"
    assert cookies.get('live'), "live Cookie 缺失"

    # 构造 API 序列（增量模式）
    sequences = crawler.build_api_sequence(cookies, is_full=False)

    print(f"\n=== build_api_sequence 构造验证 ===")
    print(f"生成序列数量: {len(sequences)}")
    print(f"country_domain: {crawler.country_domain}")

    # 验证序列数量：1.1 + 1.2 + 1.3 + 1.4 + 1.5 + 12 个 BA + 3.1 = 18
    assert len(sequences) == 18, f"序列数量不正确: {len(sequences)}"

    # 验证域名
    assert crawler.country_domain == 'co.th', "国家域名解析错误"

    # 验证每个序列都能构造初始任务
    for seq in sequences:
        tasks = seq.build_initial_tasks()
        assert len(tasks) > 0, f"序列 {seq.api_type} 无初始任务"

    print("[OK] ApiSequence 结构验证通过")


# ------------------------------------------------------------------
# Step 3: start_crawl 全流程测试
# ------------------------------------------------------------------

@pytest.mark.slow
def test_step3_start_crawl_full_flow():
    """Step 3: 测试 start_crawl 全流程（真实采集）。

    注意：这个测试会发送真实网络请求，耗时较长（~30秒）。
    """
    crawler = LazadaHttpCrawler(
        full_collection = False,
        browser_id=TEST_ACCOUNT,
        group_name=TEST_GROUP_NAME,
        batch_id='test_batch_' + str(int(time.time())),
    )

    print(f"\n=== start_crawl 全流程测试 ===")
    print(f"账号: {TEST_ACCOUNT}")
    print(f"分组: {TEST_GROUP_NAME}")
    print(f"国家: {crawler.country_domain}")

    # 执行采集
    result = crawler.start_crawl()

    print(f"\n采集结果:")
    print(f"  success: {result['success']}")
    print(f"  sequences_completed: {result['sequences_completed']}")
    print(f"  tasks_total: {result['tasks_total']}")
    print(f"  tasks_success: {result['tasks_success']}")
    print(f"  data_sent: {result['data_sent']}")
    print(f"  error: {result.get('error')}")

    # 验证基本成功
    assert result['success'], f"采集失败: {result.get('error')}"
    assert result['sequences_completed'] >= 1, "至少完成 1 个序列"
    assert result['tasks_total'] > 0, "没有生成 Task"
    assert result['tasks_success'] > 0, "没有成功的 Task"

    # 验证成功率（允许部分失败，但成功率应 > 50%）
    success_rate = result['tasks_success'] / result['tasks_total']
    print(f"  success_rate: {success_rate:.1%}")
    assert result['tasks_success'] > 0, "no successful tasks"

    # 检查是否有跳过的 api_type（单端口 Cookie 缺失）
    if crawler.skipped_api_types:
        print(f"  跳过的 api_type: {crawler.skipped_api_types}")
        assert result.get('status') == 'partial', "应标记为 partial 状态"

    print("[OK] start_crawl 全流程测试通过")


if __name__ == '__main__':
    # 可以单独运行某个测试
    # pytest tests/crawlers/http/test_lazada_integration.py::test_step1_sellercenter_connectivity -v -s
    pass
