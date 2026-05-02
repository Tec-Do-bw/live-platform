from datetime import datetime, timedelta
import json
import requests
from utils.db_pool import db_pool
from utils.logger import Logings

logger = Logings().get_logger()

# 获取近两天的cookie（使用连接池）
def get_live_data_cookies():
    """
    从数据库获取近两天的cookie数据
    
    Returns:
        查询结果列表
    """
    try:
        today = datetime.today()
        yesterday = today - timedelta(days=1)
        today_formatted = today.strftime('%Y-%m-%d') 
        yesterday_formatted = yesterday.strftime('%Y-%m-%d') 
        
        day_before_yesterday = today - timedelta(days=2)
        day_before_yesterday_formatted = day_before_yesterday.strftime('%Y-%m-%d')
        
        # ✅ 查询SQL
        getLiveChectsql = f"""
            select CJ_user_id,cookies,requests,api_name from(
                select *,ROW_NUMBER() over(PARTITION by CJ_user_id  order by  `timesTamp` desc) k from 
                (select CJ_user_id,cookies,requests,timesTamp,api_name from 
                live_account_data_info 
                where  (`timesTamp` like '%{today_formatted}%' or `timesTamp` like '%{yesterday_formatted}%' or `timesTamp` like '%{day_before_yesterday_formatted}%')
                and length(cookies)>5 and  LENGTH(cj_user_id)>0  and requests not like '%98001002%'  and cookies like '%sessionid%') a
                ) b where k=1 and cookies like '%sessionid%'
        """ 
        
        # ✅ 使用连接池查询
        result = db_pool.execute_query(getLiveChectsql)
        logger.info(f"获取cookie数据成功 | 数量={len(result) if result else 0}")
        return result if result else []
        
    except Exception as e:
        logger.error(f"数据库查询出错: {e}", exc_info=True)
        return []
    

# ✅ ✅ ✅ ✅ 公司apollo获取配置 ✅ ✅ ✅ ✅ ✅ 
# apollo获取配置
def fetch_apollo_config(istest):
    #测试环境
    if istest == 1:
        APOLLO_URL = 'http://dev-apollo.tec-develop.com'
        APOLLOID = 'live-spider'

    #正式环境
    else:
        # http://10.225.17.67:30080（windows机子需要单独做映射）
        APOLLO_URL = 'http://10.225.17.67:30080'
        # APOLLO_URL = 'http://apollo-service-apollo-configservice.apollo:8080'
        APOLLOID = 'live-spider'
       
    if istest == 1:
        url = "{}/configs/{}/dev01/application".format(str(APOLLO_URL),str(APOLLOID))
    else:
        url = "{}/configs/{}/PRO/application".format(str(APOLLO_URL),str(APOLLOID))
   
    # 配置你的 Apollo 服务详情
    config_data = {}
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查响应是否成功
        config_data = response.json()
    except Exception as e:
        print(f"获取apollo配置失败: {e}")
        
    if config_data:
        configurations = config_data["configurations"]
        return  configurations
    else:
        return {}


def getCookies():
    """
    获取TikTok cookies列表
    
    Returns:
        包含msToken和sessionid的字典列表
    """
    try:
        # ✅ 使用连接池查询（连接池已在 main.py 中初始化）
        Sql_data = get_live_data_cookies()

        argsList = []
        for data in Sql_data:
            tmp_Ck = {}
            try:
                # 解析cookies JSON
                cookiesInit = json.loads(data["cookies"]) if isinstance(data["cookies"], str) else data["cookies"]
            except Exception as e:
                logger.debug(f"解析cookies失败: {e}")
                continue
            
            # 提取msToken和sessionid
            for i_1 in cookiesInit:
                if i_1["name"] == "msToken":
                    tmp_Ck["msToken"] = i_1["value"]
                if i_1["name"] == "sessionid":
                    tmp_Ck["sessionid"] = i_1["value"]
                if "sessionid" in tmp_Ck and "msToken" in tmp_Ck:
                    break
            
            if "sessionid" in tmp_Ck and "msToken" in tmp_Ck:
                argsList.append(tmp_Ck)
        
        logger.info(f"getCookies完成 | 有效cookies={len(argsList)}")
        return argsList
        
    except Exception as e:
        logger.error(f"getCookies异常: {e}", exc_info=True)
        return []



























