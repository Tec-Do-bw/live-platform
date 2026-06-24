# 直播数据采集系统

`services/live-crawler` 是直播数据采集服务，支持 TikTok、Shopee、Lazada 多平台采集。当前架构是浏览器采集 + HTTP 采集双轨并存：Shopee 仍走浏览器链路，Lazada 走 HTTP 链路，TikTok 已接入 HTTP 采集主链路但浏览器版仍保留为 fallback。

## 核心能力

- 多平台、多账号采集，支持从 AdsPower 分组动态获取账号。
- 新账号自动全量采集，后续按增量模式运行。
- Lazada 实时采集按间隔运行，日志独立写入 `logs/realtime/lazada/`。
- Lazada Cookie 养号服务独立运行，定时刷新 Cookie 并写登录态。
- TikTok HTTP 凭据刷新支持每日兜底和人工复登后 API 触发。
- 日报 Agent 基于普通采集日志生成 T-1 采集报告并推送飞书。

## Windows 生产启动

生产环境优先使用 Windows CMD。双击 `start_pro.bat` 会一次弹出多个独立窗口：

| 窗口 | 命令 | 作用 |
| --- | --- | --- |
| `live-crawler scheduler` | `python main.py --mode scheduler` | 主采集调度，包含历史采集和 Lazada realtime 间隔采集 |
| `live-crawler api` | `python -m monitor.server` | Cookie API + TikTok 凭据刷新 API + TikTok live-status/dashboard API，监听 `8777` |
| `live-crawler lazada-cookie-keeper` | `python -m cookie_keeper` | Lazada Cookie 养号服务 |
| `live-crawler daily-report` | `python -m scripts.daily_report` | 执行一次日报生成和推送，窗口保留 |
| `live-crawler refresh-tiktok-credentials` | `python -m jobs.refresh_tiktok_credentials` | 执行一次 TikTok 凭据刷新，窗口保留 |

`start_pro.bat` 会为每个窗口设置：

```bat
set APP_ENV=pro
set LOG_LEVEL=INFO
```

如果需要手动单独启动某个入口，先进入 `services/live-crawler`，再执行上表命令。

`python -m monitor.server` 现在也是 TikTok 直播大屏查询入口：

- `POST /api/v1/tiktok/live-status/batch`：读取 Redis 中的轻量开播状态，需 `X-API-Token`
- `POST /api/v1/tiktok/dashboard/data`：按 `dataType + roomId + collectionId` 拉取 TikTok 大屏原始响应信封，需 `X-API-Token`

## 常用手动命令

```bat
python main.py --mode once
python main.py --mode full
python main.py --mode full --workers N
python main.py --mode once --platform lazada
python main.py --mode once --crawl-type realtime
python -m scripts.daily_report --dry-run
python -m scripts.daily_report --date YYYY-MM-DD
python scripts/init_tracker.py
```

`--workers N` 仅在 `--mode full` 时生效。首次部署或新增历史账号批量接入前，先运行 `python scripts/init_tracker.py`，避免老账号被误判为新账号后重复全量。

## 模块概览

| 路径 | 职责 |
| --- | --- |
| `main.py` | 主入口，支持 scheduler / once / full 模式 |
| `scheduler/` | APScheduler 定时采集任务 |
| `crawlers/browser/` | Shopee 浏览器采集，以及 TikTok 浏览器 fallback |
| `crawlers/http/` | Lazada HTTP 采集和 TikTok HTTP 采集 |
| `cookie_keeper/` | Lazada Cookie 养号和 TikTok 凭据刷新实现 |
| `monitor/` | Cookie API、TikTok 刷新 API、TikTok live-status/dashboard API、登录状态兼容层 |
| `services/` | 数据上报、Cookie 管理、登录回调等共享业务服务 |
| `scripts/` | 日报、迁移、初始化等辅助脚本 |
| `utils/` | 日志、AdsPower 客户端、HTTP session、Kafka 等工具 |
| `tests/` | pytest 测试 |

## 日志

日志位于 `logs/`，保留 30 天：

- 普通入口：`logs/services/<entry>/YYYY-MM-DD.logs`
- 实时采集：`logs/realtime/<platform>/YYYY-MM-DD.logs`
- 日报只解析 `scheduler`、`manual_once`、`manual_full` 的普通采集日志，不读取 realtime 日志

常见入口名：

- `scheduler`
- `manual_once`
- `manual_full`
- `live_crawler_api`
- `cookie_keeper`
- `daily_report`
- `refresh_tiktok_credentials`

## 运行前检查

1. AdsPower 本地 API 可访问，默认 `http://127.0.0.1:50325`。
2. Kafka 和数据上报服务可访问。
3. `APP_ENV=pro` 时回调地址、数据服务器地址、Kafka 配置指向生产。
4. `resource/collection_tracker.json`、`account_status.json` 等运行时文件不要提交 git。
5. TikTok 生产是否走 HTTP 取决于平台配置或账号凭据中的 `crawler_mode=http`。

## 测试

```bat
python -m pytest tests/ -v
python -m pytest tests/monitor/ -v
python -m pytest tests/scripts/test_log_parser.py -v
```
