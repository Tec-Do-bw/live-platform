from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from api.internal import internal_router
from api.routes import router
from orchestrator.scheduler import detect_rooms
from shared.config import settings
from shared.logger import configure_logging, get_logger
from upload.coordinator import upload_coordinator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(detect_rooms, "interval", seconds=settings.server.detect_interval_seconds)
    scheduler.start()
    await upload_coordinator.start()
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
    configure_logging()
    config = uvicorn.Config(create_app(), host=settings.server.host, port=settings.server.port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
