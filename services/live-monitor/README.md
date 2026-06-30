# live-monitor 直播间监控服务

> 主备高可用直播间监控核心服务（来源仓库 `liveSpider_Serverv3`）。负责直播间检测、房间状态管理、直播流地址获取、GMV 数据采集、插件 WebSocket 通信。

## 启动

```bash
pip install -r requirements.txt
python main.py                    # 默认端口 8080
curl http://localhost:8080/health # 健康检查
```

## 项目结构

```
live-monitor/
├── main.py                    # FastAPI 应用入口、核心路由（直播间检测、房间管理）
├── base.py                    # 基础类：AdsPowerHelper（浏览器管理）、MainHelper、OperateHelper
├── config.py                  # Apollo 配置访问门面 + 浏览器/API 文档等静态兼容配置
├── core/
│   └── apollo/                # Apollo 客户端（读取、热更新、本地缓存）
├── parseMian.py               # 直播间数据解析
├── check_cj_data.py           # CJ 数据校验
├── get_tt_Cookies.py          # TikTok Cookie 获取
├── business_functions.py      # 业务函数注册
├── start_scheduler.py         # 定时调度（GMV 实时、T+1 插件、基本信息采集）
├── env.example                # 环境变量样板
├── routes/
│   ├── websocket_routes.py    # WebSocket 端点、健康检查、Kafka 推送、节点日志同步
│   ├── activation.py          # 激活码管理（生成/验证/撤销，Redis 存储）
│   └── docs.py                # 文档、配置、离线任务、数据需求池相关 API
├── utils/
│   ├── Tools.py               # 通用工具（Kafka Producer、日志写入、API 配置生成）
│   ├── redis_bridge.py        # live-monitor/live-stream Redis 桥接仓储
│   ├── TiktokTool.py          # TikTok 直播间检测与流地址获取
│   ├── ShopeeTool.py          # Shopee 直播间检测与流地址获取
│   ├── LazadaTool.py          # Lazada 直播间检测与流地址获取
│   ├── db_pool.py             # MySQL 连接池
│   ├── logger.py              # loguru 日志
│   ├── scheduler_manager.py   # 调度器管理
│   └── wrapper.py             # 装饰器工具
├── tasks/
│   └── scheduler_tasks.py     # 定时任务实现
├── scripts/
│   ├── tiktok_live_stability_probe.py # TikTok 直播稳定性旁路探针
│   └── sync_tiktok_region.py  # TikTok 主播国家信息对比脚本
├── OfflineSpider/             # 离线爬虫脚本与配置
├── demo/                      # 示例脚本
├── query_helper/              # 查询辅助工具
└── docs/                      # 技术文档
    ├── specs/                 # 接口规范
    └── archive/               # 历史文档
```

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查（节点信息、连接数、房间数） |
| `/check_status` | GET | 心跳接口（兼容旧版） |
| `/liveRoom/portInfo` | POST | 获取 TikTok 直播流地址 |
| `/liveRoom/shopeeInfo` | POST | 获取 Shopee 直播流地址 |
| `/liveRoom/lazadaInfo` | POST | 获取 Lazada 直播流地址 |
| `/getCookies` | GET | 获取 TikTok Cookie |
| `/get_roominfo` | POST | 查询房间信息 |
| `/report_roominfo` | POST | 上报房间状态 |
| `/get_all_rooms` | GET | 获取全部房间列表 |
| `/sync_room_dict` | POST | 节点间房间数据同步 |
| `/sync_log` | POST | 节点间日志同步 |
| `/sync_offline_scripts` | POST | 节点间离线脚本同步 |
| `/ws/{user_id}` | WS | 插件 WebSocket 连接 |
| `/adsmeta/api/activation/*` | POST/GET | 激活码管理（verify/generate/revoke/status/available） |
| `/docs/*` | GET/POST | 配置管理、离线任务、数据需求池 API |

## 环境变量

Apollo 是业务配置唯一权威源，业务配置通过 `config.py` 门面读取。环境变量只保留 Apollo 引导参数。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APOLLOID` | Apollo app_id | `live-spider` |
| `APOLLO_URL` | Apollo 配置中心地址 | `http://dev-apollo.tec-develop.com` |
| `DEPLOY_ENV` | Apollo cluster（如 dev02 / PRO） | `dev02` |

已迁移到 Apollo 的旧环境变量：`NODE_ID`、`NODE_IP`、`PRIORITY`、`BACKUP_NODE_URL`、`ISTEST`、`ACCESS_KEY_ACTIVATION`、`LIVE_STATUS_TTL_SECONDS`。对应 key 为 `live_monitor.node_id`、`live_monitor.node_ip`、`live_monitor.priority`、`live_monitor.backup_node_url`、`live_monitor.access_key_activation`、`live_monitor.redis_status_ttl_seconds`；环境判断统一由 `DEPLOY_ENV` 决定。

## Redis 桥接

`live-monitor` 仍保留旧 `/get_roominfo` / `/report_roominfo`，同时将种子与直播状态双写 Redis：

- `live:monitor:collections`
- `live:collection:{collectionId}:config`
- `live:collection:{collectionId}:status`

下游查询入口已迁移到 `services/live-crawler/monitor/api/live_status_routes.py`；`live-monitor` 这里只负责写入 Redis 状态。完整契约见 `../../docs/specs/live-monitor-stream-redis-bridge.md`。

## 稳定性探针

`scripts/tiktok_live_stability_probe.py` 用于 15 分钟级别的旁路巡检：

- 正常时只记录状态快照和 FLV 指纹
- 异常时才触发 Playwright 页面验真，并生成 `anomalyReason` / `repairDirection`
- JSONL 日志写入 `logs/tiktok-live-stability/`

## 相关文档

- 项目约束与设计决策：`CLAUDE.md`
- 接口规范：`docs/specs/`
