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

    state = await state_manager.on_segment_received(room_id)
    task = SegmentTask(
        room_id=state.live_room_id or room_id,
        mediamtx_path=request.path,
        file_path=Path(request.file_path),
        duration=request.duration,
        platform=state.platform,  # P2-5: 填入 platform 供 Kafka dataSource 使用
    )
    background_tasks.add_task(upload_coordinator.enqueue, task)
    return {"code": 200, "message": "accepted"}
