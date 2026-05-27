# live-monitor

> 通用编码规范、交互规范见根 `CLAUDE.md`。项目结构、启动命令、API 清单、环境变量见 `README.md`。本文仅记录约束与设计决策。

## 项目定位

直播间监控核心服务（来源仓库 `liveSpider_Serverv3`），主备双节点高可用部署。

## 主备高可用机制

- 双节点通过 `NODE_ID`、`PRIORITY` 环境变量区分；主节点 `priority=100`，备节点 `priority=50`
- `/health` 端点返回节点状态，供对端和调度脚本判断可用性
- `/sync_log`、`/sync_room_dict`、`/sync_offline_scripts` 实现节点间数据同步

## 房间状态并发保护

`all_Live_Room_dict` 全局字典管理所有直播间状态，**必须**通过 `room_dict_lock` 加锁访问。

## WebSocket 通信

- `/ws/{user_id}` 端点供插件连接，由 `ConnectionManager` 管理生命周期，支持心跳检测和消息转发
- 连接状态定期推送到 Kafka topic `streamer_cj_user_notify`

## 定时采集任务

`start_scheduler.py` 启动三类任务：
- GMV 实时采集
- T+1 插件采集
- 基本信息采集

离线脚本通过 `OfflineSpider/offlineConfig.json` 配置，支持周期执行和定时启动。

## 直播流采集架构

- TikTok 实时路由（`/route/tiktok`）走 HTTP Downloader 路径，**不再依赖浏览器标签页池**：`utils/TiktokTool.py` 通过 `utils/downloader/`（基于 `never_primp`，含 L1 网络重试 + L2 HTTP 状态码退避 + L3 失败队列）完成抓取
- 代理策略（基于 `tests/proxy_stability/` 实测数据）：默认走 300 IP 静态池随机；请求失败（HTTP 5xx / 异常 / 直播页短响应 < 2000 字节）时由 Downloader 自动切换到 ipbiubiu 动态代理（一次一换 IP）重试。**禁止**在 `TiktokTool` 内部为单一代理类型写国家切换/兜底逻辑，新需求统一在 Downloader 层抽象
- 直播页短响应判定：通过 `Task.min_content_length=2000` 声明，由 Downloader L2 重试时自动换代理，业务层无需感知
- Lazada 走 `utils/LazadaTool.py`（Token 管理 + 请求签名）；Shopee 走 `utils/ShopeeTool.py`（多 UA 轮换）
- 路由请求构造 TikTok 实例时使用 `TiktokTool(ipList, no_proxy=True)` 显式声明无代理路径，避免误用全局代理

## 与 live-stream 的交互规则

- live-stream 通过 `/liveRoom/*Info` 接口获取直播流地址（`flv_url`），接口规范见 `docs/specs/live-room-api.md`
- 房间开播/下播事件通过 Kafka 消息通知 live-stream 启停录制
- 共享 Apollo 配置中心的数据库与 Kafka 配置
