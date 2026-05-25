---
paths:
  - "services/live-monitor/utils/TiktokTool.py"
  - "services/live-monitor/utils/ShopeeTool.py"
  - "services/live-monitor/utils/LazadaTool.py"
  - "services/live-monitor/utils/api_response.py"
---

# 爬虫工具返回值契约（live-room-api v2）

## 触发条件

修改 `services/live-monitor/utils/` 下三个爬虫工具（`TiktokTool.py`、`ShopeeTool.py`、`LazadaTool.py`）的返回值，或修改翻译层 `utils/api_response.py` 时。

## 背景

`/liveRoom/portInfo`、`/liveRoom/shopeeInfo`、`/liveRoom/lazadaInfo` 三个接口的响应结构由 `utils/api_response.py` 中的 `classify_xxx_result()` 翻译函数生成。翻译层依赖爬虫工具返回的 **raw dict 字段约定**（`flv_url`、`message`、`uniqueId`、`session`、`filePath` 等）来判定 code（200 / 2001 / 2002 / 4041 / 5001 / 5002 / 5099）。

**接口规范单一权威源**：[`services/live-monitor/docs/specs/live-room-api.md`](../../services/live-monitor/docs/specs/live-room-api.md)

## 规则

### 一、不要随意改动现有返回字段

修改爬虫工具时，必须保留 `classify_xxx_result()` 依赖的字段约定。改前先读 `utils/api_response.py`，确认你要修改的分支不影响分类逻辑。

### 二、三个工具的返回值约定（contract）

#### TikTok（`TiktokTool.getLiveStreamInfo_requests`）

| 场景 | 必备字段 | 翻译为 code |
|------|----------|-------------|
| 直播中 | `flv_url`（非空、非 `"error"`）+ `play_urls` / `startTime` / `secUid` / `uniqueId` / `roomId` / `signature` / `id` / `nickname` / `url` / `filePath` | 200 |
| 未开播但用户存在 | `flv_url=""` + `uniqueId`（及其他用户字段） | 2001 |
| 直播间不存在 | `flv_url=""` + `message` 包含 `"用户信息不存在"` 或 `"直播间不存在"` | 4041 |
| 页面解析失败 | `flv_url=""` + `message` 包含 `"页面解析失败"` | 5002 |
| 上游请求失败 | `flv_url="error"` + `message` 包含 `"请求直播页失败"` 或 `"请求个人页失败"` | 5001 |
| 内部异常 | `flv_url="error"` + `message` 包含 `"tk采集异常"` 或 `"采集内部异常"` | 5099 |

#### Shopee（`ShopeeTool.get_shopee_live_info`）

| 场景 | 必备字段 | 翻译为 code |
|------|----------|-------------|
| 直播中 | dict 含 `flv_url`（非空、非 `"error"`）+ `session` / `play_urls` / `filePath` / `startTime` | 200 |
| 未开播 | dict 含 `session` 或 `filePath`，无有效 `flv_url` | 2001 |
| 采集异常 / 短链解析失败 | 返回 `None` | 5099 |
| 数据不完整 | dict 既无 `flv_url` 也无 `session` / `filePath` | 5002 |

#### Lazada（`LazadaTool.get_lazada_live_info`）

| 场景 | 必备字段 | 翻译为 code |
|------|----------|-------------|
| 直播中 | `flv_url`（非空、非 `"error"`）+ `roomId` / `liveUuid` / `roomStatus` / `title` / `startTime` / `play_urls` / `filePath` / `mediaUserId` / `mediaUserName` | 200 |
| 历史已结束 | `flv_url="error"` + `message="当前暂无直播"` + `mediaUserId` / `mediaUserName` | 2002 |
| 直播间不存在 | `flv_url="error"` + `message` 包含 `"直播间不存在"` | 4041 |
| 解析失败 | `flv_url="error"` + `message` 包含 `"lazada数据为空"` | 5002 |
| 内部异常 | `flv_url="error"` + `message` 包含 `"lazada采集异常"` | 5099 |

### 三、新增错误类型时必须三处同步

引入新错误场景或新增字段时，按顺序修改：

1. **爬虫工具**：明确 raw dict 中的字段（如 `flv_url`、`message` 文案），与现有约定不冲突
2. **翻译层** `utils/api_response.py`：在对应 `classify_xxx_result()` 中新增分支，映射到合适的 code（沿用 `CODE_MESSAGES` / `ErrorReason`，必要时按 spec 业务码字典新增条目）
3. **单测** `tests/test_api_response.py`：新增覆盖该场景的用例
4. **接口规范** `docs/specs/live-room-api.md`：补响应示例与字段说明（单一权威源，外部对接方依赖此文档）

任一环节缺失，都视作未完成。

### 四、`message` 文案是分类依据，不要随意改写

翻译层用子串匹配识别错误类型（如 `"用户信息不存在" in message`）。修改 message 文案前必须先看 `classify_xxx_result()` 中对应的 `if "..." in message:` 分支并同步更新；否则会让原本能命中 4041 的请求悄悄落到 5099 兜底。

### 五、`flv_url` 的三种取值是契约，不是魔法值

| 取值 | 语义 |
|------|------|
| 非空字符串且非 `"error"` | 正在直播，可消费 |
| `""` | TikTok 专用：未开播或用户场景 |
| `"error"` | TikTok / Lazada 专用：错误场景，进一步看 `message` |

**禁止**新增第四种取值（如 `"timeout"`、`"unknown"`），有新错误场景请走"第三条"流程，落到合适的 code。

### 六、不要在工具层吞异常返回兜底空 dict

`classify_xxx_result()` 对 `None` 入参映射为 5099 INTERNAL_ERROR，这是预期行为。爬虫工具内部异常请直接返回 `None`（Shopee 风格）或带 `flv_url="error"` + 明确 `message` 的 dict（TikTok / Lazada 风格），不要返回 `{}` 或 `{"flv_url": ""}` 的空结构，会让翻译层落入"未识别格式"兜底。

## 自检清单

修改完成后，确认：

- [ ] `cd services/live-monitor && python -m pytest tests/test_api_response.py -v` 全部 PASS
- [ ] 新增字段 / 错误场景已在 `docs/specs/live-room-api.md` 同步
- [ ] `message` 文案修改已在 `classify_xxx_result()` 同步
- [ ] 没有引入新的 `flv_url` 取值或在工具层吞异常返回空 dict

## 原因

翻译层 `api_response.py` 通过字段子串匹配识别错误类型，本质上是**爬虫工具与翻译层之间的隐式协议**。这层协议没有类型系统兜底，靠测试和约定来维护。任何一端的偏移都会让接口悄悄输出错误的业务 code，影响调用方的重试与归档判断。

详细业务码、字段说明、调用方判断逻辑见 [`docs/specs/live-room-api.md`](../../services/live-monitor/docs/specs/live-room-api.md)（单一权威源）。
