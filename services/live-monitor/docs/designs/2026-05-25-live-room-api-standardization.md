# 直播间拉流接口响应标准化设计

> 设计日期：2026-05-25
> 适用服务：`services/live-monitor`（HTTP 路由层 + Tool 翻译层）
> 关联接口规范：[`docs/specs/live-room-api.md`](../specs/live-room-api.md)（实施完成后同步重写）

## 背景

`/liveRoom/portInfo` `/liveRoom/shopeeInfo` `/liveRoom/lazadaInfo` 三个接口当前对失败场景的表达存在以下问题：

1. HTTP 永远返回 200、业务 `code` 永远返回 200，调用方无法用状态码判断错误
2. 错误语义全靠 `port_info.flv_url == "error"` 的魔法字符串 + `message` 自然语言区分，散落十余种自由文本（如 `tk采集异常`、`shopee采集异常`、`lazada采集异常`、`直播间不存在`、`当前暂无直播`、`用户信息不存在`、`页面解析失败`、`请求直播页失败: <异常文本>`、`采集内部异常: <异常文本>`、`lazada数据为空`、`采集失败` 等）
3. TikTok 还混着两种错误形态：`flv_url=""`（用户/页面级失败）与 `flv_url="error"`（采集级失败），调用方需要同时判断两种值
4. 异常详情（含上游异常字符串）直接拼到 `message`，存在内部信息泄漏风险
5. 主备节点和未来对外开放都无法基于这套响应做统一的重试 / 告警 / 错误聚合

## 目标

- 业务 `code` 字段严格区分错误类型，调用方 `if code == 200` 即可判断成功，无需再读 `flv_url` 内容
- `port_info` 内**彻底不再**出现 `flv_url == "error"` / `flv_url == ""` 这类魔法值；`flv_url` 仅在直播中场景出现
- 错误形态机器可读：枚举 `code` + 枚举 `error.reason`，`message` 退化为人类可读说明，不参与逻辑判断
- 异常细节（堆栈、上游原始报错）只进服务端日志，不回灌给调用方

## 非目标（本期不做）

- 不改 `main.py` 内部巡检逻辑（`get_room_data` / `getCurrentLiveStreamInfo` 等对 Tool 返回值的旧式消费），保留下次独立 PR 迁移
- 不引入 RFC 7807 / 严格 HTTP 状态码语义（鉴权失败仍然走 HTTP 401，其余错误一律 HTTP 200 + 业务 `code`）
- 不改 Tool 类的爬取逻辑，只在返回边界上做一次"翻译"

## 改动范围（范围 1.5）

| 层 | 改动 | 备注 |
|----|------|------|
| HTTP 路由 (`main.py` 三个端点) | 全量重写返回结构 | 对外契约破坏式升级 |
| Tool 类 (`utils/TiktokTool.py` `utils/ShopeeTool.py` `utils/LazadaTool.py`) | **不动 Tool 类**；翻译逻辑放在新文件 `utils/api_response.py` 的 `classify_xxx_result()` 函数里 | Tool 旧返回 dict 仍保留供 main.py 内部巡检消费 |
| 聚合代理 (`services/live-platform/api/routes.py`) | 同步使用新的响应结构 | 与 live-monitor 保持一致 |
| 文档 (`docs/specs/live-room-api.md`) | 实施完成后整体重写为新规范 | 同时更新根 `docs/specs/PRD-live-platform-v1.0.md` 中相关章节 |
| `main.py` 内部巡检消费点 (`551`, `683`, `687-688`, `753-768`) | **不改** | 留下次独立迁移 |

## 错误码字典

```
2xx — 成功类
  200   正常直播中
        port_info 必含 flv_url（非空字符串）+ play_urls

2xxx — 业务正常但非直播中（不视为错误，调用方拿元数据）
  2001  当前未开播
        用户/店铺存在但不在直播；port_info 含主播档案（uniqueId/nickname/filePath/mediaUserId 等），不含 flv_url
  2002  历史直播已结束
        Lazada roomStatus=History 且无 onlineLiveJumpUrl

4xx / 4xxx — 客户端类
  401   未授权（access-token 不匹配，HTTP 401）
  4001  入参缺失（mateUrl 为空）
  4002  入参格式错误（URL 不属于支持的平台）
  4041  直播间不存在（命中 errorUrl.txt / 用户信息查不到 / Lazada 短链 302）
  4042  短链已失效

5xxx — 服务端 / 上游类
  5001  上游请求失败（HTTP 非 200、超时、网络错误）
  5002  上游响应解析失败（HTML/JSON 结构异常）
  5003  上游限流或风控（识别到验证码/封禁，预留，目前无识别逻辑可先不发，但码位占住）
  5099  采集内部异常（兜底，未分类异常）
```

> 错误码命名规则：`4xxx` 表示"调用方/资源问题，重试无意义"；`5xxx` 表示"服务端/上游问题，可重试"。调用方可据此实现统一重试策略。

## 标准响应结构

### 成功（`code=200` 或 `2xxx`）

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "mateUrl": "<原始链接>",
    "port_info": { /* 平台数据，无 flv_url='error' 这种魔法值 */ }
  }
}
```

### 失败（`code` 为 `4xxx` / `5xxx`）

```json
{
  "code": 5002,
  "message": "上游响应解析失败",
  "data": {
    "mateUrl": "<原始链接>",
    "port_info": null
  },
  "error": {
    "platform": "tiktok",
    "reason": "PARSE_FAILED",
    "detail": "SIGI_STATE 提取失败"
  }
}
```

### 鉴权失败（HTTP 401，例外）

```json
{ "code": 401, "message": "Unauthorized" }
```

### 字段约束

| 字段 | 类型 | 何时出现 | 说明 |
|------|------|----------|------|
| `code` | int | 始终 | 业务码，2xx 成功，4xxx/5xxx 错误 |
| `message` | str | 始终 | 人类可读说明，**不参与逻辑判断**；失败时是错误码标准描述 |
| `data.mateUrl` | str | 始终 | 原始请求链接（鉴权失败除外） |
| `data.port_info` | object \| null | 成功为 object；失败一律 `null` | 不再出现 `flv_url='error'` 之类魔法值 |
| `error.platform` | str | 失败时 | `tiktok` \| `shopee` \| `lazada` |
| `error.reason` | str | 失败时 | 机器可读枚举（见下） |
| `error.detail` | str | 失败时 | 简要原因摘要，**禁止**包含异常堆栈或上游原始 HTML/JSON 片段 |

### `error.reason` 枚举

```
INVALID_PARAM         入参缺失或格式错误（对应 4001/4002）
ROOM_NOT_FOUND        直播间不存在（4041）
SHORT_URL_EXPIRED     短链失效（4042）
UPSTREAM_REQUEST_FAILED   上游请求失败（5001）
PARSE_FAILED          上游响应解析失败（5002）
RATE_LIMITED          上游限流/风控（5003）
INTERNAL_ERROR        采集内部异常（5099）
```

## 三平台错误场景映射

### TikTok（`utils/TiktokTool.py`）

| 现有返回（dict 关键字段） | 来源 | 新 code | error.reason |
|--------------------------|------|---------|--------------|
| `flv_url=<url>` 且 `liveRoom.status==2` | `parse_json_data` 直播中分支 | `200` | — |
| `flv_url=""`, `message="页面解析失败"` | `_parse_user_detail` json_data 为空 | `5002` | `PARSE_FAILED` |
| `flv_url=""`, `message="用户信息不存在"` | `_parse_user_detail` 无 userInfo | `4041` | `ROOM_NOT_FOUND` |
| `flv_url=""` 且其它字段齐（用户存在、未开播） | `_parse_user_detail` 正常分支 | `2001` | — |
| `flv_url="error"`, `message="请求直播页失败: <err>"` | `_make_error` HTTP 失败 | `5001` | `UPSTREAM_REQUEST_FAILED` |
| `flv_url="error"`, `message="请求个人页失败: <err>"` | `_make_error` HTTP 失败 | `5001` | `UPSTREAM_REQUEST_FAILED` |
| `flv_url="error"`, `message="采集内部异常: <err>"` | `_make_error` 异常兜底 | `5099` | `INTERNAL_ERROR` |
| `flv_url="error"`, `message="tk采集异常"` | `getLiveStreamInfo_requests` 外层捕获 | `5099` | `INTERNAL_ERROR` |
| `parse_json_data` 中 `port_info["flv_url"]="error"`（streamData 解析失败）| `parse_json_data` except 分支 | `5002` | `PARSE_FAILED` |
| `parse_json_data` 中 `port_info["flv_url"]=""`（status≠2 或 flv 为空） | `parse_json_data` 正常分支 | `2001` | — |
| `flv_url=""`, `message="直播间不存在"` | `parse_json_data` else 分支 | `4041` | `ROOM_NOT_FOUND` |
| 命中 `errorUrl.txt`（main.py 路由层判断） | 路由层 | `4041` | `ROOM_NOT_FOUND` |

### Shopee（`utils/ShopeeTool.py`）

| 现有返回 | 来源 | 新 code | error.reason |
|----------|------|---------|--------------|
| 包含 `flv_url=<url>` 的 dict | `_format_live_data` 正常分支 | `200` | — |
| `None`（`get_shopee_live_url` 返回 None） | session_url 为空 | `4041` | `ROOM_NOT_FOUND` |
| `None`（`_format_live_data` 中 `play_url` 缺失） | data.session.play_url 为空 | `2001` | — |
| 异常被 `except` 吞掉 → `None` | `get_shopee_live_info` 兜底 | `5099` | `INTERNAL_ERROR` |
| `_make_request` 抛异常 → 路由层 except | main.py 兜底 | `5001`/`5099` | 视异常类型 |
| 命中 `errorUrl.txt` | 路由层 | `4041` | `ROOM_NOT_FOUND` |

> Shopee 现状是 `None` 一把抓所有错误。`_classify_result()` 需要按 Tool 内部状态进一步细分（建议新增一个轻量异常类 `ShopeeFetchError(reason, detail)`，让 Tool 在不同失败点抛不同 reason，路由层 catch 后映射 code）。

### Lazada（`utils/LazadaTool.py`）

| 现有返回 | 来源 | 新 code | error.reason |
|----------|------|---------|--------------|
| 含 `flv_url=<url>`、`roomId`、`play_urls` | `_format_live_data` 正常分支 | `200` | — |
| `flv_url='error', message='直播间不存在'` | `get_lazada_live_url` 302 | `4041` | `ROOM_NOT_FOUND` |
| `flv_url='error', message='当前暂无直播'` | `get_lazada_live_info` History 分支 | `2002` | — |
| `flv_url='error', message='lazada数据为空'` | `_format_live_data` data 为空 | `5002` | `PARSE_FAILED` |
| `flv_url='error', message='lazada采集异常'` | 路由层 except | `5099` | `INTERNAL_ERROR` |
| `_make_request` 抛 `ValueError` | HTTP 非 200 | `5001` | `UPSTREAM_REQUEST_FAILED` |

## 翻译层 `_classify_result()`

在 `utils/api_response.py` 中新增独立函数（不挂在 Tool 类上，避免污染 Tool 内部职责），输入 Tool 现有返回 dict / None / 异常，输出统一结构：

```python
@dataclass
class ApiOutcome:
    code: int                    # 业务码
    port_info: dict | None       # 成功时为清洗后 port_info；失败为 None
    error_reason: str | None     # 失败时的 reason 枚举；成功为 None
    error_detail: str | None     # 失败时的简要摘要；成功为 None

# 示例签名
def classify_tiktok_result(raw: dict | None, mate_url: str) -> ApiOutcome: ...
def classify_shopee_result(raw: dict | None, mate_url: str) -> ApiOutcome: ...
def classify_lazada_result(raw: dict | None, mate_url: str) -> ApiOutcome: ...
```

清洗规则：
- 从 `raw` 中**移除** `flv_url`（若值为 `"error"` 或空字符串）和内部错误 `message`
- **移除**空字符串占位字段（`roomId=""`、`filePath=""` 等），让 JSON 紧凑、调用方用 `key in port_info` 判断字段存在
- 仅在 `code=200` 时保留 `flv_url` 和 `play_urls`；其它成功 code（2001/2002）下 `port_info` 不含这两个字段

路由层使用：

```python
outcome = classify_tiktok_result(raw, mate_url)
if outcome.code == 200 or 2000 <= outcome.code < 3000:
    return success_response(outcome.code, outcome.port_info, mate_url)
return error_response(outcome.code, outcome.error_reason, outcome.error_detail,
                     platform="tiktok", mate_url=mate_url)
```

## 路由层骨架

新增公共 helper 集中包装响应：

```python
# main.py 顶部或抽到 utils/api_response.py
CODE_MESSAGES = {
    200:  "success",
    2001: "当前未开播",
    2002: "历史直播已结束",
    401:  "Unauthorized",
    4001: "入参缺失",
    4002: "入参格式错误",
    4041: "直播间不存在",
    4042: "短链已失效",
    5001: "上游请求失败",
    5002: "上游响应解析失败",
    5003: "上游限流或风控",
    5099: "采集内部异常",
}

def success_response(code: int, port_info: dict | None, mate_url: str) -> dict:
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": port_info},
    }

def error_response(code: int, reason: str, detail: str,
                   platform: str, mate_url: str) -> dict:
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": None},
        "error": {"platform": platform, "reason": reason, "detail": detail},
    }
```

`detail` 写入前必须**截断**异常文本（建议最长 200 字符）并去除堆栈片段，避免泄漏内部信息。

## 聚合代理同步改造

`services/live-platform/api/routes.py:32` 当前直接返回旧 envelope：

```python
if info is None:
    info = {"flv_url": "error", "roomId": "", "message": f"{platform}采集异常", "filePath": ""}
return {"code": 200, "message": "success", "data": {"port_info": info, "mateUrl": request.mateUrl}}
```

改为调用同样的翻译层 + 包装函数，输出与 live-monitor 一致的新结构。`adapters.get_stream_info()` 内部如果是各 Tool 调用，需要把同样的 `classify_*_result()` 串进去。

## 不变项（保持原样）

- 端点路径、HTTP 方法、请求体结构、`access-token` 鉴权
- Tool 类爬取逻辑、重试策略、cookie 管理
- 成功响应里 `port_info` 内部的字段命名（`flv_url`、`play_urls`、`roomId`、`startTime`、`filePath`、TikTok 特有 `secUid/uniqueId/...`、Shopee `session`、Lazada `liveUuid/roomStatus/...`）

## 实施顺序

1. 新增 `utils/api_response.py`：`CODE_MESSAGES`、`success_response`、`error_response`、`ApiOutcome` dataclass
2. 各 Tool 新增 `_classify_result()`（或独立 `classify_xxx_result()` 函数），覆盖该平台所有现有返回路径
3. 改 `main.py` 三个路由处理函数，全量切换到新响应结构；同时把 `errorUrl.txt` 命中检查从 Tool 抽到路由层（保持单点判定）
4. 改 `services/live-platform/api/routes.py` 与 `adapters.get_stream_info` 链路
5. 写 pytest 单测覆盖：每个 code 至少一条用例（用 mock 注入 Tool 原始返回 → 断言新响应结构）
6. 重写 `docs/specs/live-room-api.md`、更新 `docs/specs/PRD-live-platform-v1.0.md` 相关段落
7. 更新 `docs/specs/example_data/` 中的样例 JSON（TiktokLive.json / ShopeeLive.json / LazadaLive.json 维持，新增几份失败场景样例）

## 验证

- 单测：每个 `error.reason` 至少一条用例
- 联调：本地分别造三种用例（直播中 / 未开播 / 失效短链）跑一遍三个端点，比对响应结构
- 主备节点同步：升级一个节点先观察，再升级另一个；调用方仅 live-platform 聚合代理，已同步改造无需停机

## 风险与回滚

- **风险**：调用方还有未识别的旧契约依赖（`flv_url='error'` 判断）。grep 已覆盖本仓库与 `services/live-stream`，但其它仓库未必。
- **缓解**：发布前在主备的另一个仓库（如 `livelab/`）再 grep 一次；上线第一周保留上一版本镜像可快速回滚。
- **回滚**：本期改动集中在路由层 + Tool 翻译层，回滚只需还原 `main.py`、`utils/*.py` 中的 `classify_*_result()` 引入和路由处理函数；Tool 内部爬取逻辑未动，回滚无副作用。
