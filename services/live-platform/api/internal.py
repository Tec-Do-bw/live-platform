from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.state_machine import state_manager
from shared.models import SegmentTask
from upload.coordinator import upload_coordinator

internal_router = APIRouter()


class SegmentReadyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    room_id: Optional[str] = None
    path: Optional[str] = None
    file_path: str = Field(alias="filePath")
    duration: Optional[float] = None


@internal_router.post("/segment-ready")
async def segment_ready(request: SegmentReadyRequest, background_tasks: BackgroundTasks) -> dict:
    room_id = request.room_id or request.path
    if not room_id:
        return {"code": 400, "message": "room_id/path is required"}

    # 进程重启后状态机内存清空，回调找不到状态 → 降级处理（避免 500）
    try:
        state = await state_manager.on_segment_received(room_id)
    except KeyError:
        # 状态不存在时记录警告但不阻断回调（MediaMTX 会继续录制）
        from shared.logger import get_logger
        logger = get_logger(__name__)
        logger.warning(
            f"切片回调时状态不存在（可能进程重启） | room_id={room_id} file={request.file_path}"
        )
        # 降级：不入上传队列，避免缺 platform 等字段导致上传失败
        return {"code": 202, "message": "accepted but state not found"}

    task = SegmentTask(
        room_id=state.live_room_id or room_id,
        mediamtx_path=request.path,
        file_path=Path(request.file_path),
        duration=request.duration,
        platform=state.platform,  # P2-5: 填入 platform 供 Kafka dataSource 使用
    )
    background_tasks.add_task(upload_coordinator.enqueue, task)
    return {"code": 200, "message": "accepted"}
