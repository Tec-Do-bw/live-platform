# liveSpider_Serverv2 主备节点部署指南 (Windows 简化版)

**一个入口启动所有服务** | **手动配置** | **精简部署**

---

## 📋 部署前准备

### 环境要求
- ✅ Windows Server 或 Windows 10/11
- ✅ Python 3.7+
- ✅ 两台服务器可以互相访问（HTTP通信）
- ✅ 防火墙已开放8080端口
- ✅ 两台服务器都能访问同一个数据库

### 安装依赖

```cmd
cd D:\SpiderCode\livelab\liveSpider_Serverv2
pip install -r requirements.txt
```

---

## 🔧 配置节点

### 主机1 (47.237.6.199) 配置

1. **复制配置文件**
```cmd
copy .env.example .env
```

2. **编辑 `.env` 文件**（使用记事本或VS Code）
```ini
NODE_ID=node1
NODE_IP=47.237.6.199
PRIORITY=100
BACKUP_NODE_URL=http://47.236.42.104:8080
ISTEST=1
```

3. **保存文件**

---

### 主机2 (47.236.42.104) 配置

1. **复制配置文件**
```cmd
copy .env.example .env
```

2. **编辑 `.env` 文件**
```ini
NODE_ID=node2
NODE_IP=47.236.42.104
PRIORITY=50
BACKUP_NODE_URL=http://47.237.6.199:8080
ISTEST=1
```

3. **保存文件**

---

## 🚀 启动服务

### 方式1：直接启动（开发测试）

```cmd
cd D:\SpiderCode\livelab\liveSpider_Serverv2
python main.py
```

**这将启动所有服务：**
- ✅ FastAPI Web服务
- ✅ WebSocket服务
- ✅ 房间检测任务（每5分钟）
- ✅ 离线脚本监控（每5分钟）
- ✅ GMV实时采集（每5分钟）- 通过start_scheduler自动启动
- ✅ T+1插件执行（每4小时）- 通过start_scheduler自动启动
- ✅ 基本信息采集（每天12点）- 通过start_scheduler自动启动
- ✅ 主备自动切换

> 💡 **说明**: `main.py` 会自动在后台线程中启动 `start_scheduler.py`，无需手动启动

---

### 方式2：后台运行（生产环境）

创建 `start.bat`:
```batch
@echo off
title LiveSpider_Server_%NODE_ID%
cd /d D:\SpiderCode\livelab\liveSpider_Serverv2
python main.py
```

**运行：**
```cmd
start /MIN start.bat
```

---

### 方式3：使用 PowerShell（推荐）

创建 `start.ps1`:
```powershell
$env:NODE_ID = "node1"
$env:NODE_IP = "47.237.6.199"
$env:PRIORITY = "100"
$env:BACKUP_NODE_URL = "http://47.236.42.104:8080"
$env:ISTEST = "1"

Set-Location "D:\SpiderCode\livelab\liveSpider_Serverv2"
python main.py
```

**运行：**
```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

---

## ✅ 验证服务

### 检查服务状态

```cmd
REM 方式1：使用curl
curl http://localhost:8080/health

REM 方式2：使用PowerShell
powershell -Command "(Invoke-WebRequest -Uri 'http://localhost:8080/health').Content | ConvertFrom-Json"
```

**预期返回（主机1）：**
```json
{
  "code": 200,
  "status": "healthy",
  "timestamp": 1234567890000,
  "node_id": "node1",
  "priority": 100,
  "node_ip": "47.237.6.199",
  "room_count": 0,
  "ws_connections": 0
}
```

**预期返回（主机2）：**
```json
{
  "code": 200,
  "status": "healthy",
  "node_id": "node2",
  "priority": 50,
  "node_ip": "47.236.42.104",
  "room_count": 0
}
```

---

## 📊 查看日志

### 实时日志

```cmd
REM PowerShell 实时监控
powershell -Command "Get-Content -Path main.log -Wait -Tail 20"
```

### 查看最后N行

```cmd
powershell -Command "Get-Content -Path main.log -Tail 50"
```

### 搜索错误

```cmd
findstr /i "error" main.log
```

---

## 🧪 功能测试

### 测试1: 正常状态

**主机1应该显示：**
```
🚀 定时调度器已启动
✅ 已配置: 基本信息采集 (每天12点)
✅ 已配置: T+1插件采集 (每4小时)
✅ 已配置: GMV实时采集 (每5分钟)
⏰ 定时任务调度器已启动
[定时任务] 节点 node1 开始执行...
Cookie池刷新成功 | 数量=20
数据库同步完成 | 当前监控房间数=150
[数据同步] 已同步数据到备节点 | 房间数=150
[节点 node1 执行任务: GMV实时采集]
```

**主机2应该显示：**
```
🚀 定时调度器已启动
✅ 已配置: 基本信息采集 (每天12点)
✅ 已配置: T+1插件采集 (每4小时)
✅ 已配置: GMV实时采集 (每5分钟)
⏰ 定时任务调度器已启动
[定时任务] 备节点 node2 待命中... (主节点正常运行)
[备节点 node2 待命中...]
```

---

### 测试2: 故障切换

**在主机1上停止服务：**
```cmd
REM Ctrl+C 停止，或者直接关闭CMD窗口
```

**等待30秒，主机2日志应该显示：**
```
[定时任务] 主节点健康检查失败 (1/3)
[定时任务] 主节点健康检查失败 (2/3)
[定时任务] 主节点健康检查失败 (3/3)
✅ [定时任务] 主节点故障，备节点 node2 接管任务执行
[定时任务] 节点 node2 开始执行...
✅ [调度器] 主节点故障，备节点 node2 接管任务执行
[节点 node2 执行任务: GMV实时采集]
[节点 node2 执行任务: T+1插件执行]
```

---

### 测试3: 故障恢复

**在主机1上重启服务：**
```cmd
python main.py
```

**主机2日志应该显示：**
```
[定时任务] 主节点已恢复，备节点停止执行
[定时任务] 备节点 node2 待命中... (主节点正常运行)
[调度器] 主节点已恢复
[备节点 node2 待命中...]
```

---

## 🔍 常见问题

### 问题1: 端口被占用

**现象：**
```
OSError: [WinError 10048] 通常每个套接字地址只允许使用一次
```

**解决：**
```cmd
REM 查看端口占用
netstat -ano | findstr :8080

REM 结束进程
taskkill /F /PID <PID>
```

---

### 问题2: 两个节点都在执行任务

**原因：** 网络不通或防火墙阻止

**排查：**
```cmd
REM 测试网络连通性
ping 47.236.42.104

REM 测试端口
telnet 47.236.42.104 8080

REM 或使用 PowerShell
Test-NetConnection -ComputerName 47.236.42.104 -Port 8080
```

**解决：**
```cmd
REM 添加防火墙规则（管理员权限）
netsh advfirewall firewall add rule name="LiveSpider Port 8080" dir=in action=allow protocol=TCP localport=8080
```

---

### 问题3: 数据未同步

**排查：**
```cmd
REM 查看同步日志
findstr "数据同步" main.log

REM 检查备用节点配置
type .env | findstr BACKUP_NODE_URL

REM 测试备用节点连通性
curl http://<备用节点IP>:8080/health
```

---

### 问题4: 找不到Python

**解决：**
```cmd
REM 检查Python是否在PATH中
where python

REM 如果没有，使用完整路径
C:\Users\<用户名>\AppData\Local\Programs\Python\Python39\python.exe main.py
```

---

## 📁 文件说明

```
liveSpider_Serverv2/
├── main.py                    # ⭐ 主启动文件（所有功能入口）
├── .env                       # 节点配置文件（手动创建）
├── .env.example               # 配置文件模板
├── start.bat                  # Windows启动脚本（可选）
├── DEPLOYMENT_GUIDE.md        # 本文件（部署指南）
├── QUICK_REFERENCE.md         # 快速参考卡
└── requirements.txt           # Python依赖
```

---

## 🎯 配置速查表

| 配置项 | 主机1 | 主机2 |
|--------|-------|-------|
| NODE_ID | `node1` | `node2` |
| NODE_IP | `47.237.6.199` | `47.236.42.104` |
| PRIORITY | `100` | `50` |
| BACKUP_NODE_URL | `http://47.236.42.104:8080` | `http://47.237.6.199:8080` |

---

## 💡 最佳实践

### 1. 开机自启动

使用Windows任务计划程序：

1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：**启动时**
4. 操作：**启动程序**
   - 程序：`python.exe` 或完整路径
   - 参数：`main.py`
   - 起始于：`D:\SpiderCode\livelab\liveSpider_Serverv2`
5. 完成

---

### 2. 日志轮转

创建 `cleanup_logs.bat`:
```batch
@echo off
REM 每天运行，清理7天前的日志
forfiles /p "D:\SpiderCode\livelab\liveSpider_Serverv2" /m *.log /d -7 /c "cmd /c del @path"
```

使用任务计划程序，每天凌晨2点运行。

---

### 3. 监控脚本

创建 `monitor.bat`:
```batch
@echo off
:loop
cls
echo ==========================================
echo 服务监控 - %date% %time%
echo ==========================================
echo.

REM 检查进程
tasklist | findstr python.exe
if %errorlevel%==0 (
    echo [进程] 运行中
) else (
    echo [进程] 未运行！
)

echo.

REM 检查健康状态
curl -s http://localhost:8080/health
if %errorlevel%==0 (
    echo [健康] 正常
) else (
    echo [健康] 异常！
)

echo.
echo ==========================================
timeout /t 60
goto loop
```

---

## 🆘 紧急处理

### 快速重启

```cmd
REM 停止所有Python进程
taskkill /F /IM python.exe

REM 等待3秒
timeout /t 3

REM 重启服务
cd D:\SpiderCode\livelab\liveSpider_Serverv2
python main.py
```

---

### 完全重置

```cmd
REM 1. 停止服务
taskkill /F /IM python.exe

REM 2. 清理日志
del /F main.log

REM 3. 重新配置
notepad .env

REM 4. 重启服务
python main.py
```

---

## ✨ 架构优势

- ✅ **单一启动入口** - 只需运行 `python main.py`
- ✅ **自动故障切换** - 30秒内检测并切换
- ✅ **数据实时同步** - 每5分钟同步房间数据
- ✅ **手动可控** - 所有配置都是手动编辑
- ✅ **精简架构** - 无需额外脚本和工具
- ✅ **Windows友好** - 完全适配Windows环境

---

## 📞 验证检查点

部署完成后，确认：

- [ ] 主机1的 `/health` 返回 `node_id: node1, priority: 100`
- [ ] 主机2的 `/health` 返回 `node_id: node2, priority: 50`
- [ ] 主机1执行任务，主机2待命
- [ ] 停止主机1后，主机2接管
- [ ] 恢复主机1后，主机2停止执行
- [ ] 两台服务器的 `room_count` 一致

---

**部署完成！** 🎉

**启动命令：**
```cmd
python main.py
```

就这么简单！

