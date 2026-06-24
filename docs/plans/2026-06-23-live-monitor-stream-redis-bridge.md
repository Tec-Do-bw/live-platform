# Live Monitor Stream Redis Bridge Implementation Plan

> **For agentic workers:** Execute task-by-task with checkbox (`- [ ]`) tracking. Use `subagent-driven-development` only when tasks are independent and risk/scale justifies review overhead; otherwise use `executing-plans` or inline execution with checkpoints.

**Goal:** Replace the process-local `live-monitor` to `live-stream` room handoff with a Redis bridge, while adding the TikTok live-status batch API.

**Architecture:** `live-monitor` writes seed/config and live status to Redis; `live-stream` reads fresh status and atomically claims recording leases; dashboard callers read live status from `live-monitor` without triggering upstream TikTok requests.

**Tech Stack:** Python, FastAPI, redis-py, pytest, existing Apollo config keys `redisHost` / `redisPort` / `redisPassword` / `redisDb`.

> 2026-06-24 note: `services/live-platform/` 已删除。本文只保留其历史 Redis key shape 作为设计来源，不再包含任何 live-platform recorder 改动。

---

## Source Spec

Implement against `docs/specs/live-monitor-stream-redis-bridge.md`.

Do not include historical `services/live-platform` MediaMTX recorder changes in this plan. Only reuse its Redis seed/status key shape as a design precedent.

## File Structure

Create:

- `services/live-monitor/utils/redis_bridge.py`
- `services/live-monitor/tests/test_redis_bridge.py`
- `services/live-monitor/tests/test_live_status_batch.py`
- `services/live-stream/redis_room_source.py`
- `services/live-stream/tests/test_redis_room_source.py`

Modify:

- `services/live-monitor/main.py`
- `services/live-stream/TT_client.py`
- `services/live-stream/requirements.txt`
- `services/live-monitor/README.md` if new route/module needs human-facing docs
- `services/live-stream/README.md` if Redis mode changes startup/config docs

## Task 1: live-monitor Redis Bridge Repository

**Files:**
- Create: `services/live-monitor/utils/redis_bridge.py`
- Test: `services/live-monitor/tests/test_redis_bridge.py`

- [x] **Step 1: Write repository tests**

Cover:

```python
def test_upsert_config_writes_collection_set_and_hash():
    ...

def test_build_status_payload_live_success_keeps_flv_url():
    ...

def test_build_status_payload_offline_clears_flv_url():
    ...

def test_list_live_status_keeps_requested_order_and_missing_is_offline():
    ...
```

Run:

```powershell
pytest services/live-monitor/tests/test_redis_bridge.py -v
```

Expected: fail because `utils.redis_bridge` does not exist.

- [x] **Step 2: Implement key helpers and fake-redis compatible repository**

Implement these public names:

```python
COLLECTIONS_KEY = "live:monitor:collections"

def config_key(collection_id: str) -> str: ...
def status_key(collection_id: str) -> str: ...
def lease_key(collection_id: str) -> str: ...
def recording_key(collection_id: str) -> str: ...

class LiveRedisRepository:
    def __init__(self, redis_client=None): ...
    def upsert_config(self, *, collection_id, room_url, platform, legacy_room_id="", enabled=True) -> None: ...
    def write_status(self, *, collection_id, platform, room_url, outcome, port_info, source_node) -> dict[str, str]: ...
    def list_live_status(self, collection_ids: list[str]) -> list[dict]: ...
```

Use `fetch_apollo_config(ISTEST)` only in the default Redis client factory. Tests should inject a fake client and avoid network.

- [x] **Step 3: Run repository tests**

Run:

```powershell
pytest services/live-monitor/tests/test_redis_bridge.py -v
```

Expected: pass.

## Task 2: live-monitor Seed and Status Dual-Write

**Files:**
- Modify: `services/live-monitor/main.py`
- Test: `services/live-monitor/tests/test_redis_bridge.py`

- [x] **Step 1: Extend seed sync behavior in tests**

Add tests for:

- `collection_id` present: use it as `collectionId`
- `collection_id` missing: fallback to legacy `room_id`
- changed `room_url` updates the config hash every sync
- simulated MySQL failure does not prune Redis

- [x] **Step 2: Modify `select_Info()`**

Keep `all_Live_Room_dict` for backward compatibility, but also upsert Redis config for each active seed.

Use the preferred query:

```sql
SELECT room_id, room_url, allocation_status, collection_id, platform
FROM live_streaming_room
WHERE local_status = 1
```

If the query fails due to missing columns, fall back to the legacy query:

```sql
SELECT room_id, room_url, allocation_status
FROM live_streaming_room
WHERE local_status = 1
```

- [x] **Step 3: Modify `check_live_status()`**

After classifying each room result, write Redis `status` via `LiveRedisRepository.write_status()`.

Rules:

- `code=200`: write `isLive=1`, `roomId`, `flvUrl`, `expiresAt`
- `code=2001/2002`: write `isLive=0`, clear `flvUrl`
- `code=5001/5002/5003/5099`: write `lastDetectCode/lastDetectReason/lastDetectMessage/lastDetectAt`, increment `detectFailCount`, and do not clear or extend the previous `flvUrl`

Business rule:

- 检测异常不等于未开播。
- 只有平台明确返回未开播，才清空直播地址。
- 上一次直播地址如果仍在原始有效期内，可以继续被正在录制的任务使用；过期后不再分配新录制，等待下一轮成功检测。

- [x] **Step 4: Run focused tests**

Run:

```powershell
pytest services/live-monitor/tests/test_redis_bridge.py services/live-monitor/tests/test_api_response.py -v
```

Expected: pass.

## Task 3: live-status Batch API

**Files:**
- Modify: `services/live-monitor/main.py`
- Test: `services/live-monitor/tests/test_live_status_batch.py`

- [x] **Step 1: Write API tests**

Tests:

```python
def test_batch_live_status_keeps_request_order(client):
    ...

def test_batch_live_status_missing_status_is_offline(client):
    ...

def test_batch_live_status_redis_failure_returns_5099(client):
    ...
```

Expected response item:

```json
{ "collectionId": "coll_1001", "isLive": true, "roomId": "7544720840995162887", "flvUrl": "https://pull-flv.example/live.flv" }
```

Test note:

- Monkeypatch the Redis repository/factory and FastAPI dependencies so importing `main.app` does not hit real Apollo, MySQL, or Redis.
- Keep route tests focused on response shape and Redis read semantics, not service bootstrap.

- [x] **Step 2: Implement route**

Add:

```text
POST /api/v1/tiktok/live-status/batch
```

The route reads Redis only. It must not call `TiktokTool`.

- [x] **Step 3: Run API tests**

Run:

```powershell
pytest services/live-monitor/tests/test_live_status_batch.py -v
```

Expected: pass.

## Task 4: live-stream Redis Room Source and Lease

**Files:**
- Create: `services/live-stream/redis_room_source.py`
- Modify: `services/live-stream/requirements.txt`
- Test: `services/live-stream/tests/test_redis_room_source.py`

- [x] **Step 1: Add dependency**

Add to `services/live-stream/requirements.txt`:

```text
redis==7.1.0
```

- [x] **Step 2: Write lease tests**

Tests:

```python
def test_claim_allows_one_worker_only():
    ...

def test_renew_requires_same_worker():
    ...

def test_release_requires_same_worker():
    ...

def test_live_candidates_skip_expired_status():
    ...
```

- [x] **Step 3: Implement `RedisRoomSource`**

Public methods:

```python
class RedisRoomSource:
    def list_live_candidates(self, limit: int) -> list[dict]: ...
    def claim(self, collection_id: str, worker_id: str, ttl_seconds: int = 360) -> bool: ...
    def renew(self, collection_id: str, worker_id: str, ttl_seconds: int = 360) -> bool: ...
    def release(self, collection_id: str, worker_id: str) -> bool: ...
    def write_recording_status(self, collection_id: str, mapping: dict, ttl_seconds: int = 360) -> None: ...
```

Use Lua compare-and-act for renew/release.

- [x] **Step 4: Run tests**

Run:

```powershell
pytest services/live-stream/tests/test_redis_room_source.py -v
```

Expected: pass.

## Task 5: live-stream Redis Mode Integration

**Files:**
- Modify: `services/live-stream/TT_client.py`
- Test: `services/live-stream/tests/test_redis_room_source.py`

- [x] **Step 1: Add feature flag**

Use an environment flag:

```text
LIVE_STREAM_ROOM_SOURCE=redis
```

Default stays `http` for safe rollout.

- [x] **Step 2: Replace acquisition path behind the flag**

When Redis mode is enabled:

1. read live candidates;
2. claim lease;
3. re-read the candidate status after claim;
4. start `ProducerTask` with the latest `flvUrl`;
5. renew lease while recording;
6. release lease on stop/failure.

Compatibility note:

- `online_room_list` may remain as a local cache for existing file-upload and cleanup code paths.
- `report_roominfo` must stop acting as the cross-service ownership source for Redis-owned rooms; otherwise stale HTTP heartbeats can re-allocate rooms in `live-monitor` memory after Redis has expired the lease.
- Any helper that currently assumes `/get_roominfo` is the only ownership source must be routed through the Redis lease/status path first.

- [x] **Step 3: Reconnect must refresh FLV URL**

Before retrying FFmpeg after a health failure, re-read Redis status:

- if `flvUrl` changed, restart with the new URL;
- if expired/offline, stop and release lease;
- otherwise retry the same URL.

- [x] **Step 4: Run smoke tests**

Run:

```powershell
pytest services/live-stream/tests/test_redis_room_source.py -v
```

Expected: pass.

Manual smoke:

```powershell
redis-cli SADD live:monitor:collections coll_test_001
redis-cli HSET live:collection:coll_test_001:status collectionId coll_test_001 isLive 1 roomId 7544720840995162887 flvUrl https://pull-flv.example/live.flv updatedAt 1781149500 expiresAt 4102444800 platform tiktok
```

Expected: one live-stream worker can claim `coll_test_001`; a second worker cannot.

## Task 6: Documentation and Rollout

**Files:**
- Modify: `services/live-monitor/README.md`
- Modify: `services/live-stream/README.md`
- Modify: `docs/ROADMAP.md` when implementation begins/completes

- [x] **Step 1: Document config**

Add Redis keys and the `LIVE_STREAM_ROOM_SOURCE=redis` rollout flag to the service READMEs.

- [x] **Step 2: Document rollback**

Rollback path:

```text
LIVE_STREAM_ROOM_SOURCE=http
```

This restores old `/get_roominfo` and `/report_roominfo` polling while Redis dual-write remains harmless.

- [x] **Step 3: Final verification**

Run:

```powershell
pytest services/live-monitor/tests/test_redis_bridge.py services/live-monitor/tests/test_live_status_batch.py services/live-monitor/tests/test_api_response.py -v
pytest services/live-stream/tests/test_redis_room_source.py -v
git diff --stat
```

Expected: all focused tests pass; diff touches only planned files.
