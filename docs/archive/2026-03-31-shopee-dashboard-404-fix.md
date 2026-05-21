# Shopee Dashboard 接口 404 问题修复报告

## 1. 问题描述

### 1.1 错误现象
在实现 Shopee 实时直播间详情接口采集时，所有 dashboard 接口都返回 `status_404`：

```python
# 失败的接口
f'{base_url}/api/supply/lm/sellercenter/dashboard/overview?sessionId={session_id}'
f'{base_url}/api/supply/lm/sellercenter/dashboard/viewer-source?sessionId={session_id}'
f'{base_url}/api/supply/lm/sellercenter/dashboard/viewer-profile?sessionId={session_id}'
f'{base_url}/api/supply/lm/sellercenter/dashboard/buyer-profile?sessionId={session_id}'
f'{base_url}/api/supply/lm/sellercenter/dashboard/trends?sessionId={session_id}&...'
```

### 1.2 已成功的接口（作为对比）
```python
# 成功的接口
'api/supply/lm/sellercenter/realtime/sessionList'
'api/supply/lm/sellercenter/liveList/v2'
'api/supply/lm/sellercenter/overview/v3'
'api/supply/lm/sellercenter/liveDetail'
'api/supply/lm/sellercenter/liveCoordinate/v2'
```

## 2. 问题根因

### 2.1 代码对比分析

**已成功的接口（liveDetail、liveCoordinate/v2）**
```python
def _build_live_detail_request(self, session_id: str, headers: Dict[str, Any] | None = None) -> Dict[str, Any]:
    request_headers = self._build_request_headers(headers)
    request_headers.update(self._build_shopee_api_headers())  # ← 关键：添加了 Shopee API 专用 headers
    return {
        'url': f'{self._get_base_url()}/api/supply/lm/sellercenter/liveDetail?sessionId={session_id}',
        'method': 'GET',
        'headers': request_headers,
        'credentials': 'include',
    }
```

**失败的接口（dashboard/*）**
```python
def _fetch_session_detail_via_js(self, session: Dict[str, Any], headers: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_url = self._get_base_url()
    fetch_headers = self._build_request_headers(headers)  # ← 缺少 _build_shopee_api_headers()

    all_requests = [
        {
            'url': f'{base_url}/api/supply/lm/sellercenter/dashboard/overview?sessionId={session_id}',
            'method': 'GET',
            'headers': fetch_headers,  # ← 缺少关键 headers
            'credentials': 'include',
        },
        ...
    ]
```

### 2.2 缺失的关键 Headers

`_build_shopee_api_headers()` 返回的必需 headers：

```python
{
    'x-region': 'my',              # 国家代码（从 country_domain 提取）
    'x-region-domain': 'com.my',   # 域名后缀
    'x-region-timezone': '+0800',  # 时区偏移（根据国家计算）
    'language': 'en',
    'x-env': 'live',
    'accept': 'application/json',
    'content-type': 'application/json',
}
```

**结论**：Shopee API 的 `dashboard/*` 接口强制要求这些 headers，缺少它们会导致 404。

## 3. 修复方案

### 3.1 修改位置

修改 `live_dp/spiders/shopee.py` 中的两个方法：

1. `_build_trends_requests()` (第 433 行)
2. `_fetch_session_detail_via_js()` (第 467 行)

### 3.2 修改内容

**修改 1: `_build_trends_requests()`**
```python
def _build_trends_requests(self, session: dict) -> List[Dict[str, Any]]:
    """为单个 session 构造 3 个 trends 接口请求配置。"""
    session_id = session.get('sessionId')
    start_time = session.get('startTime')
    end_time = session.get('endTime')

    if not all([session_id, start_time, end_time]):
        return []

    base_url = self._get_base_url()
    headers = self._build_request_headers()
    headers.update(self._build_shopee_api_headers())  # ← 添加此行

    return [...]
```

**修改 2: `_fetch_session_detail_via_js()`**
```python
def _fetch_session_detail_via_js(self, session: Dict[str, Any], headers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """对单个实时 session 发起 7 个详情接口的 JS 注入。"""
    results = []
    try:
        session_id = session.get('sessionId')
        if not session_id:
            return results

        base_url = self._get_base_url()
        fetch_headers = self._build_request_headers(headers)
        fetch_headers.update(self._build_shopee_api_headers())  # ← 添加此行

        all_requests = [...]
```

## 4. 验证方法

### 4.1 单元测试
```python
# 验证 headers 是否包含必需字段
def test_dashboard_headers():
    crawler = ShopeeLiveCrawler(browser_id='test', group_name='马来')
    headers = crawler._build_request_headers({})
    headers.update(crawler._build_shopee_api_headers())

    assert 'x-region' in headers
    assert 'x-region-domain' in headers
    assert 'x-region-timezone' in headers
    assert headers['x-env'] == 'live'
```

### 4.2 集成测试
运行完整采集流程，检查 dashboard 接口是否返回 200 状态码和有效数据。

## 5. 经验总结

### 5.1 请求构造原则
- **对比已成功接口**：新接口出现 404 时，优先对比同项目中已成功接口的请求构造方式
- **检查 headers 完整性**：Shopee API 对 headers 要求严格，缺少任何一个必需字段都可能导致 404
- **复用工具方法**：项目中已有 `_build_shopee_api_headers()` 方法，新接口应统一复用

### 5.2 调试技巧
1. 先找到同项目中已成功的接口作为参照
2. 逐字段对比请求构造代码
3. 重点检查 headers、URL 路径、参数格式
4. 使用浏览器 DevTools 抓包验证真实请求

### 5.3 记录到 Agent Memory
- Shopee API 的 `dashboard/*` 接口必须包含 `x-region`、`x-region-domain`、`x-region-timezone`、`x-env` 等 headers
- 新增 Shopee 接口时，统一调用 `_build_shopee_api_headers()` 方法
- 404 错误优先排查 headers 缺失，而非 URL 路径错误

---

**修复日期**: 2026-03-31
**修复版本**: v1.0
**影响范围**: 实时直播间详情接口（7 个 dashboard 接口）
