"""Cookie API 服务入口。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI

from monitor.api.cookie_routes import router as cookie_router
from monitor import get_db_connection, init_db


app = FastAPI(title="Cookie API", version="1.0")

init_db(get_db_connection())
app.include_router(cookie_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8777)
