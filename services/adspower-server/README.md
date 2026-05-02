# AdsPower 登录转发投屏服务

基于 FastAPI 的浏览器管理中间层服务，提供 AdsPower 浏览器环境管理、CDP 投屏转发、多平台登录监控和动态代理管理。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 环境配置

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

### 3. 运行

**快速启动（Windows CMD 双击运行）**：
- `start_pro.bat` — 生产环境

**命令行启动**：

```bash
# Bash / Git Bash
APP_ENV=dev python -m app.main     # 开发环境
APP_ENV=pro python -m app.main     # 生产环境

# Windows CMD
set APP_ENV=dev && python -m app.main
set APP_ENV=pro && python -m app.main
```

默认端口：8080

## 核心功能

### 1. 浏览器环境管理
- 调用 AdsPower API 创建/启动/关闭浏览器环境
- 自动清理过期环境（阈值策略）
- 关闭时仅 stop，不删除环境

### 2. CDP 投屏转发
- 通过 CDP WebSocket 获取投屏帧转发给前端
- 接收前端输入事件转发到浏览器
- 支持双向实时通信

### 3. 登录监控
- 支持 Shopee / TikTok / Lazada 三平台
- 使用 DrissionPage 操作浏览器检测登录状态
- 登录回调三种状态：

| login_status | 含义 | 触发场景 |
|---|---|---|
| `success` | 登录成功 | 检测到登录成功并验证店铺匹配 |
| `error` | 登录失败 | 超时、店铺不匹配、监听异常 |
| `closed` | 主动关闭 | API 关闭、WebSocket 断开、应用关闭 |

### 4. 动态代理管理
- 为浏览器环境配置动态代理
- 支持按需切换代理 IP

## 目录结构

```
app/
├── api/
│   ├── browser.py          # 浏览器管理接口
│   └── websocket.py        # WebSocket 投屏接口
├── services/
│   ├── adspower.py         # AdsPower API 封装
│   ├── login_monitor.py    # 登录监控（Shopee/TikTok/Lazada）
│   ├── screencast.py       # 投屏服务
│   ├── session.py          # 会话管理
│   ├── notification.py     # 登录回调通知
│   └── dynamic_proxy.py    # 动态代理管理
├── models/                  # 请求/响应模型
├── utils/                   # 工具模块
├── config.py               # 配置管理
└── main.py                 # 应用入口
```

## API 接口

### REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/browser/profile/create` | 创建并启动浏览器，返回 session_id |
| POST | `/api/browser/profile/close` | 关闭浏览器环境 |
| GET | `/docs` | Swagger 文档 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/screencast/{session_id}` | 投屏双向通信 |

WebSocket 消息类型：
- **下行**：投屏帧数据（base64 图片）
- **上行**：鼠标/键盘输入事件、页面导航指令

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
- 登录回调详细规格见 `.claude/references/login-callback-spec.md`
