# live-monitor / live-stream Redis Bridge Specification

> Status: draft implementation spec
> Date: 2026-06-23
> Scope: `services/live-monitor/` and `services/live-stream/`
> 2026-06-24 note: `services/live-platform/` 已从现役服务树删除。本文保留对其 Redis key shape 的历史引用，仅作为设计来源说明。

## Goal

Use Redis as the contract between `live-monitor` and `live-stream` so that FLV URL resolution, live status, stream-worker ownership, and dashboard live-status reads no longer depend on process-local global dictionaries.

This spec does not depend on the historical `services/live-platform/` MediaMTX recorder. That removed service is only referenced as the source of the Redis seed/status key split.

## Background

Current `live-monitor` stores monitoring state in `all_Live_Room_dict`. It is protected by `room_dict_lock`, but it still has too many responsibilities:

- seed projection from MySQL `live_streaming_room`
- platform live detection result, including `flv_url`
- room allocation state for `live-stream`
- stream worker heartbeat and release decisions
- primary/backup node sync payload

Current `live-stream` polls `POST /get_roominfo`, stores active rooms in its own `online_room_list`, and starts FFmpeg with the returned `flv_url`. If the FLV URL is stale, CDN-switched, or tied to an old live room, FFmpeg retries against the wrong input until the local retry policy gives up.

The new bridge separates ownership:

| Concern | Owner | Redis keys |
|---|---|---|
| monitored room seed/config | `live-monitor` | `live:monitor:collections`, `live:collection:{collectionId}:config` |
| current platform live status and latest FLV URL | `live-monitor` | `live:collection:{collectionId}:status` |
| recording worker lease | `live-stream` | `live:collection:{collectionId}:lease` |
| recording worker runtime status | `live-stream` | `live:collection:{collectionId}:recording` |
| dashboard live-status batch API | `live-monitor` | reads `status` |

## Design Decisions

1. Redis is the bridge contract. `live-stream` must not read MySQL or depend on `live-monitor` process memory.
2. `live-monitor` is the only service that resolves platform live status and writes `flvUrl`.
3. `live-stream` is the only service that owns recording leases and FFmpeg runtime status.
4. Seed/config and runtime status are separate keys, following the historical `services/live-platform/shared/redis_store.py` shape captured during Phase 1.
5. Do not copy the historical `services/live-platform/orchestrator/seed_synchronizer.py` implementation. Reuse only the key contract, but make sync safe on query failure and update changed rows every run.
6. Keep old HTTP endpoints during migration. `/get_roominfo` and `/report_roominfo` can be backed by Redis first, then deprecated after `live-stream` moves to Redis polling.

Reference boundary:

- Historical `services/live-platform/shared/redis_store.py` is a precedent for key naming, config/status separation, and compatibility aliases.
- This bridge extends the status schema with short-lived FLV-url fields such as `expiresAt`, `code`, `errorReason`, and `flvUrl`.
- Do not copy `services/live-platform` MediaMTX recorder behavior or treat its current status hash as the complete schema for this bridge.

## Redis Key Contract

### Collection Set

Key: `live:monitor:collections`

Type: Set

Owner: `live-monitor`

Members: `collectionId`

Purpose: ordered by readers after `SMEMBERS`; this is the seed list used by status detection, batch API reads, and `live-stream` candidate discovery.

### Config Hash

Key: `live:collection:{collectionId}:config`

Type: Hash

Owner: `live-monitor`

TTL: none

Required fields:

| Field | Value |
|---|---|
| `collectionId` | canonical collection id |
| `collection_id` | same value, compatibility alias |
| `legacyRoomId` | old `live_streaming_room.room_id`, if different |
| `room_id` | old `room_id`, compatibility alias |
| `platform` | `tiktok`, `shopee`, or `lazada` |
| `roomUrl` | source live-room URL |
| `room_url` | same value, compatibility alias |
| `enabled` | `1` for active seeds |
| `updatedAt` | Unix seconds |
| `sourceNode` | `NODE_ID` of the writer |

`enabled` values `0`, `false`, `no`, and `off` are disabled. Readers must skip disabled configs.

### Status Hash

Key: `live:collection:{collectionId}:status`

Type: Hash

Owner: `live-monitor`

TTL: `LIVE_STATUS_TTL_SECONDS`, default `900`.

Required fields:

| Field | Value |
|---|---|
| `collectionId` / `collection_id` | collection id |
| `isLive` | `1` when `flvUrl` is non-empty and not `error`, else `0` |
| `roomId` / `room_id` | current platform room id when live, else empty string |
| `flvUrl` / `flv_url` | latest usable FLV URL when live, else empty string |
| `playUrls` | JSON array string, optional alternative stream URLs |
| `platform` | platform from config |
| `roomUrl` / `room_url` | original room URL |
| `status` | `live`, `offline`, `upstream_error`, `parse_error`, or `internal_error` |
| `code` | live-room API business code, such as `200`, `2001`, `5001` |
| `errorReason` / `error_reason` | machine-readable reason from `utils/api_response.py`, empty on success |
| `errorMessage` / `error_message` | concise error detail, empty on success |
| `updatedAt` | Unix seconds when detection wrote the status |
| `expiresAt` | Unix seconds after which `live-stream` must not start/restart FFmpeg with this FLV URL |
| `sourceNode` | `NODE_ID` of the writer |
| `metadata` | JSON string of sanitized `port_info` |
| `lastDetectCode` | latest detection code, including transient detection errors |
| `lastDetectReason` | latest detection error reason, empty for confirmed normal results |
| `lastDetectMessage` | latest detection error detail, empty for confirmed normal results |
| `lastDetectAt` | Unix seconds when the latest detection attempt finished |
| `detectFailCount` | consecutive transient detection failure count |

`live-stream` must treat missing status, expired status, `isLive=0`, empty `flvUrl`, or `flvUrl=error` as "do not start recording".

### Lease String

Key: `live:collection:{collectionId}:lease`

Type: String

Owner: `live-stream`

Value: `workerId`

TTL: `STREAM_LEASE_TTL_SECONDS`, default `360`.

Claim:

```text
SET live:collection:{collectionId}:lease {workerId} NX EX 360
```

Renew and release must be compare-and-act operations. Use Lua so one worker cannot renew or delete another worker's lease:

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("EXPIRE", KEYS[1], tonumber(ARGV[2]))
end
return 0
```

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
```

### Recording Hash

Key: `live:collection:{collectionId}:recording`

Type: Hash

Owner: `live-stream`

TTL: same as lease.

Fields:

| Field | Value |
|---|---|
| `collectionId` | collection id |
| `workerId` | stream worker identity |
| `ip` | stream worker IP |
| `status` | `starting`, `recording`, `reconnecting`, `stopped`, or `failed` |
| `ffmpegPid` | local FFmpeg process id |
| `flvUrlHash` | hash of the FLV URL used by the current FFmpeg process |
| `startedAt` | Unix seconds |
| `lastHeartbeatAt` | Unix seconds |
| `lastSegmentAt` | Unix seconds when a local segment was last observed |
| `lastError` | concise error string |

This key replaces `live-stream`'s cross-service heartbeat payload. It does not replace local file-processing state.

## Seed Sync

`live-monitor` should reuse the `live-platform` seed shape but keep live-monitor as the writer.

Preferred MySQL query:

```sql
SELECT room_id, room_url, allocation_status, collection_id, platform
FROM live_streaming_room
WHERE local_status = 1
```

Compatibility rule:

- If `collection_id` exists and is non-empty, use it as `collectionId`.
- If `collection_id` is missing, use legacy `room_id` as `collectionId` and also write `legacyRoomId`.
- If `platform` is missing, infer it from `room_url` domain.
- Every successful sync upserts all returned rows, not only newly added rows.
- Query failure must not prune Redis keys.
- Pruning stale configs should be guarded by `REDIS_SEED_PRUNE_ENABLED=1` for rollout safety. When disabled, old configs can be marked `enabled=0` manually or by a later controlled cleanup.

## Live Status Write Flow

1. `select_Info()` or a new seed synchronizer writes config keys.
2. `check_live_status()` selects enabled configs that need detection.
3. The platform tool returns raw `port_info`.
4. `utils/api_response.py` classifies the result.
5. `live-monitor` writes `status`:
   - `code=200`: `isLive=1`, write `roomId`, `flvUrl`, `playUrls`, `expiresAt`.
   - `code=2001/2002`: `isLive=0`, keep profile metadata, clear `flvUrl`.
   - `code=5001/5002/5003/5099`: write `lastDetectCode`, `lastDetectReason`, `lastDetectMessage`, `lastDetectAt`, and increment `detectFailCount`; do not clear the previous `flvUrl`, do not change `isLive`, and do not refresh the previous `expiresAt`.

Detection failure is not the same as confirmed offline. If a previous live status is still fresh, `live-stream` may continue using it until its original `expiresAt`; after it expires, the batch API and stream candidate discovery return non-live until a later successful detection refreshes the status.

`flvUrl` should be considered a short-lived runtime value even if the upstream URL contains a long `expire` parameter. CDN switch, room restart, and stream ID changes can invalidate it earlier.

## live-stream Read Flow

`live-stream` must move from "ask live-monitor for one room" to "read fresh Redis status and claim a lease":

1. Read `live:monitor:collections`.
2. Read each `status` and filter `isLive=1`, fresh `expiresAt`, and non-empty `flvUrl`.
3. Claim `lease` with `SET NX EX`.
4. Re-read status after claim. If the status changed to offline or expired, release the lease without starting FFmpeg.
5. Start FFmpeg with the current `flvUrl`.
6. Renew lease while the room is actively recording.
7. On FFmpeg reconnect, re-read Redis status before retrying the same URL:
   - if `flvUrl` changed, restart with the new URL;
   - if status is offline/expired, stop recording and release lease;
   - if status is still live with the same URL, use normal retry policy.
8. Release lease on stop, fatal failure, or worker shutdown.

This is the main fix for stale FLV URL failures.

## Batch Live Status API

Service: `live-monitor`

Endpoint:

```text
POST /api/v1/tiktok/live-status/batch
```

Body:

```json
{ "collectionIds": ["coll_1001", "coll_1002"] }
```

Response:

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "collectionId": "coll_1001",
      "isLive": true,
      "roomId": "7544720840995162887",
      "flvUrl": "https://pull-flv.example/live.flv"
    },
    {
      "collectionId": "coll_1002",
      "isLive": false,
      "roomId": "",
      "flvUrl": ""
    }
  ]
}
```

Rules:

- The endpoint reads Redis only. It must not call TikTok or trigger live detection.
- Response order must match request order.
- Missing, expired, or offline statuses return `isLive=false`, `roomId=""`, `flvUrl=""`.
- Redis failure returns `code=5099`, `data=null`.
- This endpoint is TikTok-only for now, matching `docs/research/tiktok-live-dashboard-apis/tiktok-live-dashboard-downstream-api.md`.

## Backward Compatibility

During rollout:

- `POST /get_roominfo` remains available.
- `POST /report_roominfo` remains available.
- The old in-memory dict can be populated from Redis for compatibility, but it must stop being the canonical bridge.
- In Redis mode, `live-stream` may still maintain `online_room_list` as a local bookkeeping cache for existing upload/cleanup code, but cross-service ownership must come from Redis lease and `recording` hash, not `/report_roominfo`.
- `report_roominfo` should be disabled or no-op for Redis-owned rooms after the feature flag is enabled, otherwise stale HTTP heartbeats can re-mark a room as allocated in `live-monitor` memory after the Redis lease has expired.
- After `live-stream` Redis mode is stable, HTTP polling can be deprecated behind a feature flag.

## Implementation Boundaries

Recommended files:

| Service | Files |
|---|---|
| `live-monitor` | `utils/redis_bridge.py`, `main.py`, `tests/test_redis_bridge.py`, `tests/test_live_status_batch.py` |
| `live-stream` | `redis_room_source.py`, `TT_client.py`, `requirements.txt`, `tests/test_redis_room_source.py` |

Do not copy `services/live-platform/shared/redis_store.py` wholesale. Keep the bridge code local to each service and preserve each service's existing style.

## Verification

Minimum tests before rollout:

1. Seed upsert writes config set/hash and updates changed `roomUrl`.
2. MySQL query failure does not prune Redis.
3. Status payload maps `code=200`, `2001`, and `5001` correctly.
4. Batch API keeps request order and returns offline for missing/expired statuses.
5. Lease claim allows one worker and rejects a second worker.
6. Lease renew/release cannot affect another worker's lease.
7. `live-stream` reconnect reads a changed `flvUrl` instead of retrying a stale one.

Manual Redis smoke test:

```powershell
redis-cli SADD live:monitor:collections coll_test_001
redis-cli HSET live:collection:coll_test_001:config collectionId coll_test_001 collection_id coll_test_001 platform tiktok roomUrl "https://www.tiktok.com/@demo/live" room_url "https://www.tiktok.com/@demo/live" enabled 1
redis-cli HSET live:collection:coll_test_001:status collectionId coll_test_001 isLive 1 roomId "7544720840995162887" flvUrl "https://pull-flv.example/live.flv" updatedAt 1781149500 expiresAt 1781150400 platform tiktok
```

Expected batch API data item:

```json
{ "collectionId": "coll_test_001", "isLive": true, "roomId": "7544720840995162887", "flvUrl": "https://pull-flv.example/live.flv" }
```
