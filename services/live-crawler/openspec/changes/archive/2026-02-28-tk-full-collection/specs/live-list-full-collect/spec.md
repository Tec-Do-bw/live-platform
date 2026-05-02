## ADDED Requirements

### Requirement: 全量模式下采集所有已结束直播间详情
系统 SHALL 在全量采集模式下，对 `_handle_tiktok_live_list` 跳过昨天时间过滤，采集所有已结束的直播间详情页。

#### Scenario: 全量模式采集所有直播间
- **WHEN** 系统处于全量采集模式（`self.full_collection=True`）且收到 `api/v2/insights/creator/live/list` 响应
- **THEN** 系统 SHALL 采集所有 `live_end_timestamp != 0` 且未处理过的直播间详情页，不进行时间范围过滤

#### Scenario: 增量模式仅采集昨天直播间
- **WHEN** 系统处于增量采集模式（`self.full_collection=False`）且收到 `api/v2/insights/creator/live/list` 响应
- **THEN** 系统 SHALL 保持原有逻辑，仅筛选 `live_start_timestamp >= 昨天 00:00:00` 的直播间
