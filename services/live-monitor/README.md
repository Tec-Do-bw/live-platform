# 🚀 liveSpider_Serverv2

**直播间监控系统 - 主备高可用架构 (Windows 精简版)**

---

## ⚡ 快速开始

### 1. 配置节点

**复制配置文件：**
```cmd
copy env.example .env
```

**编辑 `.env` 文件，填写节点信息：**

**主机1 配置：**
```ini
NODE_ID=node1
NODE_IP=47.237.6.199
PRIORITY=100
BACKUP_NODE_URL=http://47.236.42.104:8080
ISTEST=1
```

**主机2 配置：**
```ini
NODE_ID=node2
NODE_IP=47.236.42.104
PRIORITY=50
BACKUP_NODE_URL=http://47.237.6.199:8080
ISTEST=1
```

### 2. 安装依赖

```cmd
pip install -r requirements.txt
```

**注意：** 需要安装 `python-dotenv` 来自动加载 `.env` 文件（已包含在 requirements.txt 中）

### 3. 启动服务

```cmd
python main.py
```

**就这么简单！** 🎉

---

## 📦 包含的功能

一个 `main.py` 启动所有服务（自动启动 `start_scheduler.py`）：

- ✅ **FastAPI Web服务** - 提供HTTP API接口
- ✅ **WebSocket服务** - 实时数据推送
- ✅ **房间检测任务** - 每5分钟检测直播间状态
- ✅ **离线脚本监控** - 自动执行离线采集脚本
- ✅ **GMV实时采集** - 每5分钟采集GMV数据（通过start_scheduler）
- ✅ **T+1插件执行** - 每4小时执行T+1数据采集（通过start_scheduler）
- ✅ **基本信息采集** - 每天12点采集基本信息（通过start_scheduler）
- ✅ **主备自动切换** - 30秒内检测故障并切换
- ✅ **数据实时同步** - 每5分钟同步房间数据

---

## 🔍 验证服务

```cmd
REM 检查健康状态
curl http://localhost:8080/health

REM 查看日志
type main.log
```

**预期返回：**
```json
{
  "code": 200,
  "status": "healthy",
  "node_id": "node1",
  "priority": 100,
  "node_ip": "47.237.6.199",
  "room_count": 150
}
```

---

## 📚 文档

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - 详细部署指南
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - 快速参考卡
- **[env.example](env.example)** - 配置文件模板

---

## 🎯 主备架构

```
┌─────────────────────────────┐
│   主节点 (node1)              │
│   优先级: 100                 │
│   - 执行所有任务               │
│   - 同步数据到备节点           │
└─────────────────────────────┘
              │
              │ 心跳检测 (每10秒)
              ▼
┌─────────────────────────────┐
│   备节点 (node2)              │
│   优先级: 50                  │
│   - 监控主节点健康             │
│   - 主节点故障时接管           │
└─────────────────────────────┘
```

**自动故障切换：**
- 连续3次心跳失败（约30秒）→ 备节点接管
- 主节点恢复 → 立即切回主节点

---

## 🔧 常用命令

```cmd
REM 启动服务
python main.py

REM 查看日志
powershell -Command "Get-Content -Path main.log -Wait -Tail 20"

REM 检查进程
tasklist | findstr python.exe

REM 停止服务
taskkill /F /IM python.exe
```

---

## 🌟 特性

- ✅ **单一入口** - 一个命令启动所有服务
- ✅ **零依赖脚本** - 无需额外配置脚本
- ✅ **手动可控** - 所有配置手动编辑
- ✅ **Windows友好** - 完全适配Windows环境
- ✅ **精简架构** - 代码简洁，易于维护

---

## 📊 核心接口

| 接口 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /get_roominfo` | 获取可用房间 |
| `POST /report_roominfo` | 上报房间状态 |
| `POST /sync_room_dict` | 数据同步（内部） |
| `WS /ws/{user_id}` | WebSocket连接 |

---

## ⚠️ 注意事项

1. **防火墙规则** - 确保8080端口开放
2. **网络连通** - 两台服务器需要互相访问
3. **环境变量** - 首次启动前必须配置 `.env` 文件
4. **数据库访问** - 两台服务器都能访问同一个数据库

---

## 🆘 常见问题

**Q: 端口被占用怎么办？**
```cmd
netstat -ano | findstr :8080
taskkill /F /PID <PID>
```

**Q: 两个节点都在执行任务？**
- 检查网络连通性
- 检查防火墙规则
- 验证 `BACKUP_NODE_URL` 配置

**Q: 如何查看详细日志？**
```cmd
findstr /i "error" main.log
powershell -Command "Get-Content -Path main.log -Tail 50"
```

---

## 📞 技术支持

详细文档请参考：
- **部署指南**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **快速参考**: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

---

**v2.0 - 主备高可用架构** | **精简版** | **Windows优化**

