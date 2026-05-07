# live-platform

> 通用编码规范、交互规范见根 `CLAUDE.md`。项目结构、启动命令、API 清单、环境变量见 `README.md`。本文仅记录约束与设计决策。

## 项目定位

Phase 1 新服务，合并 `live-monitor` 的直播间取流能力与 `live-stream` 的录制/上传能力。Python 层只做编排，媒体录制底座交给 MediaMTX。

## 核心约束

- 房间状态必须通过 `orchestrator.state_machine.StateManager` 维护，不再用跨服务 HTTP 轮询同步状态。
- 录制健康判断以 MediaMTX 切片回调更新时间为准，默认超时 30 秒。
- FFmpeg 只负责 HTTP-FLV 到 RTMP 的协议转换，不负责切片、上传或业务状态判断。
- OSS 上传与 Kafka 推送必须通过 `upload.coordinator.UploadCoordinator` 串行编排，避免上传成功但消息未推送的状态漂移。
- 外部平台取流适配暂时复用 `services/live-monitor/utils/*Tool.py` 的旧逻辑，后续迁移时保持 `adapters.get_stream_info()` 的返回契约不变。

## MediaMTX 回调约定

`POST /internal/segment-ready` 是内部接口，只供 MediaMTX `runOnRecordSegmentComplete` 调用。请求体至少包含：

```json
{
  "path": "tiktok-123",
  "filePath": "/data/recordings/tiktok-123/segment.mp4"
}
```

`path` 可映射到状态机中的 `mediamtx_path`，接口会更新 `last_active` 并把切片推入上传队列。
