## Why

当前 TikTok 采集仅获取页面初始加载的部分数据，无法覆盖全量历史数据。具体问题：
- `replay` 页面仅监听前 4 个数据包，未滚动加载后续数据（最多覆盖近 30 天）
- `data-overview` 页面默认展示 7 天数据，未切换至"Last 28 days"时间范围
- `livestream-analytics` 的直播列表处理仅筛选昨天的直播间，全量模式需采集所有已结束的直播间详情
- `product-analysis` 按原逻辑即可，无需改动

为满足业务全量数据分析需求，需要新增独立的全量采集运行模式，与现有增量采集互不影响。

## What Changes

- **新增 `full` 运行模式**：在 `main.py` 中新增 `--mode full` 入口，通过 `full_collection` 标志贯穿 `LiveCrawler` → `BaseLiveCrawler` → `TikTokLiveCrawler` 全链路
- **replay 页面滚动加载（全量模式）**：对 `replayListContent-jBlzCz` 容器执行滚动到底部操作，触发全量 API 请求；移除 `count=4` 限制
- **data-overview 时间范围切换（全量模式）**：点击 `arco-picker-prefix` → "Last 28 days"，获取近 28 天数据
- **直播列表全量采集（全量模式）**：`_handle_tiktok_live_list` 跳过昨天时间过滤，采集所有已结束的直播间详情页
- **增量模式不受影响**：`--mode once` 和 `--mode scheduler` 行为完全保持不变

## Capabilities

### New Capabilities
- `full-collection-mode`: 全量采集运行模式，通过 `--mode full` 启动，`full_collection` 标志控制各页面的全量采集行为
- `replay-scroll-load`: replay 页面滚动加载全量数据能力（仅全量模式激活）
- `data-overview-date-range`: data-overview 页面日期范围切换能力（仅全量模式激活）
- `live-list-full-collect`: 直播列表全量采集，跳过时间过滤采集所有已结束直播间详情（仅全量模式激活）

### Modified Capabilities
（无现有 spec 需要修改）

## Impact

- **受影响代码**：
  - `main.py` — 新增 `--mode full` 入口，`run_once` 接受 `full_collection` 参数
  - `spiders/live_crawler.py` — 工厂类透传 `full_collection` 参数
  - `spiders/base.py` — 基类存储 `self.full_collection` 标志
  - `spiders/tiktok.py` — 新增滚动/日期切换方法，直播列表全量采集逻辑
- **采集数据量**：全量模式下 replay 页面和直播详情页采集量显著增加
- **采集耗时**：全量模式采集时间较增量模式大幅增加
- **增量模式零影响**：所有新逻辑均由 `self.full_collection` 守卫，增量模式行为不变
