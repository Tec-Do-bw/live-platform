# Shopee 回放直播间详情数据实现计划

## 目标

实现 Shopee 回放直播间（liveList/v2 来源）的详情数据采集，包括 liveDetail 和 liveCoordinate/v2 两个接口。

## 实现范围

基于设计文档 `2026-03-30-shopee-js-injection-design.md` 第 3.5.2 节和第 4.2 节，实现回放直播间详情数据的 JS 注入采集。

## 实现步骤

### 步骤 1: 添加回放详情数据采集方法

**文件**: `live_dp/spiders/shopee.py`

**新增方法**:

1. `_fetch_replay_detail_via_js(session: dict, headers: dict) -> List[Dict]`
   - 对单个回放 session 发起 2 个详情接口的 JS 注入
   - 先调用 liveDetail 获取基础信息
   - 从 liveDetail 响应中提取 startTime
   - 再调用 liveCoordinate/v2 获取时序数据
   - 返回两个接口的结果列表

2. `_build_live_detail_request(session_id: str) -> Dict[str, Any]`
   - 构造 liveDetail 接口的请求参数
   - URL: `/api/supply/lm/sellercenter/liveDetail?sessionId={sessionId}`
   - 添加必需的请求头（x-region, x-region-domain, x-region-timezone 等）

3. `_build_live_coordinate_request(session_id: str, start_time: int) -> Dict[str, Any]`
   - 构造 liveCoordinate/v2 接口的请求参数
   - URL: `/api/supply/lm/sellercenter/liveCoordinate/v2?sessionId={sessionId}&startTime={timestamp}&size=240`
   - 添加必需的请求头

### 步骤 2: 修改 _handle_live_list_page() 方法

**文件**: `live_dp/spiders/shopee.py`

**修改内容**:

在 `_handle_live_list_page()` 方法中，在上报 liveList/v2 数据后，添加回放直播间详情采集逻辑：

1. 从 liveList/v2 响应中提取回放 session 列表（status=2）
2. 对每个回放 session 调用 `_fetch_replay_detail_via_js()`
3. 上报详情数据

### 步骤 3: 测试验证

**验证内容**:

1. 手动运行采集，验证回放直播间详情数据是否正确采集
2. 检查 liveDetail 接口响应是否包含完整的 liveInfo、performance、promotion、keyMetrics
3. 检查 liveCoordinate/v2 接口响应是否包含时序数据数组
4. 验证数据是否正确上报到后端

## 关键技术点

### 请求头构造

两个接口都需要以下请求头：
- `x-region`: 从 country_domain 提取国家代码（如 my）
- `x-region-domain`: country_domain（如 com.my）
- `x-region-timezone`: 根据 SHOPEE_TIMEZONE_MAP 计算时区偏移（如 +0800）
- `language`: en
- `x-env`: live

### 时序数据参数

liveCoordinate/v2 的 `size` 参数：
- 计算方式：`duration / 60000`（duration 单位为毫秒）
- 最大值：240（4 小时）
- 如果直播时长超过 4 小时，使用 240

### 错误处理

- liveDetail 接口失败时，跳过该 session 的 liveCoordinate/v2 调用
- 单个 session 失败不影响其他 session 的采集
- 所有异常只记录日志，不中断主流程

## 预期效果

实现后，Shopee 采集将包含：
- ✅ 登录检测
- ✅ sessionList 触发器
- ✅ liveList/v2 补充列表
- ✅ overview/v3 + metricTrend/v2 概览数据
- ✅ 回放直播间详情数据（liveDetail + liveCoordinate/v2）

---

**计划创建日期**: 2026-03-31
**预计实现时间**: 1-2 小时
