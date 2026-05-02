import aiohttp
import asyncio


class AsyncRequestSession:
    """异步HTTP请求会话管理器，使用aiohttp替代httpx"""
    
    @staticmethod
    def get_session(
        retries: int = 3, 
        backoff_factor: float = 0.3, 
        status_forcelist: tuple = (500, 502, 504),
        timeout: float = 30.0
    ) -> aiohttp.ClientSession:
        """
        创建异步HTTP客户端
        
        Args:
            retries: 重试次数
            backoff_factor: 重试间隔因子
            status_forcelist: 需要重试的HTTP状态码
            timeout: 请求超时时间
            
        Returns:
            aiohttp.ClientSession: 异步HTTP客户端
        """
        # 创建超时配置
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        
        # 创建连接器，配置连接池
        connector = aiohttp.TCPConnector(
            limit=100,  # 最大连接数
            limit_per_host=20,  # 每个主机最大连接数
            keepalive_timeout=30,  # 保持连接时间
            enable_cleanup_closed=True
        )
        
        # 创建异步客户端会话
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout_config,
            # 默认的请求头可以在这里设置，也可以在具体请求时设置
        )
        
        return session
    
    @staticmethod
    async def close_session(session: aiohttp.ClientSession):
        """关闭异步会话"""
        await session.close()


class AsyncRetryWrapper:
    """异步重试装饰器，用于替代原有的Wrapper.retry"""
    
    @staticmethod
    def retry(retries: int = 3, delay: float = 0.1, backoff_factor: float = 1.5):
        """
        异步重试装饰器
        
        Args:
            retries: 重试次数
            delay: 初始延迟时间
            backoff_factor: 延迟递增因子
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay
                
                for attempt in range(retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        if attempt < retries:
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff_factor
                        else:
                            raise last_exception
                            
            return wrapper
        return decorator 


if __name__ == "__main__":
    async def test():
        session = AsyncRequestSession.get_session()
        session._default_headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get("https://www.baidu.com") as response:
            print(await response.text())
        await AsyncRequestSession.close_session(session)
    asyncio.run(test())