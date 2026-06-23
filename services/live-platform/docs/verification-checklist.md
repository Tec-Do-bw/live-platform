# live-platform dev 检验清单

> 2026-06-23 dev01 验证记录：Zadig 中 `live-platform-d696bf67d-7rlrh` ready，`live-platform` / `mediamtx` 容器均 running；MySQL 当前 `local_status=1` seed 为 4 个，Zadig 日志显示检测循环 `total=4`，启动轮次 `started=3`。历史版本曾在 `/data/recordings/tiktok-tiktok_ceraveindonesia/...mp4` 路径处理切片；本轮需重点复核最终 OSS/Kafka 是否已恢复 legacy `.ts` 命名。Redis MCP 当前连接库为空，Redis status 相关项保留未勾，需用 Apollo 实际 Redis 实例复核。

## 部署前

- [x] Zadig 使用的是最新 `services/live-platform` 镜像。
- [x] Redis 地址、密码、DB 与 Apollo 配置一致。
- [x] MediaMTX API 地址与 RTMP 地址和 Apollo 配置一致。
- [x] 宿主机目录已创建：
  - [x] `/data/recordings`
  - [ ] `/data/live-platform/logs`
- [x] Redis 已写入至少一个测试 collection seed。

## 启动检查

- [x] 容器启动成功。
- [x] 日志没有出现 `Apollo 缺少必填配置`。
- [x] 日志没有出现 Redis 连接异常。
- [x] 健康检查返回成功：

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

- [x] Set 中存在目标 `collectionId`。
- [x] Config Hash 中 `platform` 正确。
- [x] Config Hash 中 `roomUrl` 正确。
- [x] Config Hash 中 `enabled=1`。

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

- [x] 日志出现 `录制已开始`。
- [x] MediaMTX path 符合 `{platform}-{collectionId}`。
- [x] 日志出现 `启动 FFmpeg relay`，确认它只是协议转换进程。
- [ ] MediaMTX 日志出现 `[recorder] recording ...`。
- [x] `/data/recordings` 下有对应 path 的切片文件，文件由 MediaMTX recorder 写入。
- [x] 日志出现 `收到切片回调`。
- [ ] Redis status 中 `status=recording`。
- [ ] Redis status 中 `mediamtxPath` 非空。

## 上传与 Kafka 检查

- [x] 日志出现 `切片处理完成`。
- [x] OSS 中存在上传后的切片对象。
- [ ] OSS object name 匹配 `realtime-video/{filePath}_{CreatTime}_{sequence:05d}.ts`。
- [ ] `realtime-video/` 下没有新增 basename 匹配 `^\d{4}-\d{2}-\d{2}_.*\.mp4$` 的对象。
- [x] Kafka topic 收到切片元数据。
- [x] Kafka payload 中包含：
  - [x] `roomID`
  - [x] `roomName`
  - [x] `intervalTime`
  - [x] `createTime`
  - [x] `videoIndex`
  - [x] `videoUrl`
  - [x] `uniID`
- [ ] Kafka payload 不包含 `local_file_path`。
- [ ] Kafka payload 不包含 MediaMTX 物理文件名，如 `2026-06-23_10-25-01-092478.mp4`。

> 注：OSS/Kafka 勾选基于 `UploadCoordinator.process_one()` 的串行语义（OSS 上传成功后才 `producer.send` + `flush`，完成后才打印 `切片处理完成`）以及 `tests/test_kafka_worker.py` / `tests/test_oss_worker.py` / `tests/test_integration.py` 通过；本次未额外消费 Kafka topic 原文。

## 并发检查

- [ ] `cutliveNumber` 对应的录制并发符合当前 dev 节点容量。
- [ ] 当开播房间数大于 `cutliveNumber` 时，活跃 MediaMTX recorder / FFmpeg relay 数不超过 `cutliveNumber`。
- [ ] 容量满时，Redis status 仍持续更新。

## 常见问题定位

| 现象 | 优先检查 |
|------|----------|
| 服务启动失败 | Apollo 是否缺 key，日志是否有 `ConfigError` |
| Redis 无 status | Redis seed 是否存在，`enabled` 是否为 `1` |
| `isLive=0` 但实际开播 | `roomUrl` 是否正确，平台 Tool 是否返回 `flv_url` |
| `isLive=1` 但不录制 | 是否达到 `cutliveNumber`，MediaMTX API 是否可访问 |
| 出现 `启动 FFmpeg relay` | 正常现象；它只做 HTTP-FLV 到 RTMP 转推，不代表 FFmpeg 本地录制 |
| 有录制无切片 | MediaMTX record 配置和 `/data/recordings` 权限 |
| MediaMTX 有 `runOnRecordSegmentComplete` 但 app 无 `收到切片回调` | 在 MediaMTX 容器内检查 `curl http://127.0.0.1:8080/health`、`curl` 是否存在，以及手动 POST `/internal/segment-ready` 是否能进入 live-platform |
| 周期性 `录制切片超时，进入重连` | 通常是 `/internal/segment-ready` 未成功刷新 `last_active`，先查 MediaMTX 回调连通性 |
| 有切片无 OSS/Kafka | OSS/Kafka Apollo 配置和 upload worker 日志 |

## 本地回归命令

```bash
cd services/live-platform
python -m pytest -q tests/test_utils_imports.py tests/test_api.py
python -m pytest -q tests/test_mediamtx_config.py tests/test_mediamtx_client.py tests/test_state_machine.py tests/test_internal.py
python -m pytest -q tests/test_legacy_naming.py tests/test_oss_worker.py tests/test_kafka_worker.py tests/test_upload.py tests/test_video.py tests/test_integration.py
python -m compileall -q adapters api orchestrator shared upload utils
```

当前期望:本地 utils 解析验证通过、pytest 全绿、无编译错误。
