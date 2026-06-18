# live-platform dev 检验清单

## 部署前

- [ ] Zadig 使用的是最新 `services/live-platform` 镜像。
- [ ] Redis 地址、密码、DB 与 Apollo 配置一致。
- [ ] MediaMTX API 地址与 RTMP 地址和 Apollo 配置一致。
- [ ] 宿主机目录已创建：
  - [ ] `/data/recordings`
  - [ ] `/data/live-platform/logs`
- [ ] Redis 已写入至少一个测试 collection seed。

## 启动检查

- [ ] 容器启动成功。
- [ ] 日志没有出现 `Apollo 缺少必填配置`。
- [ ] 日志没有出现 Redis 连接异常。
- [ ] 健康检查返回成功：

```bash
curl http://127.0.0.1:8080/health
```

期望：

```json
{
  "code": 200,
  "message": "live-platform is running"
}
```

## Redis Seed 检查

```bash
redis-cli SMEMBERS live:monitor:collections
redis-cli HGETALL live:collection:{collectionId}:config
```

- [ ] Set 中存在目标 `collectionId`。
- [ ] Config Hash 中 `platform` 正确。
- [ ] Config Hash 中 `roomUrl` 正确。
- [ ] Config Hash 中 `enabled=1`。

## 状态写入检查

等待至少一个 `livePlatformDetectIntervalSeconds` 周期后执行：

```bash
redis-cli HGETALL live:collection:{collectionId}:status
```

- [ ] `collectionId` 等于请求的 collectionId。
- [ ] `platform` 与 seed 一致。
- [ ] `roomUrl` 与 seed 一致。
- [ ] `updatedAt` 有值并持续刷新。
- [ ] 未开播时：
  - [ ] `isLive=0`
  - [ ] `roomId` 为空
  - [ ] `flvUrl` 为空
- [ ] 开播时：
  - [ ] `isLive=1`
  - [ ] `roomId` 为平台真实直播间号
  - [ ] `flvUrl` 为非空且不等于 `error`

## 录制链路检查

- [ ] 日志出现 `录制已开始`。
- [ ] MediaMTX path 符合 `{platform}-{collectionId}`。
- [ ] FFmpeg relay 进程存在。
- [ ] `/data/recordings` 下有对应 path 的切片文件。
- [ ] 日志出现 `收到切片回调`。
- [ ] Redis status 中 `status=recording`。
- [ ] Redis status 中 `mediamtxPath` 非空。

## 上传与 Kafka 检查

- [ ] 日志出现 `切片处理完成`。
- [ ] OSS 中存在上传后的切片对象。
- [ ] Kafka topic 收到切片元数据。
- [ ] Kafka payload 中包含：
  - [ ] `room_id`
  - [ ] `local_file_name`
  - [ ] `duration`
  - [ ] `videoUrl`
  - [ ] `dataSource`(格式 `live_crawler_{platform}`)

## 并发检查

- [ ] `cutliveNumber` 对应的录制并发符合当前 dev 节点容量。
- [ ] 当开播房间数大于 `cutliveNumber` 时，活跃 FFmpeg 录制数不超过 `cutliveNumber`。
- [ ] 容量满时，Redis status 仍持续更新。

## 常见问题定位

| 现象 | 优先检查 |
|------|----------|
| 服务启动失败 | Apollo 是否缺 key，日志是否有 `ConfigError` |
| Redis 无 status | Redis seed 是否存在，`enabled` 是否为 `1` |
| `isLive=0` 但实际开播 | `roomUrl` 是否正确，平台 Tool 是否返回 `flv_url` |
| `isLive=1` 但不录制 | 是否达到 `cutliveNumber`，MediaMTX API 是否可访问 |
| 有录制无切片 | MediaMTX record 配置和 `/data/recordings` 权限 |
| 有切片无 OSS/Kafka | OSS/Kafka Apollo 配置和 upload worker 日志 |

## 本地回归命令

```bash
cd services/live-platform
python -c "import utils.api_response; import sys; from pathlib import Path; sys.path.insert(0, str(Path('../live-monitor').resolve())); import importlib.util; assert importlib.util.find_spec('utils.TiktokTool'), 'namespace collision'"
python -m pytest -q
python -m compileall -q .
```

当前期望:命名空间包验证通过、pytest 全绿、无编译错误。
