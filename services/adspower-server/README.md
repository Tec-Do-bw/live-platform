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

## 项目结构

```
adspower-server/
├── app/
│   ├── api/                    # API 路由
│   │   ├── browser.py         # 浏览器管理接口
│   │   └── websocket.py       # WebSocket 投屏接口
│   ├── services/               # 业务服务
│   │   ├── adspower.py        # AdsPower API 封装
│   │   ├── login_monitor.py   # 登录监控（Shopee/TikTok/Lazada）
│   │   ├── screencast.py      # 投屏服务
│   │   ├── session.py         # 会话管理
│   │   ├── notification.py    # 登录回调通知
│   │   ├── dynamic_proxy.py   # 动态代理管理
│   │   └── shopee_api.py      # Shopee 平台 API 调用封装
│   ├── models/                 # 数据模型
│   │   ├── request.py         # 请求模型
│   │   └── response.py        # 响应模型
│   ├── utils/
│   │   └── logger.py          # 日志配置
│   ├── config.py              # 配置管理
│   └── main.py                # FastAPI 应用入口
└── docs/
    └── archive/               # 历史方案与测试草稿
```

## 说明

- 登录回调规格见 `../../.claude/references/login-callback-spec.md`
- 项目约束与设计决策见 `CLAUDE.md`
- 服务默认使用 `app/config.py` 中的 `SERVER_PORT=8080`
