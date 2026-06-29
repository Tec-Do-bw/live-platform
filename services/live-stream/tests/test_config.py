import importlib
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeApollo:
    def __init__(self, store):
        self.store = store

    def get_value(self, key, default_val=None, namespace="application"):
        return self.store.get(key, default_val)


@pytest.fixture
def cfg(monkeypatch):
    old_config = sys.modules.pop("config", None)
    fake_apollo_module = types.ModuleType("core.apollo")
    fake_apollo_module.APOLLO = FakeApollo({})
    monkeypatch.setitem(sys.modules, "core.apollo", fake_apollo_module)
    cfg_module = importlib.import_module("config")
    try:
        yield cfg_module
    finally:
        if sys.modules.get("config") is cfg_module:
            sys.modules.pop("config", None)
        if old_config is not None:
            sys.modules["config"] = old_config


def test_stream_int_with_minimum(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "3"}))
    assert cfg.stream_max_retries() == 3


def test_stream_int_falls_back_to_default_on_garbage(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "abc"}))
    assert cfg.stream_max_retries() == 12


def test_stream_int_minimum_clamp(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.heartbeat_interval_seconds": "1"}))
    assert cfg.stream_heartbeat_interval_seconds() == 5  # 最小值=5


def test_redis_config_types(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "redis.host": "10.0.0.1", "redis.port": "6380",
        "redis.password": "pw", "redis.db": "2",
    }))
    rc = cfg.redis_config()
    assert rc == {"host": "10.0.0.1", "port": 6380, "password": "pw", "db": 2}


def test_kafka_servers_no_eval(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "kafka.servers": "10.0.0.1:9092,10.0.0.2:9092",
    }))
    assert cfg.kafka_servers() == ["10.0.0.1:9092", "10.0.0.2:9092"]


def test_kafka_servers_skips_blank_items(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "kafka.servers": " a:1, , b:2 ",
    }))
    assert cfg.kafka_servers() == ["a:1", "b:2"]


def test_room_source_is_redis(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.room_source": "redis"}))
    assert cfg.is_redis_room_source() is True


def test_room_source_strips_spaces_and_ignores_case(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.room_source": " ReDiS "}))
    assert cfg.is_redis_room_source() is True


def test_worker_id_strips_configured_value(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.worker_id": " worker-1 "}))
    assert cfg.worker_id() == "worker-1"


def test_worker_id_blank_config_falls_back(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.worker_id": "   "}))
    monkeypatch.setattr(cfg.socket, "gethostname", lambda: "host-1")
    monkeypatch.setattr(cfg.socket, "gethostbyname", lambda hostname: "127.0.0.1")
    monkeypatch.setattr(cfg.os, "getpid", lambda: 12345)

    assert cfg.worker_id() == "host-1:127.0.0.1:12345"


def test_worker_id_hostname_error_falls_back(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({}))

    def raise_hostname_error():
        raise OSError("hostname unavailable")

    monkeypatch.setattr(cfg.socket, "gethostname", raise_hostname_error)
    monkeypatch.setattr(cfg.os, "getpid", lambda: 12345)

    assert cfg.worker_id() == "unknown:unknown:12345"
