# live-stream

> 通用编码规范、交互规范见根 `CLAUDE.md`。项目结构、启动命令、模块表、数据流、Apollo 引导变量见 `README.md`。本文仅记录约束与设计决策。

## 项目定位

直播视频流录制客户端（Windows 多机部署），调用链：live-monitor 房间分配 → 本服务 FFmpeg 拉流 → 切片 → OSS → Kafka。

## 平台差异（推流参数）

| 参数 | TikTok | Shopee |
|------|--------|--------|
| 读写超时 | 15s | 8s |
| 复用队列 | 1024 | 9999 |
| 视频元信息 | `parse_video_Info` | `parse_video_Info_shopee`（含 `shop_id`/`nickname` 等） |
| 平台判断 | 默认 | session 中含 `shop_id` |

修改推流参数时必须分别调整两条路径（`build_ffmpeg_command` 内部分支）。

## P0 断流问题：已知约束

| 约束 | 当前值 | 问题 |
|------|--------|------|
| 最大重试次数 | 默认 12 次，可用 Apollo `live_stream.max_retries` 调整 | 直播流波动频繁，不能 5 次就放弃 |
| 心跳检测间隔 | 默认 10s，可用 Apollo `live_stream.heartbeat_interval_seconds` 调整 | 更快发现 lease / 输出异常 |
| 无数据超时 | 默认 25s，可用 Apollo `live_stream.no_data_timeout_seconds` 调整 | 断流后更快触发重连 |
| 重试初始间隔 | 默认 1s，可用 Apollo `live_stream.retry_interval_seconds` 调整 | 减少短断流空窗 |
| 稳定运行判定 | 60s 后重置重试计数 | 合理但阈值可调 |

TikTok `play_urls` 里通常有多个 FLV 候选。拉流失败重连时先轮换备用 URL，再继续等待下一轮 live-monitor/Redis 刷新，避免一直重试同一个不稳定 CDN 边缘地址。

## 与 live-monitor 的交互规则

| 接口 | 方向 | 用途 |
|------|------|------|
| `POST /get_roominfo` | stream → monitor | 获取待录制房间（携带本机 IP） |
| `POST /report_roominfo` | stream → monitor | 上报在线房间和状态，返回需释放的房间 |
| `GET /check_status` | monitor → stream | 健康检查（端口 8080） |

约束：
- 轮询间隔 **3 分钟**，先上报再获取新房间
- 主备节点通过 Apollo `live_stream.primary_node_url` / `live_stream.backup_node_url` 配置
- 推流结束后**必须**从 `online_room_list` 移除房间，否则心跳误报

## 编码注意事项

- 单文件架构（TT_client.py），修改前通读相关模块
- 全局变量 `online_room_list` 和 `MainHelperObj` 在 `__main__` 中初始化，多线程共享
- `online_room_list` 是普通 dict，多线程读写**存在已知竞态风险**（技术债）
- 文件就绪判断：修改时间超过 2 秒 + 排除最后一个文件（可能正在写入）
- 切割产物文件名格式：`xxx_NNNNN.MMMMM.ts`，需与原始切片区分
