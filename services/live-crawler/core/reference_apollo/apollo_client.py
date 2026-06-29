# -*- coding: utf-8 -*-
import json
import logging
import threading
import time
from working.util.log_util import info, error
import requests
from working.apollo.apollo_config import get_apollo_server_config

logger = logging.getLogger(__name__)
class ApolloClient(object):
    def __init__(self, app_id, cluster='default', config_server_url='http://localhost:8080', timeout=35, ip=None):
        self.config_server_url = config_server_url
        self.appId = app_id
        self.cluster = cluster
        self.timeout = timeout
        self.stopped = False
        self.init_ip(ip)

        self._stopping = False
        self._cache = {}
        self._notification_map = {'application': -1}

    def init_ip(self, ip):
        if ip:
            self.ip = ip
        else:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 53))
                ip = s.getsockname()[0]
            finally:
                s.close()
            self.ip = ip

    # Main method
    def get_value(self, key, default_val=None, namespace='application', auto_fetch_on_cache_miss=False):
        if namespace not in self._notification_map:
            self._notification_map[namespace] = -1
            logging.getLogger(__name__).debug("Add namespace '%s' to local notification map", namespace)

        if namespace not in self._cache:
            self._cache[namespace] = {}
            logging.getLogger(__name__).debug("Add namespace '%s' to local cache", namespace)
            # This is a new namespace, need to do a blocking fetch to populate the local cache
            self._long_poll()

        if key in self._cache[namespace]:
            return self._cache[namespace][key]
        else:
            if auto_fetch_on_cache_miss:
                return self._cached_http_get(key, default_val, namespace)
            else:
                return default_val

    # Start the long polling loop. Two modes are provided:
    # 1: thread mode (default), create a worker thread to do the loop. Call self.stop() to quit the loop
    # 2: eventlet mode (recommended), no need to call the .stop() since it is async
    def start(self, use_eventlet=False, eventlet_monkey_patch=False, catch_signals=True):
        # First do a blocking long poll to populate the local cache, otherwise we may get racing problems
        if len(self._cache) == 0:
            self._long_poll()
        if use_eventlet:
            import eventlet
            if eventlet_monkey_patch:
                eventlet.monkey_patch()
            eventlet.spawn(self._listener)
        else:
            if catch_signals:
                import signal
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGABRT, self._signal_handler)
            t = threading.Thread(target=self._listener)
            t.start()

    def stop(self):
        self._stopping = True
        logging.getLogger(__name__).debug("Stopping listener...")

    def _cached_http_get(self, key, default_val, namespace='application'):
        url = '{}/configfiles/json/{}/{}/{}?ip={}'.format(self.config_server_url, self.appId, self.cluster, namespace,
                                                          self.ip)
        r = requests.get(url)
        if r.ok:
            data = r.json()
            self._cache[namespace] = data
            logging.getLogger(__name__).debug('Updated local cache for namespace %s', namespace)
        else:
            data = self._cache[namespace]

        if key in data:
            return data[key]
        else:
            return default_val

    def _uncached_http_get(self, namespace='application'):
        url = '{}/configs/{}/{}/{}?ip={}'.format(self.config_server_url, self.appId, self.cluster, namespace, self.ip)
        # print('url:{}'.format(url))
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            self._cache[namespace] = data['configurations']
            logging.getLogger(__name__).debug('Updated local cache for namespace %s release key %s: %s',
                                              namespace, data['releaseKey'],
                                              repr(self._cache[namespace]))

    def _signal_handler(self, signal, frame):
        logging.getLogger(__name__).debug('You pressed Ctrl+C!')
        self._stopping = True

    def _long_poll(self):
        url = '{}/notifications/v2'.format(self.config_server_url)
        notifications = []
        for key in self._notification_map:
            notification_id = self._notification_map[key]
            notifications.append({
                'namespaceName': key,
                'notificationId': notification_id
            })

        r = requests.get(url=url, params={
            'appId': self.appId,
            'cluster': self.cluster,
            # 'envs': 'PRO',
            'notifications': json.dumps(notifications, ensure_ascii=False)
        }, timeout=self.timeout)

        logging.getLogger(__name__).debug('Long polling returns %d: url=%s', r.status_code, r.request.url)

        if r.status_code == 304:
            # no change, loop
            logging.getLogger(__name__).debug('No change, loop...')
            return

        if r.status_code == 200:
            data = r.json()
            for entry in data:
                ns = entry['namespaceName']
                nid = entry['notificationId']
                logging.getLogger(__name__).debug("%s has changes: notificationId=%d", ns, nid)
                self._uncached_http_get(ns)
                self._notification_map[ns] = nid
        else:
            logging.getLogger(__name__).warn('Sleep...')
            time.sleep(self.timeout)

    def _listener(self):
        logging.getLogger(__name__).debug('Entering listener loop...')
        while not self._stopping:
            self._long_poll()

        logging.getLogger(__name__).debug("Listener stopped!")
        self.stopped = True


# 获取apollo配置
def get_apollo_config(key):


    gotConfig = 0
    retry = 0
    while gotConfig == 0:
        if retry > 5:
            info('获取apollo配置[key]出错，返回空值')
            return ''
        try:
            apollo_config = get_apollo_server_config()
            # print(apollo_config.__dict__)
            logging.getLogger(__name__).debug('当前获取配置为%s,当前环境为%s', str(apollo_config.apollo_appid), str(apollo_config.apollo_env))
            client = ApolloClient(app_id=apollo_config.apollo_appid, cluster=apollo_config.cluster,
                                  config_server_url=apollo_config.apollo_server)
            info('当前获取配置为'+str(apollo_config.apollo_appid)+'当前环境为'+str(apollo_config.apollo_env))

            val = client.get_value(key=key, default_val='')
            if val is None or val == '':
                retry += 1
                continue
            gotConfig = 1
        except Exception as exp:
            retry += 1
            error('获取apollo配置[' + key + ']出错，尝试第' + str(retry) + '次重新获取,错误信息： ' + str(exp))
            time.sleep(1)
    return val


if __name__ == '__main__':
    import os
    os.environ['deploy_env'] = 'test'
    print(get_apollo_config('test_101'))

    # has_account = 1
    # while has_account == 1:
    #     for i in range(0, 1000):
    #         key_t = 'google_mm_account[' + str(i) + ']'
    #         config = get_apollo_config(key_t)
    #         if config == '':
    #             has_account = 0
    #             break
    #         print(config)