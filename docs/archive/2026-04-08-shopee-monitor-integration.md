# Shopee 监控系统集成设计

## 目标

将 Shopee 采集链路接入现有的采集完整性监控系统，实现按平台区分的监控能力。同时将 Shopee 登出恢复规则文档化到 CLAUDE.md。

## 架构概述

在现有监控系统基础上增加 **平台维度**：Registry 按平台注册 API 类型，后端 API 按平台过滤/聚合，前端增加平台切换。数据库 schema 不变（`collection_records` 已有 `api_type` 字段，通过命名前缀区分平台）。

## 一、Registry 平台化改造

### 当前结构（仅 TK）

```python
API_TYPE_REGISTRY = {
    'account': [...],
    'daily': [...],
    'room': [...],
}
```

### 目标结构（按平台）

```python
API_TYPE_REGISTRY = {
    'tiktok': {
        'account': [
            {'key': 'live_list', 'label': '直播间列表'},
            {'key': 'replay_info', 'label': '直播回放列表'},
        ],
        'daily': [
            {'key': 'live_stats', 'label': '关键指标(按天)'},
        ],
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
```

### 辅助函数改造

所有 `get_expected_*_types()` 函数增加 `platform` 参数：

```python
def get_expected_account_types(platform: str = 'tiktok') -> list[str]:
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['account']]
```

### 平台识别

通过 `account_sessions.group_name` 判断平台：
- 包含 Shopee 国家关键词（马来/印尼/泰国/新加坡/越南/巴西/墨西哥）→ shopee
- 其他 → tiktok

新增辅助函数 `detect_platform(group_name: str) -> str`。

## 二、Shopee 监控钩子

### API 类型映射

| api_type | 对应接口 | 级别 | 触发位置 |
|----------|----------|------|----------|
| `session_list` | sessionList（拦截） | account | `_handle_live_list_page` L371-384 |
| `live_list` | liveList/v2（JS注入） | account | `_handle_live_list_page` L390 |
| `overview` | overview/v3（逐日） | daily | `_fetch_overview_requests_via_js` |
| `metric_trend` | metricTrend/v2（逐日） | daily | `_fetch_overview_requests_via_js` |
| `session_detail` | 7个实时详情API（打包） | room | `_fetch_session_detail_via_js` |
| `replay_detail` | liveDetail + liveCoordinate（打包） | room | `_fetch_replay_detail_via_js` |

### 钩子调用方式

```python
# account 级
monitor.record(batch_id, account_id, 'session_list', status='success')
monitor.record(batch_id, account_id, 'live_list', status='success')

# daily 级（逐日）
monitor.record_daily_stats(batch_id, account_id, end_date, 'overview', 'success')
monitor.record_daily_stats(batch_id, account_id, end_date, 'metric_trend', 'success')

# room 级（需先注册 room_session）
monitor._insert_room_session(batch_id, account_id, session_id)
monitor.record(batch_id, account_id, 'session_detail', room_id=session_id, status='success')
monitor.record(batch_id, account_id, 'replay_detail', room_id=session_id, status='success')
```

### room_sessions 注册

Shopee 的 room_id 使用 `sessionId`（字符串）。直播间来源：
- 实时直播间：从 sessionList 响应的 `data.list` 中 `status != 1` 的 session
- 回放直播间：从 liveList/v2 响应的 `data.list` 中 `status == 2` 的 session

## 三、后端 API 改造

### 3.1 `/api/registry` — 增加平台维度

```json
{
  "tiktok": {"account_types": [...], "daily_types": [...], "room_types": [...]},
  "shopee": {"account_types": [...], "daily_types": [...], "room_types": [...]}
}
```

### 3.2 `/api/overview` — 增加 platform 过滤

- 新增查询参数 `platform`（可选，默认返回全部）
- 通过 `group_name` 判断平台归属
- 完整率计算使用对应平台的 expected types

### 3.3 `/api/batches` — 保持不变

一个批次包含所有平台，不按平台拆分。完整率计算需要根据每个账号的平台使用对应的 expected types。

### 3.4 `/api/batches/{batch_id}/accounts` — 增加 platform 过滤

- 新增查询参数 `platform`（可选）
- `api_status` 字段根据账号所属平台返回对应的 API 类型状态

### 3.5 账号详情 API — 平台感知

根据账号的 `group_name` 自动判断平台，返回对应平台的 expected types。

## 四、前端改造

### 4.1 采集总览（AccountOverview.vue）

- 顶部增加平台 Tab 切换：全部 / TikTok / Shopee
- 调用 `/api/overview?platform=shopee` 过滤
- 卡片样式不变

### 4.2 批次历史（BatchHistory.vue）

- 保持现有的点击展开弹窗交互
- 弹窗内账号列表增加"平台"列
- 可选：弹窗内增加平台筛选
- 完整率计算已在后端按平台区分，前端无需额外处理
- API 状态指示器根据账号平台动态渲染对应的 API 类型列

### 4.3 账号详情（AccountDetail.vue）

- 根据账号平台动态渲染 API 类型列头
- 三级数据展示逻辑不变，只是列头和期望类型不同

### 4.4 登录状态（LogoutAccounts.vue）

- 不改动，已天然兼容多平台

## 五、Shopee 登出恢复规则文档化

在 CLAUDE.md 中补充 Shopee 登出恢复规则：

**核心规则**：Shopee 的 `_auto_relogin()` 在每轮采集开始时检测 cookie 过期并自动重登录。如果上一轮采集状态为 online（数据完整），则本轮自动重登录后无需全量采集。只有当上一轮状态为 logout（数据不完整）时，才需要触发全量恢复采集。

这与 TK 的区别：TK 在采集中途检测到登出，当轮数据不完整，需要即时恢复。Shopee 在采集前就处理了登出，上一轮数据是完整的。

## 六、向后兼容

- 数据库 schema 不变，无需迁移
- 旧数据（TK）的 api_type 不变，通过 `group_name` 判断平台后使用 TK 的 expected types
- Registry 辅助函数默认 `platform='tiktok'`，现有调用方无需改动即可编译通过
- 前端默认显示"全部"平台，不影响现有使用习惯
