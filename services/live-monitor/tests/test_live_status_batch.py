import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import live_status


class FakeRepository:
    def __init__(self, rows=None, should_fail=False):
        self.rows = rows or {}
        self.should_fail = should_fail

    def list_live_status(self, collection_ids):
        if self.should_fail:
            raise RuntimeError("redis down")
        return [
            self.rows.get(
                collection_id,
                {"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""},
            )
            for collection_id in collection_ids
        ]


def make_client(repo):
    app = FastAPI()
    live_status._repository = repo
    app.include_router(live_status.router)
    return TestClient(app)


def test_batch_live_status_keeps_request_order():
    client = make_client(
        FakeRepository(
            {
                "coll_1": {
                    "collectionId": "coll_1",
                    "isLive": True,
                    "roomId": "7544720840995162887",
                    "flvUrl": "https://pull-flv.example/live.flv",
                },
                "coll_2": {
                    "collectionId": "coll_2",
                    "isLive": False,
                    "roomId": "",
                    "flvUrl": "",
                },
            }
        )
    )

    response = client.post("/api/v1/tiktok/live-status/batch", json={"collectionIds": ["coll_2", "coll_1"]})

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": [
            {"collectionId": "coll_2", "isLive": False, "roomId": "", "flvUrl": ""},
            {
                "collectionId": "coll_1",
                "isLive": True,
                "roomId": "7544720840995162887",
                "flvUrl": "https://pull-flv.example/live.flv",
            },
        ],
    }


def test_batch_live_status_missing_status_is_offline():
    client = make_client(FakeRepository())

    response = client.post("/api/v1/tiktok/live-status/batch", json={"collectionIds": ["coll_missing"]})

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"collectionId": "coll_missing", "isLive": False, "roomId": "", "flvUrl": ""}
    ]


def test_batch_live_status_redis_failure_returns_5099():
    client = make_client(FakeRepository(should_fail=True))

    response = client.post("/api/v1/tiktok/live-status/batch", json={"collectionIds": ["coll_1"]})

    assert response.status_code == 200
    assert response.json()["code"] == 5099
    assert response.json()["data"] is None
