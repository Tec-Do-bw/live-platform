## ADDED Requirements

### Requirement: 全量模式下 data-overview 页面切换至 28 天时间范围
系统 SHALL 在全量采集模式下采集 `https://shop.tiktok.com/streamer/compass/data-overview/view` 页面数据前，自动将时间范围切换至 "Last 28 days"。

#### Scenario: 全量模式正常切换日期范围
- **WHEN** 系统处于全量采集模式且访问 data-overview 页面，页面加载完成
- **THEN** 系统 SHALL 先点击 `class="arco-picker-prefix"` 元素打开日期选择器，再点击包含文本 "Last 28 days" 的元素，等待页面数据刷新后再开始监听

#### Scenario: 增量模式不触发日期切换
- **WHEN** 系统处于增量采集模式且访问 data-overview 页面
- **THEN** 系统 SHALL 不执行日期切换操作，使用默认时间范围

#### Scenario: 日期选择器打开失败
- **WHEN** 系统无法找到 `arco-picker-prefix` 元素
- **THEN** 系统 SHALL 记录警告日志并继续使用默认时间范围进行采集

#### Scenario: "Last 28 days" 选项未找到
- **WHEN** 系统成功打开日期选择器但未找到 "Last 28 days" 文本选项
- **THEN** 系统 SHALL 记录警告日志并继续使用当前时间范围进行采集

#### Scenario: 切换后等待数据刷新
- **WHEN** 系统成功点击 "Last 28 days" 选项
- **THEN** 系统 SHALL 等待至少 3 秒以确保页面数据刷新完成，然后再开始 API 请求监听
