## ADDED Requirements

### Requirement: 全量模式下 replay 页面滚动加载全量数据
系统 SHALL 在全量采集模式下访问 `https://livecenter.tiktok.com/replay` 页面时，自动滚动 `replayListContent-jBlzCz` 容器元素至底部，触发所有分页 API 请求，直至无法继续滚动为止。

#### Scenario: 全量模式正常滚动加载
- **WHEN** 系统处于全量采集模式且访问 replay 页面，页面加载完成
- **THEN** 系统 SHALL 定位 `class="replayListContent-jBlzCz"` 容器元素，循环执行 `scroll.to_bottom()` 操作，每次滚动后等待 2-4 秒

#### Scenario: 增量模式不触发滚动
- **WHEN** 系统处于增量采集模式且访问 replay 页面
- **THEN** 系统 SHALL 不执行滚动操作，保持原有行为

#### Scenario: 滚动到底判断
- **WHEN** 连续两次滚动后 `scrollTop` 值不再变化
- **THEN** 系统 SHALL 判定已到达底部，停止滚动操作

#### Scenario: 滚动安全上限
- **WHEN** 滚动次数达到最大上限（50 次）
- **THEN** 系统 SHALL 停止滚动并记录警告日志，继续后续采集流程

#### Scenario: 容器元素未找到
- **WHEN** 系统无法定位 `replayListContent-jBlzCz` 容器元素
- **THEN** 系统 SHALL 记录警告日志并跳过滚动操作，继续执行后续采集流程

### Requirement: 全量模式下移除 replay 包数量限制
系统 SHALL 在全量采集模式下的 replay 页面不限制监听的 API 请求包数量（`count=None`）；增量模式下保持 `count=4`。

#### Scenario: 全量模式无包数量限制
- **WHEN** 系统处于全量采集模式且在 replay 页面执行数据监听
- **THEN** 系统 SHALL 不设置 `count` 限制，使用超时机制结束监听

#### Scenario: 增量模式保持包数量限制
- **WHEN** 系统处于增量采集模式且在 replay 页面执行数据监听
- **THEN** 系统 SHALL 保持 `count=4` 限制
