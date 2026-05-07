from __future__ import annotations

from fastapi.testclient import TestClient

from main import create_app
from shared.config import settings


def test_health_endpoint():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["code"] == 200


def test_live_room_requires_token(monkeypatch):
    async def fake_get_stream_info(platform: str, room_url: str):
        return {"flv_url": "https://example.com/live.flv", "roomId": "123", "filePath": "demo"}

    monkeypatch.setattr("api.routes.get_stream_info", fake_get_stream_info)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/liveRoom/portInfo", json={"mateUrl": "https://example.com/live"})

    assert response.json() == {"code": 401, "message": "Unauthorized"}


def test_live_room_compatible_response(monkeypatch):
    async def fake_get_stream_info(platform: str, room_url: str):
        return {"flv_url": "https://example.com/live.flv", "roomId": "123", "filePath": "demo"}

    monkeypatch.setattr("api.routes.get_stream_info", fake_get_stream_info)
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/liveRoom/portInfo",
            headers={"access-token": settings.server.access_token},
            json={"mateUrl": "https://example.com/live"},
        )

    body = response.json()
    assert body["code"] == 200
    assert body["data"]["port_info"]["flv_url"] == "https://example.com/live.flv"
