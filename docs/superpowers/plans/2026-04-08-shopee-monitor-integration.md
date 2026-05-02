# Shopee 监控系统集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Shopee 采集链路接入现有监控系统，实现按平台区分的完整性监控。

**Architecture:** Registry 从扁平结构改为 `{platform: {level: [types]}}` 二级结构，通过 `group_name` 自动识别平台。后端 API 增加 platform 过滤参数，前端增加平台 Tab 切换。数据库 schema 不变。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Vue3 + Element Plus

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| Modify | `monitor/registry.py` | Registry 平台化改造 + `detect_platform()` |
| Modify | `monitor/api/overview.py` | `/api/overview` 增加 platform 过滤 |
| Modify | `monitor/api/batches.py` | 完整率计算按平台区分 |
| Modify | `monitor/api/accounts.py` | 账号列表/详情按平台返回对应 API 类型 |
| Modify | `monitor/api/registry_routes.py` | `/api/registry` 返回按平台结构 |
| Modify | `monitor/recrawl/gap_detector.py` | 缺失检测按平台使用对应 expected types |
| Modify | `spiders/shopee.py` | 添加监控钩子 |
| Modify | `monitor/frontend/src/api/index.js` | 增加 platform 参数 |
| Modify | `monitor/frontend/src/views/AccountOverview.vue` | 增加平台 Tab |
| Modify | `monitor/frontend/src/views/BatchHistory.vue` | 弹窗增加平台列 + 动态 API 列 |
| Modify | `monitor/frontend/src/views/AccountDetail.vue` | 平台感知的 registry 使用 |
| Modify | `CLAUDE.md` (live_dp) | 补充 Shopee 登出恢复规则 |
| Modify | `tests/monitor/test_registry.py` | Registry 测试更新 |
| Modify | `tests/monitor/test_gap_detector.py` | 缺失检测测试更新 |

---

### Task 1: Registry 平台化改造

**Files:**
- Modify: `monitor/registry.py`
- Modify: `tests/monitor/test_registry.py`

- [ ] **Step 1: 更新 test_registry.py 测试用例**

将现有测试改为平台感知，并新增 Shopee 和 `detect_platform` 测试：

```python
"""API 类型注册表测试 — 验证平台化结构"""

from monitor.registry import (
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
    get_registry_for_api,
    detect_platform,
    API_TYPE_REGISTRY,
)


class TestRegistryStructure:
    """注册表结构测试"""

    def test_registry_has_platform_keys(self):
        """注册表应包含 tiktok 和 shopee 两个平台"""
        assert 'tiktok' in API_TYPE_REGISTRY
        assert 'shopee' in API_TYPE_REGISTRY

    def test_each_platform_has_three_levels(self):
        """每个平台应包含 account / daily / room 三层"""
        for platform in ('tiktok', 'shopee'):
            assert 'account' in API_TYPE_REGISTRY[platform]
            assert 'daily' in API_TYPE_REGISTRY[platform]
            assert 'room' in API_TYPE_REGISTRY[platform]

    def test_each_item_has_key_and_label(self):
        """每项应包含 key 和 label"""
        for platform in API_TYPE_REGISTRY:
            for level in API_TYPE_REGISTRY[platform]:
                for item in API_TYPE_REGISTRY[platform][level]:
                    assert 'key' in item
                    assert 'label' in item


class TestTikTokTypes:
    """TikTok 平台类型测试"""

    def test_account_types(self):
        types = get_expected_account_types('tiktok')
        assert 'live_list' in types
        assert 'replay_info' in types

    def test_room_types(self):
        types = get_expected_room_types('tiktok')
        assert 'trend_gmv' in types
        assert 'trend_stats' in types

    def test_daily_types(self):
        types = get_expected_daily_types('tiktok')
        assert 'live_stats' in types

    def test_default_platform_is_tiktok(self):
        """默认参数应返回 tiktok 的类型（向后兼容）"""
        assert get_expected_account_types() == get_expected_account_types('tiktok')
        assert get_expected_room_types() == get_expected_room_types('tiktok')
        assert get_expected_daily_types() == get_expected_daily_types('tiktok')


class TestShopeeTypes:
    """Shopee 平台类型测试"""

    def test_account_types(self):
        types = get_expected_account_types('shopee')
        assert 'session_list' in types
        assert 'live_list' in types

    def test_room_types(self):
        types = get_expected_room_types('shopee')
        assert 'session_detail' in types
        assert 'replay_detail' in types

    def test_daily_types(self):
        types = get_expected_daily_types('shopee')
        assert 'overview' in types
        assert 'metric_trend' in types


class TestDetectPlatform:
    """平台识别测试"""

    def test_shopee_keywords(self):
        """包含 Shopee 国家关键词应识别为 shopee"""
        for keyword in ('马来', '印尼', '泰国', '新加坡', '越南', '巴西', '墨西哥'):
            assert detect_platform(f'{keyword}团队') == 'shopee'

    def test_default_is_tiktok(self):
        """不包含 Shopee 关键词应默认为 tiktok"""
        assert detect_platform('团队A') == 'tiktok'
        assert detect_platform('') == 'tiktok'

    def test_tiktok_explicit(self):
        assert detect_platform('TK美国') == 'tiktok'


class TestGetRegistryForApi:
    """前端 API 返回格式测试"""

    def test_returns_platform_structure(self):
        result = get_registry_for_api()
        assert 'tiktok' in result
        assert 'shopee' in result
        for platform in result:
            assert 'account_types' in result[platform]
            assert 'daily_types' in result[platform]
            assert 'room_types' in result[platform]


class TestHelperFunctionsReturnStrings:
    """辅助函数返回类型测试"""

    def test_all_return_list_of_strings(self):
        for platform in ('tiktok', 'shopee'):
            for func in [get_expected_account_types, get_expected_room_types, get_expected_daily_types]:
                result = func(platform)
                assert isinstance(result, list)
                for item in result:
                    assert isinstance(item, str)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_registry.py -v`
Expected: FAIL（函数签名不匹配、`detect_platform` 不存在）

- [ ] **Step 3: 实现 registry.py 平台化改造**

```python
"""API 类型注册表 — 定义完整性监控的期望 API 列表（按平台）

扩展方式：在对应平台的层级中添加 {'key': '...', 'label': '...'} 即可。
前端通过 /api/registry 获取注册表，动态渲染列头，无需改前端代码。
"""

# Shopee 国家关键词，用于从 group_name 识别平台
_SHOPEE_KEYWORDS = ('马来', '印尼', '泰国', '新加坡', '越南', '巴西', '墨西哥')

API_TYPE_REGISTRY: dict[str, dict[str, list[dict]]] = {
    'tiktok': {
        # 账号级（每个账号采集一次）
        'account': [
            {'key': 'live_list', 'label': '直播间列表'},
            {'key': 'replay_info', 'label': '直播回放列表'},
        ],
        # 日期级（每个账号 × 每天一条）
        'daily': [
            {'key': 'live_stats', 'label': '关键指标(按天)'},
        ],
        # 直播间级（每个 room_id 都需要）
        'room': [
            {'key': 'trend_gmv', 'label': 'GMV趋势'},
            {'key': 'trend_stats', 'label': '直播趋势'},
        ],
    },
    'shopee': {
        'account': [
            {'key': 'session_list', 'label': '实时直播间列表'},
            {'key': 'live_list', 'label': '历史直播间列表'},
        ],
        'daily': [
            {'key': 'overview', 'label': '概览数据'},
            {'key': 'metric_trend', 'label': '指标趋势'},
        ],
        'room': [
            {'key': 'session_detail', 'label': '实时直播详情'},
            {'key': 'replay_detail', 'label': '回放详情'},
        ],
    },
}


def detect_platform(group_name: str) -> str:
    """根据 group_name 中的关键词识别平台"""
    for keyword in _SHOPEE_KEYWORDS:
        if keyword in group_name:
            return 'shopee'
    return 'tiktok'


def get_expected_account_types(platform: str = 'tiktok') -> list[str]:
    """返回账号级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['account']]


def get_expected_daily_types(platform: str = 'tiktok') -> list[str]:
    """返回日期级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['daily']]


def get_expected_room_types(platform: str = 'tiktok') -> list[str]:
    """返回直播间级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['room']]


def get_registry_for_api() -> dict:
    """返回完整注册表供前端 /api/registry 使用（按平台）"""
    result = {}
    for platform, levels in API_TYPE_REGISTRY.items():
        result[platform] = {
            'account_types': levels['account'],
            'daily_types': levels['daily'],
            'room_types': levels['room'],
        }
    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: 运行现有测试确认向后兼容**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 部分测试可能因调用方未传 platform 参数而失败，这些将在后续 Task 中修复。记录失败的测试文件。

- [ ] **Step 6: Commit**

```bash
git add monitor/registry.py tests/monitor/test_registry.py
git commit -m "refactor(monitor): Registry 平台化改造，支持 tiktok/shopee 双平台"
```

---

### Task 2: 缺失检测器平台化适配

**Files:**
- Modify: `monitor/recrawl/gap_detector.py`
- Modify: `tests/monitor/test_gap_detector.py`

- [ ] **Step 1: 更新 gap_detector.py**

每个 `detect_*_gaps` 函数需要根据账号的 `group_name` 判断平台，然后使用对应平台的 expected types：

```python
"""缺失检测器 — 对比注册表期望与实际采集记录，找出缺失的 API 调用

三级检测：
1. 账号级：各平台对应的 account-level API 是否采集
2. 日期级：daily_collection_status 中每天的日期级 API 是否采集
3. 直播间级：每个 room_id 的 room-level API 是否采集
"""

import sqlite3

from monitor.registry import (
    detect_platform,
    get_expected_account_types,
    get_expected_daily_types,
    get_expected_room_types,
)
from monitor.recrawl.models import create_task_auto


def _make_gap(
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> dict:
    """构造缺失记录字典"""
    return {
        'batch_id': batch_id,
        'account_id': account_id,
        'group_name': group_name,
        'room_id': room_id,
        'target_date': target_date,
        'api_type': api_type,
        'level': level,
    }


def detect_account_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测账号级缺失

    遍历该批次所有账号，根据平台检查每个期望的 account-level api_type 是否有成功记录。
    """
    rows = conn.execute(
        "SELECT account_id, group_name FROM account_sessions WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for row in rows:
        account_id = row['account_id']
        group_name = row['group_name']
        platform = detect_platform(group_name)
        expected = get_expected_account_types(platform)

        collected = conn.execute(
            "SELECT DISTINCT api_type FROM collection_records "
            "WHERE batch_id = ? AND account_id = ? AND status = 'success' AND room_id = ''",
            (batch_id, account_id),
        ).fetchall()
        collected_types = {r['api_type'] for r in collected}

        for api_type in expected:
            if api_type not in collected_types:
                gaps.append(_make_gap(
                    batch_id, account_id, group_name,
                    room_id='', target_date='', api_type=api_type, level='account',
                ))
    return gaps


def detect_daily_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测日期级缺失

    从 daily_collection_status 中获取该批次所有账号的日期级采集记录，
    找出 status != 'success' 或完全缺失的日期。
    """
    accounts = conn.execute(
        "SELECT account_id, group_name FROM account_sessions WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for acc in accounts:
        account_id = acc['account_id']
        group_name = acc['group_name']
        platform = detect_platform(group_name)
        expected = get_expected_daily_types(platform)

        daily_rows = conn.execute(
            "SELECT target_date, api_type, status FROM daily_collection_status "
            "WHERE batch_id = ? AND account_id = ?",
            (batch_id, account_id),
        ).fetchall()

        # 构建 (target_date, api_type) -> status 映射
        status_map: dict[tuple[str, str], str] = {}
        all_dates: set[str] = set()
        for dr in daily_rows:
            status_map[(dr['target_date'], dr['api_type'])] = dr['status']
            all_dates.add(dr['target_date'])

        for target_date in sorted(all_dates):
            for api_type in expected:
                if status_map.get((target_date, api_type)) != 'success':
                    gaps.append(_make_gap(
                        batch_id, account_id, group_name,
                        room_id='', target_date=target_date, api_type=api_type, level='daily',
                    ))
    return gaps


def detect_room_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测直播间级缺失

    遍历 room_sessions 中每个 room_id，根据平台检查对应的 room-level API。
    """
    rooms = conn.execute(
        "SELECT rs.account_id, rs.room_id, a.group_name "
        "FROM room_sessions rs "
        "JOIN account_sessions a ON rs.batch_id = a.batch_id AND rs.account_id = a.account_id "
        "WHERE rs.batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for room in rooms:
        account_id = room['account_id']
        room_id = room['room_id']
        group_name = room['group_name']
        platform = detect_platform(group_name)
        expected = get_expected_room_types(platform)

        collected = conn.execute(
            "SELECT DISTINCT api_type FROM collection_records "
            "WHERE batch_id = ? AND account_id = ? AND room_id = ? AND status = 'success'",
            (batch_id, account_id, room_id),
        ).fetchall()
        collected_types = {r['api_type'] for r in collected}

        for api_type in expected:
            if api_type not in collected_types:
                gaps.append(_make_gap(
                    batch_id, account_id, group_name,
                    room_id=room_id, target_date='', api_type=api_type, level='room',
                ))
    return gaps


def detect_all_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """执行全部三级检测，返回合并的缺失列表"""
    gaps = []
    gaps.extend(detect_account_gaps(conn, batch_id))
    gaps.extend(detect_daily_gaps(conn, batch_id))
    gaps.extend(detect_room_gaps(conn, batch_id))
    return gaps


def detect_and_create_tasks(conn: sqlite3.Connection, batch_id: str) -> int:
    """检测缺失并自动创建补采任务

    Returns:
        新创建的任务数量
    """
    gaps = detect_all_gaps(conn, batch_id)
    created = 0
    for gap in gaps:
        task_id = create_task_auto(conn, **gap)
        if task_id is not None:
            created += 1
    return created
```

- [ ] **Step 2: 运行现有 gap_detector 测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_gap_detector.py -v`
Expected: ALL PASS（现有测试使用 `group_name='团队A'`，会被识别为 tiktok，行为不变）

- [ ] **Step 3: 在 test_gap_detector.py 末尾追加 Shopee 平台测试**

在文件末尾追加：

```python
class TestShopeeGaps:
    """Shopee 平台缺失检测"""

    def test_shopee_account_gaps(self, monitor):
        """Shopee 账号应检测 session_list 和 live_list"""
        _seed_batch(monitor, accounts=[('sp1', '马来团队')])
        monitor.record('b1', 'sp1', 'session_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'live_list'

    def test_shopee_room_gaps(self, monitor):
        """Shopee 直播间应检测 session_detail 和 replay_detail"""
        _seed_batch(monitor, accounts=[('sp1', '印尼团队')])
        monitor._insert_room_session('b1', 'sp1', 'sess1')
        monitor.record('b1', 'sp1', 'session_detail', room_id='sess1', status='success')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'replay_detail'

    def test_shopee_daily_gaps(self, monitor):
        """Shopee 日期级应检测 overview 和 metric_trend"""
        _seed_batch(monitor, accounts=[('sp1', '泰国团队')])
        monitor.record_daily_stats('b1', 'sp1', '2026-04-07', 'overview', 'success')
        monitor.record_daily_stats('b1', 'sp1', '2026-04-07', 'metric_trend', 'failed')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'metric_trend'

    def test_mixed_platform_batch(self, monitor):
        """混合平台批次：TK 和 Shopee 各自检测对应的 API 类型"""
        _seed_batch(monitor, accounts=[('tk1', '团队A'), ('sp1', '新加坡团队')])
        # TK 账号全部采集
        monitor.record('b1', 'tk1', 'live_list', status='success')
        monitor.record('b1', 'tk1', 'replay_info', status='success')
        # Shopee 账号缺少 live_list
        monitor.record('b1', 'sp1', 'session_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['account_id'] == 'sp1'
        assert gaps[0]['api_type'] == 'live_list'
```

- [ ] **Step 4: 运行全部 gap_detector 测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_gap_detector.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add monitor/recrawl/gap_detector.py tests/monitor/test_gap_detector.py
git commit -m "refactor(monitor): 缺失检测器适配平台化 Registry"
```

---

### Task 3: 后端 API 平台化改造

**Files:**
- Modify: `monitor/api/overview.py`
- Modify: `monitor/api/batches.py`
- Modify: `monitor/api/accounts.py`
- Modify: `monitor/api/registry_routes.py`

- [ ] **Step 1: 更新 registry_routes.py**

```python
"""注册表 API 路由 — 提供前端所需的 API 类型注册信息"""

from fastapi import APIRouter
from monitor.registry import get_registry_for_api

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/registry")
def get_registry():
    """返回按平台分组的 API 类型注册表，供前端动态渲染列头"""
    return get_registry_for_api()
```

无需改动逻辑，`get_registry_for_api()` 已在 Task 1 中改为返回按平台结构。

- [ ] **Step 2: 更新 overview.py — 增加 platform 过滤和平台感知完整率**

关键改动：
1. `get_overview()` 增加 `platform` 查询参数
2. 完整率计算根据每个账号的 `group_name` 使用对应平台的 expected types
3. 导入 `detect_platform`

```python
# 在文件顶部 import 中增加：
from monitor.registry import (
    detect_platform,
    get_expected_account_types,
    get_expected_room_types,
)

# get_overview 函数签名改为：
@router.get('/overview')
def get_overview(
    days: int = Query(default=3, ge=1, le=90),
    platform: str | None = Query(default=None),
):
```

在 `for acc in accounts:` 循环中，将固定的 `expected_account` / `expected_room` 改为按账号平台动态获取：

```python
    for acc in accounts:
        account_id = acc['account_id']
        acc_platform = detect_platform(acc['group_name'])

        # 平台过滤
        if platform and acc_platform != platform:
            continue

        expected_account = get_expected_account_types(acc_platform)
        expected_room = get_expected_room_types(acc_platform)
        # ... 后续计算逻辑不变，但使用上面的动态 expected 列表
```

同时删除函数开头的 `expected_account = get_expected_account_types()` 和 `expected_room = get_expected_room_types()` 两行。

对 `get_account_overview()` 做类似改造：根据账号的 `group_name` 判断平台，使用对应的 expected types。

- [ ] **Step 3: 更新 batches.py — 完整率按平台计算**

在 `list_batches()` 中，将固定的 `expected_account` / `expected_room` 改为按每个账号的 `group_name` 动态获取：

```python
from monitor.registry import (
    detect_platform,
    get_expected_account_types,
    get_expected_room_types,
)

# 在 for s in sessions: 循环中：
        for s in sessions:
            acc_platform = detect_platform(s['group_name'])
            expected_account = get_expected_account_types(acc_platform)
            expected_room = get_expected_room_types(acc_platform)
            # ... 后续计算逻辑不变
```

注意：需要修改 SQL 查询，让 `sessions` 包含 `group_name` 字段：

```python
        sessions = conn.execute(
            "SELECT account_id, group_name, total_rooms FROM account_sessions WHERE batch_id=?",
            (batch_id,)
        ).fetchall()
```

- [ ] **Step 4: 更新 accounts.py — 按平台返回对应 API 类型**

`list_accounts()` 改造：
1. 增加 `platform` 查询参数（可选）
2. 每个账号根据 `group_name` 判断平台
3. `api_status` 和 `expected_account_types` 按平台返回
4. 返回值增加 `platform` 字段

```python
from monitor.registry import (
    detect_platform,
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
)

@router.get("/batches/{batch_id}/accounts")
def list_accounts(batch_id: str, platform: str | None = Query(default=None)):
    """获取批次下的账号列表及采集状态"""
    conn = _get_conn()

    sessions = conn.execute(
        "SELECT * FROM account_sessions WHERE batch_id=? ORDER BY started_at",
        (batch_id,)
    ).fetchall()

    result = []
    for s in sessions:
        account_id = s['account_id']
        acc_platform = detect_platform(s['group_name'])

        # 平台过滤
        if platform and acc_platform != platform:
            continue

        expected_account = get_expected_account_types(acc_platform)
        expected_room = get_expected_room_types(acc_platform)

        # 账号级 API 状态
        account_records = conn.execute(
            "SELECT api_type, status FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id=''",
            (batch_id, account_id)
        ).fetchall()
        api_status = {r['api_type']: r['status'] for r in account_records}

        # 直播间级统计
        rooms = conn.execute(
            "SELECT DISTINCT room_id FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id != ''",
            (batch_id, account_id)
        ).fetchall()
        room_success = 0
        for room in rooms:
            room_records = conn.execute(
                "SELECT api_type, status FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id=? AND status='success'",
                (batch_id, account_id, room['room_id'])
            ).fetchall()
            if all(any(r['api_type'] == t for r in room_records) for t in expected_room):
                room_success += 1

        result.append({
            'account_id': account_id,
            'group_name': s['group_name'],
            'platform': acc_platform,
            'total_rooms': s['total_rooms'],
            'room_success': room_success,
            'status': s['status'],
            'api_status': {t: api_status.get(t, 'missing') for t in expected_account},
            'started_at': s['started_at'],
            'finished_at': s['finished_at'],
        })

    return {'accounts': result}
```

注意：移除返回值中的 `expected_account_types` 和 `expected_room_types`，因为不同账号可能属于不同平台。前端改为从 `/api/registry` 获取。

`get_account_detail()` 和 `list_rooms()` 做类似改造：根据账号的 `group_name` 判断平台，使用对应的 expected types。

- [ ] **Step 5: 运行后端测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_overview_api.py tests/monitor/test_api_account_detail.py -v`
Expected: 可能有部分测试需要适配（如果测试中硬编码了 expected types）。修复失败的测试。

- [ ] **Step 6: Commit**

```bash
git add monitor/api/registry_routes.py monitor/api/overview.py monitor/api/batches.py monitor/api/accounts.py
git commit -m "feat(monitor): 后端 API 平台化改造，支持 platform 过滤"
```

---

### Task 4: Shopee 爬虫监控钩子

**Files:**
- Modify: `spiders/shopee.py`

- [ ] **Step 1: 在 shopee.py 中导入 monitor**

在文件顶部 import 区域添加：

```python
from monitor import get_monitor
```

- [ ] **Step 2: 在 `_handle_live_list_page` 中添加 session_list 钩子**

在 `api_data_list` 拦截成功后（约 L384 `stats['apis_count'] += 1` 之后）添加：

```python
            # 监控钩子：记录 sessionList 拦截成功
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    monitor.record(self.batch_id, self.browser_id, 'session_list', status='success')
            except Exception:
                pass
```

- [ ] **Step 3: 在 `_handle_live_list_page` 中添加 live_list 钩子**

在 `live_list_results` 获取后（约 L390 之后）添加：

```python
            # 监控钩子：记录 liveList/v2 采集状态
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    status = 'success' if live_list_results else 'failed'
                    monitor.record(self.batch_id, self.browser_id, 'live_list', status=status)
            except Exception:
                pass
```

- [ ] **Step 4: 在 `_fetch_overview_requests_via_js` 中添加 daily 级钩子**

在每天的请求循环中（`for end_date in date_range:` 内），在 `results` 处理后添加：

```python
            # 监控钩子：记录逐日 overview 和 metric_trend 采集状态
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    # results[0] 是 overview，results[1] 是 metric_trend
                    if len(valid_results) >= 1:
                        monitor.record_daily_stats(
                            self.batch_id, self.browser_id, end_date, 'overview',
                            'success' if valid_results[0] else 'failed'
                        )
                    else:
                        monitor.record_daily_stats(self.batch_id, self.browser_id, end_date, 'overview', 'failed')
                    if len(valid_results) >= 2:
                        monitor.record_daily_stats(
                            self.batch_id, self.browser_id, end_date, 'metric_trend',
                            'success' if valid_results[1] else 'failed'
                        )
                    else:
                        monitor.record_daily_stats(self.batch_id, self.browser_id, end_date, 'metric_trend', 'failed')
            except Exception:
                pass
```

- [ ] **Step 5: 在 `_handle_live_list_page` 中添加 room_session 注册和 session_detail 钩子**

在实时直播间详情采集循环中（约 L406-418），在 `_fetch_session_detail_via_js` 调用前后添加：

```python
                    # 注册 room_session
                    try:
                        monitor = get_monitor()
                        if monitor and self.batch_id:
                            session_id = str(session.get('sessionId', ''))
                            if session_id:
                                monitor._insert_room_session(self.batch_id, self.browser_id, session_id)
                    except Exception:
                        pass

                    detail_results = self._fetch_session_detail_via_js(session, headers)

                    # 监控钩子：记录 session_detail 采集状态
                    try:
                        monitor = get_monitor()
                        if monitor and self.batch_id:
                            session_id = str(session.get('sessionId', ''))
                            has_data = any(r and r.get('response') for r in detail_results)
                            monitor.record(
                                self.batch_id, self.browser_id, 'session_detail',
                                room_id=session_id, status='success' if has_data else 'failed'
                            )
                    except Exception:
                        pass
```

- [ ] **Step 6: 在 `_handle_live_list_page` 中添加 replay_detail 钩子**

在回放详情采集循环中（约 L430-441），类似处理：

```python
                        # 注册 room_session
                        try:
                            monitor = get_monitor()
                            if monitor and self.batch_id:
                                session_id = str(session.get('sessionId', ''))
                                if session_id:
                                    monitor._insert_room_session(self.batch_id, self.browser_id, session_id)
                        except Exception:
                            pass

                        detail_results = self._fetch_replay_detail_via_js(session, headers)

                        # 监控钩子：记录 replay_detail 采集状态
                        try:
                            monitor = get_monitor()
                            if monitor and self.batch_id:
                                session_id = str(session.get('sessionId', ''))
                                has_data = any(r and r.get('response') for r in detail_results)
                                monitor.record(
                                    self.batch_id, self.browser_id, 'replay_detail',
                                    room_id=session_id, status='success' if has_data else 'failed'
                                )
                        except Exception:
                            pass
```

- [ ] **Step 7: Commit**

```bash
git add spiders/shopee.py
git commit -m "feat(shopee): 添加监控钩子，接入采集完整性监控系统"
```

---

### Task 5: 前端平台化改造

**Files:**
- Modify: `monitor/frontend/src/api/index.js`
- Modify: `monitor/frontend/src/views/AccountOverview.vue`
- Modify: `monitor/frontend/src/views/BatchHistory.vue`
- Modify: `monitor/frontend/src/views/AccountDetail.vue`

- [ ] **Step 1: 更新 api/index.js — 增加 platform 参数**

```javascript
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const fetchBatches = (limit = 20) => api.get('/batches', { params: { limit } })
export const fetchAccounts = (batchId, platform) => api.get(`/batches/${batchId}/accounts`, { params: { platform } })
export const fetchRooms = (accountId, batchId) => api.get(`/accounts/${accountId}/rooms`, { params: { batch_id: batchId } })
export const fetchRegistry = () => api.get('/registry')
export const fetchAccountDetail = (batchId, accountId) => api.get(`/batches/${batchId}/accounts/${accountId}`)

// 账号总览
export const fetchOverview = (days = 3, platform) => api.get('/overview', { params: { days, platform } })
export const fetchAccountOverview = (accountId, days = 3) => api.get(`/overview/${accountId}`, { params: { days } })

// 补采
export const triggerRecrawl = (data) => api.post('/recrawl/trigger', data)
export const fetchRecrawlTasks = (params) => api.get('/recrawl/tasks', { params })

// 登录状态监控
export const fetchLogoutAccounts = (platform) => api.get('/accounts/logout-list', { params: { platform } })
export const fetchAccountLoginStatus = (accountId) => api.get(`/accounts/${accountId}/login-status`)
export const fetchAccountLoginEvents = (accountId, limit = 100) =>
  api.get(`/accounts/${accountId}/login-events`, { params: { limit } })
export const triggerAccountRecovery = (accountId, data) =>
  api.post(`/accounts/${accountId}/trigger-recovery`, data)
```

- [ ] **Step 2: 更新 AccountOverview.vue — 增加平台 Tab**

在 `<template>` 的 `header-actions` 区域，在 `days-select` 之前添加平台切换：

```html
        <el-radio-group v-model="platformFilter" size="small" class="platform-filter" @change="loadOverview">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="tiktok">TikTok</el-radio-button>
          <el-radio-button label="shopee">Shopee</el-radio-button>
        </el-radio-group>
```

在 `<script setup>` 中添加：

```javascript
const platformFilter = ref('')
```

修改 `loadOverview` 函数：

```javascript
async function loadOverview() {
  loading.value = true
  try {
    const res = await fetchOverview(days.value, platformFilter.value || undefined)
    accounts.value = (res.data.accounts || []).map(a => ({ ...a, _recrawling: false }))
  } catch (err) {
    ElMessage.error('加载账号总览失败')
  } finally {
    loading.value = false
  }
}
```

添加 CSS（复用 status-filter 样式）：

```css
:deep(.platform-filter .el-radio-button__inner) {
  background: var(--bg-card);
  border-color: var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 5px 14px;
}
:deep(.platform-filter .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
  box-shadow: -1px 0 0 0 var(--accent-blue);
}
```

- [ ] **Step 3: 更新 BatchHistory.vue — 弹窗增加平台列和动态 API 列**

在弹窗的 `el-table` 中，在"分组"列后添加"平台"列：

```html
        <el-table-column prop="platform" label="平台" width="100" align="center">
          <template #default="{ row }">
            <span class="platform-tag" :class="'pt-' + row.platform">{{ row.platform === 'shopee' ? 'Shopee' : 'TikTok' }}</span>
          </template>
        </el-table-column>
```

将 API 状态指示器列改为动态渲染（根据每行账号的 `api_status` 键）：

```html
        <!-- 账号级 API 状态指示器（动态列） -->
        <el-table-column
          v-for="apiType in allAccountApiTypes"
          :key="apiType"
          :label="apiType"
          width="110"
          align="center"
        >
          <template #default="{ row }">
            <span v-if="apiType in row.api_status" class="status-indicator" :class="'s-' + (row.api_status[apiType] || 'missing')">
              <span class="indicator-dot"></span>
              {{ statusLabel(row.api_status[apiType]) }}
            </span>
            <span v-else class="status-indicator s-na">—</span>
          </template>
        </el-table-column>
```

在 `<script setup>` 中添加计算属性：

```javascript
// 从所有账号的 api_status 中收集所有 API 类型（去重）
const allAccountApiTypes = computed(() => {
  const types = new Set()
  for (const acc of accounts.value) {
    for (const key of Object.keys(acc.api_status || {})) {
      types.add(key)
    }
  }
  return [...types]
})
```

移除 `expectedAccountTypes` ref 和 `toggleBatch` 中对 `res.data.expected_account_types` 的赋值。

添加平台标签 CSS：

```css
.platform-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
}
.pt-tiktok { color: var(--accent-blue); background: rgba(56, 139, 253, 0.08); }
.pt-shopee { color: #ee4d2d; background: rgba(238, 77, 45, 0.08); }
.s-na { color: var(--text-muted); opacity: 0.3; }
```

- [ ] **Step 4: 更新 AccountDetail.vue — 平台感知的 registry**

修改 `onMounted` 中 registry 的使用方式。当前 registry 返回按平台结构，需要根据账号平台选择对应的 types：

在 `<script setup>` 中添加：

```javascript
const accountPlatform = ref('tiktok')

// 根据平台选择对应的 registry
const platformRegistry = computed(() => {
  const r = registry.value
  return r[accountPlatform.value] || r['tiktok'] || {}
})
```

修改 `loadDetail` 函数，在获取到账号数据后判断平台：

```javascript
// 在 loadDetail 函数中，获取到 detail 后：
// 从 group_name 判断平台（与后端 detect_platform 逻辑一致）
const shopeeKeywords = ['马来', '印尼', '泰国', '新加坡', '越南', '巴西', '墨西哥']
const groupName = detail.value?.group_name || ''
accountPlatform.value = shopeeKeywords.some(k => groupName.includes(k)) ? 'shopee' : 'tiktok'
```

将模板中所有 `registry.account_types`、`registry.daily_types`、`registry.room_types` 替换为 `platformRegistry.account_types`、`platformRegistry.daily_types`、`platformRegistry.room_types`。

注意：`get_account_detail` API 当前返回值不含 `group_name`。在 Task 3 Step 4 中，需要在 `get_account_detail()` 函数中查询 `account_sessions` 获取 `group_name`，并添加到返回值中：

```python
    # 在 get_account_detail 函数开头查询 group_name
    acc_row = conn.execute(
        "SELECT group_name FROM account_sessions WHERE batch_id=? AND account_id=?",
        (batch_id, account_id)
    ).fetchone()
    group_name = acc_row['group_name'] if acc_row else ''
    acc_platform = detect_platform(group_name)
    # 使用 acc_platform 获取对应的 expected types
    expected_account = get_expected_account_types(acc_platform)
    expected_daily = get_expected_daily_types(acc_platform)
    expected_room = get_expected_room_types(acc_platform)

    # 在返回值中添加 group_name 和 platform
    return {
        'account_id': account_id,
        'batch_id': batch_id,
        'group_name': group_name,
        'platform': acc_platform,
        'account_indicators': account_indicators,
        # ... 其余字段不变
    }
```

- [ ] **Step 5: 构建前端**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: BUILD SUCCESS

- [ ] **Step 6: Commit**

```bash
git add monitor/frontend/src/api/index.js monitor/frontend/src/views/AccountOverview.vue monitor/frontend/src/views/BatchHistory.vue monitor/frontend/src/views/AccountDetail.vue
git commit -m "feat(frontend): 前端平台化改造，支持 TikTok/Shopee 切换"
```

---

### Task 6: CLAUDE.md 补充 Shopee 登出恢复规则

**Files:**
- Modify: `live_dp/CLAUDE.md`

- [ ] **Step 1: 在 CLAUDE.md 的"规则六：登出恢复流程"之后添加 Shopee 规则**

在 `## 规则六：Shopee 时间参数必须使用对应国家时区的 T-1` 之前，添加：

```markdown
### 规则八：Shopee 登出恢复不触发即时全量采集

Shopee 的 `_auto_relogin()` 在每轮采集**开始前**检测 cookie 过期并自动重登录。这与 TK 的行为不同：

| 场景 | TK | Shopee |
|------|-----|--------|
| 登出检测时机 | 采集中途（`send_login_callback`） | 采集开始前（`_check_login_status`） |
| 上一轮数据 | 可能不完整（中途登出） | 完整（上一轮正常结束） |
| 自动重登录 | 无 | `_auto_relogin()` 自动点击已保存账号 |
| 即时恢复 | 需要（当轮切换全量） | **不需要**（上一轮数据完整） |

**核心逻辑**：
- 上一轮状态为 online → 本轮 `_auto_relogin()` 成功后正常增量采集（不触发全量）
- 上一轮状态为 logout → 本轮 `resolve_collection_mode()` 检测到 `[login, logout]` 序列 → 触发全量恢复采集

**代码路径**：`shopee.py:visit_page_and_collect()` → `_check_login_status()` → `_auto_relogin()` → `send_login_callback("success")`。由于 `send_login_callback` 中检测到当前状态为 online（上一轮正常），不会设置 `full_collection=True`。
```

- [ ] **Step 2: Commit**

```bash
git add live_dp/CLAUDE.md
git commit -m "docs: 补充 Shopee 登出恢复规则到 CLAUDE.md"
```

---

### Task 7: 全量测试验证

**Files:**
- 无新文件，验证所有改动

- [ ] **Step 1: 运行全部监控模块测试**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: ALL PASS。如有失败，逐个修复。

- [ ] **Step 2: 运行全部测试**

Run: `cd live_dp && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: 构建前端确认无报错**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: BUILD SUCCESS

- [ ] **Step 4: Commit（如有修复）**

```bash
git add -A
git commit -m "fix(monitor): 修复平台化改造后的测试兼容性问题"
```
