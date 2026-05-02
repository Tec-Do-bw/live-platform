## ADDED Requirements

### Requirement: 全量采集运行模式入口
系统 SHALL 支持 `--mode full` 命令行参数启动全量采集模式，通过 `full_collection` 标志贯穿 `main.py` → `LiveCrawler` → `BaseLiveCrawler` → 平台爬虫子类的完整调用链。

#### Scenario: 启动全量采集模式
- **WHEN** 用户执行 `python main.py --mode full`
- **THEN** 系统 SHALL 调用 `run_once(full_collection=True)`，创建爬虫实例时传递 `full_collection=True`

#### Scenario: 增量模式不受影响
- **WHEN** 用户执行 `python main.py --mode once` 或 `python main.py --mode scheduler`
- **THEN** 系统 SHALL 保持原有增量采集行为，`full_collection=False`

### Requirement: full_collection 标志透传
系统 SHALL 将 `full_collection` 参数从 `main.py` 透传至平台爬虫实例，存储为 `self.full_collection` 属性。

#### Scenario: 参数透传链路
- **WHEN** `LiveCrawler(platform, browser_id, full_collection=True)` 被调用
- **THEN** 工厂类 SHALL 将 `full_collection` 传递给对应平台爬虫类的构造函数，`BaseLiveCrawler.__init__` 存储为 `self.full_collection`
