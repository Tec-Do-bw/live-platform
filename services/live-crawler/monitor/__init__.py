"""采集完整性监控模块"""

from monitor.tracker import CollectionMonitor

_monitor: CollectionMonitor | None = None


def get_monitor() -> CollectionMonitor:
    """获取 CollectionMonitor 全局单例"""
    global _monitor
    if _monitor is None:
        _monitor = CollectionMonitor()
    return _monitor
