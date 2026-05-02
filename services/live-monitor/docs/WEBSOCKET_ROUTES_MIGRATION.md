# WebSocket 路由迁移说明

## 迁移概述

已成功将 `webSoctket/main.py` 的 WebSocket 相关代码迁移到 `liveSpider_Serverv2/routes/websocket_routes.py`。

## 迁移的路由列表

以下所有路由地址**保持不变**，与原 `webSoctket/main.py` 中的路由完全一致：

### WebSocket 连接
- **路径**: `/ws/{user_id}`
- **类型**: WebSocket
- **说明**: WebSocket 连接端点，用于建立实时通信

### HTTP 端点

1. **健康检查**
   - **路径**: `/health`
   - **方法**: GET
   - **说明**: 健康检查端点（插件和定时调度脚本都会调用此接口判断服务器是否可用）
   - **返回**: 节点状态信息（node_id, priority, connections等）

2. **日志同步**
   - **路径**: `/sync_log`
   - **方法**: POST
   - **说明**: 接收其他节点同步的日志

3. **获取活跃连接**
   - **路径**: `/get_active_connections`
   - **方法**: GET
   - **说明**: 获取当前活跃连接（用于节点间信息同步）

4. **获取在线用户ID**
   - **路径**: `/socketOnlineUserID`
   - **方法**: GET
   - **参数**: `num` (可选，默认为1) - 推送的条数
   - **说明**: 获取最新socket链接有哪些

5. **检查CJ数据**
   - **路径**: `/get_check_CJ_data`
   - **方法**: GET
   - **说明**: 校验插件与直播间关系

6. **获取监听URL列表**
   - **路径**: `/CJListenUrl`
   - **方法**: GET
   - **说明**: 返回需要监听的url列表（TikTok和Shopee平台）

## 技术实现细节

### 核心组件

1. **ConnectionManager**
   - 管理 WebSocket 连接
   - 跟踪用户连接时间和IP地址
   - 处理重复连接和断开连接

2. **KafkaHelper**
   - 从 Apollo 获取 Kafka 配置
   - 发送数据到 Kafka topic: `streamer_cj_user_notify`

3. **后台任务**
   - 每60秒检查并打印连接的用户
   - 记录连接状态到日志
   - 推送连接状态到 Kafka
   - 同步日志到备用节点

### 日志目录

WebSocket 连接日志存储在：
```
liveSpider_Serverv2/logs/socketLog/socket_YYYYMMDD.log
```

### 初始化流程

1. 在 `main.py` 的 `if __name__ == '__main__'` 中调用 `init_websocket_routes(istest)`
2. 通过 `lifespan` 上下文管理器启动后台任务 `print_connected_users()`
3. Kafka 生产者在初始化时自动连接

## 配置说明

### 节点配置

在 `/health` 端点中，需要根据部署主机修改：
- **主机1**: 
  - `node_id`: "node1"
  - `priority`: 100
  - `backup_node_url`: "http://47.236.42.104:8081" (主机2地址)

- **主机2**:
  - `node_id`: "node2"
  - `priority`: 50
  - `backup_node_url`: 配置为主机1地址

### 环境变量

- `ISTEST`: 控制是否使用测试环境 (默认: 1)
  - 1 = 测试环境
  - 0 = 生产环境

## 使用示例

### WebSocket 连接

```javascript
// 客户端连接示例
const ws = new WebSocket('ws://localhost:8080/ws/user123');

// 发送心跳
ws.send(JSON.stringify({
    type: 'ping'
}));

// 接收响应
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'pong') {
        console.log('Heart beat received');
    }
};
```

### HTTP API 调用

```bash
# 健康检查
curl http://localhost:8080/health

# 获取在线用户
curl http://localhost:8080/socketOnlineUserID?num=5

# 获取监听URL列表
curl http://localhost:8080/CJListenUrl
```

## 注意事项

1. **路由地址保持不变**: 所有路由地址与原 `webSoctket/main.py` 完全一致
2. **端口**: 原 webSocket 服务运行在 8081，现在集成到主服务的 8080 端口
3. **日志目录**: 日志存储位置从 `webSoctket/socketLog/` 迁移到 `liveSpider_Serverv2/logs/socketLog/`
4. **依赖**: 需要确保安装了 `kafka-python` 包

## 测试建议

1. 测试 WebSocket 连接和断开
2. 测试心跳机制
3. 测试多用户并发连接
4. 测试重复连接处理
5. 验证日志记录功能
6. 验证 Kafka 消息推送
7. 验证节点间日志同步

## 迁移完成清单

- [x] 创建 `routes/websocket_routes.py` 文件
- [x] 迁移所有路由定义
- [x] 保持路由地址不变
- [x] 在 `main.py` 中注册路由
- [x] 添加 lifespan 管理后台任务
- [x] 创建日志目录
- [x] 验证无 linter 错误
- [x] 编写迁移文档

