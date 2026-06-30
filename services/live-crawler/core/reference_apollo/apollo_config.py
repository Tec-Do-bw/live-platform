# Apollo配置文件，非生产环境手动替换配置
import os

from working.util.log_util import info


# Apollo配置对象
class ApolloConfig:
    apollo_server: str
    apollo_appid: str
    apollo_env: str
    cluster: str
    namespace: str

    def __init__(self, config_server_url: str, appid: str, env: str, cluster: str = 'default',
                 namespace: str = 'application'):
        self.apollo_server = config_server_url
        self.apollo_appid = appid
        self.apollo_env = env
        self.cluster = cluster
        self.namespace = namespace


def get_apollo_server_config(env: str = None) -> ApolloConfig:

    if env is None:
        env = os.getenv('deploy_env', 'dev')
        info('after detection deploy_env:{}'.format(os.getenv('deploy_env', 'dev')))
    if env == 'prod':
        config = ApolloConfig(config_server_url='http://prod.in.apollo.service.tec-develop.com',
                              appid='bee-worker', env='PRO', cluster='default')
        return config
    elif env == 'test':
        config = ApolloConfig(config_server_url='http://test-apollo.tec-develop.com',
                              appid='bee-worker', env='TEST', cluster='test01')  # env='default'
        return config
    else:
        config = ApolloConfig(config_server_url='http://dev-apollo.tec-develop.com',
                              appid='bee-worker', env='dev', cluster='default')  # env='test01'
        return config


if __name__ == '__main__':
    os.environ['deploy_env'] = 'prod'
    configparser = get_apollo_server_config()
    print(configparser.__dict__)
    # os.putenv( 'xxxxxxx', 'DEPLOY_ENV')
    print(os.getenv('deploy_env', 'dev'))
