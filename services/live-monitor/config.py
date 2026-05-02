import os


# 获取当前文件所在文件夹绝对路径
def get_current_directory():
    current_file_path = os.path.abspath(__file__)
    current_directory = os.path.dirname(current_file_path)
    return current_directory.replace("\\", '/')


# MCP配置
MCP_config = {
    "DEEPSEEK_API_KEY": ""
}

# 账号配置
account_config = {
    "ttUser": "paidaxing"
}

# 版本历史记录
version_history = [
    {
        "version": "v1.0.0",
        "releaseDate": "2025-04-27",
        "updates": [
            {
                "type": "feature",
                "items": [
                    "页面重构上线",
                    "添加直播间存在验证接口"
                ]
            },
            {
                "type": "improvement",
                "items": [
                    "优化直播间多次请求获取地址问题",
                    "加快响应50%"
                ]
            },
            {
                "type": "fix",
                "items": [
                    "修复账号风控问题"
                ]
            }
        ]
    }

]

# 初始浏览器调动配置设置
brower_config = {
    "Chromium": {
        "chrome_driver_path": "",  # 浏览器驱动driver路径,默认为空
        "initNum": 1,  # 启动浏览器数量,默认为1个浏览器
        "tabNum": 1,  # 每个浏览器打开的标签页数量，默认为1
        "isheadless": True,  # 是否无头模式，默认为否
        "proxyItem": [],  # 代理设置，默认为空
        "timeOuts": 15,  # 加载等待-默认为15秒
        "isincognito": False,  # 是否匿名无痕模式，默认为否
        "extensionPath": "",  # 加载插件路径，默认为空
        "downloadPath": "download"  # 文件下载保存地址,默认为download文件夹
    }
}

# 监听web url配置文件
requests_config = {'ShopeeLive': {'LiveRoomLink': {'addOPExec': '',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://my.shp.ee/mLYd9Av'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/shopeeInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': '',
                                                   'listenUrl': '',
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'TiktokLive': {'LiveRoomLink': {'addOPExec': 'TiktokLiveAddOP(OP,tabItem)',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://www.tiktok.com/@petersonslabbeauty/live'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/portInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': 'TiktokLiveUrl(taskParams)',
                                                   'listenUrl': ['user/room?aid=1988'],
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'LazadaLive': {'LiveRoomLink': {'addOPExec': '',
                                                   'doc': {'defaultParams': {'mateUrl': {'type': 'string',
                                                                                         'value': 'https://s.lazada.com.my/s.Gl8c1'}},
                                                           'description': '获取加密直播间真实直播地址',
                                                           'docsLinks': [],
                                                           'endpoint': 'http://47.236.42.104:8080/liveRoom/lazadaInfo',
                                                           'headers': {
                                                               'access-token': 'AFDD0B4AD2EC172C586E2150770FBF9E'},
                                                           'method': 'POST',
                                                           'responseFieldDescription': {}},
                                                   'generateRequestsUrl': '',
                                                   'listenUrl': '',
                                                   'mateUrl': '',
                                                   'parseFunc': '',
                                                   'saveFunc': ''}},
                   'socket': {'CJ_version_data': {'addOPExec': '',
                                                  'doc': {
                                                      'defaultParams': {'user_type': {'type': 'string', 'value': '5'}},
                                                      'description': '获取版本对应的插件安装信息',
                                                      'docsLinks': [],
                                                      'endpoint': 'http://47.236.42.104:8081/CJ_version_data',
                                                      'headers': {},
                                                      'method': 'GET',
                                                      'responseFieldDescription': {}},
                                                  'generateRequestsUrl': '',
                                                  'listenUrl': '',
                                                  'mateUrl': '',
                                                  'parseFunc': '',
                                                  'saveFunc': ''},
                              'check_cj': {'addOPExec': '',
                                           'doc': {'defaultParams': {},
                                                   'description': '校验插件与直播间关系',
                                                   'docsLinks': [],
                                                   'endpoint': 'http://47.236.42.104:8081/get_check_CJ_data',
                                                   'headers': {},
                                                   'method': 'GET',
                                                   'responseFieldDescription': {}},
                                           'generateRequestsUrl': '',
                                           'listenUrl': '',
                                           'mateUrl': '',
                                           'parseFunc': '',
                                           'saveFunc': ''},
                              'socketOnlineUserID': {'addOPExec': '',
                                                     'doc': {'defaultParams': {},
                                                             'description': '获取当前链接的插件ID',
                                                             'docsLinks': [],
                                                             'endpoint': 'http://47.236.42.104:8080/socketOnlineUserID',
                                                             'headers': {},
                                                             'method': 'GET',
                                                             'responseFieldDescription': {}},
                                                     'generateRequestsUrl': '',
                                                     'listenUrl': '',
                                                     'mateUrl': '',
                                                     'parseFunc': '',
                                                     'saveFunc': ''}}}

# 爬虫数据需求池
data_need_pool = []
