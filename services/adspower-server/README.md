# AdsPower 登录转发投屏服务

基于 FastAPI 的浏览器管理中间层服务，提供 AdsPower 浏览器环境管理、CDP 投屏转发、多平台登录监控和动态代理管理。

## 环境配置

通过 `APP_ENV` 环境变量区分开发/生产环境：

| 环境 | APP_ENV | 说明 |
|------|---------|------|
| 开发环境 | `dev`（默认） | 使用 test01 回调地址、DEBUG 日志 |
| 生产环境 | `pro` | 使用 livelabstar.com 回调地址、INFO 日志 |

**配置差异**：

| 配置项 | dev | pro |
|--------|-----|-----|
| 日志级别 | DEBUG | INFO |
| 回调 URL | test01-patrick-star.tec-develop.cn | www.livelabstar.com |
| 回调 Token | test token | pro token |

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

**Windows CMD 双击启动**：`start_pro.bat`（生产环境）。

**命令行指定环境**：

```bash
# Bash / Git Bash
APP_ENV=dev python -m app.main
APP_ENV=pro python -m app.main

# Windows CMD
set APP_ENV=dev && python -m app.main
```

## 核心功能

### 1. 浏览器环境管理
- 调用 AdsPower API 创建/启动/关闭浏览器环境
- 自动清理过期环境（`cleanup_old_profiles` 阈值策略）
- 关闭时仅 `stop_browser()`，**不删除**环境（详见 `CLAUDE.md`）

### 2. CDP 投屏转发
- 通过 CDP WebSocket 获取投屏帧转发给前端
- 接收前端输入事件转发到浏览器
- 双向实时通信

### 3. 登录监控
- 支持 Shopee / TikTok / Lazada 三平台
- 使用 DrissionPage 操作浏览器检测登录状态
- 登录回调三种状态见 `CLAUDE.md`

### 4. 动态代理管理
- 调用 kkoip API 获取 24 小时代理
- 含代理连通性验证

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

**WebSocket 消息类型**：
- **下行**（服务端 → 客户端）：投屏帧数据（base64 图片）
- **上行**（客户端 → 服务端）：鼠标/键盘输入事件、页面导航指令

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

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 浏览器控制 | AdsPower API + CDP |
| 页面操作 | DrissionPage |
| 实时通信 | WebSocket 双向通信 |
| 代理 | 动态代理（HTTP/SOCKS5） |

## 环境依赖

- Python 3.10+
- AdsPower 本地服务（默认端口 50325）

## 注意事项

- AdsPower 未运行时返回错误码 `-4`
- WebSocket 断开会触发资源清理
- 登录回调详细规格见 `../../.claude/rules/login-callback-spec.md`
- 项目约束与设计决策见 `CLAUDE.md`
- 服务默认使用 `app/config.py` 中的 `SERVER_PORT=8080`
