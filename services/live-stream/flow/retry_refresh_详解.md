# on_retry_refresh 取数逻辑详解

## 核心问题
FFmpeg 断流后，如何决定用哪个 URL 重连？

---

## 完整决策流程

### 步骤 1：重新读取 Redis（关键！）

```python
status = redis_source.get_status(collection_id)
if not status:
    redis_source.release(collection_id, worker_id)
    return False, None  # 停止录制
```

**数据来源**：
- Redis Key: `live:collection:{collectionId}:status`
- 关键字段：
  - `flvUrl`: live-monitor 最新检测的主 FLV URL
  - `metadata.play_urls`: 备用 URL 数组（多 CDN 节点）

**判断逻辑**：
- `status` 不存在 → 房间已下播或状态过期 → 释放租约，停止录制
- `status` 存在 → 继续下一步

---

### 步骤 2：刷新候选 URL 列表

```python
metadata = status.get("metadata") or {}
refreshed_candidates = build_live_url_candidates(
    {
        "flv_url": status.get("flvUrl"),
        "play_urls": metadata.get("play_urls") or metadata.get("playUrls") or port_info.get("play_urls"),
    }
)
if refreshed_candidates:
    live_url_candidates = refreshed_candidates  # 更新全局候选列表
```

**build_live_url_candidates 的去重逻辑**：

```python
def build_live_url_candidates(port_info: dict) -> list[str]:
    candidates = []
    raw_urls = [port_info.get("flv_url") or port_info.get("flvUrl")]
    raw_urls.extend(port_info.get("play_urls") or port_info.get("playUrls") or [])

    seen = set()
    for raw_url in raw_urls:
        url = str(raw_url or "").strip()
        if not url or url == "error" or "only_audio=1" in url:
            continue  # 过滤无效 URL
        if url in seen:
            continue  # 去重
        seen.add(url)
        candidates.append(url)
    return candidates
```

**数据来源优先级**：
1. **主 FLV URL**：`status.flvUrl`（live-monitor 最新检测结果）
2. **备用 URLs**：`status.metadata.play_urls`（TikTok 返回的多 CDN 地址）
3. **Fallback**：`port_info.play_urls`（启动时的初始备用列表）

**示例输入**：
```json
{
  "flvUrl": "https://pull-f5-web01.tiktokcdn.com/live/stream-123.flv",
  "metadata": {
    "play_urls": [
      "https://pull-f5-web01.tiktokcdn.com/live/stream-123.flv",  // 与主 URL 重复，去重
      "https://pull-f5-web02.tiktokcdn.com/live/stream-123.flv",  // 备用 CDN 节点 1
      "https://pull-f5-web03.tiktokcdn.com/live/stream-123.flv",  // 备用 CDN 节点 2
      "https://pull-f5-web04.tiktokcdn.com/live/stream-123.flv?only_audio=1"  // 纯音频，过滤
    ]
  }
}
```

**输出 live_url_candidates**：
```python
[
  "https://pull-f5-web01.tiktokcdn.com/live/stream-123.flv",  # 主 URL
  "https://pull-f5-web02.tiktokcdn.com/live/stream-123.flv",  # 备用 1
  "https://pull-f5-web03.tiktokcdn.com/live/stream-123.flv",  # 备用 2
]
```

---

### 步骤 3：检查主 URL 是否变化

```python
refreshed_live_url = status.get("flvUrl", "")
if refreshed_live_url and refreshed_live_url != current_live_url:
    port_info["flv_url"] = refreshed_live_url
    return True, refreshed_live_url  # 返回新 URL
```

**判断条件**：
- `refreshed_live_url` 非空
- `refreshed_live_url != current_live_url`（与 FFmpeg 当前使用的 URL 不同）

**变化场景**：
1. **CDN 切换**：live-monitor 检测到主 CDN 节点切换
2. **直播重开**：主播下播后重新开播，stream_id 变化
3. **平台切流**：TikTok 后台切换推流服务器

**示例**：
```python
current_live_url = "https://pull-f5-web01.tiktokcdn.com/live/stream-123.flv"
refreshed_live_url = "https://pull-f5-web05.tiktokcdn.com/live/stream-456.flv"  # 新的 stream_id

# 判断：refreshed_live_url != current_live_url → True
# 返回：("https://pull-f5-web05.tiktokcdn.com/live/stream-456.flv", True)
```

---

### 步骤 4：轮换备用 URL（主 URL 未变时）

```python
def next_candidate_url():
    if len(live_url_candidates) <= 1:
        return current_live_url  # 只有 1 个 URL，无法轮换

    try:
        current_index = live_url_candidates.index(current_live_url)
    except ValueError:
        current_index = live_url_index["value"]  # Fallback 到记录的索引

    next_index = (current_index + 1) % len(live_url_candidates)  # 循环轮换
    live_url_index["value"] = next_index
    return live_url_candidates[next_index]

fallback_url = next_candidate_url()
if fallback_url != current_live_url:
    port_info["flv_url"] = fallback_url
    logger.info(f"[{rid}] 切换备用直播源: {fallback_url}")
return True, fallback_url
```

**轮换逻辑**：
1. 在 `live_url_candidates` 列表中找到 `current_live_url` 的索引
2. 索引 +1，取模运算（循环）
3. 返回下一个 URL

**示例**：
```python
live_url_candidates = [
  "https://cdn01.com/live.flv",  # 索引 0
  "https://cdn02.com/live.flv",  # 索引 1
  "https://cdn03.com/live.flv",  # 索引 2
]

# 第 1 次断流
current_live_url = "https://cdn01.com/live.flv"  # 索引 0
next_index = (0 + 1) % 3 = 1
返回 "https://cdn02.com/live.flv"

# 第 2 次断流
current_live_url = "https://cdn02.com/live.flv"  # 索引 1
next_index = (1 + 1) % 3 = 2
返回 "https://cdn03.com/live.flv"

# 第 3 次断流
current_live_url = "https://cdn03.com/live.flv"  # 索引 2
next_index = (2 + 1) % 3 = 0
返回 "https://cdn01.com/live.flv"  # 循环回第一个
```

**边界情况**：
- **只有 1 个 URL**：`len(live_url_candidates) <= 1` → 返回原 URL，不轮换
- **current_url 不在列表中**：`ValueError` → 使用记录的 `live_url_index["value"]`

---

## 数据流向图

```
Redis status.flvUrl (live-monitor 写入)
    ↓
步骤 2: 刷新 live_url_candidates 列表
    [主 URL, 备用 URL1, 备用 URL2, ...]
    ↓
步骤 3: status.flvUrl != current_url?
    ├─ 是 → 返回 status.flvUrl（主 URL 已更新）
    └─ 否 → 步骤 4
              ↓
         在列表中找到 current_url 的索引
              ↓
         next_index = (current_index + 1) % len(list)
              ↓
         返回 list[next_index]（轮换到备用 URL）
```

---

## 为什么这样设计？

### 问题：旧模式的痛点
- FFmpeg 断流后，一直用**启动时获取的 flv_url** 重试
- live-monitor 检测到新 URL，但 live-stream 不知道
- 重试 12 次（默认）全部失败，浪费 2 分钟后才放弃

### 解决方案：三级 URL 策略

#### 1️⃣ 优先：主 URL 实时刷新
- **数据源**：Redis `status.flvUrl`（live-monitor 每轮更新）
- **触发时机**：每次断流重连前
- **效果**：CDN 切换后立即生效

#### 2️⃣ 其次：备用 URL 轮换
- **数据源**：`status.metadata.play_urls`（TikTok 返回的多 CDN）
- **触发时机**：主 URL 未变化时
- **效果**：某个 CDN 节点故障时，自动切换到其他节点

#### 3️⃣ 最后：Fallback 原 URL
- **数据源**：启动时的 `port_info.play_urls`
- **触发时机**：Redis 无新数据时
- **效果**：兼容 HTTP 模式，降级保护

---

## 实际案例

### 案例 1：CDN 切换（主 URL 变化）

```python
# 初始状态
current_live_url = "https://cdn01.com/stream-123.flv"
live_url_candidates = [
  "https://cdn01.com/stream-123.flv",
  "https://cdn02.com/stream-123.flv",
]

# live-monitor 检测到 CDN 切换
Redis status.flvUrl = "https://cdn05.com/stream-456.flv"

# 断流触发 on_retry_refresh
步骤 1: 读取 Redis
  → status.flvUrl = "https://cdn05.com/stream-456.flv"

步骤 2: 刷新候选列表
  → live_url_candidates = [
      "https://cdn05.com/stream-456.flv",  # 新主 URL
      "https://cdn06.com/stream-456.flv",  # 新备用
    ]

步骤 3: 检查主 URL
  → "https://cdn05.com/stream-456.flv" != "https://cdn01.com/stream-123.flv"
  → 返回 "https://cdn05.com/stream-456.flv" ✅

# FFmpeg 用新 URL 重连，1 次成功
```

---

### 案例 2：单 CDN 节点故障（主 URL 未变，轮换备用）

```python
# 初始状态
current_live_url = "https://cdn01.com/stream-123.flv"
live_url_candidates = [
  "https://cdn01.com/stream-123.flv",
  "https://cdn02.com/stream-123.flv",
  "https://cdn03.com/stream-123.flv",
]

# cdn01 节点故障，FFmpeg 断流

# 断流触发 on_retry_refresh
步骤 1: 读取 Redis
  → status.flvUrl = "https://cdn01.com/stream-123.flv"（live-monitor 还未感知）

步骤 2: 刷新候选列表
  → live_url_candidates 保持不变

步骤 3: 检查主 URL
  → "https://cdn01.com/stream-123.flv" == current_live_url
  → 未变化，进入步骤 4

步骤 4: 轮换备用 URL
  → current_index = 0
  → next_index = (0 + 1) % 3 = 1
  → 返回 "https://cdn02.com/stream-123.flv" ✅

# FFmpeg 用 cdn02 重连，成功
```

---

### 案例 3：只有 1 个 URL（无法轮换）

```python
# 初始状态
current_live_url = "https://cdn01.com/stream-123.flv"
live_url_candidates = [
  "https://cdn01.com/stream-123.flv",  # 只有 1 个
]

# 断流触发 on_retry_refresh
步骤 4: 轮换备用 URL
  → len(live_url_candidates) = 1
  → 返回 current_live_url（原 URL）

# FFmpeg 用原 URL 重试，依赖正常重试策略
```

---

## 监控与调试

### 关键日志

```bash
# 主 URL 变化
[room_123] 直播源已刷新，使用新的FLV URL重连

# 备用 URL 轮换
[room_123] 切换备用直播源: https://cdn02.com/live.flv

# 状态失效
[room_123] 直播源已失效或下播，停止重连
```

### Redis 数据检查

```bash
# 查看主 URL
redis-cli HGET live:collection:coll_123:status flvUrl

# 查看备用 URLs
redis-cli HGET live:collection:coll_123:status metadata
# 输出 JSON 中查找 play_urls 数组

# 查看完整状态
redis-cli HGETALL live:collection:coll_123:status
```

### 调试技巧

```python
# 在 on_retry_refresh 中添加日志
logger.debug(f"[{rid}] 候选URL列表: {live_url_candidates}")
logger.debug(f"[{rid}] 当前URL: {current_live_url}")
logger.debug(f"[{rid}] Redis返回URL: {refreshed_live_url}")
logger.debug(f"[{rid}] 最终选择URL: {result_url}")
```

---

## 总结

| 步骤 | 数据来源 | 取数逻辑 | 优先级 |
|------|---------|---------|--------|
| 1 | Redis `get_status()` | 实时读取 live-monitor 写入的最新状态 | - |
| 2 | `status.flvUrl` + `status.metadata.play_urls` | 合并去重，构建候选列表 | - |
| 3 | `status.flvUrl` | 如果 != current_url，立即返回 | 🥇 最高 |
| 4 | `live_url_candidates` | 在列表中循环轮换，索引 +1 取模 | 🥈 次高 |
| Fallback | `current_live_url` | 只有 1 个 URL 时，返回原 URL | 🥉 保底 |

**核心优势**：
✅ **实时感知 CDN 切换**：每次断流前重新读 Redis，而非用内存缓存
✅ **多 CDN 容灾**：单节点故障时自动切换到其他节点
✅ **智能轮换**：循环使用所有可用 URL，避免反复失败在同一个坏节点上
