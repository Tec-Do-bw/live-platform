from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.config import get_group_name, settings
from loguru import logger


class AdsPowerError(Exception):
    """AdsPower 异常基类。"""


class AdsPowerConnectionError(AdsPowerError):
    """AdsPower 连接异常。"""


class AdsPowerApiError(AdsPowerError):
    """AdsPower API 返回错误。"""

    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.data = data or {}


class AdsPowerService:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.ADSPOWER_API_URL).rstrip("/")
        self.api_key = api_key
        self.timeout = 20

    async def create_browser(self, group_id: str, proxy: str, remark: str, live_account: str, country: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name":live_account,
            "group_id": str(group_id),
            "remark": remark,
            "fingerprint_config": {
                "random_ua": {
                    "ua_system_version": [
                        "Windows",
                        "Windows",
                        "Windows",
                        "Windows",
                        # "Mac OS X"
                    ],
                    "ua_browser": [
                        "chrome"
                    ]
                },
                # 设置屏幕分辨率，格式: "宽度_高度"
                "screen_resolution": f"{settings.BROWSER_WIDTH}_{settings.BROWSER_HEIGHT}",
            }
        }
        # 墨西哥使用 ipapi 作为 IP 查询渠道，识别率更高
        if country.lower() == "mx":
            payload["ipchecker"] = "ipapi"
        if proxy:
            payload["user_proxy_config"] = parse_proxy(proxy)
        response = await self._request("POST", "/api/v2/browser-profile/create", json_data=payload)
        return response.get("data", {})

    async def start_browser(self, profile_id: str) -> Dict[str, Any]:
        # 使用固定窗口大小替代最大化，确保不同服务器上显示一致
        payload = {
            "profile_id": profile_id,
            # "password_saving": "1",  # 核心参数1：允许保存密码弹窗 (1: 开启, 0: 关闭)
            # "password_filling": "1",  # 核心参数2：允许密码自动填充功能 (1: 开启, 0: 关闭)
            "launch_args": [
                f"--window-size={settings.BROWSER_WIDTH},{settings.BROWSER_HEIGHT}",
                "--window-position=0,0",
            ]
        }
        response = await self._request("POST", "/api/v2/browser-profile/start", json_data=payload)
        return response.get("data", {})

    async def close_browser(self, profile_id: str) -> bool:
        payload = {"profile_id": profile_id}
        await self._request("POST", "/api/v2/browser-profile/stop", json_data=payload)
        return True

    async def delete_browser(self, profile_id: str) -> bool:
        payload = {"profile_id": [profile_id]}
        await self._request("POST", "/api/v2/browser-profile/delete", json_data=payload)
        return True

    async def update_browser_name(self, profile_id: str, name: str, remark: str = None) -> bool:
        """
        更新环境名称和备注
        用于已有环境复用时同步最新账号名和 validate_id

        Args:
            profile_id: 环境 ID
            name: 环境名称
            remark: 备注信息（可选），Shopee 多店铺场景下包含 validate_id
        """
        if not profile_id or not name:
            return False
        payload = {
            "user_id": profile_id,
            "name": name
        }
        if remark is not None:
            payload["remark"] = remark
        try:
            await self._request("POST", "/api/v1/user/update", json_data=payload)
            logger.info("环境信息已更新: profile_id={}, name={}, remark={}", profile_id, name, remark)
            return True
        except (AdsPowerConnectionError, AdsPowerApiError) as exc:
            logger.warning("更新环境信息失败: {}", exc)
            return False
        except Exception as exc:
            logger.warning("更新环境信息异常: {}", exc)
            return False

    async def stop_browser(self, profile_id: str) -> bool:
        """
        仅关闭浏览器（不删除环境）
        用于需要保留环境以便复用的场景
        """
        if not profile_id:
            return False
        try:
            await self.close_browser(profile_id)
            return True
        except (AdsPowerConnectionError, AdsPowerApiError) as exc:
            logger.warning("AdsPower 关闭浏览器失败: {}", exc)
            return False
        except Exception as exc:
            logger.warning("关闭浏览器异常: {}", exc)
            return False

    async def cleanup_browser(self, profile_id: str) -> bool:
        """
        清理浏览器配置（关闭并删除）
        仅用于异常回滚场景（如创建失败需要清理）
        """
        if not profile_id:
            return False
        try:
            await self.close_browser(profile_id)
            await self.delete_browser(profile_id)
            return True
        except (AdsPowerConnectionError, AdsPowerApiError) as exc:
            logger.warning("AdsPower 清理失败: {}", exc)
            return False
        except Exception as exc:
            logger.warning("清理浏览器异常: {}", exc)
            return False

    async def move_to_group(self, profile_ids: list, group_id: str) -> bool:
        """
        移动环境到指定分组
        API: POST /api/v1/user/regroup
        """
        payload = {
            "user_ids": profile_ids,  # 环境ID列表
            "group_id": str(group_id),
        }
        await self._request("POST", "/api/v1/user/regroup", json_data=payload)
        return True

    async def query_group_by_name(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        按名称查询分组
        API: GET /api/v1/group/list?group_name=xxx

        Args:
            group_name: 分组名称

        Returns:
            分组信息字典，不存在返回 None
        """
        response = await self._request("GET", f"/api/v1/group/list?group_name={group_name}")
        group_list = response.get("data", {}).get("list", [])
        # 精确匹配名称
        for group in group_list:
            if group.get("group_name") == group_name:
                return group
        return None

    async def create_group(self, group_name: str) -> str:
        """
        创建分组
        API: POST /api/v1/group/create

        Args:
            group_name: 分组名称

        Returns:
            新创建的 group_id
        """
        payload = {"group_name": group_name}
        response = await self._request("POST", "/api/v1/group/create", json_data=payload)
        return str(response.get("data", {}).get("group_id", ""))

    async def get_or_create_group(self, country: str, media: str) -> str:
        """
        获取或创建分组

        分组命名规范: {中文名称}团队-{媒体}
        例如: 印尼团队-tiktok, 美国团队-shopee

        Args:
            country: 国家代码
            media: 媒体类型

        Returns:
            group_id
        """
        group_name = get_group_name(country, media)

        # 先查询是否已存在
        group = await self.query_group_by_name(group_name)
        if group:
            logger.info("分组已存在: {}, group_id: {}", group_name, group.get("group_id"))
            return str(group.get("group_id"))

        # 不存在则创建
        group_id = await self.create_group(group_name)
        logger.info("创建新分组: {}, group_id: {}", group_name, group_id)
        return group_id

    async def list_browsers(
        self,
        group_id: str = "0",
        page: int = 1,
        limit: int = 100,
        sort_type: str = "last_open_time",
        sort_order: str = "asc"
    ) -> Dict[str, Any]:
        """
        查询环境列表V2
        :param group_id: 分组ID，"0"表示未分组
        :param page: 页码
        :param limit: 每页数量（1-100）
        :param sort_type: 排序类型 (profile_no/last_open_time/created_time)
        :param sort_order: 排序顺序 (asc/desc)
        :return: 包含 list, page, limit 的字典
        """
        payload = {
            "group_id": group_id,
            "page": str(page),
            "limit": str(limit),
            "sort_type": sort_type,
            "sort_order": sort_order,
        }
        response = await self._request("POST", "/api/v2/browser-profile/list", json_data=payload)
        return response.get("data", {})

    async def delete_browsers_batch(self, profile_ids: List[str]) -> bool:
        """
        批量删除环境V2（单次最多100个）
        :param profile_ids: 环境ID列表
        :return: 是否成功
        """
        if not profile_ids:
            return True
        payload = {"profile_id": profile_ids}
        await self._request("POST", "/api/v2/browser-profile/delete", json_data=payload)
        return True

    async def cleanup_old_profiles(
        self,
        threshold: int,
        cleanup_count: int,
        group_id: str = "0"
    ) -> int:
        """
        检查未分组环境数量，超过阈值时删除最旧的环境
        :param threshold: 触发清理的阈值
        :param cleanup_count: 需要删除的数量
        :param group_id: 目标分组ID
        :return: 实际删除的环境数量
        """
        try:
            # 1. 查询未分组环境，按最后打开时间升序（最旧的在前）
            data = await self.list_browsers(
                group_id=group_id,
                page=1,
                limit=100,
                sort_type="last_open_time",
                sort_order="asc"
            )

            profiles = data.get("list", [])
            total_count = len(profiles)

            # 2. 判断是否需要清理
            if total_count < threshold:
                logger.info("未分组环境数量 {} 未达到阈值 {}，无需清理", total_count, threshold)
                return 0

            # 3. 选择需要删除的环境（最旧的 cleanup_count 个）
            profiles_to_delete = profiles[:cleanup_count]
            profile_ids = [p["profile_id"] for p in profiles_to_delete]

            logger.info("未分组环境数量 {} 达到阈值 {}，准备删除 {} 个旧环境", total_count, threshold, len(profile_ids))

            # 4. 批量删除（忽略错误，如正在使用的环境无法删除）
            try:
                await self.delete_browsers_batch(profile_ids)
                logger.info("成功删除 {} 个旧环境: {}", len(profile_ids), profile_ids)
            except AdsPowerApiError as exc:
                # 忽略删除错误（如环境正在使用中），继续正常流程
                logger.warning("批量删除环境时出现错误（已忽略）: {}", exc)

            return len(profile_ids)
        except Exception as exc:
            # 清理过程出现任何异常都不应影响主流程
            logger.warning("清理旧环境时出现异常（已忽略）: {}", exc)
            return 0

    async def _request(self, method: str, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, json=json_data, headers=headers)
        except httpx.RequestError as exc:
            logger.error("AdsPower 连接失败: {}", exc)
            raise AdsPowerConnectionError(str(exc)) from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("AdsPower 响应解析失败: {}", response.text)
            raise AdsPowerApiError("AdsPower 响应不是有效 JSON") from exc

        if response.status_code != 200:
            logger.error("AdsPower HTTP 错误: {} {}", response.status_code, data)
            raise AdsPowerApiError(f"AdsPower HTTP 错误: {response.status_code}", data=data)

        if isinstance(data, dict) and data.get("code") != 0:
            logger.error("AdsPower API 错误: {}", data)
            raise AdsPowerApiError(data.get("msg", "AdsPower API 错误"), data=data)

        return data


def parse_proxy(proxy_string: str) -> Dict[str, str]:
    """解析代理字符串 socks5://host:port:user:pass"""
    if not proxy_string:
        raise ValueError("代理字符串为空")

    # 分离协议和地址
    if "//" in proxy_string:
        scheme, rest = proxy_string.split("//", 1)
        scheme = scheme.rstrip(":")
    else:
        scheme, rest = "socks5", proxy_string

    # 解析 host:port:user:password
    parts = rest.split(":")
    if len(parts) < 2:
        raise ValueError("代理格式不正确")

    proxy_config = {
        "proxy_soft": "other",
        "proxy_type": scheme,
        "proxy_host": parts[0],
        "proxy_port": parts[1],
    }
    # 添加可选的认证信息
    if len(parts) > 2 and parts[2]:
        proxy_config["proxy_user"] = parts[2]
    if len(parts) > 3 and parts[3]:
        proxy_config["proxy_password"] = parts[3]

    return proxy_config
