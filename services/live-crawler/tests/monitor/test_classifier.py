import pytest
from monitor.classifier import classify_api, extract_stats_types


class TestExtractStatsTypes:
    def test_trend_chart_format(self):
        body = {"request": {"room_filter": {"room_id": "123"}, "stats_types": [3, 20]}}
        assert extract_stats_types(body) == [3, 20]

    def test_live_list_format(self):
        body = {"request": {"params": [{"stats_types": [10, 15, 11]}]}}
        assert extract_stats_types(body) == [10, 15, 11]

    def test_json_string_input(self):
        import json
        body = json.dumps({"request": {"stats_types": [52]}})
        assert extract_stats_types(body) == [52]

    def test_empty_input(self):
        assert extract_stats_types(None) == []
        assert extract_stats_types("") == []
        assert extract_stats_types({}) == []


class TestClassifyApi:
    def test_live_list(self):
        assert classify_api("https://shop.tiktok.com/api/v2/insights/creator/live/list?aid=123") == 'live_list'

    def test_replay_info(self):
        assert classify_api("https://webcast.tiktok.com/webcast/room/replay/info") == 'replay_info'

    def test_trend_chart_gmv_stats3(self):
        body = {"request": {"stats_types": [3], "granularity": 1}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_gmv'

    def test_trend_chart_gmv_stats52(self):
        body = {"request": {"stats_types": [52], "granularity": 15}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_gmv'

    def test_trend_chart_traffic(self):
        body = {"request": {"stats_types": [60, 61]}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_traffic'

    def test_trend_chart_stats(self):
        body = {"request": {"stats_types": [3, 20, 341, 21, 22]}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_stats'

    def test_unknown_url(self):
        assert classify_api("https://example.com/other") is None

    def test_empty_url(self):
        assert classify_api("") is None
