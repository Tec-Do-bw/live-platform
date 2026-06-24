"""Cookie API 服务入口。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI

from utils.logger import Logings

Logings.configure("live_crawler_api")

from monitor import get_db_connection, init_db
from monitor.api.cookie_routes import router as cookie_router
from monitor.api.dashboard_routes import router as dashboard_router
from monitor.api.live_status_routes import router as live_status_router
from monitor.api.tiktok_refresh_routes import router as tiktok_refresh_router


app = FastAPI(title="Live Crawler API", version="1.0")

init_db(get_db_connection())
app.include_router(cookie_router)
app.include_router(tiktok_refresh_router)
app.include_router(live_status_router)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8777)
