#!/usr/bin/env python
"""TikTok 直播稳定性旁路探针。

该脚本只读 live-crawler batch API 和 live-monitor Redis status hash。只有监控状态异常时，
才启动 Playwright 打开 TikTok 页面做一次真实页面复核。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


DEFAULT_API_URL = "http://127.0.0.1:8777/api/v1/tiktok/live-status/batch"
DEFAULT_API_TOKEN = os.environ.get("LIVE_CRAWLER_API_TOKEN") or os.environ.get("COOKIE_API_TOKEN") or ""
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_RETRY_DELAY_SECONDS = 2
DEFAULT_PLAYWRIGHT_TIMEOUT_SECONDS = 45
DEFAULT_SESSION_NAME = "tiktok-live-stability-probe"

REPAIR_DIRECTIONS = {
    "live_monitor_false_offline": "refresh_live_monitor_detection",
    "api_error": "verify_redis_write_path",
    "redis_error": "verify_redis_write_path",
    "ambiguous": "browser_or_access_retry",
    "confirmed_offline": "manual_check_or_expected_offline",
}

MONITORED_ROOMS = [
    {
        "collectionId": "tiktok_greameofficialstore",
        "url": "https://www.tiktok.com/@greameofficialstore/live",
    },
    {
        "collectionId": "tiktok_ceraveindonesia",
        "url": "https://www.tiktok.com/@ceraveindonesia/live",
    },
    {
        "collectionId": "tiktok_thiefs",
        "url": "https://www.tiktok.com/@thiefs/live",
    },
    {
        "collectionId": "tiktok_bagsmart_official_id",
        "url": "https://www.tiktok.com/@bagsmart_official.id/live",
    },
]


@dataclass(frozen=True)
class MonitorSample:
    batch_by_id: dict[str, dict[str, Any]]
    batch_error: str
    redis_by_id: dict[str, dict[str, Any]]
    redis_errors: dict[str, str]
    sampled_at: int


class PlaywrightVerifier:
    """用 playwright-cli 做页面验真，便于测试时替换为 fake verifier。"""

    def __init__(
        self,
        *,
        session_name: str = DEFAULT_SESSION_NAME,
        timeout_seconds: int = DEFAULT_PLAYWRIGHT_TIMEOUT_SECONDS,
    ) -> None:
        self.session_name = session_name
        self.timeout_seconds = timeout_seconds
        self._opened = False

    def verify(self, url: str) -> dict[str, Any]:
        try:
            if not self._opened:
                self._run(["open", "--browser=chrome", url])
                self._opened = True
            else:
                self._run(["goto", url])
            raw = self._run(["--raw", "eval", PAGE_SNAPSHOT_SCRIPT])
            snapshot = parse_playwright_json(raw)
            page_classification = classify_page_snapshot(snapshot)
            snapshot["pageClassification"] = page_classification
            return snapshot
        except Exception as exc:
            return {
                "pageClassification": "ambiguous",
                "error": f"{type(exc).__name__}: {exc}",
            }

    def close(self) -> None:
        if self._opened:
            try:
                self._run(["close"])
            finally:
                self._opened = False

    def _run(self, args: list[str]) -> str:
        command = ["playwright-cli", f"-s={self.session_name}", *args]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            raise RuntimeError(stderr or stdout or f"playwright-cli exited {completed.returncode}")
        return completed.stdout.strip()


PAGE_SNAPSHOT_SCRIPT = r"""
(() => {
  const text = document.body?.innerText || "";
  const sigiText = document.querySelector("#SIGI_STATE")?.textContent || "";
  let liveRoomStatus = null;
  let hasLiveRoom = false;
  let uniqueId = "";
  try {
    const sigi = sigiText ? JSON.parse(sigiText) : null;
    const info = sigi?.LiveRoom?.liveRoomUserInfo || {};
    const room = info.liveRoom || {};
    hasLiveRoom = Boolean(info.liveRoom);
    liveRoomStatus = room.status ?? null;
    uniqueId = String(info.user?.uniqueId || "");
  } catch (e) {}
  const videos = [...document.querySelectorAll("video")].map(v => ({
    readyState: v.readyState,
    paused: v.paused,
    ended: v.ended,
    duration: Number.isFinite(v.duration) ? v.duration : null,
    videoWidth: v.videoWidth,
    videoHeight: v.videoHeight,
  }));
  return JSON.stringify({
    url: location.href,
    title: document.title,
    hasSigiState: Boolean(sigiText),
    hasLiveRoom,
    liveRoomStatus,
    uniqueId,
    videoCount: videos.length,
    videos,
    bodySample: text.replace(/\s+/g, " ").slice(0, 500),
  });
})()
"""


def fingerprint_flv_url(flv_url: str) -> dict[str, str]:
    """提取可记录的 FLV 指纹，避免落完整签名 URL。"""
    if not flv_url:
        return {"hash": "", "host": "", "streamId": "", "expire": ""}
    parsed = urlparse(flv_url)
    query = parse_qs(parsed.query)
    filename = parsed.path.rsplit("/", 1)[-1]
    stream_id = filename[:-4] if filename.endswith(".flv") else filename
    return {
        "hash": hashlib.md5(flv_url.encode("utf-8")).hexdigest()[:12],
        "host": parsed.netloc,
        "streamId": stream_id,
        "expire": (query.get("expire") or [""])[0],
    }


def classify_flv_change(current: dict[str, str], previous: dict[str, str] | None) -> str:
    if not current.get("hash"):
        return "none"
    if not previous or not previous.get("hash"):
        return "new"
    if current["hash"] == previous.get("hash"):
        return "unchanged"
    if current.get("streamId") and current.get("streamId") == previous.get("streamId"):
        return "renewed"
    return "stream_changed"


def classify_page_snapshot(snapshot: dict[str, Any]) -> str:
    title = str(snapshot.get("title") or "")
    body_sample = str(snapshot.get("bodySample") or "")
    videos = snapshot.get("videos") or []
    live_title = bool(re.search(r"正在直播|LIVE", title, flags=re.IGNORECASE))
    offline_text = bool(
        re.search(
            r"isn't live|not live|live has ended|no live|当前没有直播|直播已结束|暂未开播",
            f"{title} {body_sample}",
            flags=re.IGNORECASE,
        )
    )
    active_video = any(
        int(video.get("readyState") or 0) >= 2
        and not video.get("ended")
        and int(video.get("videoWidth") or 0) > 0
        and int(video.get("videoHeight") or 0) > 0
        for video in videos
    )
    live_room_status = snapshot.get("liveRoomStatus")
    if (live_title or active_video) and live_room_status == 2:
        return "confirmed_live"
    if live_title and active_video:
        return "confirmed_live"
    if offline_text and not active_video and live_room_status != 2:
        return "confirmed_offline"
    return "ambiguous"


def parse_playwright_json(raw: str) -> dict[str, Any]:
    value: Any = raw.strip()
    for _ in range(2):
        if isinstance(value, str):
            value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("playwright eval did not return an object")
    return value


def fetch_batch_status(
    api_url: str,
    collection_ids: list[str],
    timeout_seconds: int,
    api_token: str = "",
) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        headers = {"X-API-Token": api_token} if api_token else {}
        response = requests.post(
            api_url,
            headers=headers,
            json={"collectionIds": collection_ids},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"

    if payload.get("code") != 200:
        return {}, f"batch API code={payload.get('code')} message={payload.get('message')}"
    data = payload.get("data")
    if not isinstance(data, list):
        return {}, "batch API data is not a list"
    return {
        str(item.get("collectionId")): item
        for item in data
        if isinstance(item, dict) and item.get("collectionId")
    }, ""


def create_redis_client() -> Any:
    live_monitor_dir = Path(__file__).resolve().parents[1]
    if str(live_monitor_dir) not in sys.path:
        sys.path.insert(0, str(live_monitor_dir))

    import redis
    import config

    # Redis 连接参数已迁移到 Apollo（config 门面）
    return redis.Redis(
        **config.redis_config(),
        decode_responses=True,
    )


def read_redis_statuses(redis_client: Any, collection_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    statuses: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for collection_id in collection_ids:
        key = f"live:collection:{collection_id}:status"
        try:
            raw = redis_client.hgetall(key)
            statuses[collection_id] = {
                "key": key,
                "raw": dict(raw or {}),
                "ttl": redis_client.ttl(key),
            }
        except Exception as exc:
            errors[collection_id] = f"{type(exc).__name__}: {exc}"
    return statuses, errors


def collect_monitor_sample(
    *,
    api_url: str,
    api_token: str,
    rooms: list[dict[str, str]],
    timeout_seconds: int,
    redis_client: Any | None,
    redis_init_error: str = "",
) -> MonitorSample:
    collection_ids = [room["collectionId"] for room in rooms]
    sampled_at = int(time.time())
    batch_by_id, batch_error = fetch_batch_status(api_url, collection_ids, timeout_seconds, api_token)
    if redis_client is None:
        redis_errors = {collection_id: redis_init_error or "redis client unavailable" for collection_id in collection_ids}
        return MonitorSample(batch_by_id, batch_error, {}, redis_errors, sampled_at)
    redis_by_id, redis_errors = read_redis_statuses(redis_client, collection_ids)
    return MonitorSample(batch_by_id, batch_error, redis_by_id, redis_errors, sampled_at)


def build_probe_items(
    *,
    rooms: list[dict[str, str]],
    sample: MonitorSample,
    previous_fingerprints: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    items = []
    for room in rooms:
        collection_id = room["collectionId"]
        batch_item = sample.batch_by_id.get(collection_id) or {}
        redis_status = sample.redis_by_id.get(collection_id) or {}
        raw = redis_status.get("raw") or {}
        flv_url = str(batch_item.get("flvUrl") or raw.get("flvUrl") or raw.get("flv_url") or "")
        flv_fingerprint = fingerprint_flv_url(flv_url)

        item: dict[str, Any] = {
            "collectionId": collection_id,
            "url": room["url"],
            "classification": "confirmed_live",
            "isLive": bool(batch_item.get("isLive")),
            "roomId": str(batch_item.get("roomId") or raw.get("roomId") or raw.get("room_id") or ""),
            "monitor": sanitize_monitor_status(raw, redis_status.get("ttl")),
            "flv": flv_fingerprint,
            "flvChange": classify_flv_change(flv_fingerprint, previous_fingerprints.get(collection_id)),
            "sampledAt": sample.sampled_at,
            "needsPlaywrightVerification": False,
        }

        reasons: list[str] = []
        preliminary = "confirmed_live"
        monitor_says_live = bool(batch_item.get("isLive")) and bool(batch_item.get("flvUrl"))

        if sample.batch_error:
            preliminary = "api_error"
            reasons.append(sample.batch_error)
        elif not batch_item:
            preliminary = "api_error"
            reasons.append("batch API missing collection item")
        elif not monitor_says_live:
            preliminary = "confirmed_offline"
            reasons.append("batch API returned offline or empty flvUrl")

        redis_error = sample.redis_errors.get(collection_id, "")
        if redis_error:
            preliminary = "redis_error" if preliminary == "confirmed_live" else preliminary
            reasons.append(f"Redis status read failed: {redis_error}")
        else:
            if not raw:
                preliminary = "redis_error" if preliminary == "confirmed_live" else preliminary
                reasons.append("Redis status hash missing")
            else:
                expires_at = safe_int(raw.get("expiresAt"))
                detect_fail_count = safe_int(raw.get("detectFailCount"))
                if expires_at and expires_at <= sample.sampled_at:
                    reasons.append("Redis status expired")
                if detect_fail_count > 0:
                    preliminary = "redis_error" if preliminary == "confirmed_live" else preliminary
                    reasons.append(f"detectFailCount={detect_fail_count}")

        if reasons:
            item["classification"] = preliminary
            item["needsPlaywrightVerification"] = True
            item["_pendingReasons"] = reasons
            item["_monitorSaysLive"] = monitor_says_live
        items.append(item)
    return items


def finalize_with_page_verification(
    item: dict[str, Any],
    page_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    reasons = list(item.pop("_pendingReasons", []))
    monitor_says_live = bool(item.pop("_monitorSaysLive", False))
    item["needsPlaywrightVerification"] = False

    if not reasons:
        return item

    page_classification = (page_snapshot or {}).get("pageClassification", "ambiguous")
    if page_snapshot:
        item["pageVerification"] = sanitize_page_snapshot(page_snapshot)

    if item["classification"] == "api_error":
        classification = "api_error"
    elif item["classification"] == "redis_error" and monitor_says_live:
        classification = "redis_error"
    elif page_classification == "confirmed_live" and not monitor_says_live:
        classification = "live_monitor_false_offline"
        reasons.append("TikTok page is still live while live-monitor reported offline/empty/expired")
    elif page_classification == "confirmed_offline":
        classification = "confirmed_offline"
        reasons.append("TikTok page also indicates offline")
    else:
        classification = "ambiguous"
        reasons.append("Playwright could not prove live or offline")

    item["classification"] = classification
    item["anomalyReason"] = "; ".join(reasons)
    item["repairDirection"] = REPAIR_DIRECTIONS[classification]
    return item


def sanitize_monitor_status(raw: dict[str, Any], ttl: Any) -> dict[str, Any]:
    return {
        "status": str(raw.get("status") or ""),
        "code": str(raw.get("code") or ""),
        "updatedAt": safe_int(raw.get("updatedAt")),
        "expiresAt": safe_int(raw.get("expiresAt")),
        "lastDetectCode": str(raw.get("lastDetectCode") or ""),
        "detectFailCount": safe_int(raw.get("detectFailCount")),
        "ttl": safe_int(ttl, default=-2),
        "sourceNode": str(raw.get("sourceNode") or ""),
    }


def sanitize_page_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "pageClassification": snapshot.get("pageClassification", "ambiguous"),
        "title": snapshot.get("title", ""),
        "liveRoomStatus": snapshot.get("liveRoomStatus"),
        "videoCount": snapshot.get("videoCount", 0),
        "hasSigiState": bool(snapshot.get("hasSigiState")),
        "error": snapshot.get("error", ""),
    }


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_previous_fingerprints(log_dir: Path) -> dict[str, dict[str, str]]:
    if not log_dir.exists():
        return {}
    files = sorted(log_dir.glob("*.jsonl"), reverse=True)
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            fingerprints = {}
            for item in record.get("items", []):
                collection_id = item.get("collectionId")
                flv = item.get("flv") or {}
                if collection_id and flv:
                    fingerprints[str(collection_id)] = flv
            if fingerprints:
                return fingerprints
    return {}


def write_jsonl(record: dict[str, Any], log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def run_probe(
    *,
    api_url: str = DEFAULT_API_URL,
    api_token: str = DEFAULT_API_TOKEN,
    rooms: list[dict[str, str]] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    skip_playwright: bool = False,
    force_playwright: bool = False,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    rooms = rooms or MONITORED_ROOMS
    log_dir = log_dir or default_log_dir()
    previous = load_previous_fingerprints(log_dir)
    redis_client, redis_init_error = init_redis_client()

    sample = collect_monitor_sample(
        api_url=api_url,
        api_token=api_token,
        rooms=rooms,
        timeout_seconds=timeout_seconds,
        redis_client=redis_client,
        redis_init_error=redis_init_error,
    )
    items = build_probe_items(rooms=rooms, sample=sample, previous_fingerprints=previous)
    retry_attempted = any(item.get("needsPlaywrightVerification") for item in items)

    if retry_attempted:
        if retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)
        retry_sample = collect_monitor_sample(
            api_url=api_url,
            api_token=api_token,
            rooms=rooms,
            timeout_seconds=timeout_seconds,
            redis_client=redis_client,
            redis_init_error=redis_init_error,
        )
        items = build_probe_items(rooms=rooms, sample=retry_sample, previous_fingerprints=previous)

    verifier: PlaywrightVerifier | None = None
    if force_playwright or (not skip_playwright and any(item.get("needsPlaywrightVerification") for item in items)):
        verifier = PlaywrightVerifier()

    try:
        for item in items:
            if force_playwright:
                item["needsPlaywrightVerification"] = True
                item.setdefault("_pendingReasons", ["forced Playwright verification"])
                item.setdefault("_monitorSaysLive", bool(item.get("isLive")))
            if item.get("needsPlaywrightVerification"):
                page_snapshot = verifier.verify(item["url"]) if verifier else {"pageClassification": "ambiguous", "error": "Playwright skipped"}
                finalize_with_page_verification(item, page_snapshot)
            else:
                item.pop("_pendingReasons", None)
                item.pop("_monitorSaysLive", None)
    finally:
        if verifier:
            verifier.close()

    record = build_record(items, retry_attempted=retry_attempted)
    record["logPath"] = str(write_jsonl(record, log_dir))
    return record


def init_redis_client() -> tuple[Any | None, str]:
    try:
        return create_redis_client(), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def build_record(items: list[dict[str, Any]], *, retry_attempted: bool) -> dict[str, Any]:
    anomalies = [item for item in items if "anomalyReason" in item]
    return {
        "probe": "tiktok_live_stability",
        "createdAt": int(time.time()),
        "createdAtIso": datetime.now().isoformat(timespec="seconds"),
        "retrySampleAttempted": retry_attempted,
        "summary": {
            "total": len(items),
            "confirmedLive": sum(1 for item in items if item.get("classification") == "confirmed_live"),
            "anomalyCount": len(anomalies),
            "playwrightTriggered": sum(1 for item in items if "pageVerification" in item),
            "flvChanges": summarize_flv_changes(items),
        },
        "items": items,
    }


def summarize_flv_changes(items: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        change = str(item.get("flvChange") or "unknown")
        result[change] = result.get(change, 0) + 1
    return result


def default_log_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "logs" / "tiktok-live-stability"


def format_summary(record: dict[str, Any]) -> str:
    summary = record["summary"]
    if summary["anomalyCount"] == 0:
        return (
            f"OK: {summary['confirmedLive']}/{summary['total']} confirmed_live; "
            f"flvChanges={summary['flvChanges']}; log={record.get('logPath', '')}"
        )

    lines = [
        (
            f"ANOMALY: {summary['anomalyCount']}/{summary['total']} rooms abnormal; "
            f"playwrightTriggered={summary['playwrightTriggered']}; log={record.get('logPath', '')}"
        )
    ]
    for item in record["items"]:
        if "anomalyReason" not in item:
            continue
        lines.append(
            "- {collectionId}: {classification}; reason={reason}; repair={repair}".format(
                collectionId=item["collectionId"],
                classification=item["classification"],
                reason=item["anomalyReason"],
                repair=item["repairDirection"],
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TikTok live stability probe")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-token", default=DEFAULT_API_TOKEN)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY_SECONDS)
    parser.add_argument("--log-dir", type=Path, default=default_log_dir())
    parser.add_argument("--skip-playwright", action="store_true")
    parser.add_argument("--force-playwright", action="store_true")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 结果")
    parser.add_argument("--fail-on-anomaly", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    record = run_probe(
        api_url=args.api_url,
        api_token=args.api_token,
        timeout_seconds=args.timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
        skip_playwright=args.skip_playwright,
        force_playwright=args.force_playwright,
        log_dir=args.log_dir,
    )
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_summary(record))
    if args.fail_on_anomaly and record["summary"]["anomalyCount"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
