# AdsPower 登录转发投屏服务

基于 FastAPI 的浏览器管理中间层服务，提供 AdsPower 浏览器环境管理、CDP 投屏转发、多平台登录监控和动态代理管理。

## 启动

```bash
pip install -r requirements.txt
python -m app.main
```

默认端口：`8080`

开发模式：

```bash
uvicorn app.main:app --reload --port 8080
```

## 接口总览

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/browser/profile/create` | 创建并启动浏览器，返回 session_id |
| POST | `/api/browser/profile/close` | 关闭浏览器环境 |
| GET | `/docs` | Swagger 文档 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/remote/{session_id}` | 投屏双向通信 |

## 说明

- 登录回调规格见 `../../.claude/references/login-callback-spec.md`
- 详细项目规则见 `CLAUDE.md`
- 服务默认使用 `app/config.py` 中的 `SERVER_PORT=8080`
