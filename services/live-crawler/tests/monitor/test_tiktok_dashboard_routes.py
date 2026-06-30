from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from monitor.api import dashboard_routes
from monitor.api.auth import API_TOKEN
from services.dashboard_data import DashboardApiError


def make_client(monkeypatch, handler):
    app = FastAPI()
    monkeypatch.setattr(dashboard_routes, "fetch_dashboard_data", handler)
    app.include_router(dashboard_routes.router)
    return TestClient(app)


def _payload(**overrides):
    payload = {
        "dataType": "core_stats",
        "roomId": "room-1",
        "collectionId": "coll-1",
        "timeRange": "full",
    }
    payload.update(overrides)
    return payload


def test_dashboard_route_requires_token(monkeypatch):
    client = make_client(monkeypatch, lambda req: {"code": 200, "message": "success", "data": {}})

    response = client.post("/api/v1/tiktok/dashboard/data", json=_payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API token"


def test_dashboard_route_rejects_invalid_request(monkeypatch):
    client = make_client(monkeypatch, lambda req: {"code": 200, "message": "success", "data": {}})

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": API_TOKEN},
        json=_payload(roomId=""),
    )

    assert response.status_code == 422


def test_dashboard_route_rejects_product_list_last_30m(monkeypatch):
    client = make_client(monkeypatch, lambda req: {"code": 200, "message": "success", "data": {}})

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": API_TOKEN},
        json=_payload(dataType="product_list", timeRange="last_30m"),
    )

    assert response.status_code == 422


def test_dashboard_route_returns_service_success(monkeypatch):
    seen = {}

    def fake_service(req):
        seen["req"] = req
        return {"code": 200, "message": "success", "data": {"roomId": req.roomId}}

    client = make_client(monkeypatch, fake_service)

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": API_TOKEN},
        json=_payload(dataType="room_info"),
    )

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "success", "data": {"roomId": "room-1"}}
    assert seen["req"].dataType.value == "room_info"


def test_dashboard_route_maps_upstream_error(monkeypatch):
    def fake_service(req):
        raise DashboardApiError(5001, "upstream_error", "bad gateway")

    client = make_client(monkeypatch, fake_service)

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": API_TOKEN},
        json=_payload(dataType="trend_chart"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 5001,
        "message": "上游请求失败",
        "dataType": "trend_chart",
        "roomId": "room-1",
        "error": {"reason": "upstream_error", "detail": "bad gateway"},
    }


def test_dashboard_route_maps_non_upstream_error_message(monkeypatch):
    def fake_service(req):
        raise DashboardApiError(5099, "internal_error", "boom")

    client = make_client(monkeypatch, fake_service)

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": API_TOKEN},
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.json()["message"] == "API request failed"
    assert response.json()["error"] == {"reason": "internal_error", "detail": "boom"}
