
import json
from core.apollo import APOLLO

KAFKA_HOSTS = APOLLO.get_value(key='kafka', default_val='')
AUTO_OFFSET_RESET = APOLLO.get_value(key='auto_offset_reset', default_val='latest')
IPLIST = eval(APOLLO.get_value(key='ip_list', default_val='[]'))

# ============================================================
# 并发配置说明（基于 asyncio + never-primp v2.0）
# ============================================================
# 总并发数 ≈ max_workers × detail_thread_workers
# 
# 推荐配置：
#   - 小规模（代理少/网络一般）: max_workers=3,  detail_thread_workers=8   → 总并发≈24
#   - 中等规模（推荐）:         max_workers=5,  detail_thread_workers=12  → 总并发≈60
#   - 大规模（代理多/网络好）:  max_workers=8,  detail_thread_workers=15  → 总并发≈120
#
# 注意事项：
#   1. max_workers 过大会导致内存占用增加（每行需加载商品数据）
#   2. detail_thread_workers 过大可能触发目标网站反爬
#   3. 建议根据代理池大小调整，并发数不要超过代理数量的 2 倍
# ============================================================
index_thread_workers = int(APOLLO.get_value(key='index_thread_workers', default_val=2))
detail_thread_workers = int(APOLLO.get_value(key='detail_thread_workers', default_val=6))
primp_client_pool_size = int(APOLLO.get_value(key='primp_client_pool_size', default_val=8))
detail_queue_size_factor = int(APOLLO.get_value(key='detail_queue_size_factor', default_val=4))
max_concurrent_tasks = int(APOLLO.get_value(key='max_concurrent_tasks', default_val=1))