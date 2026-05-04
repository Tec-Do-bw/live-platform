# live-monitor

> 通用编码规范、交互规范见根目录 `CLAUDE.md`。以下仅记录 live-monitor 特有规则。

## 项目定位

- 直播间监控核心服务，来源仓库 `liveSpider_Serverv3`
- 职责：直播间检测、房间状态管理、直播流地址获取、GMV 数据采集、插件 WebSocket 通信
- 主备双节点高可用部署，通过优先级选主

## 目录结构

```
live-monitor/
├── main.py                    # FastAPI 应用入口，核心路由（直播间检测、房间管理）
├── base.py                    # 基础类：AdsPowerHelper（浏览器管理）、MainHelper、OperateHelper
├── config.py                  # 配置管理：浏览器配置、监听 URL 配置、版本历史
├── parseMian.py               # 直播间数据解析
├── check_cj_data.py           # CJ 数据校验
├── get_tt_Cookies.py          # TikTok Cookie 获取
├── business_functions.py      # 业务函数注册
├── start_scheduler.py         # 定时调度：GMV 实时采集、T+1 插件采集、基本信息采集
├── routes/
│   ├── websocket_routes.py    # WebSocket 端点、健康检查、Kafka 推送、节点日志同步
│   ├── activation.py          # 激活码管理（生成/验证/撤销，Redis 存储）
│   └── docs.py                # 文档管理面板、离线任务管理、配置生成器、数据需求池
├── utils/
│   ├── Tools.py               # 通用工具：Kafka Producer、日志写入、API 配置生成
│   ├── TiktokTool.py          # TikTok 直播间检测与流地址获取
│   ├── ShopeeTool.py          # Shopee 直播间检测与流地址获取
│   ├── LazadaTool.py          # Lazada 直播间检测与流地址获取
│   ├── serverTool.py          # Apollo 配置中心对接
│   ├── db_pool.py             # MySQL 数据库连接池
│   ├── logger.py              # 日志配置（loguru）
│   ├── scheduler_manager.py   # 调度器管理
│   └── wrapper.py             # 装饰器工具
├── tasks/
│   └── scheduler_tasks.py     # 定时任务实现（GMV/T+1/基本信息采集）
├── OfflineSpider/             # 离线爬虫脚本与配置
├── ReCrawl/                   # 重爬任务脚本
├── static/                    # 前端页面（管理面板、文档、登录等）
├── demo/                      # 示例脚本
├── query_helper/              # 查询辅助工具
└── docs/                      # 技术文档
    ├── specs/                 # 接口规范
    └── archive/               # 历史文档
```

## 运行命令

```bash
pip install -r requirements.txt
python main.py                                    # 启动服务（默认端口 8080）
curl http://localhost:8080/health                  # 健康检查
```

## 核心架构

### 主备高可用

- 双节点部署，通过 `NODE_ID`、`PRIORITY` 环境变量区分主备
- 主节点（node1, priority=100）、备节点（node2, priority=50）
- `/health` 端点返回节点状态，供对端和调度脚本判断可用性
- `/sync_log`、`/sync_room_dict`、`/sync_offline_scripts` 实现节点间数据同步

### 房间检测与状态管理

- `all_Live_Room_dict` 全局字典管理所有直播间状态，`room_dict_lock` 线程锁保护并发访问
- `/liveRoom/portInfo`（TikTok）、`/liveRoom/shopeeInfo`（Shopee）、`/liveRoom/lazadaInfo`（Lazada）获取直播流地址
- `/get_roominfo` 查询房间信息、`/report_roominfo` 上报房间状态、`/get_all_rooms` 获取全部房间
- 浏览器管理通过 `base.py` 中的 `AdsPowerHelper` + DrissionPage 实现

### WebSocket 通信

- `/ws/{user_id}` 端点，插件通过 WebSocket 连接上报数据
- `ConnectionManager` 管理连接生命周期，支持心跳检测和消息转发
- 连接状态定期推送到 Kafka（topic: `streamer_cj_user_notify`）

### 定时采集任务

- `start_scheduler.py` 启动 GMV 实时采集、T+1 插件采集、基本信息采集
- 离线脚本通过 `OfflineSpider/offlineConfig.json` 配置，支持周期执行和定时启动
- 哨兵线程 `sentryTabItem` 监控浏览器进程健康，自动重启异常 tab

## API 接口清单

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查（含节点信息、连接数、房间数） |
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
| `/docs/*` | GET/POST | 文档面板、配置管理、离线任务、数据需求池 |

## 与 live-stream 的交互规则

- live-monitor 通过 `/liveRoom/*Info` 接口获取直播流地址（flv_url）
- live-stream 服务消费这些流地址进行 FFmpeg 录制
- 房间状态变更（开播/下播）通过 Kafka 消息通知 live-stream 启停录制
- 两个服务共享 Apollo 配置中心的数据库和 Kafka 连接配置

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `NODE_ID` | 节点标识 | `node1` |
| `NODE_IP` | 节点 IP | `127.0.0.1` |
| `PRIORITY` | 节点优先级（越大越优先） | `100` |
| `BACKUP_NODE_URL` | 备用节点 URL | 空 |
| `ISTEST` | 环境标识（0=生产, 1=测试） | `1` |

详见 `env.example`。
