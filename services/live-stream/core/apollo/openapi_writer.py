"""Apollo OpenAPI 写入/发布能力。

仅用于运维脚本把配置写入 Apollo,业务读取仍走 ApolloClient.get_value。
token 从环境变量 APOLLO_OPENAPI_TOKEN 读取,绝不硬编码或提交。
"""
from __future__ import annotations

import json
import os

import requests


def _token() -> str:
    token = os.environ.get("APOLLO_OPENAPI_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少环境变量 APOLLO_OPENAPI_TOKEN,无法写入 Apollo")
    return token


def update_apollo_item(
    portal_url: str,
    env: str,
    app_id: str,
    cluster: str,
    namespace: str,
    key: str,
    value: str,
    operator: str,
    comment: str = "脚本更新配置",
) -> None:
    """新增或更新单个配置项（PUT items/{key},Apollo 会自动 create-or-update）。"""
    headers = {"Content-Type": "application/json", "Authorization": _token()}
    body = {
        "key": key,
        "value": value,
        "comment": comment,
        "dataChangeLastModifiedBy": operator,
        "dataChangeCreatedBy": operator,
    }
    url = (
        f"{portal_url}/openapi/v1/envs/{env}/apps/{app_id}"
        f"/clusters/{cluster}/namespaces/{namespace}/items/{key}"
        f"?createIfNotExists=true"
    )
    resp = requests.put(url, headers=headers, data=json.dumps(body), timeout=10)
    resp.raise_for_status()


def publish_namespace(
    portal_url: str,
    env: str,
    app_id: str,
    cluster: str,
    namespace: str,
    operator: str,
    release_title: str = "脚本发布配置",
    release_comment: str = "脚本发布配置",
) -> None:
    """发布 namespace,使写入的配置生效。"""
    headers = {"Content-Type": "application/json", "Authorization": _token()}
    body = {
        "releaseTitle": release_title,
        "releaseComment": release_comment,
        "releasedBy": operator,
    }
    url = (
        f"{portal_url}/openapi/v1/envs/{env}/apps/{app_id}"
        f"/clusters/{cluster}/namespaces/{namespace}/releases"
    )
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
    resp.raise_for_status()
