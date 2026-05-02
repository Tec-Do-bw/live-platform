"""
动态代理获取服务
调用 kkoip API 获取 24 小时动态代理
"""
import asyncio
from typing import Optional

import httpx

from app.config import settings
from loguru import logger


class DynamicProxyService:
    """动态代理服务"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        sign: Optional[str] = None,
        access_id: Optional[str] = None
    ):
        self.api_url = api_url or settings.DYNAMIC_PROXY_API_URL
        self.sign = sign or settings.DYNAMIC_PROXY_SIGN
        self.access_id = access_id or settings.DYNAMIC_PROXY_ACCESS_ID

    async def get_proxy(self, country_code: str) -> Optional[str]:
        """
        调用 kkoip API 获取 24 小时动态代理

        Args:
            country_code: 国家代码（如 US, JP, TH）

        Returns:
            代理字符串，格式: socks5://host:port:user:password
            获取失败返回 None
        """
        params = {
            "auth": "pwd",
            "format": "4",  # 假设返回格式为 IP:Port:User:Pass (具体取决于format定义)
            "n": "1",
            "p": "socks5",  # 使用 socks5 协议
            "gate": "gate-hk.kkoip.com:14376",
            "g": country_code.upper(),  # 国家
            "r": "1440",  # 24小时
            "type": "txt",
            "sign": self.sign,  # 注意：切换国家可能需要重新计算签名
            "accessid": self.access_id,
            "dl": "\\r\\n"
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.api_url, params=params)
                response.raise_for_status()
                response_text = response.text.strip()

                logger.info("动态代理 API 响应: {}", response_text)

                # 解析响应
                proxy = self.parse_response(response_text)
                if not proxy:
                    logger.warning("动态代理解析失败，响应: {}", response_text)
                    return None

                # 验证代理是否可用
                is_valid = await self.verify_proxy(proxy)
                if not is_valid:
                    logger.warning("动态代理验证失败，代理不可用: {}", proxy)
                    return None

                logger.info("成功获取并验证动态代理: {} (国家: {})", proxy, country_code)
                return proxy

        except httpx.HTTPError as exc:
            logger.error("动态代理 API 请求失败: {}", exc)
            return None
        except Exception as exc:
            logger.error("获取动态代理异常: {}", exc)
            return None

    def parse_response(self, response_text: str) -> Optional[str]:
        """
        解析 kkoip API 响应，兼容新旧两种格式

        旧格式（5字段）: gate-hk.kkoip.com:14376:11000:1687631-a22643b3:a70dedb0-US-801247402-24h
        新格式（4字段）: gate-hk.kkoip.com:14376:1687631-a22643b3:a70dedb0-FR-208278899-24h

        解析后:
        - host: gate-hk.kkoip.com
        - port: 14376
        - user: 1687631-a22643b3
        - password: a70dedb0-XX-XXXXXXXXX-24h

        转换为项目标准格式: socks5://host:port:user:password

        Args:
            response_text: API 响应文本

        Returns:
            代理字符串或 None
        """
        if not response_text:
            return None

        # 检查是否包含错误信息
        if "error" in response_text.lower() or "fail" in response_text.lower():
            logger.warning("动态代理响应包含错误: {}", response_text)
            return None

        try:
            parts = response_text.split(":")
            if len(parts) == 4:
                # 新格式: host:port:user:password
                host, port, user, password = parts
            elif len(parts) == 5:
                # 旧格式: host:port:line_id:user:password
                host = parts[0]
                port = parts[1]
                # parts[2] 是线路ID，跳过
                user = parts[3]
                password = parts[4]
            else:
                logger.warning("动态代理响应格式不正确，字段数: {}", len(parts))
                return None

            # 构建项目标准格式: socks5://host:port:user:password
            proxy = f"socks5://{host}:{port}:{user}:{password}"
            return proxy

        except Exception as exc:
            logger.error("解析动态代理响应失败: {}", exc)
            return None

    async def verify_proxy(self, proxy: str) -> bool:
        """
        验证代理是否可用

        通过 curl 命令走 socks5 代理请求 IP 检测服务，绕开 socksio 的兼容性 bug

        Args:
            proxy: 代理字符串，格式: socks5://host:port:user:password

        Returns:
            代理是否可用
        """
        try:
            if not proxy.startswith("socks5://"):
                logger.warning("代理格式不正确: {}", proxy)
                return False

            proxy_content = proxy[len("socks5://"):]
            parts = proxy_content.split(":")
            if len(parts) < 4:
                logger.warning("代理格式解析失败: {}", proxy)
                return False

            host = parts[0]
            port = parts[1]
            user = parts[2]
            password = parts[3]

            # curl 的 socks5 代理格式: socks5://user:password@host:port
            proxy_url = f"socks5://{user}:{password}@{host}:{port}"

            process = await asyncio.create_subprocess_exec(
                "curl", "-s", "--max-time", "10",
                "--proxy", proxy_url,
                "https://api.ipify.org",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)

            if process.returncode == 0 and stdout:
                exit_ip = stdout.decode().strip()
                logger.info("代理验证成功，出口IP: {}", exit_ip)
                return True
            else:
                error_msg = stderr.decode().strip() if stderr else "未知错误"
                logger.warning("代理验证失败，curl 返回码: {}，错误: {}", process.returncode, error_msg)
                return False

        except asyncio.TimeoutError:
            logger.warning("代理验证超时")
            return False
        except Exception as exc:
            logger.warning("代理验证失败: {}", exc)
            return False


# 全局单例
dynamic_proxy_service = DynamicProxyService()
