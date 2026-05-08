---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.vue"
  - "**/*.js"
---

# 中文注释与提交信息

## 触发条件

编写代码、注释、docstring 或 commit message 时。

## 规则

所有代码注释、docstring、commit message 使用中文，技术术语保持英文。

## 示例

```python
# ✅ 正确
def get_live_stream_info(room_url: str) -> dict:
    """获取直播间信息
    
    Args:
        room_url: 直播间 URL
        
    Returns:
        包含 flv_url、roomId 等字段的字典
    """
    # 通过 HTTP 请求获取直播流地址
    response = requests.get(room_url)
    return response.json()

# ❌ 错误
def get_live_stream_info(room_url: str) -> dict:
    """Get live stream information"""
    # Fetch stream URL via HTTP request
    response = requests.get(room_url)
    return response.json()
```

```bash
# ✅ 正确的 commit message
git commit -m "修复 TikTok 直播流断流重连逻辑"

# ❌ 错误的 commit message
git commit -m "Fix TikTok live stream reconnection logic"
```

## 原因

团队主要使用中文沟通，中文注释降低理解成本，提高协作效率。技术术语保持英文避免翻译歧义。
