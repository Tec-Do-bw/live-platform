from __future__ import annotations

import httpx
import pytest

from orchestrator.mediamtx_client import MediaMTXClient
from shared.config import MediaMTXConfig


@pytest.mark.asyncio
async def test_add_path_creates_missing_path_without_delete_noise():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        mediamtx = MediaMTXClient(
            MediaMTXConfig(api_base_url="http://mediamtx:9997"),
            client=client,
        )

        await mediamtx.add_path("tiktok-c1")

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v3/config/paths/list"),
        ("POST", "/v3/config/paths/add/tiktok-c1"),
    ]
    assert requests[1].read() == b'{"source":"publisher"}'


@pytest.mark.asyncio
async def test_add_path_removes_existing_path_before_recreate():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"name": "tiktok-c1"}]})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        mediamtx = MediaMTXClient(
            MediaMTXConfig(api_base_url="http://mediamtx:9997"),
            client=client,
        )

        await mediamtx.add_path("tiktok-c1")

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v3/config/paths/list"),
        ("DELETE", "/v3/config/paths/delete/tiktok-c1"),
        ("POST", "/v3/config/paths/add/tiktok-c1"),
    ]


@pytest.mark.asyncio
async def test_remove_path_treats_missing_path_as_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v3/config/paths/delete/tiktok-c1"
        return httpx.Response(404, json={"error": "path not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        mediamtx = MediaMTXClient(
            MediaMTXConfig(api_base_url="http://mediamtx:9997"),
            client=client,
        )

        await mediamtx.remove_path("tiktok-c1")
