# Live Platform DDD 领域模型设计

> **版本：** v1.0  
> **日期：** 2026-05-03  
> **状态：** Draft

---

## 1. 领域概述

### 1.1 核心领域（Core Domain）

**直播数据采集与监控系统** - 为派大星系统提供准确、实时的直播 GMV 数据

### 1.2 支撑子域（Supporting Subdomain）

- 浏览器管理
- 视频流录制
- 登录态管理

### 1.3 通用子域（Generic Subdomain）

- 消息队列
- 对象存储
- 定时任务调度

---

## 2. 限界上下文（Bounded Contexts）

### 2.1 上下文地图

```
┌─────────────────────────────────────────────────────────────────┐
│                        派大星系统 (外部)                          │
│                        [Customer/Supplier]                       │
└────────────┬────────────────────────────────────────────────────┘
             │ Open Host Service (REST API)
┌────────────▼────────────────────────────────────────────────────┐
│  直播间监控上下文 (LiveRoomMonitoring)                            │
│  - 直播间状态管理                                                 │
│  - 开播检测                                                       │
│  - 房间分配                                                       │
└────────────┬────────────────────────────────────────────────────┘
             │ Published Language (房间分配协议)
┌────────────▼────────────────────────────────────────────────────┐
│  视频流录制上下文 (StreamRecording)                               │
│  - FFmpeg 推流                                                    │
│  - 断流重连                                                       │
│  - 视频切割上传                                                   │
└────────────┬────────────────────────────────────────────────────┘
             │ Shared Kernel (登录态)
┌────────────▼────────────────────────────────────────────────────┐
│  浏览器管理上下文 (BrowserManagement)                             │
│  - 浏览器生命周期                                                 │
│  - 投屏转发                                                       │
│  - 登录监控                                                       │
└────────────┬────────────────────────────────────────────────────┘
             │ Conformist (依赖登录态)
┌────────────▼────────────────────────────────────────────────────┐
│  数据采集上下文 (DataCollection)                                  │
│  - 双轨采集                                                       │
│  - 数据上报                                                       │
│  - 采集完整性监控                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 上下文关系

| 上游 | 下游 | 关系模式 | 说明 |
|------|------|---------|------|
| 派大星系统 | 直播间监控 | Customer/Supplier | 派大星调用监控 API |
| 直播间监控 | 视频流录制 | Published Language | 房间分配协议 |
| 浏览器管理 | 数据采集 | Shared Kernel | 共享登录态模型 |

---

## 3. 聚合根与实体

### 3.1 直播间监控上下文

#### 聚合根：LiveRoom

```python
class LiveRoom:
    """直播间聚合根"""
    
    # 标识
    room_id: RoomId                     # 值对象
    room_url: RoomUrl                   # 值对象
    
    # 基本信息
    platform: Platform                  # 值对象：TikTok/Shopee/Lazada
    country: Country                    # 值对象
    
    # 状态
    monitoring_status: MonitoringStatus # 值对象：Pending/Monitoring/Stopped
    live_status: LiveStatus             # 值对象：Offline/Online/Ended
    allocation_status: AllocationStatus # 值对象：Unallocated/Allocated
    
    # 直播信息（实体）
    live_info: Optional[LiveInfo]       # 实体
    
    # 分配信息（值对象）
    allocation: Optional[Allocation]    # 值对象
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    status_update_time: datetime
    
    # 行为
    def start_monitoring(self) -> None:
        """开始监控"""
        if self.monitoring_status != MonitoringStatus.PENDING:
            raise InvalidStateTransition()
        self.monitoring_status = MonitoringStatus.MONITORING
        self._publish(LiveRoomMonitoringStartedEvent(self.room_id))
    
    def detect_live_status(self) -> LiveStatus:
        """检测直播状态"""
        # 调用领域服务 LiveStatusDetector
        pass
    
    def go_live(self, live_info: LiveInfo) -> None:
        """直播间开播"""
        if self.live_status == LiveStatus.ONLINE:
            return  # 幂等
        self.live_status = LiveStatus.ONLINE
        self.live_info = live_info
        self._publish(LiveRoomDetectedEvent(
            room_id=self.room_id,
            flv_url=live_info.flv_url,
            detected_at=datetime.now()
        ))
    
    def allocate_to_client(self, client_ip: str) -> None:
        """分配给客户端"""
        if self.allocation_status == AllocationStatus.ALLOCATED:
            raise AlreadyAllocatedException()
        if not self.live_info or not self.live_info.flv_url:
            raise NoLiveStreamException()
        
        self.allocation = Allocation(
            client_ip=client_ip,
            allocated_at=datetime.now()
        )
        self.allocation_status = AllocationStatus.ALLOCATED
        self.status_update_time = datetime.now()
    
    def report_status(self) -> None:
        """客户端上报状态"""
        self.status_update_time = datetime.now()
    
    def release(self) -> None:
        """释放分配"""
        self.allocation_status = AllocationStatus.UNALLOCATED
        self.allocation = None
    
    def is_timeout(self, timeout_seconds: int = 300) -> bool:
        """是否超时"""
        if self.allocation_status != AllocationStatus.ALLOCATED:
            return False
        elapsed = (datetime.now() - self.status_update_time).total_seconds()
        return elapsed > timeout_seconds
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        self.monitoring_status = MonitoringStatus.STOPPED
        if self.allocation_status == AllocationStatus.ALLOCATED:
            self.release()
```

#### 实体：LiveInfo

```python
class LiveInfo:
    """直播信息实体"""
    flv_url: str                        # 直播流地址
    room_id_platform: str               # 平台房间ID
    play_urls: list[str]                # 播放地址列表（Shopee）
    message: str                        # 状态消息
    extra_data: dict                    # 平台特定数据
```

#### 值对象

```python
@dataclass(frozen=True)
class RoomId:
    value: str

@dataclass(frozen=True)
class RoomUrl:
    value: str
    
    def __post_init__(self):
        if not self.value.startswith('http'):
            raise InvalidRoomUrlException()

@dataclass(frozen=True)
class Platform:
    value: str  # 'tiktok' | 'shopee' | 'lazada'
    
    @classmethod
    def tiktok(cls): return cls('tiktok')
    @classmethod
    def shopee(cls): return cls('shopee')
    @classmethod
    def lazada(cls): return cls('lazada')

@dataclass(frozen=True)
class Country:
    code: str  # 'MY', 'SG', 'TH', etc.
    name: str

class MonitoringStatus(Enum):
    PENDING = "pending"
    MONITORING = "monitoring"
    STOPPED = "stopped"

class LiveStatus(Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    ENDED = "ended"

class AllocationStatus(Enum):
    UNALLOCATED = "unallocated"
    ALLOCATED = "allocated"

@dataclass(frozen=True)
class Allocation:
    client_ip: str
    allocated_at: datetime
```

---

### 3.2 视频流录制上下文

#### 聚合根：StreamSession

```python
class StreamSession:
    """视频流会话聚合根"""
    
    # 标识
    session_id: SessionId               # 值对象
    room_id: RoomId                     # 关联直播间
    
    # 基本信息
    flv_url: str
    platform: Platform
    country: Country
    output_dir: str
    
    # 状态
    stream_status: StreamStatus         # 值对象
    retry_count: int
    
    # 统计
    start_time: Optional[datetime]
    last_frame_time: Optional[datetime]
    total_duration: int                 # 秒
    uploaded_segments: int
    failed_segments: int
    
    # 配置（值对象）
    config: StreamConfig
    
    # 行为
    def start_stream(self) -> None:
        """开始推流"""
        if self.stream_status != StreamStatus.IDLE:
            raise InvalidStateTransition()
        
        self.stream_status = StreamStatus.CONNECTING
        self.start_time = datetime.now()
        self.retry_count = 0
        
        self._publish(StreamStartedEvent(
            session_id=self.session_id,
            room_id=self.room_id,
            started_at=self.start_time
        ))
    
    def on_stream_connected(self) -> None:
        """推流连接成功"""
        self.stream_status = StreamStatus.STREAMING
        self.last_frame_time = datetime.now()
    
    def on_frame_received(self) -> None:
        """收到新帧"""
        self.last_frame_time = datetime.now()
    
    def check_health(self) -> bool:
        """健康检查"""
        if self.stream_status != StreamStatus.STREAMING:
            return False
        
        if not self.last_frame_time:
            return False
        
        elapsed = (datetime.now() - self.last_frame_time).total_seconds()
        return elapsed < self.config.no_data_timeout
    
    def on_disconnected(self, reason: str) -> None:
        """断流"""
        if self.stream_status == StreamStatus.STOPPED:
            return
        
        self.stream_status = StreamStatus.RECONNECTING
        self._publish(StreamDisconnectedEvent(
            session_id=self.session_id,
            reason=reason,
            retry_count=self.retry_count
        ))
    
    def reconnect(self) -> bool:
        """重连"""
        if self.retry_count >= self.config.max_retries:
            self.stream_status = StreamStatus.FAILED
            return False
        
        self.retry_count += 1
        self.stream_status = StreamStatus.CONNECTING
        return True
    
    def on_segment_uploaded(self, oss_url: str, duration: int) -> None:
        """片段上传成功"""
        self.uploaded_segments += 1
        self.total_duration += duration
        
        self._publish(SegmentUploadedEvent(
            session_id=self.session_id,
            oss_url=oss_url,
            duration=duration
        ))
    
    def on_segment_failed(self) -> None:
        """片段上传失败"""
        self.failed_segments += 1
    
    def stop_stream(self) -> None:
        """停止推流"""
        self.stream_status = StreamStatus.STOPPED
        
        self._publish(StreamStoppedEvent(
            session_id=self.session_id,
            total_duration=self.total_duration,
            uploaded_segments=self.uploaded_segments
        ))
```

#### 值对象

```python
class StreamStatus(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPED = "stopped"

@dataclass(frozen=True)
class StreamConfig:
    max_retries: int = 10
    retry_interval: int = 1
    retry_backoff: float = 1.2
    max_retry_interval: int = 15
    heartbeat_interval: int = 10
    no_data_timeout: int = 30
    segment_time: int = 8
```

---

### 3.3 浏览器管理上下文

#### 聚合根：BrowserSession

```python
class BrowserSession:
    """浏览器会话聚合根"""
    
    # 标识
    session_id: SessionId
    collection_id: str                  # AdsPower 环境ID
    
    # 基本信息
    platform: Platform
    country: Country
    validate_id: str                    # 验证ID（shop_id/user_id）
    
    # 状态
    status: SessionStatus               # Active/Closed/Error
    login_status: LoginStatus           # Pending/Success/Error/Closed
    
    # 浏览器信息
    debug_port: int
    ws_url: str
    
    # 回调信息
    login_callback_sent: bool
    cleanup_started: bool
    
    # 时间戳
    created_at: datetime
    login_started_at: Optional[datetime]
    login_completed_at: Optional[datetime]
    
    # 行为
    def start_login_monitor(self) -> None:
        """开始登录监控"""
        if self.login_status != LoginStatus.PENDING:
            raise InvalidStateTransition()
        
        self.login_started_at = datetime.now()
        self._publish(LoginMonitorStartedEvent(
            session_id=self.session_id,
            platform=self.platform
        ))
    
    def on_login_success(self, shop_id: str) -> None:
        """登录成功"""
        if self.login_callback_sent:
            return  # 防止重复回调
        
        self.login_status = LoginStatus.SUCCESS
        self.login_completed_at = datetime.now()
        self.login_callback_sent = True
        
        self._publish(LoginSuccessEvent(
            session_id=self.session_id,
            platform=self.platform,
            shop_id=shop_id,
            logged_in_at=self.login_completed_at
        ))
    
    def on_login_failed(self, reason: str) -> None:
        """登录失败"""
        if self.login_callback_sent:
            return
        
        self.login_status = LoginStatus.ERROR
        self.login_completed_at = datetime.now()
        self.login_callback_sent = True
        
        self._publish(LoginFailedEvent(
            session_id=self.session_id,
            reason=reason
        ))
    
    def close(self) -> None:
        """关闭会话"""
        if self.cleanup_started:
            return
        
        self.cleanup_started = True
        self.status = SessionStatus.CLOSED
        
        # 如果登录未完成且未发送过回调，发送 closed 回调
        if not self.login_callback_sent:
            self.login_status = LoginStatus.CLOSED
            self.login_callback_sent = True
            self._publish(SessionClosedEvent(
                session_id=self.session_id,
                reason="manual_close"
            ))
```

#### 值对象

```python
class SessionStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ERROR = "error"

class LoginStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    CLOSED = "closed"

@dataclass(frozen=True)
class LoginResult:
    status: LoginStatus
    reason: Optional[str]
    shop_id: Optional[str]
```

---

### 3.4 数据采集上下文

#### 聚合根：CollectionSession

```python
class CollectionSession:
    """采集会话聚合根"""
    
    # 标识
    session_id: SessionId
    batch_id: str
    account_id: str
    
    # 基本信息
    platform: Platform
    country: Country
    
    # 状态
    collection_mode: CollectionMode     # Incremental/Full
    collection_status: CollectionStatus # Pending/Running/Completed/Failed
    
    # 统计
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    api_collected: list[str]            # 已采集的API列表
    data_count: int
    error_count: int
    
    # 行为
    def start_collection(self, mode: CollectionMode) -> None:
        """开始采集"""
        if self.collection_status != CollectionStatus.PENDING:
            raise InvalidStateTransition()
        
        self.collection_mode = mode
        self.collection_status = CollectionStatus.RUNNING
        self.start_time = datetime.now()
        
        self._publish(CollectionStartedEvent(
            session_id=self.session_id,
            account_id=self.account_id,
            mode=mode
        ))
    
    def on_api_collected(self, api_type: str, count: int) -> None:
        """API 采集完成"""
        self.api_collected.append(api_type)
        self.data_count += count
    
    def on_api_failed(self, api_type: str, reason: str) -> None:
        """API 采集失败"""
        self.error_count += 1
        self._publish(ApiCollectionFailedEvent(
            session_id=self.session_id,
            api_type=api_type,
            reason=reason
        ))
    
    def complete(self) -> None:
        """采集完成"""
        self.collection_status = CollectionStatus.COMPLETED
        self.end_time = datetime.now()
        
        self._publish(CollectionCompletedEvent(
            session_id=self.session_id,
            account_id=self.account_id,
            data_count=self.data_count,
            completed_at=self.end_time
        ))
    
    def fail(self, reason: str) -> None:
        """采集失败"""
        self.collection_status = CollectionStatus.FAILED
        self.end_time = datetime.now()
        
        self._publish(CollectionFailedEvent(
            session_id=self.session_id,
            reason=reason
        ))
    
    def check_completeness(self) -> bool:
        """检查完整性"""
        # 调用领域服务 CompletenessChecker
        pass
```

#### 值对象

```python
class CollectionMode(Enum):
    INCREMENTAL = "incremental"
    FULL = "full"
    REALTIME = "realtime"

class CollectionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class ApiType:
    value: str  # 'live_list', 'trend_gmv', etc.
```

---

## 4. 领域事件

### 4.1 直播间监控上下文

```python
@dataclass(frozen=True)
class LiveRoomMonitoringStartedEvent:
    room_id: RoomId
    occurred_at: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class LiveRoomDetectedEvent:
    room_id: RoomId
    flv_url: str
    detected_at: datetime

@dataclass(frozen=True)
class LiveRoomEndedEvent:
    room_id: RoomId
    ended_at: datetime
```

### 4.2 视频流录制上下文

```python
@dataclass(frozen=True)
class StreamStartedEvent:
    session_id: SessionId
    room_id: RoomId
    started_at: datetime

@dataclass(frozen=True)
class StreamDisconnectedEvent:
    session_id: SessionId
    reason: str
    retry_count: int

@dataclass(frozen=True)
class SegmentUploadedEvent:
    session_id: SessionId
    oss_url: str
    duration: int
```

### 4.3 浏览器管理上下文

```python
@dataclass(frozen=True)
class LoginSuccessEvent:
    session_id: SessionId
    platform: Platform
    shop_id: str
    logged_in_at: datetime

@dataclass(frozen=True)
class LoginFailedEvent:
    session_id: SessionId
    reason: str
```

### 4.4 数据采集上下文

```python
@dataclass(frozen=True)
class CollectionCompletedEvent:
    session_id: SessionId
    account_id: str
    data_count: int
    completed_at: datetime

@dataclass(frozen=True)
class CollectionFailedEvent:
    session_id: SessionId
    api_type: str
    reason: str
```

---

## 5. 领域服务

### 5.1 直播间监控上下文

```python
class LiveStatusDetector:
    """直播状态检测服务"""
    
    def detect(self, room: LiveRoom) -> LiveStatus:
        """检测直播状态"""
        if room.platform == Platform.tiktok():
            return self._detect_tiktok(room)
        elif room.platform == Platform.shopee():
            return self._detect_shopee(room)
        elif room.platform == Platform.lazada():
            return self._detect_lazada(room)

class RoomAllocator:
    """房间分配服务"""
    
    def allocate(self, client_ip: str) -> Optional[LiveRoom]:
        """分配可用房间"""
        # 查找满足条件的房间
        # 原子操作设置分配状态
        pass
```

### 5.2 视频流录制上下文

```python
class StreamHealthChecker:
    """流健康检查服务"""
    
    def check(self, session: StreamSession) -> HealthStatus:
        """检查流健康状态"""
        # 检查帧率、文件生成、进程状态
        pass

class ReconnectStrategy:
    """重连策略服务"""
    
    def calculate_delay(self, retry_count: int, config: StreamConfig) -> int:
        """计算重连延迟"""
        base_delay = config.retry_interval
        backoff = config.retry_backoff ** retry_count
        delay = min(base_delay * backoff, config.max_retry_interval)
        return int(delay)
```

### 5.3 浏览器管理上下文

```python
class LoginMonitor:
    """登录监控服务"""
    
    def monitor(self, session: BrowserSession) -> LoginResult:
        """监控登录状态"""
        if session.platform == Platform.tiktok():
            return self._monitor_tiktok(session)
        elif session.platform == Platform.shopee():
            return self._monitor_shopee(session)
        elif session.platform == Platform.lazada():
            return self._monitor_lazada(session)
```

### 5.4 数据采集上下文

```python
class CompletenessChecker:
    """完整性检查服务"""
    
    def check(self, session: CollectionSession) -> CompletenessReport:
        """检查采集完整性"""
        # 检查必需的 API 是否都已采集
        # 检查数据量是否合理
        pass

class CollectionModeResolver:
    """采集模式解析服务"""
    
    def resolve(self, account_id: str, platform: Platform) -> CollectionMode:
        """解析采集模式"""
        # 新账号 → 全量
        # 登出恢复 → 全量
        # 正常 → 增量
        pass
```

---

## 6. 仓储接口

### 6.1 直播间监控上下文

```python
class LiveRoomRepository(ABC):
    @abstractmethod
    def find_by_id(self, room_id: RoomId) -> Optional[LiveRoom]:
        pass
    
    @abstractmethod
    def find_available_rooms(self, timeout_seconds: int) -> list[LiveRoom]:
        pass
    
    @abstractmethod
    def save(self, room: LiveRoom) -> None:
        pass
    
    @abstractmethod
    def delete(self, room_id: RoomId) -> None:
        pass
```

### 6.2 视频流录制上下文

```python
class StreamSessionRepository(ABC):
    @abstractmethod
    def find_by_id(self, session_id: SessionId) -> Optional[StreamSession]:
        pass
    
    @abstractmethod
    def find_active_sessions(self) -> list[StreamSession]:
        pass
    
    @abstractmethod
    def save(self, session: StreamSession) -> None:
        pass
```

### 6.3 浏览器管理上下文

```python
class BrowserSessionRepository(ABC):
    @abstractmethod
    def find_by_id(self, session_id: SessionId) -> Optional[BrowserSession]:
        pass
    
    @abstractmethod
    def save(self, session: BrowserSession) -> None:
        pass
    
    @abstractmethod
    def delete(self, session_id: SessionId) -> None:
        pass
```

### 6.4 数据采集上下文

```python
class CollectionSessionRepository(ABC):
    @abstractmethod
    def find_by_id(self, session_id: SessionId) -> Optional[CollectionSession]:
        pass
    
    @abstractmethod
    def find_by_batch(self, batch_id: str) -> list[CollectionSession]:
        pass
    
    @abstractmethod
    def save(self, session: CollectionSession) -> None:
        pass
```

---

## 7. 应用服务

### 7.1 直播间监控应用服务

```python
class LiveRoomMonitoringService:
    def __init__(
        self,
        room_repo: LiveRoomRepository,
        detector: LiveStatusDetector,
        event_bus: EventBus
    ):
        self.room_repo = room_repo
        self.detector = detector
        self.event_bus = event_bus
    
    def register_room(self, room_url: str, platform: str, country: str) -> RoomId:
        """注册直播间"""
        room = LiveRoom.create(
            room_url=RoomUrl(room_url),
            platform=Platform(platform),
            country=Country(country)
        )
        room.start_monitoring()
        self.room_repo.save(room)
        return room.room_id
    
    def detect_live_status(self, room_id: RoomId) -> None:
        """检测直播状态"""
        room = self.room_repo.find_by_id(room_id)
        if not room:
            raise RoomNotFoundException()
        
        status = self.detector.detect(room)
        if status == LiveStatus.ONLINE and room.live_status != LiveStatus.ONLINE:
            # 检测到开播
            live_info = self._fetch_live_info(room)
            room.go_live(live_info)
            self.room_repo.save(room)
```

### 7.2 视频流录制应用服务

```python
class StreamRecordingService:
    def __init__(
        self,
        session_repo: StreamSessionRepository,
        health_checker: StreamHealthChecker,
        event_bus: EventBus
    ):
        self.session_repo = session_repo
        self.health_checker = health_checker
        self.event_bus = event_bus
    
    def start_recording(
        self,
        room_id: RoomId,
        flv_url: str,
        platform: Platform
    ) -> SessionId:
        """开始录制"""
        session = StreamSession.create(
            room_id=room_id,
            flv_url=flv_url,
            platform=platform
        )
        session.start_stream()
        self.session_repo.save(session)
        
        # 启动 FFmpeg 进程（基础设施层）
        self._start_ffmpeg(session)
        
        return session.session_id
```

---

## 8. 实施路线图

### 8.1 阶段一：核心聚合根（1周）

1. 实现 LiveRoom 聚合根
2. 实现 StreamSession 聚合根
3. 实现基本的仓储接口

### 8.2 阶段二：领域服务（1周）

1. 实现 LiveStatusDetector
2. 实现 StreamHealthChecker
3. 实现 LoginMonitor

### 8.3 阶段三：应用服务（1周）

1. 实现应用服务
2. 集成事件总线
3. 实现 API 接口

### 8.4 阶段四：完善与优化（持续）

1. 完善领域事件
2. 优化性能
3. 补充单元测试

---

**文档结束**
