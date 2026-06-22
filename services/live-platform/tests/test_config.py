from __future__ import annotations

import pytest

from shared.config import ConfigError, load_settings


def full_apollo_config(**overrides):
    config = {
        "livePlatformHost": "0.0.0.0",
        "livePlatformPort": "8080",
        "livePlatformDetectIntervalSeconds": "60",
        "livePlatformAccessToken": "token",
        "mediaMtxApiBaseUrl": "http://mediamtx:9997",
        "mediaMtxRtmpBaseUrl": "rtmp://mediamtx:1935/live",
        "mediaMtxRecordRoot": "/data/recordings",
        "segmentTimeoutSeconds": "30",
        "redisHost": "redis",
        "redisPort": "6379",
        "redisPassword": "secret",
        "redisDb": "0",
        "endpoint": "https://oss.example.com",
        "bucket_name": "live-bucket",
        "access_key_id": "ak",
        "access_key_secret": "sk",
        "ossPrefix": "realtime-video/",
        "ossSignedUrlTtlSeconds": "15552000",
        "kafkaPro": "['host1:9092','host2:9092']",
        "topic_name": "liveTs",
        "cutliveNumber": "4",
        "uploadWorkerCount": "2",
        "livePlatformLogDir": "logs",
        "devSqlHost": "mysql",
        "devSqlPort": "3306",
        "devSqlUser": "live_user",
        "devSqlPassword": "live_password",
        "database": "live_test01",
    }
    config.update(overrides)
    return config


def full_settings(**overrides):
    return load_settings(full_apollo_config(**overrides))


def test_apollo_required_keys_fill_settings():
    settings = load_settings(full_apollo_config())

    assert settings.oss.endpoint == "https://oss.example.com"
    assert settings.oss.bucket_name == "live-bucket"
    assert settings.kafka.bootstrap_servers == "host1:9092,host2:9092"
    assert settings.kafka.topic_name == "liveTs"
    assert settings.server.max_active_recordings == 4
    assert settings.redis.host == "redis"


def test_kafka_address_alias_used_when_kafka_pro_missing():
    config = full_apollo_config(kafkaAddress="['backup1:9092']")
    del config["kafkaPro"]

    settings = load_settings(config)

    assert settings.kafka.bootstrap_servers == "backup1:9092"


def test_missing_apollo_key_raises_config_error():
    config = full_apollo_config()
    del config["topic_name"]

    with pytest.raises(ConfigError, match="topic_name"):
        load_settings(config)


def test_invalid_int_raises_config_error():
    with pytest.raises(ConfigError, match="livePlatformPort"):
        load_settings(full_apollo_config(livePlatformPort="not-int"))
