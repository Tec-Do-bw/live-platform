# liveSpider_Serverv2 主备节点部署指南

基于HTTP心跳的主备自动切换架构

---

## 📋 部署前检查清单

- [ ] 两台服务器都可以访问
- [ ] 两台服务器都安装了Python 3.7+
- [ ] 两台服务器都能访问同一个数据库
- [ ] 两台服务器之间可以互相访问（HTTP通信）
- [ ] 防火墙已开放8080端口
- [ ] 已安装必要的Python依赖 (`pip install -r requirements.txt`)

---

## 🔧 配置差异对照表

### 主机1 (47.237.6.199)

**环境变量配置：**
```bash
NODE_ID=node1
NODE_IP=47.237.6.199
PRIORITY=100
BACKUP_NODE_URL=http://47.236.42.104:8080
ISTEST=1  # 0=生产环境, 1=测试环境
```

---

### 主机2 (47.236.42.104)

**环境变量配置：**
```bash
NODE_ID=node2
NODE_IP=47.236.42.104
PRIORITY=50
BACKUP_NODE_URL=http://47.237.6.199:8080
ISTEST=1  # 0=生产环境, 1=测试环境
```

---

## 📦 主机1部署步骤

### 1. 上传代码到服务器

```bash
# 通过scp或其他方式上传整个 liveSpider_Serverv2 目录
cd /path/to/project
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置节点

```bash
cd liveSpider_Serverv2
chmod +x configure_node.sh
./configure_node.sh node1
```

> 💡 此脚本会自动生成 `.env` 配置文件

### 4. 启动服务

**启动 FastAPI Web服务：**
```bash
export $(cat .env | xargs) && nohup python main.py > main.log 2>&1 &
```

**启动定时调度器（可选）：**
```bash
export $(cat .env | xargs) && nohup python start_scheduler.py > scheduler.log 2>&1 &
```

### 5. 验证服务

```bash
# 测试健康检查端点
curl http://47.237.6.199:8080/health

# 预期返回:
# {
#   "code": 200,
#   "status": "healthy",
#   "timestamp": ...,
#   "node_id": "node1",
#   "priority": 100,
#   "node_ip": "47.237.6.199",
#   "room_count": 0,
#   "ws_connections": 0
# }

# 查看日志
tail -f main.log
tail -f scheduler.log
```

---

## 📦 主机2部署步骤

### 1. 上传代码到服务器

```bash
# 与主机1相同的代码
cd /path/to/project
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置节点

```bash
cd liveSpider_Serverv2
chmod +x configure_node.sh
./configure_node.sh node2
```

> ⚠️ 注意：主机2配置为 `node2`

### 4. 启动服务

```bash
# 启动 FastAPI Web服务
export $(cat .env | xargs) && nohup python main.py > main.log 2>&1 &

# 启动定时调度器（可选）
export $(cat .env | xargs) && nohup python start_scheduler.py > scheduler.log 2>&1 &
```

### 5. 验证服务

```bash
curl http://47.236.42.104:8080/health

# 预期返回:
# {
#   "code": 200,
#   "status": "healthy",
#   "timestamp": ...,
#   "node_id": "node2",
#   "priority": 50,
#   "node_ip": "47.236.42.104",
#   "room_count": 0,
#   "ws_connections": 0
# }

# 查看备节点日志（应该显示在待命状态）
tail -f main.log
```

---

## 🧪 功能测试

### 测试1: 正常状态

**主机1日志应该显示:**
```
[定时任务] 节点 node1 开始执行...
Cookie池刷新成功 | 数量=20
[数据同步] 已同步数据到备节点 | 房间数=150
⏰ 等待下次检测（5分钟后）
```

**主机2日志应该显示:**
```
[定时任务] 备节点 node2 待命中... (主节点正常运行)
```

---

### 测试2: 故障切换

**在主机1上停止定时任务（模拟主节点故障）:**
```bash
# 停止main.py进程
pkill -f "python main.py"
```

**等待30秒，观察主机2日志:**
```
[定时任务] 主节点健康检查失败 (1/3): ...
[定时任务] 主节点健康检查失败 (2/3): ...
[定时任务] 主节点健康检查失败 (3/3): ...
✅ [定时任务] 主节点故障，备节点 node2 接管任务执行
[定时任务] 节点 node2 开始执行...
Cookie池刷新成功 | 数量=20
```

---

### 测试3: 故障恢复

**在主机1上重启服务:**
```bash
export $(cat .env | xargs) && nohup python main.py > main.log 2>&1 &
```

**主机2日志应该显示:**
```
[定时任务] 主节点已恢复，备节点停止执行
[定时任务] 备节点 node2 待命中... (主节点正常运行)
```

---

### 测试4: 数据同步验证

**在主机1上访问房间数据接口:**
```bash
curl http://47.237.6.199:8080/health
# 查看 room_count 字段
```

**在主机2上访问相同接口（应该返回相同的 room_count）:**
```bash
curl http://47.236.42.104:8080/health
# room_count 应该与主机1一致（每5分钟同步一次）
```

---

## 🔍 日常监控

### 查看服务状态

```bash
# 查看进程
ps aux | grep python

# 查看Web服务日志
tail -100 main.log
tail -f main.log

# 查看定时调度日志
tail -100 scheduler.log
tail -f scheduler.log
```

### 查看节点健康状态

```bash
# 主机1
curl http://47.237.6.199:8080/health | python -m json.tool

# 主机2
curl http://47.236.42.104:8080/health | python -m json.tool
```

### 查看WebSocket连接数

```bash
# 获取活跃连接
curl http://47.237.6.199:8080/get_active_connections | python -m json.tool
```

---

## ⚠️ 故障排查

### 问题1: 两个节点都在执行任务

**原因:** 主机2无法访问主机1的健康检查端点

**排查:**
```bash
# 在主机2上测试
curl http://47.237.6.199:8080/health

# 如果失败，检查防火墙
sudo iptables -L -n | grep 8080

# 检查服务是否在监听
netstat -tulpn | grep 8080
```

**解决:** 开放防火墙端口或修复网络连接

---

### 问题2: 备节点一直显示主节点故障

**原因:** 主节点的health端点返回异常

**排查:**
```bash
# 检查主节点health返回内容
curl -v http://47.237.6.199:8080/health

# 检查是否返回 "code": 200
```

**解决:** 确保主节点服务正常运行，返回正确的JSON格式

---

### 问题3: 数据未同步到备节点

**原因:** 主节点无法访问备节点的同步接口

**排查:**
```bash
# 在主机1上测试
curl -X POST http://47.236.42.104:8080/sync_room_dict \
  -H "Content-Type: application/json" \
  -d '{"room_dict":{}, "timestamp":0, "node_id":"test"}'

# 查看主机1日志中的同步错误
grep "数据同步" main.log
```

**解决:** 
- 确保备节点服务正常运行
- 检查网络连接
- 查看BACKUP_NODE_URL是否配置正确

---

### 问题4: 进程意外退出

**排查:**
```bash
# 查看日志中的错误
tail -100 main.log | grep -i error
tail -100 scheduler.log | grep -i error

# 检查Python进程
ps aux | grep python
```

**解决:**
- 检查数据库连接是否正常
- 检查Apollo配置是否可访问
- 确保依赖包都已正确安装

---

## 📊 架构优势总结

✅ **无需数据库表** - 零额外依赖，通过HTTP心跳实现  
✅ **自动故障切换** - 30秒内检测并切换  
✅ **自动故障恢复** - 主节点恢复后立即切回  
✅ **数据实时同步** - 每5分钟同步房间数据  
✅ **双重保障** - Web服务 + 定时调度都有高可用  
✅ **易于部署** - 一键配置脚本，无需手动修改代码

---

## 📞 技术支持

如有问题，请查看日志文件：
- `main.log` - Web服务日志
- `scheduler.log` - 定时调度日志
- `logs/socketLog/socket_YYYYMMDD.log` - WebSocket连接日志

**常用调试命令:**
```bash
# 查看实时日志
tail -f main.log

# 搜索错误日志
grep -i error main.log

# 查看最近的50条日志
tail -50 main.log

# 查看进程状态
ps aux | grep python

# 重启服务
pkill -f "python main.py" && \
export $(cat .env | xargs) && \
nohup python main.py > main.log 2>&1 &
```

---

## 🎯 部署检查点

部署完成后，确认以下几点：

- [ ] 主机1的health返回 `node_id: node1, priority: 100`
- [ ] 主机2的health返回 `node_id: node2, priority: 50`
- [ ] 主机1日志显示"节点 node1 开始执行..."
- [ ] 主机2日志显示"备节点 node2 待命中..."
- [ ] 停止主机1后，主机2接管任务
- [ ] 恢复主机1后，主机2停止执行
- [ ] 两台服务器的 `room_count` 数据一致（每5分钟同步）
- [ ] WebSocket连接正常（通过 /get_active_connections 验证）

---

## 🔄 升级和回滚

### 升级步骤

1. 先升级备节点（主机2）
2. 验证备节点功能正常
3. 停止主节点（主机1），备节点自动接管
4. 升级主节点
5. 启动主节点，自动恢复为主节点

### 回滚步骤

1. 停止新版本服务
2. 恢复旧版本代码
3. 重新配置环境变量
4. 启动服务并验证

---

**部署完成！** 🎉

