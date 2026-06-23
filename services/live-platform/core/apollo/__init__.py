
import os

from core.apollo.apollo_client import ApolloClient


apollo_id = os.environ.get('APOLLOID', 'live-spider')
config_url = os.environ.get('APOLLO_URL', 'http://dev-apollo.tec-develop.com')
cluster = os.environ.get('DEPLOY_ENV', 'dev01')


APOLLO = ApolloClient(
    app_id=apollo_id, 
    cluster=cluster, 
    config_url=config_url
)
#
# print(apollo_id, config_url, cluster)
# print('KAFKA_HOSTS：',APOLLO.get_value(key='kafka', default_val=''))