
import os

from core.apollo.apollo_client import ApolloClient


apollo_id = os.environ.get('APOLLOID', 'ads-snapchat-spider')
config_url = os.environ.get('APOLLO_URL', 'http://dev-apollo.tec-develop.com')
cluster = os.environ.get('DEPLOY_ENV', 'default')


APOLLO = ApolloClient(
    app_id=apollo_id, 
    cluster=cluster, 
    config_url=config_url
)
