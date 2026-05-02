# 实现任务清单

## 1. 核心修复：队列获取超时

- [x] 1.1 修改 `utils/TiktokTool.py` 的 `getPageinfo_selenium` 方法
  - 将 `self.tabItemQ.get()` 改为 `self.tabItemQ.get(timeout=30)`
  - 捕获 `queue.Empty` 异常并返回 `None`

## 2. 线程池执行超时保护

- [x] 2.1 修改 `main.py` 的 `check_live_status` 函数
  - 为 `future.result()` 添加 `timeout=180`（3分钟，支持200个URL并发）

## 3. 调度器线程健康监控

- [x] 3.1 修改 `start_select_info_scheduler` 函数
  - 保存线程引用到全局变量 `scheduler_thread`
  - 添加心跳时间更新（每30秒）

- [x] 3.2 创建 `start_scheduler_monitor()` 函数
  - 每2分钟检查一次
  - 心跳超时10分钟判定为死亡
  - 自动重启 + 飞书告警

## 4. 测试验证

- [ ] 4.1 部署到测试环境观察24小时

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `utils/TiktokTool.py` | `getPageinfo_selenium` 添加30秒超时 |
| `main.py` | 线程池任务180秒超时、调度器监控（10分钟心跳超时） |
