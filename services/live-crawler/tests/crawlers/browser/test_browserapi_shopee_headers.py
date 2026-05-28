"""BrowserApi 对 Shopee sessionList 透传请求头的测试。"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _load_browserapi_module():
    """最小化加载 BrowserApi 模块，避免真实浏览器依赖。"""
    module_name = "webdriver.browserapi_for_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    swapped_modules = {}

    def _swap_module(name: str, module: types.ModuleType) -> None:
        swapped_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    fake_utils = types.ModuleType("utils")
    fake_utils.__path__ = []
    _swap_module("utils", fake_utils)

    fake_core = types.ModuleType("core")
    fake_core.__path__ = []
    _swap_module("core", fake_core)

    fake_logger_module = types.ModuleType("utils.logger")

    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

    fake_logger_module.logger = DummyLogger()
    _swap_module("utils.logger", fake_logger_module)

    fake_config_module = types.ModuleType("core.config")

    class DummySettings:
        PLATFORM_CONFIG = {}
        ADSPOWER_CONFIG = {"api_url": "http://127.0.0.1:50325"}

    fake_config_module.Settings = DummySettings
    _swap_module("core.config", fake_config_module)

    fake_drission = types.ModuleType("DrissionPage")

    class DummyChromium:
        pass

    class DummyChromiumOptions:
        def set_address(self, *args, **kwargs):
            pass

        def set_browser_path(self, *args, **kwargs):
            pass

    fake_drission.Chromium = DummyChromium
    fake_drission.ChromiumOptions = DummyChromiumOptions
    _swap_module("DrissionPage", fake_drission)

    module_path = Path(__file__).resolve().parents[3] / "webdriver" / "browserapi.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in swapped_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_get_listened_data_attaches_headers_for_shopee_session_list():
    """Shopee sessionList 被拦截时应附带原始请求头，供后续 JS 注入复用。"""
    browserapi_module = _load_browserapi_module()
    browser_api = browserapi_module.BrowserApi()
    tab = MagicMock()

    packet = MagicMock()
    packet.url = "https://seller.shopee.com.my/api/supply/lm/sellercenter/realtime/sessionList"
    packet.method = "GET"
    packet.request = MagicMock()
    packet.request.postData = None
    packet.request.headers = {
        ":authority": "seller.shopee.com.my",
        "x-test-header": "token",
        "referer": "https://seller.shopee.com.my/creator-center/insight/live/list",
    }
    packet.response = MagicMock()
    packet.response.body = {"data": {"list": []}}
    tab.listen.steps.return_value = [packet]

    result = browser_api.get_listened_data(
        tab,
        ["api/supply/lm/sellercenter/realtime/sessionList"],
        wait_time=1,
        count=1,
    )

    assert len(result) == 1
    assert result[0]["headers"] == {
        "x-test-header": "token",
        "referer": "https://seller.shopee.com.my/creator-center/insight/live/list",
    }
