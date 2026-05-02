## 1. 全量采集模式入口

- [x] 1.1 `main.py` 新增 `--mode full` 命令行参数，调用 `run_once(full_collection=True)`
- [x] 1.2 `spiders/live_crawler.py` 工厂类 `__new__` 透传 `full_collection` 参数
- [x] 1.3 `spiders/base.py` 基类 `__init__` 接收并存储 `self.full_collection` 标志
- [x] 1.4 `spiders/tiktok.py` 构造函数透传 `full_collection` 给基类

## 2. replay 页面全量采集

- [x] 2.1 新增 `_scroll_replay_list()` 方法：定位容器元素循环 `scroll.to_bottom()`，比较 `scrollTop` 判断到底，最大 50 次上限
- [x] 2.2 在 `visit_page_and_collect` 中 `get_listened_data` 之前，当 `self.full_collection=True` 且 URL 为 replay 时调用滚动
- [x] 2.3 全量模式 `count=None`，增量模式保持 `count=4`

## 3. data-overview 28天日期切换

- [x] 3.1 新增 `_select_28_days_range()` 方法：点击 `arco-picker-prefix` → "Last 28 days"，找不到元素时记录警告跳过
- [x] 3.2 在 `visit_page_and_collect` 中 `get_listened_data` 之前，当 `self.full_collection=True` 且 URL 为 data-overview 时调用

## 4. 直播列表全量采集

- [x] 4.1 `_handle_tiktok_live_list` 根据 `self.full_collection` 切换过滤逻辑：全量模式跳过昨天时间过滤，采集所有已结束直播间

## 5. 测试验证

- [x] 5.1 对不同国家单个 TikTok 账号执行 `--mode full` 端到端测试，验证 replay 滚动、data-overview 日期切换、直播列表全量采集均正常工作
- [x] 5.2 对单个 TikTok 账号执行 `--mode once` 验证增量模式行为不受影响
- [ ] 墨西哥国家当前请求有问题 后续需要处理
