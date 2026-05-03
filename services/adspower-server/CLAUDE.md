# adspower-server

> 通用编码规范、交互规范见根目录 `CLAUDE.md`。以下仅记录 adspower-server 特有规则。

## 项目定位

- 中间层服务，不直接与前端交互
- 调用链路：前端 → 后端 → FastAPI（本项目）

## 目录结构

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
│   │   └── dynamic_proxy.py   # 动态代理管理
│   ├── models/                 # 数据模型
│   │   ├── request.py         # 请求模型
│   │   └── response.py        # 响应模型
│   ├── utils/                  # 工具模块
│   │   └── logger.py          # 日志配置
│   ├── config.py              # 配置管理
│   └── main.py                # FastAPI 应用入口
└── docs/                       # 技术设计与对接文档
```

## 运行命令

```bash
pip install -r requirements.txt
python -m app.main                              # 启动服务（默认端口 8000）
uvicorn app.main:app --reload --port 8000       # 开发模式（热重载）
```

## 登录回调规则

### login_status 三种值

| 值 | 含义 | 触发场景 |
|----|------|----------|
| `success` | 登录成功 | 检测到登录成功并验证店铺匹配 |
| `error` | 登录失败 | 超时、店铺不匹配、监听异常等 |
| `closed` | 主动关闭 | API关闭、WebSocket断开、应用关闭等（未完成登录流程） |

详细 reason 字段说明、Lazada 双端口登录流程、WebSocket 投屏功能见 `../.claude/references/login-callback-spec.md`。

## 浏览器环境管理规则

### 关闭浏览器时不删除环境

所有场景下关闭浏览器时，只调用 `stop_browser()`（仅关闭），不调用 `cleanup_browser()`（关闭+删除）。

**原因**：创建浏览器时已有自动清理机制（`cleanup_old_profiles`），会在未分组环境超过阈值时自动删除最旧的环境，无需在关闭时删除。

### 方法说明

| 方法 | 作用 | 使用场景 |
|------|------|----------|
| `stop_browser()` | 仅关闭浏览器，保留环境 | API关闭、WebSocket断开、登录完成、应用关闭 |
| `cleanup_browser()` | 关闭并删除环境 | 仅用于创建失败时的异常回滚 |