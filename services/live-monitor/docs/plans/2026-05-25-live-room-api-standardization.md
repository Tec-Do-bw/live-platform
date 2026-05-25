# 直播间拉流接口响应标准化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 标准化 `/liveRoom/portInfo` `/liveRoom/shopeeInfo` `/liveRoom/lazadaInfo` 三个接口的响应格式，用业务 code 区分错误类型，移除 flv_url 魔法值，引入机器可读的 error 对象。

**Architecture:** 在 HTTP 路由层和 Tool 返回值之间插入翻译层（`utils/api_response.py`），将 Tool 现有的 dict/None 返回值映射为标准化的 ApiOutcome 结构；路由层使用 success_response/error_response 包装函数输出统一格式。Tool 类内部爬取逻辑不动，main.py 内部巡检逻辑保持旧消费方式。

**Tech Stack:** Python 3.12, FastAPI, pytest, dataclasses

---

## 文件结构

**新增文件：**
- `utils/api_response.py` — 翻译层核心：ApiOutcome dataclass、classify_xxx_result() 函数、success_response/error_response 包装函数、CODE_MESSAGES 字典

**修改文件：**
- `main.py:354-393` — `/liveRoom/portInfo` 路由处理函数
- `main.py:397-429` — `/liveRoom/shopeeInfo` 路由处理函数
- `main.py:433-463` — `/liveRoom/lazadaInfo` 路由处理函数
- `services/live-platform/api/routes.py:26-33` — `_platform_response` 函数

**测试文件：**
- `tests/test_api_response.py` — 翻译层单测（classify_xxx_result 覆盖所有 code）
- `tests/test_routes.py` — 路由层集成测试（mock Tool 返回 → 断言响应结构）

---

### Task 1: 创建翻译层基础结构

**Files:**
- Create: `utils/api_response.py`

- [ ] **Step 1: 创建 ApiOutcome dataclass 和常量**

```python
"""API 响应翻译层：将 Tool 返回值映射为标准化响应结构"""
from dataclasses import dataclass

@dataclass
class ApiOutcome:
    """Tool 返回值翻译后的统一结构"""
    code: int                    # 业务码（200/2001/2002/4xxx/5xxx）
    port_info: dict | None       # 成功时为清洗后 port_info；失败为 None
    error_reason: str | None     # 失败时的 reason 枚举；成功为 None
    error_detail: str | None     # 失败时的简要摘要；成功为 None


# 业务码与人类可读消息映射
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


# error.reason 枚举常量
class ErrorReason:
    INVALID_PARAM = "INVALID_PARAM"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    SHORT_URL_EXPIRED = "SHORT_URL_EXPIRED"
    UPSTREAM_REQUEST_FAILED = "UPSTREAM_REQUEST_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
```

- [ ] **Step 2: 创建响应包装函数**

```python
def success_response(code: int, port_info: dict | None, mate_url: str) -> dict:
    """成功响应包装（code=200 或 2xxx）"""
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": port_info},
    }


def error_response(
    code: int, reason: str, detail: str, platform: str, mate_url: str
) -> dict:
    """失败响应包装（code=4xxx 或 5xxx）"""
    # 截断 detail 避免泄漏内部信息
    safe_detail = detail[:200] if detail else ""
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": None},
        "error": {"platform": platform, "reason": reason, "detail": safe_detail},
    }
```

- [ ] **Step 3: 提交基础结构**

```bash
git add utils/api_response.py
git commit -m "feat(api): 新增响应翻译层基础结构

- ApiOutcome dataclass
- CODE_MESSAGES 业务码字典
- ErrorReason 枚举常量
- success_response/error_response 包装函数"
```

---

### Task 2: 实现 TikTok 翻译函数

**Files:**
- Modify: `utils/api_response.py`

- [ ] **Step 1: 添加 classify_tiktok_result 函数**

```python
def classify_tiktok_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 TikTok Tool 返回值翻译为 ApiOutcome
    
    Args:
        raw: TiktokTool.getLiveStreamInfo_requests() 返回值
        mate_url: 原始请求链接
        
    Returns:
        ApiOutcome 统一结构
    """
    if raw is None:
        return ApiOutcome(
            code=5099,
            port_info=None,
            error_reason=ErrorReason.INTERNAL_ERROR,
            error_detail="Tool 返回 None"
        )
    
    # 提取关键字段
    flv_url = raw.get("flv_url", "")
    message = raw.get("message", "")
    
    # 场景 1: flv_url 是有效 URL（直播中）
    if flv_url and flv_url not in ("", "error"):
        # 清洗：移除内部 message 字段
        clean_info = {k: v for k, v in raw.items() if k != "message"}
        return ApiOutcome(code=200, port_info=clean_info, error_reason=None, error_detail=None)
    
    # 场景 2: flv_url="" 且有用户信息（未开播）
    if flv_url == "" and raw.get("uniqueId"):
        # 清洗：移除 flv_url、message、空字符串字段
        clean_info = {
            k: v for k, v in raw.items()
            if k not in ("flv_url", "message") and v != ""
        }
        return ApiOutcome(code=2001, port_info=clean_info, error_reason=None, error_detail=None)
    
    # 场景 3: flv_url="" 且 message 指示错误
    if flv_url == "":
        if "页面解析失败" in message:
            return ApiOutcome(
                code=5002, port_info=None,
                error_reason=ErrorReason.PARSE_FAILED, error_detail=message
            )
        if "用户信息不存在" in message or "直播间不存在" in message:
            return ApiOutcome(
                code=4041, port_info=None,
                error_reason=ErrorReason.ROOM_NOT_FOUND, error_detail=message
            )
    
    # 场景 4: flv_url="error"
    if flv_url == "error":
        if "请求直播页失败" in message or "请求个人页失败" in message:
            return ApiOutcome(
                code=5001, port_info=None,
                error_reason=ErrorReason.UPSTREAM_REQUEST_FAILED, error_detail=message
            )
        if "采集内部异常" in message or "tk采集异常" in message:
            return ApiOutcome(
                code=5099, port_info=None,
                error_reason=ErrorReason.INTERNAL_ERROR, error_detail=message
            )
        # streamData 解析失败
        return ApiOutcome(
            code=5002, port_info=None,
            error_reason=ErrorReason.PARSE_FAILED, error_detail=message or "解析失败"
        )
    
    # 兜底
    return ApiOutcome(
        code=5099, port_info=None,
        error_reason=ErrorReason.INTERNAL_ERROR, error_detail=f"未识别的返回格式: {raw}"
    )
```

- [ ] **Step 2: 提交 TikTok 翻译函数**

```bash
git add utils/api_response.py
git commit -m "feat(api): 实现 TikTok 翻译函数 classify_tiktok_result

覆盖场景：
- 直播中 (code=200)
- 未开播 (code=2001)
- 直播间不存在 (code=4041)
- 上游请求失败 (code=5001)
- 解析失败 (code=5002)
- 内部异常 (code=5099)"
```

---

### Task 3: 实现 Shopee 翻译函数

**Files:**
- Modify: `utils/api_response.py`

- [ ] **Step 1: 添加 classify_shopee_result 函数**

```python
def classify_shopee_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 Shopee Tool 返回值翻译为 ApiOutcome
    
    Args:
        raw: ShopeeTool.get_shopee_live_info() 返回值
        mate_url: 原始请求链接
        
    Returns:
        ApiOutcome 统一结构
    """
    # Shopee Tool 返回 None 表示失败（多种原因）
    if raw is None:
        # 无法区分具体原因，统一归为内部异常
        return ApiOutcome(
            code=5099,
            port_info=None,
            error_reason=ErrorReason.INTERNAL_ERROR,
            error_detail="Shopee 采集失败"
        )
    
    # 有返回值：检查是否有 flv_url
    flv_url = raw.get("flv_url", "")
    
    # 场景 1: 有 flv_url（直播中）
    if flv_url and flv_url not in ("", "error"):
        return ApiOutcome(code=200, port_info=raw, error_reason=None, error_detail=None)
    
    # 场景 2: 无 flv_url 但有 session/filePath（未开播）
    if raw.get("session") or raw.get("filePath"):
        # 清洗：移除 flv_url、play_urls、startTime
        clean_info = {
            k: v for k, v in raw.items()
            if k not in ("flv_url", "play_urls", "startTime") and v != ""
        }
        return ApiOutcome(code=2001, port_info=clean_info, error_reason=None, error_detail=None)
    
    # 兜底：数据不完整
    return ApiOutcome(
        code=5002,
        port_info=None,
        error_reason=ErrorReason.PARSE_FAILED,
        error_detail="Shopee 数据不完整"
    )
```

- [ ] **Step 2: 提交 Shopee 翻译函数**

```bash
git add utils/api_response.py
git commit -m "feat(api): 实现 Shopee 翻译函数 classify_shopee_result

覆盖场景：
- 直播中 (code=200)
- 未开播 (code=2001)
- 采集失败 (code=5099)
- 数据不完整 (code=5002)"
```

---

### Task 4: 实现 Lazada 翻译函数

**Files:**
- Modify: `utils/api_response.py`

- [ ] **Step 1: 添加 classify_lazada_result 函数**

```python
def classify_lazada_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 Lazada Tool 返回值翻译为 ApiOutcome
    
    Args:
        raw: LazadaTool.get_lazada_live_info() 返回值
        mate_url: 原始请求链接
        
    Returns:
        ApiOutcome 统一结构
    """
    if raw is None:
        return ApiOutcome(
            code=5099,
            port_info=None,
            error_reason=ErrorReason.INTERNAL_ERROR,
            error_detail="Tool 返回 None"
        )
    
    flv_url = raw.get("flv_url", "")
    message = raw.get("message", "")
    
    # 场景 1: 有效 flv_url（直播中）
    if flv_url and flv_url not in ("", "error"):
        # 清洗：移除内部 message 字段
        clean_info = {k: v for k, v in raw.items() if k != "message"}
        return ApiOutcome(code=200, port_info=clean_info, error_reason=None, error_detail=None)
    
    # 场景 2: flv_url="error" 且有 message
    if flv_url == "error":
        if "直播间不存在" in message:
            return ApiOutcome(
                code=4041, port_info=None,
                error_reason=ErrorReason.ROOM_NOT_FOUND, error_detail=message
            )
        if "当前暂无直播" in message:
            # 历史直播已结束，但保留用户信息
            clean_info = {
                k: v for k, v in raw.items()
                if k not in ("flv_url", "message", "play_urls", "startTime", "liveUuid", "roomStatus", "title") and v != ""
            }
            return ApiOutcome(code=2002, port_info=clean_info, error_reason=None, error_detail=None)
        if "lazada数据为空" in message:
            return ApiOutcome(
                code=5002, port_info=None,
                error_reason=ErrorReason.PARSE_FAILED, error_detail=message
            )
        if "lazada采集异常" in message:
            return ApiOutcome(
                code=5099, port_info=None,
                error_reason=ErrorReason.INTERNAL_ERROR, error_detail=message
            )
    
    # 兜底
    return ApiOutcome(
        code=5099, port_info=None,
        error_reason=ErrorReason.INTERNAL_ERROR, error_detail=f"未识别的返回格式: {raw}"
    )
```

- [ ] **Step 2: 提交 Lazada 翻译函数**

```bash
git add utils/api_response.py
git commit -m "feat(api): 实现 Lazada 翻译函数 classify_lazada_result

覆盖场景：
- 直播中 (code=200)
- 历史直播已结束 (code=2002)
- 直播间不存在 (code=4041)
- 解析失败 (code=5002)
- 内部异常 (code=5099)"
```

---

### Task 5: 改造 main.py 路由层

**Files:**
- Modify: `main.py:354-463`

> **重要**：main.py 内部巡检逻辑（551/683/687/753 行）**不改**，只改三个 HTTP 路由处理函数。

- [ ] **Step 1: 在 main.py 顶部添加 import**

在 main.py 现有 import 区域添加：

```python
from utils.api_response import (
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
)
```

- [ ] **Step 2: 新增 errorUrl 检查辅助函数**

在 `get_error_room_url()` 函数附近添加：

```python
def _check_error_url(mate_url: str, platform: str) -> dict | None:
    """检查 URL 是否在已知错误列表中，命中则返回标准错误响应"""
    try:
        error_urls = get_error_room_url()
        if mate_url in error_urls:
            return error_response(
                code=4041,
                reason=ErrorReason.ROOM_NOT_FOUND,
                detail="命中已知错误链接列表",
                platform=platform,
                mate_url=mate_url,
            )
    except FileNotFoundError:
        pass
    return None
```

- [ ] **Step 3: 重写 /liveRoom/portInfo 路由**

替换 main.py 中 `@app.post("/liveRoom/portInfo")` 整个函数体：

```python
@app.post("/liveRoom/portInfo")
async def portInfo(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="tiktok", mate_url=""
        ))

    # errorUrl 检查
    err_resp = _check_error_url(mateUrl, "tiktok")
    if err_resp:
        return JSONResponse(content=err_resp)

    # 调用 Tool（保持原有逻辑不变）
    cookie_list = tiktokTool.get_cookie_list()
    tiktok_no_proxy = TiktokTool(ipList)
    raw = tiktok_no_proxy.getLiveStreamInfo_requests(mateUrl, cookie_list, OP)

    # 翻译为标准响应
    outcome = classify_tiktok_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="tiktok", mate_url=mateUrl
    ))
```

- [ ] **Step 4: 重写 /liveRoom/shopeeInfo 路由**

替换 main.py 中 `@app.post("/liveRoom/shopeeInfo")` 整个函数体：

```python
@app.post("/liveRoom/shopeeInfo")
async def get_shopee_live_info(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="shopee", mate_url=""
        ))

    logger.info(f"接收到Shopee直播间请求 | url={mateUrl}")

    # errorUrl 检查
    err_resp = _check_error_url(mateUrl, "shopee")
    if err_resp:
        return JSONResponse(content=err_resp)

    # 调用 Tool
    try:
        raw = shopeeTool.get_shopee_live_info(mateUrl, proxy=False)
        logger.info(f"成功获取Shopee直播间信息 | url={mateUrl}")
    except Exception as e:
        logger.error(f"获取Shopee直播间失败 | url={mateUrl} error={e}", exc_info=True)
        raw = None

    # 翻译为标准响应
    outcome = classify_shopee_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="shopee", mate_url=mateUrl
    ))
```

- [ ] **Step 5: 重写 /liveRoom/lazadaInfo 路由**

替换 main.py 中 `@app.post("/liveRoom/lazadaInfo")` 整个函数体：

```python
@app.post("/liveRoom/lazadaInfo")
async def get_lazadalive_info(request: Request):
    headers = request.headers
    body = await request.json()

    access_token = headers.get('access-token')
    if access_token != 'AFDD0B4AD2EC172C586E2150770FBF9E':
        return JSONResponse(content={'code': 401, 'message': 'Unauthorized'}, status_code=401)

    mateUrl = body.get('mateUrl')
    if not mateUrl:
        return JSONResponse(content=error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform="lazada", mate_url=""
        ))

    logger.info(f"接收到lazada直播间请求 | url={mateUrl}")

    # 调用 Tool
    try:
        raw = lazadaTool.get_lazada_live_info(mateUrl, proxy=False)
        logger.info(f"成功获取lazada直播间信息 | url={mateUrl}")
    except Exception as e:
        logger.error(f"获取lazada直播间失败 | url={mateUrl} error={e}", exc_info=True)
        raw = None

    # 翻译为标准响应
    outcome = classify_lazada_result(raw, mateUrl)
    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return JSONResponse(content=success_response(outcome.code, outcome.port_info, mateUrl))
    return JSONResponse(content=error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform="lazada", mate_url=mateUrl
    ))
```

- [ ] **Step 6: 提交路由层改造**

```bash
git add main.py
git commit -m "feat(api): 重写三个拉流接口路由，使用标准化响应结构

- /liveRoom/portInfo: TikTok 接口标准化
- /liveRoom/shopeeInfo: Shopee 接口标准化
- /liveRoom/lazadaInfo: Lazada 接口标准化
- 新增 _check_error_url 辅助函数
- 新增 mateUrl 空值校验 (code=4001)
- 内部巡检逻辑保持不变"
```

---

### Task 6: 单元测试

**Files:**
- Create: `tests/test_api_response.py`

- [ ] **Step 1: 创建测试文件，测试 TikTok 翻译函数**

```python
"""utils/api_response.py 翻译层单测"""
import pytest
from utils.api_response import (
    ApiOutcome,
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
    CODE_MESSAGES,
)


class TestClassifyTiktokResult:
    """TikTok 翻译函数测试"""

    def test_live_streaming(self):
        """直播中 → code=200"""
        raw = {
            "flv_url": "https://pull-flv.example.com/live.flv",
            "play_urls": ["https://pull-flv.example.com/live.flv"],
            "startTime": "1756642228",
            "secUid": "MS4wLjABAAAA",
            "uniqueId": "testuser",
            "roomId": "123456",
            "signature": "sig",
            "id": "789",
            "nickname": "Test User",
            "url": "https://www.tiktok.com/@testuser/live",
            "filePath": "testuser",
        }
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@testuser/live")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "https://pull-flv.example.com/live.flv"
        assert outcome.error_reason is None

    def test_offline_with_user_info(self):
        """用户存在但未开播 → code=2001"""
        raw = {
            "flv_url": "",
            "startTime": "",
            "secUid": "MS4wLjABAAAA",
            "uniqueId": "testuser",
            "roomId": "123456",
            "signature": "sig",
            "id": "789",
            "nickname": "Test User",
            "url": "https://www.tiktok.com/@testuser/live",
            "filePath": "testuser",
        }
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@testuser/live")
        assert outcome.code == 2001
        assert "flv_url" not in outcome.port_info
        assert outcome.port_info["uniqueId"] == "testuser"

    def test_room_not_found(self):
        """用户信息不存在 → code=4041"""
        raw = {"flv_url": "", "roomId": "", "message": "用户信息不存在", "url": "..."}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@bad/live")
        assert outcome.code == 4041
        assert outcome.error_reason == ErrorReason.ROOM_NOT_FOUND
        assert outcome.port_info is None

    def test_upstream_request_failed(self):
        """请求直播页失败 → code=5001"""
        raw = {"flv_url": "error", "roomId": "", "message": "请求直播页失败: timeout", "filePath": ""}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5001
        assert outcome.error_reason == ErrorReason.UPSTREAM_REQUEST_FAILED

    def test_parse_failed(self):
        """页面解析失败 → code=5002"""
        raw = {"flv_url": "", "roomId": "", "message": "页面解析失败", "url": "..."}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5002
        assert outcome.error_reason == ErrorReason.PARSE_FAILED

    def test_internal_error(self):
        """tk采集异常 → code=5099"""
        raw = {"flv_url": "error", "roomId": "", "message": "tk采集异常", "filePath": ""}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5099
        assert outcome.error_reason == ErrorReason.INTERNAL_ERROR

    def test_none_input(self):
        """Tool 返回 None → code=5099"""
        outcome = classify_tiktok_result(None, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5099
```

- [ ] **Step 2: 添加 Shopee 翻译函数测试**

```python
class TestClassifyShopeeResult:
    """Shopee 翻译函数测试"""

    def test_live_streaming(self):
        """直播中 → code=200"""
        raw = {
            "session": {"uid": 123, "username": "shop1"},
            "play_urls": ["https://play.shopee.com/live.flv"],
            "flv_url": "https://play.shopee.com/live.flv",
            "filePath": "shop1",
            "startTime": 1765530323368,
        }
        outcome = classify_shopee_result(raw, "https://my.shp.ee/xxx")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "https://play.shopee.com/live.flv"

    def test_offline(self):
        """有 session 但无 flv_url → code=2001"""
        raw = {
            "session": {"uid": 123, "username": "shop1"},
            "filePath": "shop1",
        }
        outcome = classify_shopee_result(raw, "https://my.shp.ee/xxx")
        assert outcome.code == 2001
        assert "flv_url" not in outcome.port_info

    def test_none_input(self):
        """Tool 返回 None → code=5099"""
        outcome = classify_shopee_result(None, "https://my.shp.ee/xxx")
        assert outcome.code == 5099
        assert outcome.error_reason == ErrorReason.INTERNAL_ERROR
```

- [ ] **Step 3: 添加 Lazada 翻译函数测试**

```python
class TestClassifyLazadaResult:
    """Lazada 翻译函数测试"""

    def test_live_streaming(self):
        """直播中 → code=200"""
        raw = {
            "roomId": "10026286",
            "liveUuid": "7aca9015-f670-4fcd-aead-f02c3f7c8ad1",
            "roomStatus": "Online",
            "title": "SALE",
            "startTime": 1765516431000,
            "play_urls": ["http://pull-live.lazcdn.com/live.flv"],
            "flv_url": "http://pull-live.lazcdn.com/live.flv",
            "filePath": "teamfulove",
            "mediaUserId": "300680704072",
            "mediaUserName": "teamfulove",
        }
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "http://pull-live.lazcdn.com/live.flv"

    def test_room_not_found(self):
        """直播间不存在 → code=4041"""
        raw = {"flv_url": "error", "roomId": "", "message": "直播间不存在", "filePath": ""}
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 4041
        assert outcome.error_reason == ErrorReason.ROOM_NOT_FOUND

    def test_history_ended(self):
        """当前暂无直播 → code=2002"""
        raw = {
            "flv_url": "error",
            "roomId": "10026286",
            "message": "当前暂无直播",
            "filePath": "",
            "mediaUserId": "300680704072",
            "mediaUserName": "teamfulove",
        }
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 2002
        assert outcome.port_info["mediaUserId"] == "300680704072"
        assert "flv_url" not in outcome.port_info

    def test_parse_failed(self):
        """lazada数据为空 → code=5002"""
        raw = {"flv_url": "error", "roomId": "", "message": "lazada数据为空", "filePath": ""}
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 5002
        assert outcome.error_reason == ErrorReason.PARSE_FAILED
```

- [ ] **Step 4: 添加响应包装函数测试**

```python
class TestResponseHelpers:
    """success_response / error_response 包装函数测试"""

    def test_success_response_structure(self):
        resp = success_response(200, {"flv_url": "http://x.flv"}, "https://tiktok.com/@x/live")
        assert resp["code"] == 200
        assert resp["message"] == "success"
        assert resp["data"]["mateUrl"] == "https://tiktok.com/@x/live"
        assert resp["data"]["port_info"]["flv_url"] == "http://x.flv"
        assert "error" not in resp

    def test_error_response_structure(self):
        resp = error_response(4041, "ROOM_NOT_FOUND", "用户不存在", "tiktok", "https://tiktok.com/@x/live")
        assert resp["code"] == 4041
        assert resp["message"] == "直播间不存在"
        assert resp["data"]["port_info"] is None
        assert resp["error"]["platform"] == "tiktok"
        assert resp["error"]["reason"] == "ROOM_NOT_FOUND"
        assert resp["error"]["detail"] == "用户不存在"

    def test_error_detail_truncation(self):
        """detail 超过 200 字符时截断"""
        long_detail = "x" * 500
        resp = error_response(5099, "INTERNAL_ERROR", long_detail, "tiktok", "url")
        assert len(resp["error"]["detail"]) == 200
```

- [ ] **Step 5: 运行测试**

```bash
cd D:\SpiderCode\VAT\patrick_star\live-platform\services\live-monitor
python -m pytest tests/test_api_response.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: 提交测试**

```bash
git add tests/test_api_response.py
git commit -m "test(api): 翻译层单测覆盖所有 code 场景

- TikTok: 7 条用例 (200/2001/4041/5001/5002/5099/None)
- Shopee: 3 条用例 (200/2001/5099)
- Lazada: 4 条用例 (200/2002/4041/5002)
- 响应包装: 3 条用例 (结构/截断)"
```

---

### Task 7: 改造聚合代理

**Files:**
- Modify: `services/live-platform/api/routes.py`

- [ ] **Step 1: 重写 _platform_response 函数**

```python
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from adapters import get_stream_info
from orchestrator.state_machine import state_manager
from shared.config import settings

# 复用 live-monitor 的翻译层（路径需按实际部署调整）
import sys
sys.path.insert(0, str(settings.live_monitor_path)) if hasattr(settings, 'live_monitor_path') else None
from utils.api_response import (
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
)

router = APIRouter()

PLATFORM_CLASSIFIERS = {
    "tiktok": classify_tiktok_result,
    "shopee": classify_shopee_result,
    "lazada": classify_lazada_result,
}


class LiveRoomRequest(BaseModel):
    mateUrl: str


def _unauthorized(access_token: Optional[str]) -> Optional[dict]:
    if access_token != settings.server.access_token:
        return {"code": 401, "message": "Unauthorized"}
    return None


async def _platform_response(platform: str, request: LiveRoomRequest, access_token: Optional[str]) -> dict:
    auth_error = _unauthorized(access_token)
    if auth_error:
        return auth_error

    mate_url = request.mateUrl
    if not mate_url:
        return error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform=platform, mate_url=""
        )

    raw = await get_stream_info(platform, mate_url)

    classifier = PLATFORM_CLASSIFIERS[platform]
    outcome = classifier(raw, mate_url)

    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return success_response(outcome.code, outcome.port_info, mate_url)
    return error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform=platform, mate_url=mate_url
    )
```

- [ ] **Step 2: 提交聚合代理改造**

```bash
git add services/live-platform/api/routes.py
git commit -m "feat(live-platform): 聚合代理同步使用标准化响应结构

- _platform_response 使用 classify_xxx_result 翻译层
- 移除旧的 flv_url='error' 兜底逻辑
- 与 live-monitor 输出格式完全一致"
```

---

### Task 8: 最终验证与文档同步

**Files:**
- Verify: 手动联调三个端点
- Already done: `docs/specs/live-room-api.md`（已在 brainstorming 阶段重写为 v2）

- [ ] **Step 1: 本地启动服务验证**

```bash
cd D:\SpiderCode\VAT\patrick_star\live-platform\services\live-monitor
python main.py
```

- [ ] **Step 2: 验证 TikTok 接口（失效链接 → code=4041）**

```bash
curl -X POST http://localhost:8080/liveRoom/portInfo \
  -H "Content-Type: application/json" \
  -H "access-token: AFDD0B4AD2EC172C586E2150770FBF9E" \
  -d '{"mateUrl": "https://www.tiktok.com/@nonexistentuser12345/live"}'
```

Expected: `{"code": 4041, "message": "直播间不存在", "data": {"mateUrl": "...", "port_info": null}, "error": {...}}`

- [ ] **Step 3: 验证入参校验（空 mateUrl → code=4001）**

```bash
curl -X POST http://localhost:8080/liveRoom/portInfo \
  -H "Content-Type: application/json" \
  -H "access-token: AFDD0B4AD2EC172C586E2150770FBF9E" \
  -d '{"mateUrl": ""}'
```

Expected: `{"code": 4001, "message": "入参缺失", ...}`

- [ ] **Step 4: 验证鉴权失败（HTTP 401）**

```bash
curl -X POST http://localhost:8080/liveRoom/portInfo \
  -H "Content-Type: application/json" \
  -H "access-token: wrong_token" \
  -d '{"mateUrl": "https://www.tiktok.com/@x/live"}'
```

Expected: HTTP 401, `{"code": 401, "message": "Unauthorized"}`

- [ ] **Step 5: 提交最终验证通过**

```bash
git add -A
git commit -m "chore: 响应标准化实施完成，联调验证通过"
```

---

## 完成标准

- [ ] `utils/api_response.py` 包含完整翻译层（3 个 classify 函数 + 2 个包装函数）
- [ ] `main.py` 三个路由全部使用新响应结构
- [ ] `tests/test_api_response.py` 全部 PASS（覆盖每个 code 至少一条用例）
- [ ] 本地联调三个端点，响应结构符合 `docs/specs/live-room-api.md` v2 规范
- [ ] `services/live-platform/api/routes.py` 同步改造
- [ ] main.py 内部巡检逻辑（551/683/687/753）**未被修改**（留下次 PR）
