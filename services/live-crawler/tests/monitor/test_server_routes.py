import sys
import types


def _fake_drission_page_module():
    drission_page = types.ModuleType("DrissionPage")
    drission_page.Chromium = object
    drission_page.ChromiumOptions = object
    return drission_page


def test_monitor_server_registers_existing_api_routes(monkeypatch):
    monkeypatch.setitem(sys.modules, "DrissionPage", _fake_drission_page_module())

    from monitor.server import app

    paths = {route.path for route in app.routes}

    assert "/api/cookies/{account_id}" in paths
    assert "/api/refresh_tiktok_credential" in paths
    assert "/api/v1/tiktok/live-status/batch" in paths
    assert "/api/v1/tiktok/dashboard/data" in paths
