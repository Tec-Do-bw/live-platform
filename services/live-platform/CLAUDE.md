# live-platform

> 通用编码规范、交互规范见根 `CLAUDE.md`。项目结构、启动命令、API 清单、环境变量见 `README.md`。本文仅记录约束与设计决策。

## 项目定位

Phase 1 新服务，合并 `live-monitor` 的直播间取流能力与 `live-stream` 的录制/上传能力。Python 层只做编排，媒体录制底座交给 MediaMTX。

## 核心约束

- 房间状态必须通过 `orchestrator.state_machine.StateManager` 维护，不再用跨服务 HTTP 轮询同步状态。
- 录制健康判断以 MediaMTX 切片回调更新时间为准，默认超时 30 秒。
- FFmpeg relay 只负责 HTTP-FLV 到 RTMP 的协议转换；长切片兼容拆分只能在 `UploadCoordinator` 回调后按需使用 `ffmpeg -c copy`，不替代 MediaMTX recorder。
- OSS 上传与 Kafka 推送必须通过 `upload.coordinator.UploadCoordinator` 串行编排，避免上传成功但消息未推送的状态漂移。
- 外部平台取流适配通过本地 `utils/*Tool.py` 维护旧取流工具副本，迁移时保持 `adapters.get_stream_info()` 的返回契约不变。

## OSS/Kafka Legacy Compatibility

- OSS object name 与 Kafka video identity 必须使用 legacy basename `{filePath}_{CreatTime}_{sequence:05d}.ts`。
- MediaMTX 物理回调文件名只用于读取本地文件内容，不可作为业务文件名。
- 缺少 `filePath` 必须直接失败；禁止 fallback 到 `2026-...mp4` 这类物理文件名。
- OSS 与 Kafka 必须共享同一个 `upload.legacy_naming.LegacySegmentName` 值。
- MediaMTX 录制格式需保持 `recordFormat: mpegts`；不要用 `.ts` 后缀伪装 MP4 内容。

## MediaMTX 回调约定

`POST /internal/segment-ready` 是内部接口，只供 MediaMTX `runOnRecordSegmentComplete` 调用。请求体至少包含：

```json
{
  "path": "tiktok-123",
  "filePath": "/data/recordings/tiktok-123/2026-06-23_10-25-01-092478.ts"
}
```

`path` 可映射到状态机中的 `mediamtx_path`，接口会更新 `last_active` 并把切片推入上传队列。`filePath` 是 MediaMTX 物理文件路径，不是最终 OSS/Kafka 业务文件名。
