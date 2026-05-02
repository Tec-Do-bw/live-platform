import time

# ✅ ✅ ✅ ✅ 通用性数据获取 ✅ ✅ ✅ ✅ ✅ 
def TiktokLiveUrl(taskParams):
    initRequestsData = {   'addOPExec': 'TiktokLiveAddOP(OP,tabItem)',
                            'doc': {   'defaultParams': {   'listenUrl': {'type': 'string', 'value': 'user/room.aid=1988'},
                                                            'mateUrl': {'type': 'string', 'value': taskParams["body"]["mateUrl"]}},
                                       'description': '获取加密直播间真实直播地址',
                                       'docsLinks': [],
                                       'endpoint': 'http://127.0.0.1:8080/liveRoom/portInfo',
                                       'headers': {},
                                       'method': 'POST',
                                       'responseFieldDescription': {}},
                            'generateRequestsUrl': 'TiktokLiveUrl(taskParams)',
                            'listenUrl': ['user/room.aid=1988'],
                            'mateUrl': taskParams["body"]["mateUrl"],
                            'parseFunc': '',
                            'saveFunc': ''}
    
    return initRequestsData

# 通用性数据获取需要额外操作的动作。默认等待5秒
def TiktokLiveAddOP(OP,tabItem):
    time.sleep(15)











