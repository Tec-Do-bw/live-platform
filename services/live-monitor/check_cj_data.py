import json
from datetime import datetime, timedelta
import pymysql
import requests
import json
from datetime import datetime, timedelta
from fastapi import FastAPI

import config


# 获取当前链接的插件ID
def online_cjID():
    response = requests.get('http://47.236.42.104:8080/socketOnlineUserID').text
    responseData = json.loads(response)["data"][0]
    Cj_user_id_list = []
    for dataItem in responseData:
        Cj_user_id_list.append(dataItem["cjUserId"])
    return Cj_user_id_list


# 获取近两天的cookie
def get_live_data_cookies(db_config):
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 查询local_status=1的数据
                getLiveChectsql = f"""
                    WITH prefiltered_data AS (
                        SELECT 
                            CJ_user_id,
                            cookies,
                            requests,
                            api_name,
                            ROW_NUMBER() OVER (
                                PARTITION BY CJ_user_id 
                                ORDER BY timesTamp DESC
                            ) AS latest_record
                        FROM live_account_data_info
                        WHERE
                            DATE(timesTamp) IN (
                                CURRENT_DATE,                      
                                CURRENT_DATE - INTERVAL 1 DAY,       
                                CURRENT_DATE - INTERVAL 2 DAY       
                            )
                            AND LENGTH(cookies) > 5
                            AND CJ_user_id != ''                     
                            AND requests NOT LIKE '%98001002%'
                            AND cookies LIKE '%sessionid%'           
                    )
                    SELECT 
                        CJ_user_id,
                        cookies,
                        requests,
                        api_name
                    FROM prefiltered_data
                    WHERE latest_record = 1;                         
                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
        return []


# userID_CJID_mediaUser_id 映射关系
def get_user_id_mapping(db_config):
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 获取满足条件的media_user_id与插件ID的关系
                mappingSql = """select media_user_id,user_id,cj_user_id from  live_tiktok_media_user_id_mapping"""
                cursor.execute(mappingSql)
                result = cursor.fetchall()
                return result
        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
        return []


# 构造映射关系
def mapping_info_func(mapping_info):
    mapping_info_dict = {}
    mapping_info_dict_media_user_id = {}
    for i in mapping_info:
        mapping_info_dict[i["media_user_id"]] = i["user_id"]
        mapping_info_dict_media_user_id[i["user_id"]] = i["media_user_id"]
    return mapping_info_dict, mapping_info_dict_media_user_id


# 1.在线且连接的插件ID与对应账号ID
def get_online_and_connected_plugin_id_and_account_id(db_config):
    # 当前链接的插件ID
    result = list()
    Cj_user_id_list = online_cjID()
    # print(Cj_user_id_list)
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                """
                整个查询的逻辑流程是：
                    找出所有有效的直播间。
                    找出所有有效的GMV数据。
                    将上述两者根据 room_id 关联起来，以便让每个直播间都带上它对应的GMV数据（包括采集该数据的用户ID）
                """
                getLiveChectsql = f"""
                select c.room_id,c.room_name,c.media_user_id,c.media_user_name,c.country_code,c.room_url,c.platform,c.CJ_User_id from (
                    select a.room_id,a.room_name,a.media_user_id,a.media_user_name,a.country_code,a.room_url,a.platform,b.CJ_User_id from (select * from live_streaming_room   where local_status = 1 ) a 
                    left join 
                    (select * from live_streaming_gmv_data where local_status = 1) b 
                    on a.room_id = b.room_id ) c where CJ_User_id in ('{"','".join(Cj_user_id_list)}')
                """
                # print(getLiveChectsql)
                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()

        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    # 如果结果存在，进行处理返回
    if not result:
        result = []
    return result


# 2.有安装插件但未注册的账号ID与名称
def get_plugin_not_registered_account_id_and_name(db_config):
    mapping_info = get_user_id_mapping(db_config)
    mapping_info_dict, mapping_info_dict_media_user_id = mapping_info_func(mapping_info)
    result = list()
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 查询local_status=1的数据
                """
                整个查询的逻辑流程是：
                1. **圈定范围**: 只看最近三天的数据，并筛选出所有有效登录的记录（比如有sessionid且没有未登录标记）。
                2. **分组排序**: 将这些记录按每个插件用户(CJ_user_id)分组，并在组内按时间从新到旧排序。
                3. **精确提取**: 最后，为每个用户只提取出排名第一的那条记录，也就是他们最近一次的有效登录数据。
                简单概括就是：“给我每个用户在过去三天里最新的一次成功登录记录”。
                """
                getLiveChectsql = f"""
                    WITH recent_data AS (
                        SELECT 
                            CJ_user_id,
                            cookies,
                            requests,
                            api_name,
                            ROW_NUMBER() OVER (
                                PARTITION BY CJ_user_id 
                                ORDER BY timesTamp DESC
                            ) AS row_rank
                        FROM live_account_data_info
                        WHERE
                            SUBSTRING(timesTamp, 1, 10) IN (
                                DATE_FORMAT(CURRENT_DATE, '%Y-%m-%d'),
                                DATE_FORMAT(CURRENT_DATE - INTERVAL 1 DAY, '%Y-%m-%d'),
                                DATE_FORMAT(CURRENT_DATE - INTERVAL 2 DAY, '%Y-%m-%d')
                            )
                            AND LENGTH(cookies) > 5
                            AND CJ_user_id != ''  
                            AND requests NOT LIKE '%98001002%'
                            AND cookies LIKE '%sessionid%'  
                    )
                    SELECT
                        CJ_user_id,
                        cookies,
                        requests,
                        api_name
                    FROM recent_data
                    WHERE row_rank = 1;  
                """
                # print(getLiveChectsql)
                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()

        finally:
            pass
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    if not result:
        result = []

    # # 这里开始清洗获取到的数据，返回userid,cookies,mstoken
    argsList = list()
    cj_IDList = []
    for data in result:
        tmp_Ck = {}
        try:
            responseInit = json.loads(data["requests"])
            CJ_user_id = data["CJ_user_id"]

            responseInit_json = json.loads(responseInit.get("response"))
            ctData = responseInit_json.get("data", "")
            # 如果是creator_id在responseInit_json 里面说明是关键指标接口；否则是账号信息接口来的
            if "creator_id" in str(ctData):
                creator_id = ctData.get("segments")[0].get("filter").get("creator_id", "")
                tmp_Ck["user_id"] = mapping_info_dict.get(creator_id)
                tmp_Ck["media_user_id"] = creator_id
                tmp_Ck["user_name"] = ""
            else:
                tmp_Ck["user_id"] = ctData.get("user_id", "")
                tmp_Ck["media_user_id"] = mapping_info_dict_media_user_id.get(ctData.get("user_id", ""))
                tmp_Ck["user_name"] = ctData.get("user_name", "")
            # tmp_Ck["api_name"] = data["api_name"]
            tmp_Ck["CJ_user_id"] = CJ_user_id
        except:
            continue
        if tmp_Ck["CJ_user_id"] not in cj_IDList:
            cj_IDList.append(tmp_Ck["CJ_user_id"])
            argsList.append(tmp_Ck)
    # print("argsList--->",argsList)
    # 最近两天在线安装了插件且登录的账号ID

    with connection.cursor() as cursor:
        # 查询满足条件的数据
        """
        整个查询的逻辑流程是：
        1. **准备账号清单**: 从`live_streaming_room`表中获取所有我们系统内已知的、有效的TikTok账号列表。
        2. **准备插件绑定清单**: 从`live_streaming_gmv_data`表中获取所有“账号-插件ID”的绑定关系。
        3. **合并信息**: 将上述两个列表进行关联，生成一个包含所有已知账号的完整列表，并附上它们各自绑定的插件ID（如果存在的话）。
        简单概括就是：“给我一份所有已注册账号的完整清单，并注明它们是否已绑定插件。”
        """
        getLiveChectsql2 = f"""
                WITH filtered_rooms AS (
            SELECT 
                room_id,
                room_name,
                media_user_id,
                media_user_name,
                country_code,
                room_url,
                platform
            FROM live_streaming_room
            WHERE local_status = 1  
        ),
        filtered_gmv AS (
            SELECT 
                room_id,
                CJ_User_id
            FROM live_streaming_gmv_data
            WHERE local_status = 1  
        )
        SELECT 
            r.media_user_id,
            r.media_user_name,
            r.country_code,
            r.room_url,
            r.platform
        FROM filtered_rooms r
        LEFT JOIN filtered_gmv g
            ON r.room_id = g.room_id;

        """
        # print(getLiveChectsql)
        cursor.execute(getLiveChectsql2)
        result2 = cursor.fetchall()
    connection.close()
    media_user_id_tmp_list2 = [i["media_user_id"] for i in result2]

    有安装插件但未注册的账号ID与名称 = list()
    for j in argsList:
        if j["media_user_id"] not in media_user_id_tmp_list2:
            有安装插件但未注册的账号ID与名称.append(j)

    # responseEndData["有安装插件但未注册的账号ID与名称"] = 有安装插件但未注册的账号ID与名称
    return 有安装插件但未注册的账号ID与名称


# 3.有安装插件但未登录的插件ID(这里需要给出对应国家，以及历史登录过的直播间账号)
def get_plugin_not_logged_in_plugin_id(db_config):
    result = list()
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                # 查询最新一条数据是为登录的插件ID
                """
                整个查询的逻辑流程是：
                1. **筛选近期活跃用户**: 从`live_account_data_info`表中获取最近2天内有活动记录的所有插件用户，并为每个用户找出最新的一条记录。
                2. **识别未登录状态**: 检查这些最新记录中的`requests`字段，如果包含'%98001002%'错误码，则表示该用户最近一次尝试时处于未登录状态。
                3. **关联用户信息**: 将这些"未登录"的插件ID与`live_streaming_gmv_data`和`live_streaming_room`表关联，获取用户的详细账号信息。
                简单概括就是："给我列出所有最近一次活动时显示未登录状态的插件用户，并附上他们的账号详情。"
                """
                getLiveChectsql = f"""
                    WITH filtered_accounts AS (
                        SELECT CJ_user_id
                        FROM (
                            SELECT 
                                CJ_user_id,
                                requests,
                                ROW_NUMBER() OVER (PARTITION BY CJ_user_id ORDER BY timesTamp DESC) AS rn
                            FROM live_account_data_info
                            WHERE 
                                DATE(timesTamp) BETWEEN DATE_SUB(CURDATE(), INTERVAL 2 DAY) AND CURDATE()  
                                AND LENGTH(cookies) > 20
                                AND CJ_user_id != ''
                        ) t
                        WHERE rn = 1 AND requests LIKE '%98001002%'
                    )
                    SELECT 
                        g.CJ_User_id,
                        l.media_user_id,
                        l.media_user_name,
                        l.country_code,
                        g.platform
                    FROM live_streaming_gmv_data g
                    JOIN filtered_accounts ON g.CJ_User_id = filtered_accounts.CJ_user_id
                    LEFT JOIN live_streaming_room l ON g.room_id = l.room_id;

                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()

        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    if not result:
        result = []
    有安装插件但未登录的插件ID = result
    return 有安装插件但未登录的插件ID


# 4.注册了但未安装插件的直播账号ID
def get_registered_but_not_installed_plugin_account_id(db_config):
    注册了但未安装插件的直播账号ID = []
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                getLiveChectsql = f"""
                    SELECT
                        a.room_id,
                        a.CJ_User_id,
                        b.media_user_id,
                        b.media_user_name,
                        b.country_code,
                        b.room_url 
                        FROM
                        ( SELECT * FROM live_streaming_gmv_data WHERE local_status = 1 AND CJ_User_id = "" AND platform = 'tiktok' ) a
                        LEFT JOIN live_streaming_room b ON a.room_id = b.room_id
                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()

        finally:
            connection.close()
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    注册了但未安装插件的直播账号ID = result

    return 注册了但未安装插件的直播账号ID


# 5.注册了且安装了插件但没有打开插件或断开连接的直播账号ID
def get_registered_and_installed_plugin_but_not_opened_or_disconnected_account_id(db_config):
    注册了且安装了插件但没有打开插件或断开连接的直播账号ID = []
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                """
                整个查询的逻辑流程是：
                -查询tk童虎映射表在昨天至今天之间有更新的记录。
                """
                getLiveChectsql_1 = f"""
                     SELECT media_user_id
                    FROM live_tiktok_media_user_id_mapping
                    WHERE STR_TO_DATE(update_time, '%Y-%m-%d %H:%i:%s') BETWEEN 
                        (CURDATE() - INTERVAL 1 DAY) AND 
                        (CURDATE() + INTERVAL 1 DAY - INTERVAL 1 SECOND)
                """

                cursor.execute(getLiveChectsql_1)
                result = cursor.fetchall()

        finally:
            pass

        try:
            with connection.cursor() as cursor:
                """
                整个查询的逻辑流程是：
                    从 GMV 数据表中筛选 TikTok 平台、用户 ID 不为空、且状态正常的记录，然后关联房间信息表，输出相应的房间/主播信息。
                """
                getLiveChectsql_2 = f"""
                       select b.media_user_id,b.room_id,b.media_user_name,b.room_url from(
                        select *from live_streaming_gmv_data where local_status = 1 and  platform = 'tiktok' and CJ_User_id != '') a 
                        left join 
                        live_streaming_room b 
                        on a.room_id = b.room_id

                """

                cursor.execute(getLiveChectsql_2)
                result2 = cursor.fetchall()

        finally:
            pass
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")
    media_user_id_list = [i["media_user_id"] for i in result]
    for i in result2:
        if i["media_user_id"] not in media_user_id_list:
            注册了且安装了插件但没有打开插件或断开连接的直播账号ID.append(i)

    return 注册了且安装了插件但没有打开插件或断开连接的直播账号ID


# 6.安装了插件但从没有登录过的CJID
def get_installed_plugin_but_not_logged_in_cjid(db_config):
    online_cj_Id_list = online_cjID()
    安装了插件但从没有登录过的CJID = []
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                getLiveChectsql = f"""
                    select CJ_User_id from live_streaming_gmv_data where local_status = 1  and CJ_User_id != ''
                """

                cursor.execute(getLiveChectsql)
                result = cursor.fetchall()

        finally:
            pass
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    login_cj_Id_list = [i["CJ_User_id"] for i in result]
    安装了插件但从没有登录过的CJID1 = [i for i in online_cj_Id_list if i not in login_cj_Id_list]

    result2 = []
    try:
        # 建立数据库连接
        connection = pymysql.connect(**db_config)
        try:
            with connection.cursor() as cursor:
                getLiveChectsql2 = f"""
                    select CJ_User_id from live_tiktok_media_user_id_mapping
                """

                cursor.execute(getLiveChectsql2)
                result2 = cursor.fetchall()

        finally:
            pass
    except Exception as e:
        print(f"数据库连接或查询出错: {e}")

    login_cj_Id_list2 = [i["CJ_User_id"] for i in result2]
    安装了插件但从没有登录过的CJID = [i for i in 安装了插件但从没有登录过的CJID1 if
                                      i not in login_cj_Id_list2 and i != 'paidaxing']
    connection.close()
    return 安装了插件但从没有登录过的CJID


def check_CJ_data(istest=0):
    # 数据库连接参数已迁移到 Apollo（config 门面）；istest 参数保留兼容旧调用，已不再使用
    db_config = {
        **config.mysql_config(),
        'cursorclass': pymysql.cursors.DictCursor,
    }

    # # 链接数据库配置
    responseEndData = {
        "在线且连接的插件ID与对应账号ID": get_online_and_connected_plugin_id_and_account_id(db_config),
        "有安装插件但未注册的账号ID与名称": get_plugin_not_registered_account_id_and_name(db_config),
        "有安装插件但未登录的插件ID": get_plugin_not_logged_in_plugin_id(db_config),
        "注册了但未安装插件的直播账号ID": get_registered_but_not_installed_plugin_account_id(db_config),
        "注册了且安装了插件但没有打开插件或断开连接的直播账号ID": get_registered_and_installed_plugin_but_not_opened_or_disconnected_account_id(
            db_config),
        "安装了插件但从没有登录过的CJID": get_installed_plugin_but_not_logged_in_cjid(db_config)
    }

    return responseEndData

if __name__ == '__main__':
    print(check_CJ_data(1))