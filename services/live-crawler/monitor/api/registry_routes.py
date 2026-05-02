"""注册表 API 路由 — 提供前端所需的 API 类型注册信息"""

from fastapi import APIRouter
from monitor.registry import get_registry_for_api

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/registry")
def get_registry():
    """返回三层 API 类型注册表，供前端动态渲染列头"""
    return get_registry_for_api()
