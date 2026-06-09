# Shopee 登录检测重构实施计划 (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 adspower-server 被动监听丢包问题，新增主动验证快速路径 + 跨境店多店列表接口 + live-crawler 跨境店 HTTP 切换

**Architecture:** 被动监听保留作安全网，URL 离开登录页后 5s 节流触发主动验证，双路径证据合并；跨境店切换从浏览器点击改为 HTTP API 调用

**Tech Stack:** Python 3.12 · DrissionPage · pytest + pytest-mock · FastAPI (异步) · curl_cffi (live-crawler)

---

## Task 1: 搭建 adspower-server pytest 测试框架

**Files:**
- Create: `services/adspower-server/pytest.ini`
- Create: `services/adspower-server/conftest.py`
- Modify: `services/adspower-server/requirements.txt`

- [ ] **Step 1: 添加 pytest 依赖**

编辑 `services/adspower-server/requirements.txt`，末尾追加：

```
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.11.0
```

- [ ] **Step 2: 创建 pytest.ini 配置**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

- [ ] **Step 3: 创建 conftest.py 测试基础设施**

```python
import sys
from pathlib import Path

# 添加 app 目录到 sys.path，允许测试直接 import app.services.login_monitor
sys.path.insert(0, str(Path(__file__).parent / "app"))
```

- [ ] **Step 4: 安装依赖并验证 pytest 可用**

Run: `cd services/adspower-server && pip install -r requirements.txt`
Expected: pytest 安装成功

Run: `pytest --collect-only`
Expected: `collected 0 items` (当前无测试)

- [ ] **Step 5: Commit**

```bash
git add services/adspower-server/pytest.ini services/adspower-server/conftest.py services/adspower-server/requirements.txt
git commit -m "test(adspower): 搭建 pytest 测试框架"
```

---

## Task 2: adspower-server 新增 _fetch_shopee_shop_ids 主动验证方法

**Files:**
- Modify: `services/adspower-server/app/services/login_monitor.py:502-597` (在 `_verify_shopee_login_by_api` 后插入)

- [ ] **Step 1: 新增 _fetch_shopee_shop_ids 方法（第一部分：框架与跨境店）**

在 `login_monitor.py` 的 `_verify_shopee_login_by_api` 方法后插入（约 613 行后）：

```python
def _fetch_shopee_shop_ids(self, session: Session) -> tuple[bool, set[int]]:
    """主动验证登录态并获取 shop_id 集合。
    
    通过 JS 注入调用验证接口 + 店铺列表接口，5s 节流后在 URL 离开登录页时调用。
    
    Args:
        session: 会话对象，包含 cb_option/country/drissionpage_tab
    
    Returns:
        (login_ok, shop_ids): 登录态是否有效 + 店铺 ID 集合
    """
    tab = session.drissionpage_tab
    
    if session.cb_option == 1:
        # 跨境店：CN get_session + get_merchant_shop_list
        return self._fetch_cn_shop_ids(tab)
    else:
        # 本土店：api/v2/login + get_shop_list
        return self._fetch_local_shop_ids(tab, session.country)
```

- [ ] **Step 2: 新增 _fetch_cn_shop_ids（跨境店主动验证）**

紧接上一方法插入：

```python
def _fetch_cn_shop_ids(self, tab) -> tuple[bool, set[int]]:
    """跨境店主动验证：CN get_session + get_merchant_shop_list"""
    try:
        ts = int(time.time() * 1000)
        session_key = f"__cn_session_{ts}"
        list_key = f"__cn_list_{ts}"
        
        js_code = f"""
        window['{session_key}'] = null;
        window['{list_key}'] = null;
        fetch('https://seller.shopee.cn/api/cnsc/selleraccount/get_session/', {{
            method: 'GET', credentials: 'include'
        }}).then(async r => {{
            try {{ window['{session_key}'] = {{ status: r.status, response: await r.json() }}; }}
            catch (e) {{ window['{session_key}'] = {{ error: String(e) }}; }}
        }}).catch(e => {{ window['{session_key}'] = {{ error: String(e) }}; }});
        
        fetch('https://seller.shopee.cn/api/cnsc/selleraccount/get_merchant_shop_list/', {{
            method: 'GET', credentials: 'include'
        }}).then(async r => {{
            try {{ window['{list_key}'] = {{ status: r.status, response: await r.json() }}; }}
            catch (e) {{ window['{list_key}'] = {{ error: String(e) }}; }}
        }}).catch(e => {{ window['{list_key}'] = {{ error: String(e) }}; }});
        """
        
        self._inject_js_with_retry(tab, js_code)
        
        # Poll 等待结果
        session_result = self._poll_window_var(tab, session_key, timeout=10.0)
        list_result = self._poll_window_var(tab, list_key, timeout=10.0)
        
        # 清理
        try:
            tab.run_js(f"delete window['{session_key}']; delete window['{list_key}'];")
        except Exception:
            pass
        
        # 验证 get_session
        if not session_result or 'error' in session_result:
            return False, set()
        session_data = session_result.get('response', {})
        if session_data.get('code') != 0:
            return False, set()
        
        # 提取 current_shop_id
        shop_ids = set()
        sub_info = session_data.get('sub_account_info', {}) or {}
        current_id = self._to_int(sub_info.get('current_shop_id'))
        if current_id:
            shop_ids.add(current_id)
        
        # 提取 merchant_shop_list（可能无权限，不影响 login_ok）
        if list_result and 'error' not in list_result:
            list_data = list_result.get('response', {})
            if list_data.get('code') == 0:
                shops = list_data.get('data', {}).get('shops', [])
                for shop in shops:
                    sid = self._to_int(shop.get('shop_id'))
                    if sid:
                        shop_ids.add(sid)
        
        return True, shop_ids
    except Exception as e:
        logger.warning("跨境店主动验证异常: {}", e)
        return False, set()
```

- [ ] **Step 3: 新增 _fetch_local_shop_ids（本土店主动验证）**

紧接上一方法插入：

```python
def _fetch_local_shop_ids(self, tab, country: str) -> tuple[bool, set[int]]:
    """本土店主动验证：api/v2/login + get_shop_list"""
    try:
        domain = get_shopee_seller_domain(country)
        ts = int(time.time() * 1000)
        login_key = f"__local_login_{ts}"
        list_key = f"__local_list_{ts}"
        
        js_code = f"""
        window['{login_key}'] = null;
        window['{list_key}'] = null;
        fetch('https://{domain}/api/v2/login/', {{
            method: 'GET', credentials: 'include'
        }}).then(async r => {{
            try {{ window['{login_key}'] = {{ status: r.status, response: await r.json() }}; }}
            catch (e) {{ window['{login_key}'] = {{ error: String(e) }}; }}
        }}).catch(e => {{ window['{login_key}'] = {{ error: String(e) }}; }});
        
        fetch('https://{domain}/api/selleraccount/subaccount/get_shop_list/', {{
            method: 'POST', credentials: 'include'
        }}).then(async r => {{
            try {{ window['{list_key}'] = {{ status: r.status, response: await r.json() }}; }}
            catch (e) {{ window['{list_key}'] = {{ error: String(e) }}; }}
        }}).catch(e => {{ window['{list_key}'] = {{ error: String(e) }}; }});
        """
        
        self._inject_js_with_retry(tab, js_code)
        
        login_result = self._poll_window_var(tab, login_key, timeout=10.0)
        list_result = self._poll_window_var(tab, list_key, timeout=10.0)
        
        try:
            tab.run_js(f"delete window['{login_key}']; delete window['{list_key}'];")
        except Exception:
            pass
        
        if not login_result or 'error' in login_result:
            return False, set()
        login_data = login_result.get('response', {})
        if login_data.get('errcode') != 0:
            return False, set()
        
        shop_ids = set()
        current_id = self._to_int(
            login_data.get('shopid') or (login_data.get('user') or {}).get('shop_id')
        )
        if current_id:
            shop_ids.add(current_id)
        
        if list_result and 'error' not in list_result:
            list_data = list_result.get('response', {})
            if list_data.get('code') == 0:
                shops = list_data.get('shops', [])
                for shop in shops:
                    sid = self._to_int(shop.get('shop_id'))
                    if sid:
                        shop_ids.add(sid)
        
        return True, shop_ids
    except Exception as e:
        logger.warning("本土店主动验证异常: {}", e)
        return False, set()
```

- [ ] **Step 4: 新增 _poll_window_var 辅助方法**

紧接上一方法插入：

```python
def _poll_window_var(self, tab, var_name: str, timeout: float = 10.0) -> dict | None:
    """Poll 等待 window 变量赋值完成"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        val = tab.run_js(f"return window['{var_name}'];")
        if val is not None:
            return val
        time.sleep(0.5)
    return None
```

- [ ] **Step 5: 更新 SHOPEE_PATTERN 加入 get_merchant_shop_list**

修改 `login_monitor.py:35-41`：

```python
SHOPEE_PATTERN = [
    "api/v2/login",
    "subaccount/get_shop_list",
    "selleraccount/shop_info",
    "shop_info/get_shop_inactive_status",
    "cnsc/selleraccount/get_session",
    "cnsc/selleraccount/get_merchant_shop_list",  # 新增
]
```

- [ ] **Step 6: Commit**

```bash
git add services/adspower-server/app/services/login_monitor.py
git commit -m "feat(adspower): 新增主动验证方法 _fetch_shopee_shop_ids + 跨境店多店列表接口"
```

---

## Task 3: adspower-server 重构 _listen_once 混合监听

**Files:**
- Modify: `services/adspower-server/app/services/login_monitor.py:297-380`

- [ ] **Step 1: 重构 _listen_once 方法（替换整个方法）**

替换 `login_monitor.py:297-380` 的 `_listen_once` 方法：

```python
def _listen_once(self, session: Session) -> Optional[Dict[str, Any]]:
    """混合监听：被动安全网 + 主动快速路径。
    
    被动监听持续收集接口响应包，URL 离开登录页后每 5s 触发一次主动验证，
    双路径证据合并，任一命中 validate_id 即退出。
    
    Returns:
        {"login_ok": bool, "shop_ids": set[int]} 或 None（超时未拿到任何证据）
    """
    tab = session.drissionpage_tab
    tab.listen.start(self.SHOPEE_PATTERN)
    
    deadline = time.time() + settings.LOGIN_TIMEOUT_SECONDS
    login_ok = False
    shop_ids: set[int] = set()
    last_active_verify = 0.0
    
    while time.time() < deadline:
        # ① 被动排水：等待网络包
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        packet = tab.listen.wait(timeout=min(remaining, 1.0))
        
        if packet:
            url = getattr(packet, "url", "") or ""
            response = getattr(packet, "response", None)
            body = getattr(response, "body", None) if response else None
            parsed_body = self._parse_body(body)
            
            if "api/v2/login" in url:
                shop_id = self._extract_shop_id(parsed_body)
                if shop_id and shop_id != 0:
                    shop_ids.add(shop_id)
                    login_ok = True
            elif "subaccount/get_shop_list" in url:
                ids = self._extract_shop_ids_from_shop_list(parsed_body)
                shop_ids.update(ids)
                if ids:
                    login_ok = True
            elif "selleraccount/shop_info" in url or "shop_info/get_shop_inactive_status" in url:
                shop_id = self._extract_shop_id_from_data(parsed_body)
                if shop_id and shop_id != 0:
                    shop_ids.add(shop_id)
                    login_ok = True
            elif "cnsc/selleraccount/get_session" in url:
                shop_id = self._extract_shop_id_from_cn_session(parsed_body)
                if shop_id and shop_id != 0:
                    shop_ids.add(shop_id)
                    login_ok = True
            elif "cnsc/selleraccount/get_merchant_shop_list" in url:
                ids = self._extract_shop_ids_from_cn_merchant_list(parsed_body)
                shop_ids.update(ids)
                if ids:
                    login_ok = True
        
        # ② 主动验证：URL 离开登录页 + 5s 节流
        try:
            current_url = tab.url or ""
            not_in_login_page = (
                "seller/login" not in current_url
                and "account/signin" not in current_url
                and "agentaccount.seller.shopee.com" not in current_url
            )
            if not_in_login_page and time.time() - last_active_verify > 5.0:
                last_active_verify = time.time()
                ok, sids = self._fetch_shopee_shop_ids(session)
                login_ok = login_ok or ok
                shop_ids.update(sids)
        except Exception as e:
            logger.debug("主动验证异常（继续被动监听）: {}", e)
        
        # ③ 命中即退出
        if login_ok and str(session.validate_id) in {str(i) for i in shop_ids}:
            break
    
    try:
        tab.listen.stop()
    except Exception as exc:
        logger.debug("停止监听失败: {}", exc)
    
    if not login_ok and not shop_ids:
        return None
    return {"login_ok": login_ok, "shop_ids": shop_ids}
```

- [ ] **Step 2: 新增 _extract_shop_ids_from_cn_merchant_list（提取跨境多店列表）**

在 `_extract_shop_id_from_cn_session` 方法后插入（约 463 行后）：

```python
def _extract_shop_ids_from_cn_merchant_list(self, body: Any) -> list[int]:
    """从 get_merchant_shop_list 响应的 data.shops 数组中提取所有 shop_id"""
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    shops = data.get("shops", [])
    shop_ids = []
    for shop in shops:
        if isinstance(shop, dict) and "shop_id" in shop:
            shop_id = self._to_int(shop.get("shop_id"))
            if shop_id is not None:
                shop_ids.append(shop_id)
    return shop_ids
```

- [ ] **Step 3: 修改 _run 判定逻辑适配新返回结构**

修改 `login_monitor.py:73-115` 的 `_run` 方法判定部分（83-115 行）：

```python
if result is None:
    session.login_status = "error"
    await self._handle_result(session, status="error", reason="timeout", shop_id=None)
    return

login_ok = result.get("login_ok", False)
shop_ids = result.get("shop_ids", set())

validate_id = str(session.validate_id)

if login_ok:
    if validate_id in {str(sid) for sid in shop_ids}:
        session.login_status = "success"
        await self._handle_result(session, status="success", reason="", shop_id=int(validate_id) if validate_id.isdigit() else None)
        return

session.login_status = "error"
reported_shop_id = list(shop_ids)[0] if shop_ids else None
await self._handle_result(session, status="error", reason="shop_mismatch", shop_id=reported_shop_id)
```

- [ ] **Step 4: Commit**

```bash
git add services/adspower-server/app/services/login_monitor.py
git commit -m "refactor(adspower): 重构 _listen_once 为混合监听(被动安全网+主动快速路径)"
```

---

## Task 4: adspower-server 单元测试

**Files:**
- Create: `services/adspower-server/tests/services/test_login_monitor_shopee.py`

- [ ] **Step 1: 创建测试目录结构**

Run: `mkdir -p services/adspower-server/tests/services`

- [ ] **Step 2: 写测试文件头部与 fixtures（第1段）**

创建 `services/adspower-server/tests/services/test_login_monitor_shopee.py`：

```python
"""Shopee 登录监听单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.login_monitor import LoginMonitorService
from app.services.session import Session


@pytest.fixture
def service():
    """LoginMonitorService 实例"""
    return LoginMonitorService()


@pytest.fixture
def mock_tab():
    """Mock DrissionPage tab"""
    tab = MagicMock()
    tab.url = "https://seller.shopee.com.my/"
    tab.run_js = MagicMock(return_value=None)
    return tab


@pytest.fixture
def session_cn(mock_tab):
    """跨境店 session"""
    session = Session(
        session_id="test-cn",
        profile_id="profile-cn",
        country="MY",
        media="shopee",
        validate_id="123456",
        cb_option=1,
        drissionpage_tab=mock_tab,
    )
    return session


@pytest.fixture
def session_local(mock_tab):
    """本土店 session"""
    session = Session(
        session_id="test-local",
        profile_id="profile-local",
        country="MY",
        media="shopee",
        validate_id="789012",
        cb_option=0,
        drissionpage_tab=mock_tab,
    )
    return session
```

- [ ] **Step 3: 测试 _fetch_cn_shop_ids 成功场景（第2段）**

追加到测试文件：

```python
def test_fetch_cn_shop_ids_success(service, mock_tab):
    """跨境店主动验证成功，get_session + get_merchant_shop_list 都返回"""
    # Mock _inject_js_with_retry 和 _poll_window_var
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                # get_session 结果
                {
                    'status': 200,
                    'response': {
                        'code': 0,
                        'sub_account_info': {'current_shop_id': 123456}
                    }
                },
                # get_merchant_shop_list 结果
                {
                    'status': 200,
                    'response': {
                        'code': 0,
                        'data': {
                            'shops': [
                                {'shop_id': 123456},
                                {'shop_id': 789012},
                            ]
                        }
                    }
                }
            ]
            
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            
            assert login_ok is True
            assert shop_ids == {123456, 789012}


def test_fetch_cn_shop_ids_only_current(service, mock_tab):
    """跨境店 get_merchant_shop_list 无权限，仅 current_shop_id 可用"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'code': 0, 'sub_account_info': {'current_shop_id': 123456}}},
                {'error': 'NetworkError'},  # 列表接口失败
            ]
            
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            
            assert login_ok is True
            assert shop_ids == {123456}


def test_fetch_cn_shop_ids_logout(service, mock_tab):
    """跨境店未登录"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'code': 2, 'message': 'token not found'}},
                None,
            ]
            
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            
            assert login_ok is False
            assert shop_ids == set()
```

- [ ] **Step 4: 测试 _fetch_local_shop_ids（第3段）**

追加到测试文件：

```python
def test_fetch_local_shop_ids_success(service, mock_tab):
    """本土店主动验证成功"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'errcode': 0, 'shopid': 789012}},
                {'status': 200, 'response': {'code': 0, 'shops': [{'shop_id': 789012}, {'shop_id': 111111}]}},
            ]
            
            login_ok, shop_ids = service._fetch_local_shop_ids(mock_tab, "MY")
            
            assert login_ok is True
            assert shop_ids == {789012, 111111}


def test_fetch_local_shop_ids_logout(service, mock_tab):
    """本土店未登录"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'errcode': 1, 'fields': None}},
                None,
            ]
            
            login_ok, shop_ids = service._fetch_local_shop_ids(mock_tab, "MY")
            
            assert login_ok is False
            assert shop_ids == set()
```

- [ ] **Step 5: 测试 _poll_window_var 辅助方法（第4段）**

追加到测试文件：

```python
def test_poll_window_var_success(service, mock_tab):
    """poll 成功获取值"""
    mock_tab.run_js.return_value = {'key': 'value'}
    
    result = service._poll_window_var(mock_tab, "__test_var", timeout=2.0)
    
    assert result == {'key': 'value'}


def test_poll_window_var_timeout(service, mock_tab):
    """poll 超时返回 None"""
    mock_tab.run_js.return_value = None
    
    result = service._poll_window_var(mock_tab, "__test_var", timeout=0.5)
    
    assert result is None
```

- [ ] **Step 6: 运行测试验证**

Run: `cd services/adspower-server && pytest tests/services/test_login_monitor_shopee.py -v`
Expected: 所有测试 PASSED

- [ ] **Step 7: Commit**

```bash
git add services/adspower-server/tests/services/test_login_monitor_shopee.py
git commit -m "test(adspower): 新增 Shopee 登录监听单元测试"
```

---

## Task 5: live-crawler 新增 _switch_to_shop_by_http（跨境店 HTTP 切换）

**Files:**
- Modify: `services/live-crawler/crawlers/browser/shopee.py:815` (在 `_switch_to_shop` 前插入)

- [ ] **Step 1: 新增 _switch_to_shop_by_http 方法（第1部分：切换+语言设置）**

在 `shopee.py` 的 `_switch_to_shop` 方法前插入（约 815 行前）：

```python
def _switch_to_shop_by_http(self, target_shop_id: str, region: str) -> bool:
    """跨境店通过 HTTP API 切换店铺（非浏览器点击）
    
    Steps:
        ① POST switch_merchant_shop/  切换店铺
        ② POST set_language/          设置语言（必需）
        ③ GET  get_session/           校验 current_shop_id == target
    
    Args:
        target_shop_id: 目标店铺 ID
        region: 店铺所在国家（大写，如 MY/TH/VN）
    
    Returns:
        True: 切换成功
        False: 失败（HTTP 403 表示 Cookie 过期）
    """
    if not self.is_cross_border:
        logger.error("HTTP 切换仅适用于跨境店")
        return False
    
    try:
        # 读取 Cookie 用于 query params
        cookies_list = self.tab.cookies(all_info=True)
        cookie_dict = {c.get('name'): c.get('value') for c in cookies_list}
        spc_cds = cookie_dict.get('SPC_CDS')
        if not spc_cds:
            logger.error("缺少 SPC_CDS Cookie，无法切换店铺")
            return False
        
        # 构造公共 query 参数
        switch_url = (
            f"https://seller.shopee.cn/api/cnsc/selleraccount/switch_merchant_shop/"
            f"?cnsc_shop_id={self.media_shop_id}&cbsc_shop_region={region.upper()}"
            f"&SPC_CDS={spc_cds}&SPC_CDS_VER=2"
        )
        lang_url = (
            f"https://seller.shopee.cn/api/cnsc/selleraccount/set_language/"
            f"?cnsc_shop_id={self.media_shop_id}&cbsc_shop_region={region.upper()}"
            f"&SPC_CDS={spc_cds}&SPC_CDS_VER=2"
        )
        
        # ① 切换店铺
        results = self.browser_api.run_js_fetch(
            self.tab,
            [{
                'url': switch_url,
                'method': 'POST',
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'shop_id': int(target_shop_id)}),
                'credentials': 'include',
            }],
            max_retries=0,
        )
        
        if not results or not results[0]:
            logger.error("切换店铺接口超时")
            return False
        
        switch_result = results[0]
        if 'error' in switch_result:
            error_msg = switch_result['error']
            if 'status_403' in error_msg:
                logger.warning("Cookie 已过期（HTTP 403），需重新登录")
                self.send_login_callback("logout", reason="cookie_expired")
                return False
            logger.error(f"切换店铺接口失败: {error_msg}")
            return False
        
        # ② 设置语言（必需）
        results = self.browser_api.run_js_fetch(
            self.tab,
            [{
                'url': lang_url,
                'method': 'POST',
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'language': 'zh-CN'}),
                'credentials': 'include',
            }],
            max_retries=0,
        )
        
        if not results or not results[0] or 'error' in results[0]:
            logger.warning("设置语言失败，但不阻塞切换流程")
        
        # ③ 校验：重新获取 get_session，检查 current_shop_id
        results = self.browser_api.run_js_fetch(
            self.tab,
            [{
                'url': 'https://seller.shopee.cn/api/cnsc/selleraccount/get_session/',
                'method': 'GET',
                'credentials': 'include',
            }],
            max_retries=1,
        )
        
        if not results or not results[0] or 'error' in results[0]:
            logger.error("校验切换结果失败：get_session 接口异常")
            return False
        
        session_data = results[0].get('response', {})
        new_current = (session_data.get('sub_account_info') or {}).get('current_shop_id')
        
        if str(new_current) != str(target_shop_id):
            logger.error(f"切换后店铺 ID 仍不匹配: {new_current} != {target_shop_id}")
            return False
        
        logger.info(f"跨境店 HTTP 切换成功: {target_shop_id}")
        return True
        
    except Exception as e:
        logger.error(f"跨境店 HTTP 切换异常: {e}")
        return False
```

- [ ] **Step 2: 新增 _get_shop_region_from_list 辅助方法（查询店铺所属国家）**

在 `_switch_to_shop_by_http` 后插入：

```python
def _get_shop_region_from_list(self, shop_id: str) -> str | None:
    """从跨境店多店列表中查询指定店铺的 region"""
    try:
        results = self.browser_api.run_js_fetch(
            self.tab,
            [{
                'url': 'https://seller.shopee.cn/api/cnsc/selleraccount/get_merchant_shop_list/',
                'method': 'GET',
                'credentials': 'include',
            }],
            max_retries=1,
        )
        
        if not results or not results[0] or 'error' in results[0]:
            return None
        
        list_data = results[0].get('response', {})
        shops = list_data.get('data', {}).get('shops', [])
        for shop in shops:
            if str(shop.get('shop_id')) == str(shop_id):
                return shop.get('region')
        return None
    except Exception as e:
        logger.warning(f"查询店铺 region 失败: {e}")
        return None
```

- [ ] **Step 3: Commit**

```bash
git add services/live-crawler/crawlers/browser/shopee.py
git commit -m "feat(live-crawler): 新增跨境店 HTTP 切换方法 _switch_to_shop_by_http"
```

---

## Task 6: live-crawler 修改 _switch_to_shop 分流逻辑

**Files:**
- Modify: `services/live-crawler/crawlers/browser/shopee.py:815-870`

- [ ] **Step 1: 重构 _switch_to_shop 入口方法**

替换 `shopee.py:815-870` 的 `_switch_to_shop` 方法：

```python
def _switch_to_shop(self, target_shop_id: str, original_url: str) -> bool:
    """切换店铺入口：跨境店走 HTTP API，本土店走浏览器点击
    
    Args:
        target_shop_id: 目标店铺 ID
        original_url: 原始采集页面 URL，切换后需要回到此页面
    """
    if self.is_cross_border:
        # 跨境店：HTTP API 切换
        region = self._get_shop_region_from_list(target_shop_id)
        if not region:
            # 从 remark 或域名兜底推断
            region = (self._get_country_from_remark() or self.country_domain).upper()
        
        success = self._switch_to_shop_by_http(target_shop_id, region)
        if success:
            # HTTP 切换成功后需重新获取 login info 并导航回采集页
            if not self._fetch_login_info_via_js():
                return False
            self._sync_remark_country_if_needed(target_shop_id)
            logger.info(f'导航回原始采集页面: {original_url}')
            self._open_collection_page(original_url)
        return success
    else:
        # 本土店：保持原有浏览器点击逻辑
        return self._switch_to_shop_by_browser(target_shop_id, original_url)
```

- [ ] **Step 2: 重命名原 _switch_to_shop 逻辑为 _switch_to_shop_by_browser**

将原 `_switch_to_shop` 方法体重命名为 `_switch_to_shop_by_browser`，保持逻辑不变：

```python
def _switch_to_shop_by_browser(self, target_shop_id: str, original_url: str) -> bool:
    """本土店通过浏览器点击 Details 按钮切换店铺（保持原逻辑）
    
    Args:
        target_shop_id: 目标店铺 ID
        original_url: 原始采集页面 URL，切换后需要回到此页面
    """
    try:
        shop_list_url = f'https://seller.shopee.{self.country_domain}/portal/shop'
        logger.info(f'导航到店铺列表页: {shop_list_url}')
        self.tab.get(shop_list_url)
        time.sleep(3)
        self.tab.wait.eles_loaded('xpath://*[@class="eds-react-table"]', timeout=5)

        detail_link = self.tab.ele(
           f'xpath://*[@data-row-key="{target_shop_id}"]//button',
            timeout=5
        )

        self.tab.run_js('arguments[0].click();', detail_link)
        time.sleep(3)

        latest_tab = self.driver.latest_tab
        if latest_tab:
            self.tab = latest_tab
            logger.info('已切换到新打开的店铺 tab')

        try:
            self.tab.close(others=True)
            logger.info('已关闭其他无用的 tab')
        except Exception as e:
            logger.warning(f'关闭其他 tab 失败: {e}')

        if not self._fetch_login_info_via_js():
            return False

        if str(self.media_shop_id) != target_shop_id:
            logger.warning(f'切换后 shop_id 仍不匹配: {self.media_shop_id} != {target_shop_id}')
            return False

        logger.info(f'店铺切换成功: {target_shop_id}')
        self._sync_remark_country_if_needed(target_shop_id)

        logger.info(f'导航回原始采集页面: {original_url}')
        self._open_collection_page(original_url)

        return True
    except Exception as e:
        logger.error(f'店铺切换异常: {e}')
        return False
```

- [ ] **Step 3: Commit**

```bash
git add services/live-crawler/crawlers/browser/shopee.py
git commit -m "refactor(live-crawler): _switch_to_shop 分流跨境/本土切换逻辑"
```

---

## Task 7: live-crawler 单元测试

**Files:**
- Create: `services/live-crawler/tests/crawlers/browser/test_shopee_switch_to_shop.py`

- [ ] **Step 1: 写测试文件框架与 fixtures**

创建 `services/live-crawler/tests/crawlers/browser/test_shopee_switch_to_shop.py`：

```python
"""Shopee 店铺切换单元测试"""
import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

# 最小化加载避免真实依赖
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def _make_crawler(is_cross_border=False):
    """构造最小可测试的 Shopee 爬虫实例"""
    from crawlers.browser import shopee as shopee_module
    
    crawler = object.__new__(shopee_module.ShopeeLiveCrawler)
    crawler.is_cross_border = is_cross_border
    crawler.country_domain = "cn" if is_cross_border else "com.my"
    crawler.media_shop_id = "123456"
    crawler.media_user_id = "999"
    crawler.browser_api = MagicMock()
    crawler.tab = MagicMock()
    crawler.tab.cookies.return_value = [
        {'name': 'SPC_CDS', 'value': 'test_cds_token'}
    ]
    crawler.send_login_callback = MagicMock(return_value=True)
    crawler._fetch_login_info_via_js = MagicMock(return_value=True)
    crawler._sync_remark_country_if_needed = MagicMock()
    crawler._open_collection_page = MagicMock()
    crawler._get_country_from_remark = MagicMock(return_value=None)
    
    return crawler
```

- [ ] **Step 2: 测试跨境店 HTTP 切换成功场景**

追加到测试文件：

```python
def test_switch_to_shop_by_http_success():
    """跨境店 HTTP 切换成功"""
    crawler = _make_crawler(is_cross_border=True)
    
    # Mock run_js_fetch 三次调用：switch / set_language / get_session
    crawler.browser_api.run_js_fetch.side_effect = [
        # ① switch_merchant_shop
        [{'response': {'code': 0}}],
        # ② set_language
        [{'response': {'code': 0}}],
        # ③ get_session 验证
        [{'response': {
            'code': 0,
            'sub_account_info': {'current_shop_id': 789012}
        }}],
    ]
    
    result = crawler._switch_to_shop_by_http("789012", "MY")
    
    assert result is True
    assert crawler.browser_api.run_js_fetch.call_count == 3
```

- [ ] **Step 3: 测试跨境店 HTTP 403 Cookie 过期场景**

追加到测试文件：

```python
def test_switch_to_shop_by_http_cookie_expired():
    """跨境店切换遇到 HTTP 403，触发 cookie_expired 回调"""
    crawler = _make_crawler(is_cross_border=True)
    
    crawler.browser_api.run_js_fetch.return_value = [
        {'error': 'status_403'}
    ]
    
    result = crawler._switch_to_shop_by_http("789012", "MY")
    
    assert result is False
    crawler.send_login_callback.assert_called_once_with("logout", reason="cookie_expired")
```

- [ ] **Step 4: 测试跨境店切换后校验失败**

追加到测试文件：

```python
def test_switch_to_shop_by_http_verify_failed():
    """跨境店切换后校验 shop_id 不匹配"""
    crawler = _make_crawler(is_cross_border=True)
    
    crawler.browser_api.run_js_fetch.side_effect = [
        [{'response': {'code': 0}}],  # switch 成功
        [{'response': {'code': 0}}],  # set_language 成功
        [{'response': {
            'code': 0,
            'sub_account_info': {'current_shop_id': 999999}  # 不匹配
        }}],
    ]
    
    result = crawler._switch_to_shop_by_http("789012", "MY")
    
    assert result is False
```

- [ ] **Step 5: 测试 _switch_to_shop 跨境/本土分流**

追加到测试文件：

```python
def test_switch_to_shop_cross_border_route():
    """_switch_to_shop 跨境店走 HTTP 路径"""
    crawler = _make_crawler(is_cross_border=True)
    crawler._get_shop_region_from_list = MagicMock(return_value="MY")
    crawler._switch_to_shop_by_http = MagicMock(return_value=True)
    
    result = crawler._switch_to_shop("789012", "https://seller.shopee.cn/test")
    
    assert result is True
    crawler._switch_to_shop_by_http.assert_called_once_with("789012", "MY")
    crawler._fetch_login_info_via_js.assert_called_once()


def test_switch_to_shop_local_route():
    """_switch_to_shop 本土店走浏览器点击路径"""
    crawler = _make_crawler(is_cross_border=False)
    crawler._switch_to_shop_by_browser = MagicMock(return_value=True)
    
    result = crawler._switch_to_shop("789012", "https://seller.shopee.com.my/test")
    
    assert result is True
    crawler._switch_to_shop_by_browser.assert_called_once_with("789012", "https://seller.shopee.com.my/test")
```

- [ ] **Step 6: 运行测试验证**

Run: `cd services/live-crawler && pytest tests/crawlers/browser/test_shopee_switch_to_shop.py -v`
Expected: 所有测试 PASSED

- [ ] **Step 7: Commit**

```bash
git add services/live-crawler/tests/crawlers/browser/test_shopee_switch_to_shop.py
git commit -m "test(live-crawler): 新增 Shopee 店铺切换单元测试"
```

---

## Task 8: 集成测试与文档更新

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `services/adspower-server/CLAUDE.md`
- Modify: `services/live-crawler/CLAUDE.md`

- [ ] **Step 1: 手动集成测试（本土多店子账号）**

使用测试账号 k1a414nc（本土多店子账号）：

1. 启动 adspower-server: `cd services/adspower-server && python -m app.main`
2. 触发登录监听，观察日志
3. 验证主动验证是否在 URL 离开登录页后 5s 内触发
4. 验证 validate_id 命中后立即退出（不等 900s）
5. 检查回调 payload 中的 shop_id 字段

Expected: 登录检测时延 < 10s，成功率 100%

- [ ] **Step 2: 手动集成测试（跨境子账号）**

使用测试账号 k1curyr1（跨境子账号）：

1. 验证 OAuth 中转页时主动验证自然失败，不报错
2. 验证跳出 agentaccount 域名后主动验证成功
3. 验证 get_merchant_shop_list 被动监听或主动验证能拿到列表

Expected: OAuth 流程不阻塞，最终成功检测

- [ ] **Step 3: 手动测试跨境店 HTTP 切换**

模拟跨境多店账号切换场景：

1. 在 live-crawler 中触发 `_ensure_correct_shop`
2. 观察是否调用 `_switch_to_shop_by_http`
3. 验证 switch_merchant_shop + set_language + get_session 三步调用
4. 验证切换后 media_shop_id 更新正确

Expected: 切换成功，无浏览器 tab 操作

- [ ] **Step 4: 更新 ROADMAP.md**

在 `docs/ROADMAP.md` 的 "Phase 1: 核心整合与生产验证" 章节下标记已完成：

```markdown
- [x] Shopee 登录检测重构 Phase 1
  - 主动验证快速路径（5s 节流）
  - 跨境店多店列表接口接入
  - 跨境店 HTTP 切换替代浏览器点击
  - adspower-server pytest 框架搭建
```

- [ ] **Step 5: 更新 services/adspower-server/CLAUDE.md**

在 `services/adspower-server/CLAUDE.md` 的 "技术决策" 章节追加：

```markdown
### 登录监听架构（2026-06-09 重构）

- **混合监听**：被动安全网 + 主动快速路径，双路径证据合并
- **主动验证触发条件**：URL 离开登录页 + 5s 节流
- **跨境店接口**：get_session（验证）+ get_merchant_shop_list（多店列表）
- **本土店接口**：api/v2/login（验证）+ get_shop_list（多店列表）
- **测试覆盖**：pytest 单元测试覆盖主动验证、poll 等核心方法
```

- [ ] **Step 6: 更新 services/live-crawler/CLAUDE.md**

在 `services/live-crawler/CLAUDE.md` 的 "Shopee 特殊约束" 章节追加：

```markdown
### 店铺切换策略（2026-06-09 重构）

- **跨境店**：HTTP API 切换（switch_merchant_shop + set_language + get_session 验证）
- **本土店**：浏览器点击 Details 按钮切换（保持原逻辑）
- **HTTP 403 处理**：识别为 cookie_expired，触发 logout 回调
- **region 查询**：优先从 get_merchant_shop_list 查，兜底用 remark/country_domain
```

- [ ] **Step 7: 最终 Commit**

```bash
git add docs/ROADMAP.md services/adspower-server/CLAUDE.md services/live-crawler/CLAUDE.md
git commit -m "docs: 更新 Shopee 登录重构 Phase 1 完成状态与架构决策"
```

---

## 验收标准

Phase 1 完成后应满足：

1. **功能完整性**
   - ✅ adspower-server 主动验证在 URL 离开登录页后 5s 内触发
   - ✅ 跨境店 get_merchant_shop_list 被动监听 + 主动验证双路径覆盖
   - ✅ live-crawler 跨境店切换走 HTTP API（3 步调用成功）
   - ✅ HTTP 403 触发 cookie_expired 回调

2. **测试覆盖**
   - ✅ adspower-server: 8 个单元测试覆盖主动验证、poll、判定逻辑
   - ✅ live-crawler: 5 个单元测试覆盖 HTTP 切换、分流、403 处理
   - ✅ 集成测试通过（本土/跨境各 1 个账号验证）

3. **性能指标**
   - ✅ 登录检测时延从 15-20s 降至 < 10s
   - ✅ validate_id 命中后立即退出（不等 900s）
   - ✅ 跨境店切换无浏览器 tab 操作，耗时 < 3s

4. **代码质量**
   - ✅ 所有新增代码有中文注释和 docstring
   - ✅ Commit 遵循约定式提交规范（feat/refactor/test/docs）
   - ✅ 无 TODO/TBD/FIXME 标记

---

## 执行方式

计划已保存至 `docs/plans/2026-06-09-shopee-login-refactor-phase1.md`。

**两种执行方式：**

**1. Subagent-Driven (推荐)** — 每个 Task 派发一个 fresh subagent，主 session 在 Task 间 review，快速迭代修正

**2. Inline Execution** — 在当前 session 用 executing-plans skill 批量执行，checkpoint 处暂停 review

选择哪种方式？
