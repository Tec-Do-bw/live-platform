"""
Apollo 配置客户端（标准模板）

环境变量：
- APOLLOID: Apollo App ID，默认 'live-spider'
- APOLLO_URL: Apollo 配置中心地址，默认 'http://dev-apollo.tec-develop.com'
- DEPLOY_ENV: 部署环境/集群，默认 'default'
"""
import os
from core.apollo.apollo_client import ApolloClient


# 从环境变量读取 Apollo 连接参数
apollo_id = os.environ.get('APOLLOID', 'live-spider')
config_url = os.environ.get('APOLLO_URL', 'http://dev-apollo.tec-develop.com')
cluster = os.environ.get('DEPLOY_ENV', 'default')

# 全局 Apollo 客户端实例
APOLLO = ApolloClient(
    app_id=apollo_id,
    cluster=cluster,
    config_url=config_url
)


def fetch_apollo_config() -> dict:
    """
    拉取 Apollo 配置（兼容旧版调用方式）

    Returns:
        dict: 配置字典，失败返回空 dict
    """
    try:
        # Apollo 客户端已在初始化时拉取并缓存配置
        # 这里直接返回内存缓存或触发首次网络请求
        namespace = 'application'
        configurations = APOLLO._cache.get(namespace, {}).get('configurations', {})

        # 如果内存为空，尝试从网络拉取
        if not configurations:
            result = APOLLO.get_json_from_net(namespace)
            if result:
                configurations = result.get('configurations', {})

        return configurations
    except Exception as e:
        import logging
        logging.error(f"Apollo 配置拉取失败: {e}")
        return {}
