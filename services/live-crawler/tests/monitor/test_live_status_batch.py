from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from monitor.api import auth
from monitor.api import live_status_routes


class FakeRepository:
    def __init__(self, rows=None, should_fail=False):
        self.rows = rows or {}
        self.should_fail = should_fail
        self.seen_collection_ids = []

    def list_live_status(self, collection_ids):
        self.seen_collection_ids = list(collection_ids)
        if self.should_fail:
            raise RuntimeError("redis down")
        return [
            self.rows.get(
                collection_id,
                {"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""},
            )
            for collection_id in collection_ids
        ]


def make_client(repo, monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(live_status_routes, "get_repository", lambda: repo)
    app.include_router(live_status_routes.router)
    return TestClient(app)


def test_batch_live_status_requires_token(monkeypatch):
    client = make_client(FakeRepository(), monkeypatch)
    response = client.post("/api/v1/tiktok/live-status/batch", json={"collectionIds": ["coll_1"]})
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API token"


def test_batch_live_status_rejects_wrong_token(monkeypatch):
    client = make_client(FakeRepository(), monkeypatch)
    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": "wrong"},
        json={"collectionIds": ["coll_1"]},
    )
    assert response.status_code == 403


def test_cookie_api_token_missing_config_fails_closed(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")

    with pytest.raises(HTTPException) as exc_info:
        auth.require_cookie_api_token("")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid API token"


def test_batch_live_status_keeps_request_order_and_casts_ids(monkeypatch):
    repo = FakeRepository(
        {
            "coll_1": {
                "collectionId": "coll_1",
                "isLive": True,
                "roomId": "7544720840995162887",
                "flvUrl": "https://pull-flv.example/live.flv",
            },
            "2": {"collectionId": "2", "isLive": False, "roomId": "", "flvUrl": ""},
        }
    )
    client = make_client(repo, monkeypatch)
    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={"collectionIds": [2, "coll_1"]},
    )
    assert response.status_code == 200
    assert repo.seen_collection_ids == ["2", "coll_1"]
    assert response.json()["data"] == [
        {"collectionId": "2", "isLive": False, "roomId": "", "flvUrl": ""},
        {
            "collectionId": "coll_1",
            "isLive": True,
            "roomId": "7544720840995162887",
            "flvUrl": "https://pull-flv.example/live.flv",
        },
    ]


def test_batch_live_status_missing_collection_ids_returns_empty_data(monkeypatch):
    repo = FakeRepository()
    client = make_client(repo, monkeypatch)
    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={},
    )
    assert response.status_code == 200
    assert repo.seen_collection_ids == []
    assert response.json() == {"code": 200, "message": "success", "data": []}


def test_batch_live_status_redis_failure_returns_5099(monkeypatch):
    client = make_client(FakeRepository(should_fail=True), monkeypatch)
    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={"collectionIds": ["coll_1"]},
    )
    assert response.status_code == 200
    assert response.json()["code"] == 5099
    assert response.json()["message"] == "Redis unavailable: redis down"
    assert response.json()["data"] is None
