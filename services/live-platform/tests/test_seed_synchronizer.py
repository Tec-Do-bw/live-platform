from __future__ import annotations

from orchestrator.seed_synchronizer import SeedSynchronizer


def test_fetch_seeds_from_mysql_builds_monitored_rooms(monkeypatch):
    rows = [
        (
            "legacy-room-id",
            "https://example.com/live",
            "0",
            "collection-1",
            "TikTok",
        )
    ]

    monkeypatch.setattr("orchestrator.seed_synchronizer.db_pool.execute_query", lambda sql: rows)

    seeds = SeedSynchronizer(repository=object())._fetch_seeds_from_mysql()

    assert len(seeds) == 1
    assert seeds[0].collection_id == "collection-1"
    assert seeds[0].platform == "tiktok"
    assert seeds[0].room_url == "https://example.com/live"
