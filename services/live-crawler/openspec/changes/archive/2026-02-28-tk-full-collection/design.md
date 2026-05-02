## Context

当前 TikTok 采集系统基于 DrissionPage 浏览器自动化，通过 AdsPower 指纹浏览器连接，对 4 个固定 URL 进行访问并监听 API 请求响应。系统采用"被动监听"模式——不直接调用 TikTok API，而是拦截浏览器发出的请求收集数据。

现有限制：
- `replay` 页面仅监听 4 个数据包（`count=4`），页面内容需要滚动才能触发更多 API 请求
- `data-overview` 页面使用默认时间范围（7 天），未切换到 28 天视图
- `_handle_tiktok_live_list` 仅筛选昨天的直播间访问详情页

关键前提：
- 监听是全局启动的（`base.py` 中一次性调用 `listen.start()`），只要没暂停就一直在收集数据
- `tab.listen.steps()` 会返回自上次调用以来监听到的所有数据包
- 因此只需要：**先完成页面操作（滚动/点击）→ 再调用 `get_listened_data` 取数据**，无需考虑时序竞争

## Goals / Non-Goals

**Goals:**
- 新增独立的 `--mode full` 全量采集入口，与增量模式互不影响
- replay 页面通过滚动加载获取近 30 天全量直播录像数据
- data-overview 页面自动切换至 "Last 28 days" 时间范围后再采集
- 直播列表全量采集所有已结束直播间的详情页
- 最简化实现，不过度设计

**Non-Goals:**
- 不修改 `product-analysis` 页面逻辑（按原逻辑即可）
- 不增加新的 API 监听 URL
- 不修改数据上报接口
- 不处理 Shopee 平台（另行提案）
- 不影响增量模式（`--mode once` / `--mode scheduler`）的任何行为

## Decisions

### 决策 1：全量采集模式入口

新增 `--mode full` 命令行参数，通过 `full_collection` 布尔标志贯穿整个调用链：
- `main.py` → `run_once(full_collection=True)`
- `LiveCrawler(platform, browser_id, full_collection=True)` 工厂类透传
- `BaseLiveCrawler.__init__` 存储 `self.full_collection`
- `TikTokLiveCrawler` 中各方法通过 `self.full_collection` 判断执行全量还是增量逻辑

### 决策 2：replay 页面滚动策略（仅全量模式）

在 `visit_page_and_collect` 中、`get_listened_data` 调用之前，当 `self.full_collection=True` 时：
- 定位 `class="replayListContent-jBlzCz"` 容器元素
- 循环执行 `ele.scroll.to_bottom()`，每次滚动后等待让数据加载
- 通过比较滚动前后的 `scrollTop` 值判断是否到底
- 滚动完成后 `count=None`（不限制包数量）

增量模式下保持 `count=4` 不变。

### 决策 3：data-overview 日期选择器交互（仅全量模式）

在 `visit_page_and_collect` 中、`get_listened_data` 调用之前，当 `self.full_collection=True` 时：
1. 点击 `class="arco-picker-prefix"` 元素
2. 点击 "Last 28 days" 文本元素
3. 等待页面数据刷新后再取数据

### 决策 4：直播列表全量采集（仅全量模式）

`_handle_tiktok_live_list` 方法根据 `self.full_collection` 切换行为：
- **增量模式**：保持原逻辑，仅筛选 `live_start_timestamp >= 昨天` 的直播间
- **全量模式**：跳过时间过滤，采集所有 `live_end_timestamp != 0`（已结束）的直播间详情页

### 决策 5：集成方式

直接在 `visit_page_and_collect` 方法中通过 URL + `self.full_collection` 判断插入对应的前置操作，不搞配置化、不搞抽象。

## Risks / Trade-offs

- **[元素选择器变化]** → `replayListContent-jBlzCz` 类名含哈希后缀，TikTok 更新后可能变化 → 定位失败则跳过滚动，记录日志，不影响其他采集
- **[日期选择器语言差异]** → "Last 28 days" 文本可能因语言不同而变化 → 找不到时记录警告继续采集
- **[反爬风险]** → 每次滚动间加随机等待时间
- **[全量采集耗时]** → 全量模式下直播详情页数量大幅增加，采集时间显著延长 → 这是获取全量数据的必要代价
