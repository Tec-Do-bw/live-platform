"""utils/api_response.py 翻译层单测"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.api_response import (
    ApiOutcome,
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
    CODE_MESSAGES,
)


class TestClassifyTiktokResult:

    def test_live_streaming(self):
        raw = {
            "flv_url": "https://pull-flv.example.com/live.flv",
            "play_urls": ["https://pull-flv.example.com/live.flv"],
            "startTime": "1756642228",
            "secUid": "MS4wLjABAAAA",
            "uniqueId": "testuser",
            "roomId": "123456",
            "signature": "sig",
            "id": "789",
            "nickname": "Test User",
            "url": "https://www.tiktok.com/@testuser/live",
            "filePath": "testuser",
        }
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@testuser/live")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "https://pull-flv.example.com/live.flv"
        assert outcome.error_reason is None

    def test_offline_with_user_info(self):
        raw = {
            "flv_url": "",
            "startTime": "",
            "secUid": "MS4wLjABAAAA",
            "uniqueId": "testuser",
            "roomId": "123456",
            "signature": "sig",
            "id": "789",
            "nickname": "Test User",
            "url": "https://www.tiktok.com/@testuser/live",
            "filePath": "testuser",
        }
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@testuser/live")
        assert outcome.code == 2001
        assert "flv_url" not in outcome.port_info
        assert outcome.port_info["uniqueId"] == "testuser"

    def test_room_not_found(self):
        raw = {"flv_url": "", "roomId": "", "message": "用户信息不存在", "url": "..."}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@bad/live")
        assert outcome.code == 4041
        assert outcome.error_reason == ErrorReason.ROOM_NOT_FOUND
        assert outcome.port_info is None

    def test_upstream_request_failed(self):
        raw = {"flv_url": "error", "roomId": "", "message": "请求直播页失败: timeout", "filePath": ""}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5001
        assert outcome.error_reason == ErrorReason.UPSTREAM_REQUEST_FAILED

    def test_parse_failed(self):
        raw = {"flv_url": "", "roomId": "", "message": "页面解析失败", "url": "..."}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5002
        assert outcome.error_reason == ErrorReason.PARSE_FAILED

    def test_internal_error(self):
        raw = {"flv_url": "error", "roomId": "", "message": "tk采集异常", "filePath": ""}
        outcome = classify_tiktok_result(raw, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5099
        assert outcome.error_reason == ErrorReason.INTERNAL_ERROR

    def test_none_input(self):
        outcome = classify_tiktok_result(None, "https://www.tiktok.com/@x/live")
        assert outcome.code == 5099


class TestClassifyShopeeResult:

    def test_live_streaming(self):
        raw = {
            "session": {"uid": 123, "username": "shop1"},
            "play_urls": ["https://play.shopee.com/live.flv"],
            "flv_url": "https://play.shopee.com/live.flv",
            "filePath": "shop1",
            "startTime": 1765530323368,
        }
        outcome = classify_shopee_result(raw, "https://my.shp.ee/xxx")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "https://play.shopee.com/live.flv"

    def test_offline(self):
        raw = {"session": {"uid": 123, "username": "shop1"}, "filePath": "shop1"}
        outcome = classify_shopee_result(raw, "https://my.shp.ee/xxx")
        assert outcome.code == 2001
        assert "flv_url" not in outcome.port_info

    def test_none_input(self):
        outcome = classify_shopee_result(None, "https://my.shp.ee/xxx")
        assert outcome.code == 5099
        assert outcome.error_reason == ErrorReason.INTERNAL_ERROR


class TestClassifyLazadaResult:

    def test_live_streaming(self):
        raw = {
            "roomId": "10026286",
            "liveUuid": "7aca9015",
            "roomStatus": "Online",
            "title": "SALE",
            "startTime": 1765516431000,
            "play_urls": ["http://pull-live.lazcdn.com/live.flv"],
            "flv_url": "http://pull-live.lazcdn.com/live.flv",
            "filePath": "teamfulove",
            "mediaUserId": "300680704072",
            "mediaUserName": "teamfulove",
        }
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 200
        assert outcome.port_info["flv_url"] == "http://pull-live.lazcdn.com/live.flv"

    def test_room_not_found(self):
        raw = {"flv_url": "error", "roomId": "", "message": "直播间不存在", "filePath": ""}
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 4041
        assert outcome.error_reason == ErrorReason.ROOM_NOT_FOUND

    def test_history_ended(self):
        raw = {
            "flv_url": "error",
            "roomId": "10026286",
            "message": "当前暂无直播",
            "filePath": "",
            "mediaUserId": "300680704072",
            "mediaUserName": "teamfulove",
        }
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 2002
        assert outcome.port_info["mediaUserId"] == "300680704072"
        assert "flv_url" not in outcome.port_info

    def test_parse_failed(self):
        raw = {"flv_url": "error", "roomId": "", "message": "lazada数据为空", "filePath": ""}
        outcome = classify_lazada_result(raw, "https://s.lazada.com.my/s.xxx")
        assert outcome.code == 5002
        assert outcome.error_reason == ErrorReason.PARSE_FAILED


class TestResponseHelpers:

    def test_success_response_structure(self):
        resp = success_response(200, {"flv_url": "http://x.flv"}, "https://tiktok.com/@x/live")
        assert resp["code"] == 200
        assert resp["message"] == "success"
        assert resp["data"]["mateUrl"] == "https://tiktok.com/@x/live"
        assert resp["data"]["port_info"]["flv_url"] == "http://x.flv"
        assert "error" not in resp

    def test_error_response_structure(self):
        resp = error_response(4041, "ROOM_NOT_FOUND", "用户不存在", "tiktok", "https://tiktok.com/@x/live")
        assert resp["code"] == 4041
        assert resp["message"] == "直播间不存在"
        assert resp["data"]["port_info"] is None
        assert resp["error"]["platform"] == "tiktok"
        assert resp["error"]["reason"] == "ROOM_NOT_FOUND"
        assert resp["error"]["detail"] == "用户不存在"

    def test_error_detail_truncation(self):
        long_detail = "x" * 500
        resp = error_response(5099, "INTERNAL_ERROR", long_detail, "tiktok", "url")
        assert len(resp["error"]["detail"]) == 200
