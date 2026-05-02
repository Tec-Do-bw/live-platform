"""登出恢复全量主流程测试。"""

import sys
import types


background_module = types.ModuleType('apscheduler.schedulers.background')
cron_module = types.ModuleType('apscheduler.triggers.cron')
drission_module = types.ModuleType('DrissionPage')
ddddocr_module = types.ModuleType('ddddocr')


class _FakeBackgroundScheduler:
    def __init__(self, *args, **kwargs):
        self._jobs = []

    def add_job(self, *args, **kwargs):
        self._jobs.append(types.SimpleNamespace(
            name=kwargs.get('name', ''),
            id=kwargs.get('id', ''),
            next_run_time=None,
        ))

    def get_jobs(self):
        return list(self._jobs)

    def start(self):
        return None

    def shutdown(self, wait=True):
        return None


class _FakeCronTrigger:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs


class _FakeChromium:
    def __init__(self, *args, **kwargs):
        pass


class _FakeChromiumOptions:
    def __init__(self, *args, **kwargs):
        pass


class _FakeDdddOcr:
    def __init__(self, *args, **kwargs):
        pass


background_module.BackgroundScheduler = _FakeBackgroundScheduler
cron_module.CronTrigger = _FakeCronTrigger
drission_module.Chromium = _FakeChromium
drission_module.ChromiumOptions = _FakeChromiumOptions
ddddocr_module.DdddOcr = _FakeDdddOcr
sys.modules.setdefault('apscheduler', types.ModuleType('apscheduler'))
sys.modules.setdefault('apscheduler.schedulers', types.ModuleType('apscheduler.schedulers'))
sys.modules.setdefault('apscheduler.triggers', types.ModuleType('apscheduler.triggers'))
sys.modules['apscheduler.schedulers.background'] = background_module
sys.modules['apscheduler.triggers.cron'] = cron_module
sys.modules['DrissionPage'] = drission_module
sys.modules['ddddocr'] = ddddocr_module

import main
from scheduler.task_scheduler import TaskScheduler


class DummyMonitor:
    """最小监控桩对象。"""

    def __init__(self):
        self.conn = object()
        self.started_batches = []
        self.finished_batches = []

    def start_batch(self, batch_id, mode):
        self.started_batches.append((batch_id, mode))

    def finish_batch(self, batch_id):
        self.finished_batches.append(batch_id)


class DummyTracker:
    """最小 tracker 桩对象。"""

    def __init__(self, new_accounts=None):
        self.new_accounts = set(new_accounts or [])
        self.marked = []

    def is_new_account(self, platform, user_id):
        return (platform, user_id) in self.new_accounts

    def mark_full_collected(self, platform, user_id):
        self.marked.append((platform, user_id))


class DummyStatusManager:
    """最小登录状态管理桩对象。"""

    def __init__(self, recent_events=None):
        self.recent_events = dict(recent_events or {})
        self.appended_events = []

    def get_recent_events(self, account_id, limit=2):
        return list(self.recent_events.get(account_id, []))[:limit]

    def append_event(self, account_id, platform, group_name, event_type, batch_id='', detail=None, **kwargs):
        self.appended_events.append({
            'account_id': account_id,
            'platform': platform,
            'group_name': group_name,
            'event_type': event_type,
            'batch_id': batch_id,
            'detail': detail or {},
        })


class DummyAlertManager:
    """最小告警桩对象。"""

    def __init__(self):
        self.alerts = []

    def send_alert(self, **kwargs):
        self.alerts.append(kwargs)


class DummyCrawler:
    """记录构造参数并返回可配置结果的爬虫桩。"""

    calls = []
    results_by_user = {}

    def __init__(self, platform, browser_id, full_collection=False, group_name='', batch_id=''):
        self.platform = platform
        self.browser_id = browser_id
        DummyCrawler.calls.append({
            'platform': platform,
            'browser_id': browser_id,
            'full_collection': full_collection,
            'group_name': group_name,
            'batch_id': batch_id,
        })

    def start_crawl(self):
        result = {
            'success': True,
            'login_status': True,
            'error': None,
            'pages_visited': 1,
            'apis_collected': 1,
            'data_sent': 1,
        }
        result.update(self.results_by_user.get(self.browser_id, {}))
        return result


def _patch_run_once(monkeypatch, platform_config, tracker, status_mgr, monitor):
    import monitor.recrawl as recrawl

    DummyCrawler.calls = []
    DummyCrawler.results_by_user = {}
    monkeypatch.setattr(main.Settings, 'PLATFORM_CONFIG', platform_config, raising=False)
    monkeypatch.setattr(main, 'get_monitor', lambda: monitor)
    monkeypatch.setattr(main, 'CollectionTracker', lambda: tracker)
    monkeypatch.setattr(main, 'LoginStatusManager', lambda conn: status_mgr)
    monkeypatch.setattr(main, 'LiveCrawler', DummyCrawler)
    monkeypatch.setattr(recrawl, 'auto_detect_and_recrawl', lambda *args, **kwargs: None)


def _patch_scheduler(monkeypatch, platform_config, tracker, status_mgr, monitor):
    import scheduler.task_scheduler as task_scheduler

    DummyCrawler.calls = []
    DummyCrawler.results_by_user = {}
    monkeypatch.setattr(task_scheduler.Settings, 'PLATFORM_CONFIG', platform_config, raising=False)
    monkeypatch.setattr(task_scheduler, 'get_monitor', lambda: monitor)
    monkeypatch.setattr(task_scheduler, 'CollectionTracker', lambda: tracker)
    monkeypatch.setattr(task_scheduler, 'LoginStatusManager', lambda conn: status_mgr)
    monkeypatch.setattr(task_scheduler, 'AlertManager', DummyAlertManager)
    monkeypatch.setattr(task_scheduler, 'LiveCrawler', DummyCrawler)


def test_run_once_uses_full_collection_for_new_account(monkeypatch):
    tracker = DummyTracker({('tiktok', 'acc1')})
    status_mgr = DummyStatusManager()
    monitor = DummyMonitor()

    _patch_run_once(
        monkeypatch,
        {'tiktok': {'use_dynamic_users': False, 'user_ids': ['acc1']}},
        tracker,
        status_mgr,
        monitor,
    )

    main.run_once()

    assert DummyCrawler.calls[0]['full_collection'] is True
    assert tracker.marked == [('tiktok', 'acc1')]
    assert status_mgr.appended_events == []


def test_run_once_uses_full_collection_after_logout_then_login(monkeypatch):
    tracker = DummyTracker()
    status_mgr = DummyStatusManager({
        'acc1': [
            {'event_type': 'login'},
            {'event_type': 'logout'},
        ]
    })
    monitor = DummyMonitor()

    _patch_run_once(
        monkeypatch,
        {'tiktok': {'use_dynamic_users': False, 'user_ids': ['acc1']}},
        tracker,
        status_mgr,
        monitor,
    )

    main.run_once()

    assert DummyCrawler.calls[0]['full_collection'] is True
    assert tracker.marked == [('tiktok', 'acc1')]
    assert [event['event_type'] for event in status_mgr.appended_events] == [
        'full_recovery_started',
        'full_recovery_succeeded',
    ]


def test_run_once_keeps_incremental_for_continuous_logout(monkeypatch):
    tracker = DummyTracker()
    status_mgr = DummyStatusManager({
        'acc1': [
            {'event_type': 'logout'},
            {'event_type': 'logout'},
        ]
    })
    monitor = DummyMonitor()

    _patch_run_once(
        monkeypatch,
        {'tiktok': {'use_dynamic_users': False, 'user_ids': ['acc1']}},
        tracker,
        status_mgr,
        monitor,
    )

    main.run_once()

    assert DummyCrawler.calls[0]['full_collection'] is False
    assert tracker.marked == []
    assert status_mgr.appended_events == []


def test_run_once_manual_full_does_not_write_recovery_events(monkeypatch):
    tracker = DummyTracker()
    status_mgr = DummyStatusManager({
        'acc1': [
            {'event_type': 'login'},
            {'event_type': 'logout'},
        ]
    })
    monitor = DummyMonitor()

    _patch_run_once(
        monkeypatch,
        {'tiktok': {'use_dynamic_users': False, 'user_ids': ['acc1']}},
        tracker,
        status_mgr,
        monitor,
    )

    main.run_once(full_collection=True)

    assert DummyCrawler.calls[0]['full_collection'] is True
    assert status_mgr.appended_events == []


def test_scheduler_writes_failed_event_for_recovery_full_failure(monkeypatch):
    tracker = DummyTracker()
    status_mgr = DummyStatusManager({
        'acc1': [
            {'event_type': 'login'},
            {'event_type': 'logout'},
        ]
    })
    monitor = DummyMonitor()

    _patch_scheduler(
        monkeypatch,
        {'tiktok': {'use_dynamic_users': False, 'user_ids': ['acc1']}},
        tracker,
        status_mgr,
        monitor,
    )
    DummyCrawler.results_by_user = {
        'acc1': {
            'success': False,
            'login_status': True,
            'error': 'mock failure',
        }
    }

    scheduler = TaskScheduler()
    scheduler.execute_crawl_task()

    assert DummyCrawler.calls[0]['full_collection'] is True
    assert tracker.marked == []
    assert [event['event_type'] for event in status_mgr.appended_events] == [
        'full_recovery_started',
        'full_recovery_failed',
    ]
