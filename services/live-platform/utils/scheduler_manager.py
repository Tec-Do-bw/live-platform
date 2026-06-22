"""
定时调度器管理 - 基于HTTP心跳的主备切换
无需数据库表，通过HTTP健康检查实现
迁移自: webSoctket/scheduler_manager.py
"""
import requests
import time
from datetime import datetime


class SimpleSchedulerManager:
    """
    简化的调度器管理器
    - 通过HTTP健康检查判断是否应该执行任务
    - 主机1优先级高，主机2只在主机1故障时执行
    - 故障判断：连续3次HTTP请求失败
    """
    
    def __init__(self, node_id, node_ip, primary_node_url=None, check_interval=10):
        """
        初始化调度器管理器
        
        :param node_id: 节点ID ('node1' 或 'node2')
        :param node_ip: 节点IP地址
        :param primary_node_url: 主节点的健康检查URL（仅node2需要配置）
        :param check_interval: 健康检查间隔（秒）
        """
        self.node_id = node_id
        self.node_ip = node_ip
        self.is_primary = (node_id == 'node1')  # 是否为主节点
        self.primary_node_url = primary_node_url  # 主节点URL
        self.check_interval = check_interval  # 健康检查间隔
        self.primary_failed_count = 0  # 主节点失败计数
        self.max_failed_count = 3  # 连续失败3次才判定为故障
        self.last_check_time = 0  # 上次健康检查时间（时间戳）
        self.primary_is_healthy = True  # 缓存主节点健康状态
        
        print(f"\n{'='*60}")
        print(f"[调度器] 初始化完成")
        print(f"  - 节点ID: {self.node_id}")
        print(f"  - 节点IP: {self.node_ip}")
        print(f"  - 节点类型: {'主节点 (优先执行)' if self.is_primary else '备节点 (待命)'}")
        if self.primary_node_url:
            print(f"  - 监控主节点: {self.primary_node_url}")
            print(f"  - 健康检查间隔: {self.check_interval}秒")
        print(f"{'='*60}\n")
    
    def check_primary_health(self):
        """
        检查主节点健康状态
        返回: True-健康, False-故障
        """
        if not self.primary_node_url:
            return True  # 如果没有配置主节点URL，默认返回True
        
        try:
            response = requests.get(
                f"{self.primary_node_url}/health",
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    # 主节点健康，重置失败计数
                    if self.primary_failed_count > 0:
                        print(f"[调度器] 主节点 {self.primary_node_url} 已恢复")
                    self.primary_failed_count = 0
                    return True
            
            # HTTP状态码非200或code非200
            self.primary_failed_count += 1
            print(f"[调度器] 主节点健康检查异常 (失败计数: {self.primary_failed_count}/{self.max_failed_count})")
            return self.primary_failed_count < self.max_failed_count
            
        except requests.exceptions.RequestException as e:
            self.primary_failed_count += 1
            print(f"[调度器] 主节点健康检查失败: {e} (失败计数: {self.primary_failed_count}/{self.max_failed_count})")
            return self.primary_failed_count < self.max_failed_count
    
    def should_execute_task(self):
        """
        判断当前节点是否应该执行定时任务
        
        规则：
        - node1（主节点）: 总是执行
        - node2（备节点）: 只有在主节点故障时才执行
        
        返回: True-应该执行, False-不应该执行
        """
        if self.is_primary:
            # 主节点总是执行
            return True
        else:
            # 备节点需要检查主节点状态
            current_time = time.time()
            
            # 只有距离上次检查超过 check_interval 秒才重新检查
            if current_time - self.last_check_time >= self.check_interval:
                self.last_check_time = current_time
                self.primary_is_healthy = self.check_primary_health()
            
            # 使用缓存的健康状态判断
            if not self.primary_is_healthy:
                if self.primary_failed_count >= self.max_failed_count:
                    print(f"✅ [调度器] 主节点故障，备节点 {self.node_id} 接管任务执行")
                return True
            else:
                return False
    
    def wrap_task(self, task_func, task_name=""):
        """
        包装定时任务函数，添加执行判断逻辑
        
        :param task_func: 原始任务函数
        :param task_name: 任务名称（用于日志）
        :return: 包装后的任务函数
        """
        def wrapped_task():
            if self.should_execute_task():
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n{'='*60}")
                print(f"[{timestamp}] 节点 {self.node_id} 执行任务: {task_name}")
                print(f"{'='*60}")
                try:
                    task_func()
                    print(f"[调度器] 任务 {task_name} 执行完成\n")
                except Exception as e:
                    print(f"[调度器] 任务 {task_name} 执行失败: {e}\n")
            else:
                # 备节点不执行，只打印日志（降低日志输出频率）
                if not self.is_primary:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # 只在整点输出待命日志，避免刷屏
                    if datetime.now().minute == 0:
                        print(f"[{timestamp}] 备节点 {self.node_id} 待命中... (主节点正常运行)")
        
        return wrapped_task


# ========== 便捷函数 ==========

def create_scheduler_manager(node_id, node_ip, check_interval=10):
    """
    创建调度器管理器的便捷函数
    
    :param node_id: 'node1' 或 'node2'
    :param node_ip: 节点IP地址
    :param check_interval: 健康检查间隔（秒），默认10秒
    :return: SchedulerManager实例
    """
    if node_id == 'node1':
        # 主节点：不需要监控其他节点
        return SimpleSchedulerManager(
            node_id=node_id,
            node_ip=node_ip,
            primary_node_url=None,
            check_interval=check_interval
        )
    elif node_id == 'node2':
        # 备节点：需要监控主节点
        return SimpleSchedulerManager(
            node_id=node_id,
            node_ip=node_ip,
            primary_node_url='http://47.237.6.199:8080',  # ✅ 主节点地址（端口8080）
            check_interval=check_interval
        )
    else:
        raise ValueError(f"无效的node_id: {node_id}，必须是 'node1' 或 'node2'")
