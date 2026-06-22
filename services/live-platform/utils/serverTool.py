import os
import time
import requests



#apollo获取配置
def fetch_apollo_config(istest=0):
    # APOLLO_URL = str(os.environ.get('APOLLO_URL')).strip()
    # APOLLOID = str(os.environ.get('APOLLOID')).strip()
    # if APOLLO_URL=="None" and APOLLOID=="None":
    #     print("测试环境")
    #     istest = 1
    # else:
    #     print("生产环境")
    #     istest = 0
    
    #测试环境
    if istest == 1:
        APOLLO_URL = 'http://dev-apollo.tec-develop.com'
        APOLLOID = 'live-spider'

    #正式环境
    else:
        # http://10.225.17.67:30080（windows机子需要单独做映射）
        if os.name == 'nt': # win系统等于nt，
            APOLLO_URL = 'http://10.225.17.67:30080'
        else:
            APOLLO_URL = 'http://apollo-service-apollo-configservice.apollo:8080'
        APOLLOID = 'live-spider'
       
    if istest == 1:
        url = "{}/configs/{}/dev01/application".format(str(APOLLO_URL),str(APOLLOID))
    else:
        url = "{}/configs/{}/PRO/application".format(str(APOLLO_URL),str(APOLLOID))
   
    # 配置你的 Apollo 服务详情
    config_data = {}
    for i in range(5):
        try:
            response = requests.get(url)
            response.raise_for_status()  # 检查响应是否成功
            config_data = response.json()
            break
        except Exception as e:
            print(f"获取apollo配置失败: {e}")
            time.sleep(3) # apollo有别的地方同时请求获取会暂时限制

    if config_data:
        configurations = config_data["configurations"]
        return  configurations
    else:
        return {}
