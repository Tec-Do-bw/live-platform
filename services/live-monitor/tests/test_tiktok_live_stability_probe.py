import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "tiktok_live_stability_probe.py"
)
SPEC = importlib.util.spec_from_file_location("tiktok_live_stability_probe", SCRIPT_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def make_sample(
    collection_id,
    *,
    is_live=True,
    flv_url="https://pull.example/game/stream-1.flv?expire=2000&sign=abc",
    now=1000,
):
    batch_item = {
        "collectionId": collection_id,
        "isLive": is_live,
        "roomId": "room-1" if is_live else "",
        "flvUrl": flv_url if is_live else "",
    }
    raw = {
        "status": "live" if is_live else "offline",
        "code": "200" if is_live else "2001",
        "updatedAt": str(now),
        "expiresAt": str(now + 900 if is_live else 0),
        "lastDetectCode": "200" if is_live else "2001",
        "detectFailCount": "0",
        "sourceNode": "node1",
        "flvUrl": flv_url if is_live else "",
        "roomId": "room-1" if is_live else "",
    }
    return probe.MonitorSample(
        batch_by_id={collection_id: batch_item},
        batch_error="",
        redis_by_id={collection_id: {"raw": raw, "ttl": 900}},
        redis_errors={},
        sampled_at=now,
    )


def test_fingerprint_change_treats_same_stream_as_renewal():
    previous = probe.fingerprint_flv_url(
        "https://pull.example/game/stream-123.flv?expire=1000&sign=old"
    )
    current = probe.fingerprint_flv_url(
        "https://pull.example/game/stream-123.flv?expire=2000&sign=new"
    )

    assert current["streamId"] == "stream-123"
    assert current["host"] == "pull.example"
    assert "sign" not in current
    assert probe.classify_flv_change(current, previous) == "renewed"


def test_normal_live_item_has_no_anomaly_reason_or_repair_direction():
    room = {"collectionId": "tiktok_thiefs", "url": "https://www.tiktok.com/@thiefs/live"}
    sample = make_sample(room["collectionId"])

    [item] = probe.build_probe_items(
        rooms=[room],
        sample=sample,
        previous_fingerprints={},
    )

    assert item["classification"] == "confirmed_live"
    assert item["needsPlaywrightVerification"] is False
    assert "anomalyReason" not in item
    assert "repairDirection" not in item
    assert "flvUrl" not in item


def test_offline_monitor_but_live_page_becomes_false_offline():
    room = {"collectionId": "tiktok_thiefs", "url": "https://www.tiktok.com/@thiefs/live"}
    sample = make_sample(room["collectionId"], is_live=False)
    [item] = probe.build_probe_items(
        rooms=[room],
        sample=sample,
        previous_fingerprints={},
    )

    finalized = probe.finalize_with_page_verification(
        item,
        {
            "pageClassification": "confirmed_live",
            "title": "Thiefs (@thiefs) 正在直播 - TikTok 直播",
            "liveRoomStatus": 2,
            "videoCount": 1,
            "hasSigiState": True,
        },
    )

    assert finalized["classification"] == "live_monitor_false_offline"
    assert finalized["repairDirection"] == "refresh_live_monitor_detection"
    assert "batch API returned offline" in finalized["anomalyReason"]


def test_offline_monitor_and_offline_page_gets_reason():
    room = {"collectionId": "tiktok_thiefs", "url": "https://www.tiktok.com/@thiefs/live"}
    sample = make_sample(room["collectionId"], is_live=False)
    [item] = probe.build_probe_items(
        rooms=[room],
        sample=sample,
        previous_fingerprints={},
    )

    finalized = probe.finalize_with_page_verification(
        item,
        {
            "pageClassification": "confirmed_offline",
            "title": "TikTok LIVE has ended",
            "liveRoomStatus": 4,
            "videoCount": 0,
            "hasSigiState": True,
        },
    )

    assert finalized["classification"] == "confirmed_offline"
    assert finalized["repairDirection"] == "manual_check_or_expected_offline"
    assert "TikTok page also indicates offline" in finalized["anomalyReason"]


def test_page_snapshot_classifier_covers_live_offline_and_ambiguous():
    assert probe.classify_page_snapshot(
        {
            "title": "Thiefs (@thiefs) 正在直播 - TikTok 直播",
            "liveRoomStatus": 2,
            "videos": [{"readyState": 4, "ended": False, "videoWidth": 360, "videoHeight": 640}],
        }
    ) == "confirmed_live"
    assert probe.classify_page_snapshot(
        {
            "title": "TikTok LIVE has ended",
            "bodySample": "LIVE has ended",
            "liveRoomStatus": 4,
            "videos": [],
        }
    ) == "confirmed_offline"
    assert probe.classify_page_snapshot(
        {
            "title": "TikTok",
            "bodySample": "登录后继续体验",
            "liveRoomStatus": None,
            "videos": [],
        }
    ) == "ambiguous"


def test_record_does_not_contain_full_signed_flv_url():
    room = {"collectionId": "tiktok_thiefs", "url": "https://www.tiktok.com/@thiefs/live"}
    signed_url = "https://pull.example/game/stream-1.flv?expire=2000&sign=secret"
    sample = make_sample(room["collectionId"], flv_url=signed_url)
    items = probe.build_probe_items(
        rooms=[room],
        sample=sample,
        previous_fingerprints={},
    )
    record = probe.build_record(items, retry_attempted=False)

    serialized = probe.json.dumps(record, ensure_ascii=False)
    assert "sign=secret" not in serialized
    assert signed_url not in serialized


def test_fetch_batch_status_sends_api_token(monkeypatch):
    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 200,
                "message": "success",
                "data": [{"collectionId": "coll-1", "isLive": False, "roomId": "", "flvUrl": ""}],
            }

    def fake_post(url, *, headers, json, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(probe.requests, "post", fake_post)

    data, error = probe.fetch_batch_status("http://api.example/batch", ["coll-1"], 5, "secret-token")

    assert error == ""
    assert seen["headers"] == {"X-API-Token": "secret-token"}
    assert seen["json"] == {"collectionIds": ["coll-1"]}
    assert seen["timeout"] == 5
    assert data["coll-1"]["collectionId"] == "coll-1"
