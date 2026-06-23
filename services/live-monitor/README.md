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
├── config.py                  # 浏览器配置、监听 URL 配置、版本历史
├── parseMian.py               # 直播间数据解析
├── check_cj_data.py           # CJ 数据校验
├── get_tt_Cookies.py          # TikTok Cookie 获取
├── business_functions.py      # 业务函数注册
├── start_scheduler.py         # 定时调度（GMV 实时、T+1 插件、基本信息采集）
├── env.example                # 环境变量样板
├── routes/
│   ├── websocket_routes.py    # WebSocket 端点、健康检查、Kafka 推送、节点日志同步
│   ├── activation.py          # 激活码管理（生成/验证/撤销，Redis 存储）
│   ├── live_status.py         # TikTok 批量开播状态 API（Redis 读取）
│   └── docs.py                # 文档、配置、离线任务、数据需求池相关 API
├── utils/
│   ├── Tools.py               # 通用工具（Kafka Producer、日志写入、API 配置生成）
│   ├── redis_bridge.py        # live-monitor/live-stream Redis 桥接仓储
│   ├── TiktokTool.py          # TikTok 直播间检测与流地址获取
│   ├── ShopeeTool.py          # Shopee 直播间检测与流地址获取
│   ├── LazadaTool.py          # Lazada 直播间检测与流地址获取
│   ├── serverTool.py          # Apollo 配置中心对接
│   ├── db_pool.py             # MySQL 连接池
│   ├── logger.py              # loguru 日志
│   ├── scheduler_manager.py   # 调度器管理
│   └── wrapper.py             # 装饰器工具
├── tasks/
│   └── scheduler_tasks.py     # 定时任务实现
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
| `/api/v1/tiktok/live-status/batch` | POST | 批量读取 TikTok 开播状态（Redis-only） |
| `/get_all_rooms` | GET | 获取全部房间列表 |
| `/sync_room_dict` | POST | 节点间房间数据同步 |
| `/sync_log` | POST | 节点间日志同步 |
| `/sync_offline_scripts` | POST | 节点间离线脚本同步 |
| `/ws/{user_id}` | WS | 插件 WebSocket 连接 |
| `/adsmeta/api/activation/*` | POST/GET | 激活码管理（verify/generate/revoke/status/available） |
| `/docs/*` | GET/POST | 配置管理、离线任务、数据需求池 API |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NODE_ID` | 节点标识 | `node1` |
| `NODE_IP` | 节点 IP | `127.0.0.1` |
| `PRIORITY` | 节点优先级（越大越优先） | `100` |
| `BACKUP_NODE_URL` | 备用节点 URL | 空 |
| `ISTEST` | 环境标识（0=生产, 1=测试） | `1` |
| `LIVE_STATUS_TTL_SECONDS` | Redis 直播状态 TTL | `900` |

详见 `env.example`。

## Redis 桥接

`live-monitor` 仍保留旧 `/get_roominfo` / `/report_roominfo`，同时将种子与直播状态双写 Redis：

- `live:monitor:collections`
- `live:collection:{collectionId}:config`
- `live:collection:{collectionId}:status`

`/api/v1/tiktok/live-status/batch` 只读 Redis，不触发 TikTok 请求。完整契约见 `../../docs/specs/live-monitor-stream-redis-bridge.md`。

## 相关文档

- 项目约束与设计决策：`CLAUDE.md`
- 接口规范：`docs/specs/`
