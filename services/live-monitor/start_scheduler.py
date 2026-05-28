"""
定时调度任务启动脚本
启动所有定时任务：GMV实时采集、T+1插件采集、基本信息采集
迁移自: webSoctket/ALLSpider_Paidaxing.py
"""
import os
import schedule
import sys
import time
import pymysql
from datetime import datetime

# 导入必要的模块
from utils.serverTool import fetch_apollo_config
from utils.logger import Logings

logger = Logings().get_logger()
from utils.scheduler_manager import create_scheduler_manager
from tasks import mainSpider_gmv, mainSpider_T1, mainSpider_requests


def init_database_config(istest=1):
    """初始化数据库配置"""
    try:
        config_data = fetch_apollo_config(istest)
        db_config = {
            'host': config_data["devSqlHost"],
            'port': int(config_data["devSqlPort"]),
            'user': config_data["devSqlUser"],
            'password': config_data["devSqlPassword"],
            'database': config_data['database'],
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor
        }
        if istest != 1:
            # 初始化 Holo 数据库配置
            holo_db_config = {
                'host': config_data["holoHost"] if istest == 1 else "hgprecn-cn-vc241gnwp001-ap-southeast-1-vpc-st.hologres.aliyuncs.com",
                'port': int(config_data["holoPort"]),
                'dbname': config_data["holoDBname"],
                'user': config_data["holoUser"],
                'password': config_data["holoPassword"]
            }
        else:
            holo_db_config = {}

        return config_data, db_config, holo_db_config
    except Exception as e:
        logger.error(f"数据库配置初始化失败: {e}", exc_info=True)
        raise


def main():
    """主入口函数"""
    
    logger.info("=" * 60)
    logger.info("🚀 定时调度器启动中...")
    logger.info("=" * 60)
    
    # ========== 配置节点信息（从环境变量读取）==========
    # ⚠️ 部署时通过环境变量或 configure_node.sh 配置
    # 主机1: NODE_ID='node1', NODE_IP='47.237.6.199', PRIORITY=100
    # 主机2: NODE_ID='node2', NODE_IP='47.236.42.104', PRIORITY=50
    
    NODE_ID = os.environ.get('NODE_ID', 'node1')  # 节点ID
    NODE_IP = os.environ.get('NODE_IP', '127.0.0.1')  # 节点IP
    PRIORITY = int(os.environ.get('PRIORITY', '100'))  # 节点优先级
    ISTEST = int(os.environ.get('ISTEST', '1'))  # 0: 生产环境, 1: 测试环境
    
    logger.info(f"\n{'='*60}")
    logger.info(f"节点配置:")
    logger.info(f"  - 节点ID: {NODE_ID}")
    logger.info(f"  - 节点IP: {NODE_IP}")
    logger.info(f"  - 优先级: {PRIORITY}")
    logger.info(f"  - 角色: {'主节点 (优先执行)' if NODE_ID == 'node1' else '备节点 (监控主节点)'}")
    logger.info(f"  - 环境: {'测试环境' if ISTEST == 1 else '生产环境'}")
    logger.info(f"{'='*60}\n")
    
    # 初始化数据库配置
    try:
        config_data, db_config, holo_db_config = init_database_config(ISTEST)
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)
    
    # 创建调度器管理器
    scheduler_manager = create_scheduler_manager(NODE_ID, NODE_IP, check_interval=10)
    
    # ========== 定义原始任务函数 ==========
    
    def run_mainSpider_gmv():
        """GMV实时采集"""
        mainSpider_gmv(db_config, holo_db_config, ISTEST)

    def run_mainSpider_T1():
        """T+1插件执行"""
        mainSpider_T1(db_config, ISTEST)

    def run_mainSpider_requests():
        """基本信息采集"""
        mainSpider_requests(db_config, num=3, ISTEST=ISTEST)
    
    # ========== 包装任务函数（添加执行判断逻辑）==========
    
    # wrapped_gmv = scheduler_manager.wrap_task(run_mainSpider_gmv, "GMV实时采集")
    wrapped_t1 = scheduler_manager.wrap_task(run_mainSpider_T1, "T+1插件执行")
    wrapped_requests = scheduler_manager.wrap_task(run_mainSpider_requests, "基本信息采集")
    # ========== 配置定时任务 ==========
    
    logger.info("📋 配置定时任务...")
    
    # 每天12点执行基本信息采集
    schedule.every().day.at("12:00").do(wrapped_requests)
    logger.info("✅ 已配置: 基本信息采集 (每天12点)")

    # 每4小时执行T+1插件
    schedule.every(4).hours.do(wrapped_t1)
    logger.info("✅ 已配置: T+1插件采集 (每4小时)")
    
    # 每5分钟执行GMV实时采集
    # schedule.every(5).minutes.do(wrapped_gmv)
    # logger.info("✅ 已配置: GMV实时采集 (每5分钟)")
    
    # ========== 启动调度循环 ==========
    
    logger.info(f"\n{'='*60}")
    logger.info(f"定时调度器启动")
    logger.info(f"节点ID: {NODE_ID}")
    logger.info(f"节点IP: {NODE_IP}")
    logger.info(f"节点角色: {'主节点 (优先执行任务)' if NODE_ID == 'node1' else '备节点 (监控主节点)'}")
    logger.info(f"{'='*60}\n")
    
    logger.info("💡 提示: 按 Ctrl+C 停止任务调度器\n")
    
    # 主循环
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n" + "="*60)
        logger.info("👋 定时调度器已停止")
        logger.info("="*60)
        # 如果是作为模块调用，不要退出整个程序
        if __name__ == "__main__":
            sys.exit(0)


if __name__ == "__main__":
    main()
