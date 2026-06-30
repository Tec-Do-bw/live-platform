import os

from core.apollo.apollo_client import ApolloClient


# Apollo 引导参数（唯一允许走环境变量的配置，鸡生蛋问题）
apollo_id = os.environ.get("APOLLOID", "live-spider")
config_url = os.environ.get("APOLLO_URL", "http://dev-apollo.tec-develop.com")
cluster = os.environ.get("DEPLOY_ENV", "dev02")


APOLLO = ApolloClient(
    app_id=apollo_id,
    cluster=cluster,
    config_url=config_url,
)
