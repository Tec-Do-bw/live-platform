import json
import math
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import redis
from fastapi import APIRouter, Body, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config

router = APIRouter(prefix="/adsmeta/api/activation", tags=["activation"])

CODE_PATTERN = re.compile(r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")
DEFAULT_VALID_DAYS = 7
RATE_LIMIT_WINDOW = 60  # 秒
RATE_LIMIT_MAX = 10

_redis_client: Optional[redis.Redis] = None
_access_key_cache: Optional[str] = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ms_to_date(ms: int) -> str:
    """将毫秒时间戳转换为日期字符串"""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _success(data) -> JSONResponse:
    return JSONResponse({"success": True, "data": data})


def _fail(code: str, message: str) -> JSONResponse:
    return JSONResponse({"success": False, "error": {"code": code, "message": message}}, status_code=200)


def _get_client_ip(request: Request) -> str:
    if request.client:
        return request.client.host
    return "unknown"


def _get_access_key() -> Optional[str]:
    """
    获取服务端配置的 access_key_activation，用于简单鉴权。
    """
    global _access_key_cache
    if _access_key_cache is not None:
        return _access_key_cache

    # 激活码密钥已迁移到 Apollo（config 门面）
    key = config.access_key_activation()
    _access_key_cache = key
    return key


def _check_access_key(client_key: Optional[str]) -> Optional[JSONResponse]:
    server_key = _get_access_key()
    if not server_key:
        # 未配置服务端密钥，直接拒绝，避免误开放
        return _fail("ACCESS_KEY_MISSING", "服务端未配置 access_key_activation")
    if not client_key:
        return _fail("ACCESS_KEY_REQUIRED", "缺少 access_key_activation")
    if client_key != server_key:
        return _fail("ACCESS_KEY_INVALID", "access_key_activation 无效")
    return None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    # Redis 连接参数已迁移到 Apollo（config 门面）
    _redis_client = redis.Redis(**config.redis_config(), decode_responses=True)
    return _redis_client


def _check_rate_limit(r: redis.Redis, client_ip: str) -> bool:
    key = f"activation:ratelimit:{client_ip}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, RATE_LIMIT_WINDOW)
    return count <= RATE_LIMIT_MAX


def _load_activation(r: redis.Redis, code: str) -> Optional[Dict]:
    raw = r.get(f"activation:code:{code}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _save_activation(r: redis.Redis, code: str, data: Dict, ttl_seconds: Optional[int] = None, keepttl: bool = False):
    key = f"activation:code:{code}"
    serialized = json.dumps(data, ensure_ascii=False)
    if keepttl:
        r.set(key, serialized, keepttl=True)
    else:
        r.set(key, serialized, ex=ttl_seconds)


def _generate_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parts: List[str] = []
    for _ in range(4):
        parts.append("".join(random.choice(alphabet) for _ in range(4)))
    return "-".join(parts)


def _validate_code(code: str) -> bool:
    return bool(code) and CODE_PATTERN.match(code) is not None


class ActivationVerifyRequest(BaseModel):
    """验证激活码请求体"""

    code: str


class ActivationGenerateRequest(BaseModel):
    """生成激活码请求体"""

    days: int = 7
    count: int = 1  # 生成数量，默认 1，最大 100


class ActivationRevokeRequest(BaseModel):
    """撤销激活码请求体"""

    code: str


@router.post(
    "/verify",
    description="验证激活码有效性（一次性激活），校验格式、过期、撤销、是否已用，并在首次使用时标记为 used。",
)
async def verify_activation(
    request: Request,
    payload: ActivationVerifyRequest = Body(..., description="验证激活码参数"),
    access_key_activation: Optional[str] = Header(default=None, description="激活接口鉴权密钥"),
):
    auth_error = _check_access_key(access_key_activation)
    if auth_error:
        return auth_error

    code = str(payload.code).strip().upper()
    if not _validate_code(code):
        return _fail("INVALID_CODE", "激活码格式不正确")

    r = _get_redis_client()
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(r, client_ip):
        return _fail("RATE_LIMITED", "请求过于频繁，请稍后再试")

    record = _load_activation(r, code)
    if not record:
        return _fail("INVALID_CODE", "激活码无效")

    now_ms = _now_ms()
    if record.get("status") == "revoked":
        return _fail("REVOKED", "激活码已被撤销")
    if record.get("expiresAt") and record["expiresAt"] < now_ms:
        return _fail("EXPIRED", "激活码已过期")
    if record.get("status") == "used":
        return _fail("ALREADY_USED", "激活码已被使用")

    if not record.get("usedAt"):
        record["usedAt"] = now_ms
        record["usedBy"] = client_ip
        record["status"] = "used"
        _save_activation(r, code, record, keepttl=True)

    expires_at = record.get("expiresAt")
    return _success({
        "valid": True,
        "expiresAt": expires_at,
        "expiresDate": _ms_to_date(expires_at),
    })


@router.get(
    "/status",
    description="查询激活码状态，返回有效性、过期时间和剩余天数。",
)
async def activation_status(
    request: Request,
    code: str = Query(..., description="激活码"),
    access_key_activation: Optional[str] = Header(default=None, description="激活接口鉴权密钥"),
):
    auth_error = _check_access_key(access_key_activation)
    if auth_error:
        return auth_error

    code = str(code).strip().upper()
    if not _validate_code(code):
        return _fail("INVALID_CODE", "激活码格式不正确")

    r = _get_redis_client()
    record = _load_activation(r, code)
    if not record:
        return _fail("NOT_FOUND", "激活码不存在")

    now_ms = _now_ms()
    if record.get("status") == "revoked":
        return _fail("REVOKED", "激活码已被撤销")
    if record.get("expiresAt") and record["expiresAt"] < now_ms:
        return _fail("EXPIRED", "激活码已过期")
    if record.get("status") == "used":
        return _fail("ALREADY_USED", "激活码已被使用")

    expires_at = record.get("expiresAt")
    remaining_days = max(0, math.ceil((expires_at or now_ms - now_ms) / 86400000))
    return _success({
        "valid": True,
        "expiresAt": expires_at,
        "expiresDate": _ms_to_date(expires_at),
        "remainingDays": remaining_days,
    })


@router.get(
    "/available",
    description="获取当前可用的激活码列表（未使用、未过期、状态为 active）。",
)
async def available_codes(access_key_activation: Optional[str] = Header(default=None, description="激活接口鉴权密钥")):
    auth_error = _check_access_key(access_key_activation)
    if auth_error:
        return auth_error

    r = _get_redis_client()
    now_ms = _now_ms()
    items: List[Dict] = []
    for key in r.scan_iter(match="activation:code:*", count=200):
        record = _load_activation(r, key.replace("activation:code:", ""))
        if not record:
            continue
        if record.get("status") == "active" and record.get("expiresAt", 0) > now_ms and not record.get("usedAt"):
            expires_at = record.get("expiresAt")
            items.append({
                "code": record.get("code"),
                "expiresAt": expires_at,
                "expiresDate": _ms_to_date(expires_at),
            })
    return _success(items)


@router.post(
    "/generate",
    description="生成新的激活码，支持自定义有效天数（默认 7 天）和批量生成（默认 1 个，最大 100 个）。",
)
async def generate_code(
    payload: ActivationGenerateRequest = Body(..., description="可选参数：days 有效天数，count 生成数量"),
    access_key_activation: Optional[str] = Header(default=None, description="激活接口鉴权密钥"),
):
    auth_error = _check_access_key(access_key_activation)
    if auth_error:
        return auth_error

    # 处理有效天数
    raw_days = payload.days
    try:
        days = int(raw_days)
        if days <= 0:
            days = DEFAULT_VALID_DAYS
    except Exception:
        days = DEFAULT_VALID_DAYS

    # 处理生成数量
    raw_count = payload.count
    try:
        count = int(raw_count)
        if count <= 0:
            count = 1
        elif count > 100:
            return _fail("INVALID_COUNT", "生成数量不能超过 100")
    except Exception:
        count = 1

    ttl_seconds = days * 24 * 3600
    expires_at = _now_ms() + ttl_seconds * 1000

    r = _get_redis_client()
    generated_codes: List[Dict] = []

    # 批量生成激活码
    for i in range(count):
        code = None
        for _ in range(5):
            candidate = _generate_code()
            if not r.exists(f"activation:code:{candidate}"):
                code = candidate
                break
        if not code:
            # 如果已经生成了部分，返回已生成的
            if generated_codes:
                return _success({"codes": generated_codes, "total": len(generated_codes), "requested": count})
            return _fail("GENERATION_FAILED", "生成激活码失败，请重试")

        record = {
            "code": code,
            "createdAt": _now_ms(),
            "expiresAt": expires_at,
            "status": "active",
            "usedBy": None,
            "usedAt": None,
        }
        _save_activation(r, code, record, ttl_seconds=ttl_seconds)
        generated_codes.append({
            "code": code,
            "expiresAt": expires_at,
            "expiresDate": _ms_to_date(expires_at),
        })

    # 兼容旧接口：如果只生成 1 个，返回单个对象；否则返回列表
    if count == 1:
        return _success(generated_codes[0])
    else:
        return _success({"codes": generated_codes, "total": len(generated_codes)})


@router.post(
    "/revoke",
    description="撤销指定激活码，状态置为 revoked，并保留 7 天 TTL 以便审计。",
)
async def revoke_code(
    payload: ActivationRevokeRequest = Body(..., description="撤销激活码参数"),
    access_key_activation: Optional[str] = Header(default=None, description="激活接口鉴权密钥"),
):
    auth_error = _check_access_key(access_key_activation)
    if auth_error:
        return auth_error

    code = str(payload.code).strip().upper()
    if not _validate_code(code):
        return _fail("INVALID_CODE", "激活码格式不正确")

    r = _get_redis_client()
    record = _load_activation(r, code)
    if not record:
        return _fail("NOT_FOUND", "激活码不存在")

    record["status"] = "revoked"
    revoked_at = _now_ms()
    record["revokedAt"] = revoked_at
    _save_activation(r, code, record, ttl_seconds=DEFAULT_VALID_DAYS * 24 * 3600)
    return _success({
        "code": code,
        "status": "revoked",
        "revokedAt": revoked_at,
        "revokedDate": _ms_to_date(revoked_at),
    })

