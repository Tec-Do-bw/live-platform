"""监控面板 FastAPI 服务入口

启动方式：cd live_dp && python -m monitor.server
"""

import sys
from pathlib import Path

# 确保 live_dp/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from monitor.api.batches import router as batches_router
from monitor.api.accounts import router as accounts_router
from monitor.api.registry_routes import router as registry_router
from monitor.api.overview import router as overview_router
from monitor.api.recrawl_routes import router as recrawl_router
from monitor.api.login_status_routes import router as login_status_router
from monitor.api.cookie_routes import router as cookie_router
from monitor.db import get_connection, init_db

app = FastAPI(title="采集完整性监控", version="1.0")

# 启动时确保数据库 schema 已迁移（补齐新增列等）
init_db(get_connection())

# 注册路由
app.include_router(batches_router)
app.include_router(accounts_router)
app.include_router(registry_router)
app.include_router(overview_router)
app.include_router(recrawl_router)
app.include_router(login_status_router)
app.include_router(cookie_router)

# 前端静态文件（构建后）
FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback：所有非 API 路由返回 index.html"""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8777)
