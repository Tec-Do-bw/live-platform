# Live Platform 架构极简化实施计划

> **开始日期：** 2026-05-06  
> **预计完成：** 2026-06-03（4 周）  
> **负责人：** XBW  
> **状态：** 待开始

---

## 总览

| Phase | 任务 | 时间 | 优先级 | 状态 |
|-------|------|------|--------|------|
| Phase 1 | 修复 FFmpeg 断流 | 1 周 | P0 | ⏳ 待开始 |
| Phase 2 | 删除非核心代码 | 2 天 | P1 | ⏳ 待开始 |
| Phase 3 | 合并服务 | 1 周 | P2 | ⏳ 待开始 |
| Phase 4 | 监控简化 | 3 天 | P3 | ⏳ 待开始 |

---

## Phase 1：修复 FFmpeg 断流（P0）

**时间：** 2026-05-06 ~ 2026-05-12（1 周）  
**目标：** 断流重连成功率 > 95%

### 任务清单

- [ ] **1.1 修改 FFmpeg 重连参数**
  - [ ] 打开 `services/live-stream/TT_client.py`
  - [ ] 找到 `FFmpegStreamManager` 类的配置部分
  - [ ] 修改以下参数：
    ```python
    # 心跳检测间隔
    heartbeat_interval = 10  # 从 30s 改为 10s
    
    # 无数据超时
    no_data_timeout = 15  # 从 60s 改为 15s
    
    # 最大重试次数
    max_retries = 15  # 从 5 改为 15
    
    # 重试初始间隔
    retry_initial_interval = 1  # 从 3s 改为 1s
    
    # 稳定运行判定
    stable_threshold = 30  # 从 60s 改为 30s
    ```
  - [ ] 提交代码：`git commit -m "优化 FFmpeg 断流重连参数"`

- [ ] **1.2 部署到生产环境**
  - [ ] 停止 live-stream 服务：`systemctl stop live-stream`
  - [ ] 拉取最新代码：`git pull origin main`
  - [ ] 重启服务：`systemctl start live-stream`
  - [ ] 检查日志：`tail -f logs/ffmpeg_stream_*.log`

- [ ] **1.3 监控断流情况（3 天）**
  - [ ] 每天检查断流日志
  - [ ] 统计重连成功率
  - [ ] 记录异常情况
  - [ ] 目标：重连成功率 > 95%

- [ ] **1.4 调优（如需要）**
  - [ ] 如果成功率未达标，继续调整参数
  - [ ] 考虑增加重试次数或缩短超时时间

---

## Phase 2：删除非核心代码（P1）

**时间：** 2026-05-13 ~ 2026-05-14（2 天）  
**目标：** 删除 1,400 行非核心代码

### 任务清单

- [ ] **2.1 精简 docs 路由（保留数据在线 API 调试页）**
  - [ ] 打开 `services/live-monitor/routes/docs.py`
  - [ ] 保留 `GET /docs/doc`
  - [ ] 保留 `GET /docs/getConfig`（`/docs/doc` 的配置数据源）
  - [ ] 删除非核心页面与后台能力：
    - `login`
    - `chat`
    - `offlineTask`
    - `configGenerator`
    - `versionHistory`
    - `dataNeedForm`
    - `updateConfig`
  - [ ] 保留 `main.py` 中的 docs 路由注册
  - [ ] 提交代码：`git commit -m "精简 docs 路由，保留数据在线 API 调试页"`

- [ ] **2.2 删除激活码系统（372 行）**
  - [ ] 备份：`cp services/live-monitor/routes/activation.py docs/archive/`
  - [ ] 删除：`rm services/live-monitor/routes/activation.py`
  - [ ] 从 `main.py` 移除路由注册
  - [ ] 提交：`git commit -m "删除激活码系统"`

- [ ] **2.3 删除主备 HA 机制（~200 行）**
  - [ ] 打开 `services/live-monitor/main.py`
  - [ ] 删除以下函数：
    - `sync_room_dict_to_backup()`
    - `sync_offline_scripts_to_backup()`
    - `check_primary_health()`
  - [ ] 删除路由：
    - `POST /sync_room_dict`
    - `POST /sync_offline_scripts`
    - `POST /sync_log`
  - [ ] 删除定时任务调度（APScheduler 中的同步任务）
  - [ ] 提交：`git commit -m "删除主备 HA 机制"`

- [ ] **2.4 删除未挂载的路由（~100 行）**
  - [ ] 打开 `services/live-monitor/routes/websocket_routes.py`
  - [ ] 删除已注释的代码（line 149 附近）
  - [ ] 提交：`git commit -m "清理未挂载的死代码"`

- [ ] **2.5 测试核心功能**
  - [ ] 运行测试：`cd services/live-monitor && pytest tests/`
  - [ ] 验证调试页可用：
    ```bash
    curl http://localhost:8080/docs/getConfig
    ```
  - [ ] 手动打开 `/docs/doc`，确认可调试以下接口：
    - `POST /liveRoom/portInfo`
    - `POST /liveRoom/shopeeInfo`
    - `POST /liveRoom/lazadaInfo`
  - [ ] 手动测试核心端点：
    ```bash
    # 测试获取直播间信息
    curl -X POST http://localhost:8080/liveRoom/portInfo \
      -H "Content-Type: application/json" \
      -d '{"room_url": "https://www.tiktok.com/@xxx/live"}'
    
    # 测试健康检查
    curl http://localhost:8080/health
    ```
  - [ ] 确认 live-stream 仍能正常获取房间：
    ```bash
    curl -X POST http://localhost:8080/get_roominfo \
      -H "Content-Type: application/json" \
      -d '{"client_ip": "192.168.1.100"}'
    ```

- [ ] **2.6 部署验证**
  - [ ] 部署到生产环境
  - [ ] 观察 1 天，确认无异常

---

## Phase 3：合并服务（P2）

**时间：** 2026-05-15 ~ 2026-05-21（1 周）  
**目标：** 合并 live-monitor + live-stream + live-crawler 监控

### 任务清单

- [ ] **3.1 创建新项目结构**
  ```bash
  mkdir -p services/live-platform/{api,tasks,ffmpeg,crawler,monitor,data}
  mkdir -p services/live-platform/tests
  ```

- [ ] **3.2 创建主入口文件**
  - [ ] 创建 `services/live-platform/main.py`
  - [ ] 实现基础框架：
    ```python
    import asyncio
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from fastapi import FastAPI
    import uvicorn
    
    async def main():
        scheduler = AsyncIOScheduler()
        
        # TODO: 添加定时任务
        
        # FastAPI
        app = FastAPI(title="Live Platform")
        
        # TODO: 添加路由
        
        scheduler.start()
        config = uvicorn.Config(app, host="0.0.0.0", port=8080)
        server = uvicorn.Server(config)
        await server.serve()
    
    if __name__ == "__main__":
        asyncio.run(main())
    ```

- [ ] **3.3 迁移房间检测逻辑**
  - [ ] 创建 `services/live-platform/tasks/room_detector.py`
  - [ ] 从 `live-monitor/main.py` 复制 `select_Info()` 和 `check_live_status()`
  - [ ] 重构为 `detect_rooms()` 函数
  - [ ] 添加到定时任务：`scheduler.add_job(detect_rooms, 'interval', seconds=60)`

- [ ] **3.4 迁移 FFmpeg 管理逻辑**
  - [ ] 创建 `services/live-platform/ffmpeg/manager.py`
  - [ ] 从 `live-stream/TT_client.py` 复制 `FFmpegStreamManager` 类
  - [ ] 实现 `start_recording()` 函数（直接启动 subprocess）
  - [ ] 实现 `stop_recording()` 函数
  - [ ] 在 `room_detector.py` 中调用：
    ```python
    if live_info and live_info.get("flv_url"):
        start_recording(room.id, live_info)
    ```

- [ ] **3.5 迁移 OSS 上传逻辑**
  - [ ] 创建 `services/live-platform/tasks/oss_uploader.py`
  - [ ] 从 `live-stream/TT_client.py` 复制上传逻辑
  - [ ] 实现为后台任务：
    ```python
    async def upload_segments():
        while True:
            for ts_file in glob.glob("output/*.ts"):
                if is_file_ready(ts_file):
                    await upload_to_oss(ts_file)
                    await send_kafka_message(ts_file)
                    os.remove(ts_file)
            await asyncio.sleep(10)
    ```
  - [ ] 在 `main.py` 中启动：`asyncio.create_task(upload_segments())`

- [ ] **3.6 迁移 GMV 采集逻辑**
  - [ ] 创建 `services/live-platform/crawler/gmv_crawler.py`
  - [ ] 从 `live-crawler/main.py` 复制采集逻辑
  - [ ] 添加到定时任务：`scheduler.add_job(crawl_gmv, 'interval', minutes=5)`

- [ ] **3.7 迁移 API 路由**
  - [ ] 创建 `services/live-platform/api/routes.py`
  - [ ] 迁移核心端点：
    - `POST /liveRoom/portInfo`
    - `POST /liveRoom/shopeeInfo`
    - `POST /liveRoom/lazadaInfo`
    - `GET /health`
  - [ ] 在 `main.py` 中注册路由

- [ ] **3.8 配置文件整合**
  - [ ] 创建 `services/live-platform/config.py`
  - [ ] 合并 live-monitor、live-stream、live-crawler 的配置
  - [ ] 使用环境变量或配置文件

- [ ] **3.9 数据库迁移**
  - [ ] 确认 SQLite 数据库位置：`services/live-platform/data/monitor.db`
  - [ ] 迁移表结构（如需要）

- [ ] **3.10 编写测试**
  - [ ] 单元测试：`services/live-platform/tests/test_room_detector.py`
  - [ ] 集成测试：`services/live-platform/tests/test_integration.py`
  - [ ] 端到端测试：录入直播间 → 60 秒内检测 → FFmpeg 启动

- [ ] **3.11 压力测试**
  - [ ] 模拟 80 路并发直播流
  - [ ] 监控资源占用：
    - CPU < 80%
    - 内存 < 20 GB
    - 网络带宽 < 500 Mbps
  - [ ] 验证稳定性（运行 24 小时）

- [ ] **3.12 灰度发布**
  - [ ] 在测试环境部署新服务
  - [ ] 双写验证（新旧服务同时运行，对比结果）
  - [ ] 逐步切流量到新服务
  - [ ] 观察 3 天无异常后全量切换

- [ ] **3.13 下线旧服务**
  - [ ] 停止 live-monitor：`systemctl stop live-monitor`
  - [ ] 停止 live-stream：`systemctl stop live-stream`
  - [ ] 归档旧代码：`mv services/live-monitor docs/archive/`
  - [ ] 提交：`git commit -m "合并服务完成，下线 live-monitor 和 live-stream"`

---

## Phase 4：监控简化（P3）

**时间：** 2026-05-22 ~ 2026-05-24（3 天）  
**目标：** 用飞书日报替代 Vue 监控面板

### 任务清单

- [ ] **4.1 删除 Vue 前端（3,600 行）**
  - [ ] 备份：`cp -r services/live-crawler/monitor/frontend docs/archive/`
  - [ ] 删除：`rm -rf services/live-crawler/monitor/frontend`
  - [ ] 提交：`git commit -m "删除 Vue 监控面板"`

- [ ] **4.2 创建飞书日报脚本**
  - [ ] 创建 `scripts/daily_completeness_report.py`
  - [ ] 实现逻辑：
    ```python
    import sqlite3
    from datetime import date
    from feishu_webhook import send_message
    
    def generate_report():
        db = sqlite3.connect("services/live-platform/data/monitor.db")
        today = date.today()
        
        # 查询今日缺失数据
        missing = db.execute("""
            SELECT account_id, platform, error_message
            FROM account_sessions
            WHERE date = ? AND status != 'success'
        """, (today,)).fetchall()
        
        if not missing:
            message = f"✅ {today} 数据采集完整，无缺失"
        else:
            message = f"⚠️ {today} 数据缺失 {len(missing)} 条\n\n"
            for account_id, platform, error in missing:
                message += f"- {account_id} ({platform}): {error}\n"
        
        send_message(message)
    
    if __name__ == "__main__":
        generate_report()
    ```

- [ ] **4.3 实现飞书 Webhook**
  - [ ] 创建 `scripts/feishu_webhook.py`
  - [ ] 实现 `send_message()` 函数
  - [ ] 配置 Webhook URL（环境变量）

- [ ] **4.4 测试脚本**
  - [ ] 手动运行：`python scripts/daily_completeness_report.py`
  - [ ] 验证飞书消息接收

- [ ] **4.5 添加到 cron**
  ```bash
  crontab -e
  # 每天 18:00 执行
  0 18 * * * cd /path/to/live-platform && python scripts/daily_completeness_report.py
  ```

- [ ] **4.6 添加实时告警**
  - [ ] 在 `services/live-platform/tasks/completeness_checker.py` 中添加：
    ```python
    async def check_completeness():
        """每小时检查一次，发现异常立即告警"""
        missing = await db.query("SELECT * FROM account_sessions WHERE status != 'success'")
        if len(missing) > threshold:
            await send_feishu_alert(f"⚠️ 当前缺失 {len(missing)} 条数据")
    ```
  - [ ] 添加到定时任务：`scheduler.add_job(check_completeness, 'interval', hours=1)`

---

## Phase 5：验收与文档（收尾）

**时间：** 2026-05-25 ~ 2026-06-03（1 周）

### 任务清单

- [ ] **5.1 验收测试**
  - [ ] 开播检测延迟 < 60 秒 ✅
  - [ ] 断流重连成功率 > 95% ✅
  - [ ] 代码量 < 10,000 行 ✅
  - [ ] 服务数 = 2 个 ✅
  - [ ] API 端点数 < 5 个 ✅
  - [ ] 部署机器数 = 1 台 ✅

- [ ] **5.2 更新文档**
  - [ ] 更新根 `CLAUDE.md`（删除已废弃的服务描述）
  - [ ] 更新根 `README.md`（更新架构图和启动命令）
  - [ ] 创建 `services/live-platform/CLAUDE.md`
  - [ ] 创建 `services/live-platform/README.md`
  - [ ] 更新 `.claude/references/` 中的交互规则

- [ ] **5.3 清理代码**
  - [ ] 删除未使用的依赖（`requirements.txt`）
  - [ ] 删除未使用的配置文件
  - [ ] 删除注释掉的代码
  - [ ] 运行 linter：`black services/live-platform/`

- [ ] **5.4 性能基线**
  - [ ] 记录 CPU 使用率（峰值/平均）
  - [ ] 记录内存使用率
  - [ ] 记录网络带宽
  - [ ] 记录磁盘 I/O

- [ ] **5.5 监控告警配置**
  - [ ] 配置 systemd 服务自动重启
  - [ ] 配置磁盘空间告警（< 20% 时飞书通知）
  - [ ] 配置 CPU 告警（> 90% 时飞书通知）
  - [ ] 配置进程存活检查

- [ ] **5.6 备份策略**
  - [ ] 配置每日数据库备份
  - [ ] 配置日志轮转
  - [ ] 配置代码仓库备份

- [ ] **5.7 运维文档**
  - [ ] 编写部署文档
  - [ ] 编写故障排查手册
  - [ ] 编写回滚方案

---

## 里程碑

| 日期 | 里程碑 | 交付物 |
|------|--------|--------|
| 2026-05-12 | Phase 1 完成 | FFmpeg 断流修复，重连成功率 > 95% |
| 2026-05-14 | Phase 2 完成 | 删除 1,400 行非核心代码 |
| 2026-05-21 | Phase 3 完成 | 服务合并，开播检测 < 60 秒 |
| 2026-05-24 | Phase 4 完成 | 飞书日报上线 |
| 2026-06-03 | 项目完成 | 全部验收通过，文档齐全 |

---

## 回滚方案

如果新架构出现严重问题，按以下步骤回滚：

1. **立即回滚**
   ```bash
   # 停止新服务
   systemctl stop live-platform
   
   # 启动旧服务
   systemctl start live-monitor
   systemctl start live-stream
   
   # 回滚代码
   git revert <commit-hash>
   ```

2. **数据恢复**
   ```bash
   # 恢复数据库备份
   cp backup/monitor.db.backup services/live-monitor/data/monitor.db
   ```

3. **验证**
   - 检查旧服务是否正常运行
   - 验证核心功能
   - 通知团队

---

## 注意事项

1. **每个 Phase 完成后必须验证核心功能正常**
2. **Phase 3（合并服务）风险最高，必须灰度发布**
3. **保留旧代码备份至少 1 个月**
4. **每次修改前先创建 git 分支**
5. **重要操作前先在测试环境验证**

---

**计划结束**
