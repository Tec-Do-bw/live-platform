import json
import os

import requests

from working.apollo.apollo_client import get_apollo_config
from working.apollo.apollo_config import ApolloConfig
from working.util.log_util import info as info_log


# 获取到 apollo 配置信息
apollo_config_dev = ApolloConfig(
    config_server_url='http://dev-apollo.tec-do.com',
    env='dev',
    appid='bee-worker',
    cluster='default',
    namespace='application',
)
apollo_config_test = ApolloConfig(
    config_server_url='http://dev-apollo.tec-do.com',
    env='dev',
    appid='bee-worker',
    cluster='test',
    namespace='application',
)
apollo_config_prod = ApolloConfig(
    config_server_url='http://dev-apollo.tec-do.com',
    env='dev',
    appid='bee-worker',
    cluster='prod',
    namespace='application',
)
api_token = ''

user = 'bw.xie'


# 更新配置
def update_apollo_config(apollo_config: ApolloConfig, key: str, value: str, comment: str = '爬虫脚本更新配置文件'):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': api_token,
    }
    body = {
        'key': key,
        'value': value,
        'comment': comment,
        'dataChangeLastModifiedBy': user,
    }
    url = (
        apollo_config.apollo_server
        + '/openapi/v1/envs/'
        + apollo_config.apollo_env
        + '/apps/'
        + apollo_config.apollo_appid
        + '/clusters/'
        + apollo_config.cluster
        + '/namespaces/'
        + apollo_config.namespace
        + '/items/'
        + key
    )
    res = requests.put(url=url, headers=headers, data=json.dumps(body))
    if res.status_code == 200:
        info_log('配置项[' + key + ']更新成功！')
    else:
        info_log('配置项[' + key + ']更新失败！')


def publish_apollo_config(
    apollo_config: ApolloConfig,
    release_title: str = '更新配置',
    release_comment: str = '更新配置',
):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': api_token,
    }
    body = {
        'releaseTitle': release_title,
        'releaseComment': release_comment,
        'releasedBy': user,
    }
    url = (
        apollo_config.apollo_server
        + '/openapi/v1/envs/'
        + apollo_config.apollo_env
        + '/apps/'
        + apollo_config.apollo_appid
        + '/clusters/'
        + apollo_config.cluster
        + '/namespaces/'
        + apollo_config.namespace
        + '/releases'
    )
    res = requests.post(url=url, headers=headers, data=json.dumps(body))
    if res.status_code == 200:
        info_log('更新应用配置成功！')
    else:
        info_log('发布应用配置失败！')


# 更新发布 apollo 配置
def update_and_publish_apollo_config(env: str, key: str, value: str, comment: str = 'api更新配置文件'):
    config: ApolloConfig
    if 'prod' == env:
        config = apollo_config_prod
    else:
        config = apollo_config_dev
    # 更新配置
    update_apollo_config(apollo_config=config, key=key, value=value, comment=comment)
    # 发布配置
    publish_apollo_config(apollo_config=config, release_title=comment, release_comment=comment)


if __name__ == '__main__':
    update_key = 'test_101'
    update_value = ''
    update_and_publish_apollo_config(env='dev', key=update_key, value=update_value)

    os.environ['deploy_env'] = 'dev'
    print(get_apollo_config(update_key))
