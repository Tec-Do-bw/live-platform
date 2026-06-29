import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg


class FakeApollo:
    def __init__(self, store):
        self.store = store

    def get_value(self, key, default_val=None, namespace="application"):
        return self.store.get(key, default_val)


def test_stream_int_with_minimum(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "3"}))
    assert cfg.stream_max_retries() == 3


def test_stream_int_falls_back_to_default_on_garbage(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "abc"}))
    assert cfg.stream_max_retries() == 12


def test_stream_int_minimum_clamp(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.heartbeat_interval_seconds": "1"}))
    assert cfg.stream_heartbeat_interval_seconds() == 5  # 最小值=5


def test_redis_config_types(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "redis.host": "10.0.0.1", "redis.port": "6380",
        "redis.password": "pw", "redis.db": "2",
    }))
    rc = cfg.redis_config()
    assert rc == {"host": "10.0.0.1", "port": 6380, "password": "pw", "db": 2}


def test_kafka_servers_no_eval(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "kafka.servers": "10.0.0.1:9092,10.0.0.2:9092",
    }))
    assert cfg.kafka_servers() == ["10.0.0.1:9092", "10.0.0.2:9092"]


def test_room_source_is_redis(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.room_source": "redis"}))
    assert cfg.is_redis_room_source() is True
