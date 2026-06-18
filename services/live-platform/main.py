from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from adapters import get_stream_url
from api.internal import internal_router
from api.routes import router
from orchestrator.scheduler import detect_rooms
from orchestrator.state_machine import state_manager
from shared.config import settings
from shared.logger import configure_logging, get_logger
from upload.coordinator import upload_coordinator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P0-2: Apollo 配置预加载到线程,避免首次访问 settings 时在 event loop 同步阻塞
    await asyncio.to_thread(settings.load)

    # P1-4: 注入 stream_resolver 使断流重连能重新获取流地址
    state_manager.stream_resolver = get_stream_url

    scheduler = AsyncIOScheduler()
    scheduler.add_job(detect_rooms, "interval", seconds=settings.server.detect_interval_seconds)
    scheduler.start()
    await upload_coordinator.start(worker_count=settings.upload.worker_count)
    logger.info("live-platform 已启动")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await upload_coordinator.stop()
        logger.info("live-platform 已停止")


def create_app() -> FastAPI:
    app = FastAPI(title="Live Platform", lifespan=lifespan)
    app.include_router(router)
    app.include_router(internal_router, prefix="/internal")
    return app


async def main() -> None:
    await asyncio.to_thread(settings.load)
    configure_logging()
    config = uvicorn.Config(create_app(), host=settings.server.host, port=settings.server.port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
