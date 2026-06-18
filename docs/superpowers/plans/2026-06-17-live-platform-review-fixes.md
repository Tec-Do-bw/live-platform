# live-platform Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four code review blockers in `services/live-platform`: failing segment callback test, reconnect MediaMTX path lifecycle, Apollo startup loading, and loguru placeholder logs.

**Architecture:** Keep the existing Phase 1 design: `StateManager` owns room runtime state, MediaMTX path lifecycle is tied to recording/reconnect transitions, `UploadCoordinator` preserves OSS then Kafka ordering, and Apollo config remains lazily loaded but explicitly warmed before startup components read it.

**Tech Stack:** Python 3.13 locally, FastAPI, APScheduler, pytest, Redis repository abstraction, MediaMTX client, FFmpeg relay, loguru-style f-string logging.

---

## Scope

Fix only these review issues:

1. `test_segment_ready_uses_actual_room_id_for_upload` fails because the fake state does not include `platform`.
2. Timeout/reconnect can repeat `MediaMTXClient.add_path()` for an existing path without removing it.
3. `python main.py` can still synchronously load Apollo while constructing `uvicorn.Config`.
4. `upload/*` still has `%s` logging placeholders that violate repo loguru rules.

Do not fix in this plan:

- Broken checklist/curl text in `docs/plans/2026-05-07-live-platform-phase1.md`.
- Dockerfile `nodejs npm` question.
- Existing untracked `diff_*.txt` files or unrelated staged renames.

---

## Files

- Modify: `services/live-platform/tests/test_internal.py`
  - Replace the brittle `FakeState` with a realistic fake that includes `platform`, or return a real `RoomState`.
  - Add an assertion for `SegmentTask.platform`.
- Modify: `services/live-platform/tests/test_state_machine.py`
  - Add a regression test covering timeout -> reconnect success resource lifecycle.
- Modify: `services/live-platform/orchestrator/state_machine.py`
  - Ensure reconnect does not duplicate an existing MediaMTX path.
- Modify: `services/live-platform/main.py`
  - Explicitly warm `settings` before reading `settings.server` in direct CLI startup.
- Modify: `services/live-platform/upload/coordinator.py`
  - Convert `%s` logs to f-strings.
- Modify: `services/live-platform/upload/oss_worker.py`
  - Convert `%s` logs to f-strings.
- Modify: `services/live-platform/upload/kafka_worker.py`
  - Convert `%s` logs to f-strings.

---

### Task 1: Repair Segment Callback Test Contract

**Files:**
- Modify: `services/live-platform/tests/test_internal.py`

- [ ] **Step 1: Reproduce the current failure**

Run from `services/live-platform`:

```powershell
python -m pytest tests/test_internal.py -q
```

Expected before the fix:

```text
AttributeError: 'FakeState' object has no attribute 'platform'
```

- [ ] **Step 2: Replace the fake state with a complete state**

In `services/live-platform/tests/test_internal.py`, replace:

```python
class FakeState:
    live_room_id = "actual-room-1"
```

with:

```python
from shared.models import RoomState, Status
```

and in `fake_on_segment_received`, return:

```python
return RoomState(
    collection_id="c1",
    live_room_id="actual-room-1",
    platform="tiktok",
    room_url="https://example.com/live",
    status=Status.RECORDING,
    mediamtx_path="tiktok-c1",
)
```

This keeps the test aligned with the real `segment_ready()` contract instead of growing another partial fake.

- [ ] **Step 3: Assert platform propagation**

Add this assertion after the existing `mediamtx_path` assertion:

```python
assert captured[0].platform == "tiktok"
```

- [ ] **Step 4: Verify the focused test passes**

Run:

```powershell
python -m pytest tests/test_internal.py -q
```

Expected:

```text
1 passed
```

---

### Task 2: Fix Reconnect MediaMTX Path Lifecycle

**Files:**
- Modify: `services/live-platform/tests/test_state_machine.py`
- Modify: `services/live-platform/orchestrator/state_machine.py`

**Design choice:** On timeout, remove the MediaMTX path when stopping FFmpeg. Reconnect success can then call `on_live_detected()` and recreate the path cleanly. This is the smallest change that preserves current `on_live_detected()` semantics.

- [ ] **Step 1: Add a failing reconnect lifecycle test**

Append this test to `services/live-platform/tests/test_state_machine.py`:

```python
@pytest.mark.asyncio
async def test_timeout_removes_path_before_reconnect_success():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()

    async def stream_resolver(platform: str, room_url: str) -> str:
        assert platform == "tiktok"
        assert room_url == "https://example.com/live"
        return "https://example.com/live-new.flv"

    manager = StateManager(
        mediamtx_client=mediamtx,
        relay_controller=relay,
        stream_resolver=stream_resolver,
        timeout_seconds=1,
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})
    state.last_active = 0

    await manager.run_health_check()
    changed = await manager.retry_reconnecting()

    assert changed[0].status == Status.RECORDING
    assert mediamtx.added == ["tiktok-c1", "tiktok-c1"]
    assert mediamtx.removed == ["tiktok-c1"]
    assert relay.stopped == [101]
    assert relay.started == [
        ("https://example.com/live.flv", "tiktok-c1"),
        ("https://example.com/live-new.flv", "tiktok-c1"),
    ]
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```powershell
python -m pytest tests/test_state_machine.py::test_timeout_removes_path_before_reconnect_success -q
```

Expected before implementation:

```text
AssertionError: assert [] == ['tiktok-c1']
```

The important failing evidence is that `mediamtx.removed` is empty after timeout.

- [ ] **Step 3: Remove MediaMTX path during timeout cleanup**

In `services/live-platform/orchestrator/state_machine.py`, update `on_stream_timeout()` from:

```python
await self.relay_controller.stop_ffmpeg_relay(state.ffmpeg_pid)
state.ffmpeg_pid = None
return state
```

to:

```python
await self.relay_controller.stop_ffmpeg_relay(state.ffmpeg_pid)
state.ffmpeg_pid = None
if state.mediamtx_path:
    await self.mediamtx_client.remove_path(state.mediamtx_path)
return state
```

Do not clear `state.mediamtx_path`; keeping it lets callbacks and logs still identify the path while the room is reconnecting.

- [ ] **Step 4: Verify state machine tests**

Run:

```powershell
python -m pytest tests/test_state_machine.py -q
```

Expected:

```text
5 passed
```

---

### Task 3: Warm Apollo Settings Before Direct Uvicorn Startup Reads

**Files:**
- Modify: `services/live-platform/main.py`
- Test manually with import-safe checks; no network call should run during module import.

- [ ] **Step 1: Add explicit warm load in `main()`**

In `services/live-platform/main.py`, update `main()` from:

```python
async def main() -> None:
    configure_logging()
    config = uvicorn.Config(create_app(), host=settings.server.host, port=settings.server.port)
    server = uvicorn.Server(config)
    await server.serve()
```

to:

```python
async def main() -> None:
    await asyncio.to_thread(settings.load)
    configure_logging()
    config = uvicorn.Config(create_app(), host=settings.server.host, port=settings.server.port)
    server = uvicorn.Server(config)
    await server.serve()
```

This makes the CLI path match the lifespan path: the network-backed Apollo load is explicit before components read nested settings.

- [ ] **Step 2: Verify importing `main` does not call Apollo**

Run from `services/live-platform`:

```powershell
@'
from unittest.mock import patch

with patch("shared.config.fetch_apollo_config") as mocked:
    import main
    assert mocked.call_count == 0, mocked.call_count
print("import-ok")
'@ | python -
```

Expected:

```text
import-ok
```

- [ ] **Step 3: Verify `main.main()` warms settings before uvicorn reads host/port**

Run from `services/live-platform`:

```powershell
@'
import asyncio
from unittest.mock import patch

import main
from shared.config import settings
from tests.test_config import full_apollo_config

events = []

class FakeServer:
    def __init__(self, config):
        events.append(("server_init", config.host, config.port))

    async def serve(self):
        events.append(("serve", None, None))

def fake_fetch():
    events.append(("fetch", None, None))
    return full_apollo_config(livePlatformHost="127.0.0.9", livePlatformPort="9099")

settings.override(None)
with patch("shared.config.fetch_apollo_config", side_effect=fake_fetch), patch("main.uvicorn.Server", FakeServer):
    asyncio.run(main.main())

print(events)
assert events[0][0] == "fetch"
assert ("server_init", "127.0.0.9", 9099) in events
'@ | python -
```

Expected:

```text
[('fetch', None, None), ('server_init', '127.0.0.9', 9099), ('serve', None, None)]
```

---

### Task 4: Convert Upload Logs To f-strings

**Files:**
- Modify: `services/live-platform/upload/coordinator.py`
- Modify: `services/live-platform/upload/oss_worker.py`
- Modify: `services/live-platform/upload/kafka_worker.py`

- [ ] **Step 1: Update coordinator logs**

In `services/live-platform/upload/coordinator.py`, replace:

```python
logger.info("切片处理完成 | room_id=%s file=%s worker=%s", task.room_id, task.file_path, index)
```

with:

```python
logger.info(f"切片处理完成 | room_id={task.room_id} file={task.file_path} worker={index}")
```

Replace:

```python
logger.exception("切片处理失败 | room_id=%s file=%s", task.room_id, task.file_path)
```

with:

```python
logger.exception(f"切片处理失败 | room_id={task.room_id} file={task.file_path}")
```

- [ ] **Step 2: Update OSS retry log**

In `services/live-platform/upload/oss_worker.py`, replace:

```python
logger.warning("OSS 上传失败，准备重试 | file=%s attempt=%s error=%s", file_path, attempt, exc)
```

with:

```python
logger.warning(f"OSS 上传失败，准备重试 | file={file_path} attempt={attempt} error={exc}")
```

- [ ] **Step 3: Update Kafka retry log**

In `services/live-platform/upload/kafka_worker.py`, replace:

```python
logger.warning("Kafka 推送失败，准备重试 | room_id=%s attempt=%s error=%s", room_id, attempt, exc)
```

with:

```python
logger.warning(f"Kafka 推送失败，准备重试 | room_id={room_id} attempt={attempt} error={exc}")
```

- [ ] **Step 4: Verify no upload `%s` logger calls remain**

Run:

```powershell
rg -n "logger\\.(info|warning|exception)\\([\\\"'][^\\\"']*%s" services/live-platform/upload
```

Expected:

```text
```

No output.

---

## Final Verification

- [ ] **Run focused tests**

From `services/live-platform`:

```powershell
python -m pytest tests/test_config.py tests/test_redis_store.py tests/test_internal.py tests/test_scheduler.py tests/test_state_machine.py tests/test_api.py -q
```

Expected:

```text
23 passed
```

The exact number may differ if adjacent tests are added, but there must be zero failures.

- [ ] **Run upload tests**

From `services/live-platform`:

```powershell
python -m pytest tests/test_upload.py -q
```

Expected: all tests pass.

- [ ] **Run static log check for touched upload files**

From repo root:

```powershell
rg -n "logger\\.(info|warning|exception)\\([\\\"'][^\\\"']*%s" services/live-platform/upload
```

Expected: no output.

- [ ] **Review diff**

From repo root:

```powershell
git diff -- services/live-platform/tests/test_internal.py services/live-platform/tests/test_state_machine.py services/live-platform/orchestrator/state_machine.py services/live-platform/main.py services/live-platform/upload/coordinator.py services/live-platform/upload/oss_worker.py services/live-platform/upload/kafka_worker.py
```

Expected: diff only covers the four requested fixes above.

---

## Self-Review Notes

- Spec coverage: all four requested issues map to Tasks 1-4.
- Placeholder scan: no TODO/TBD/implement-later steps.
- Type consistency: `RoomState.platform`, `RoomState.live_room_id`, `RoomState.mediamtx_path`, and `Status.RECORDING` match existing model definitions.
- Minimality check: no plan step edits docs checklist, Dockerfile, Redis schema, scheduler behavior, or adapter contracts.
