import pandas as pd
from kafka import KafkaProducer
import json
import requests
import os
import time
import inspect
import httpx
import sys
from urllib.parse import urlparse, parse_qs
import importlib
from datetime import datetime
import subprocess
import re
from threading import Thread
from queue import Queue, Empty
import hashlib
from fastapi import HTTPException
from contextlib import asynccontextmanager
import logging
import traceback
from collections import defaultdict
import urllib3
import urllib.request
import gzip
from lxml import etree
from urllib import parse
import random
from requests.auth import HTTPProxyAuth
import pymysql
from dbutils.pooled_db import PooledDB
import threading
import psycopg2
from typing import List
from alibabacloud_hologram20220601.client import Client as Hologram20220601Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util.client import Client as UtilClient


try:
    from config import brower_config, requests_config, MCP_config
except:
    # 添加上一级目录到系统路径
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import brower_config, requests_config, MCP_config



# ✅ ✅ ✅ ✅ 禁用警告 ✅ ✅ ✅ ✅ ✅ 
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ✅ ✅ ✅ ✅ 日志解析 ✅ ✅ ✅ ✅ ✅ 
def parse_log_to_dict(log_path):
    """
    解析日志文件并生成结构化字典
    
    参数：
    log_path : str - 日志文件路径
    
    返回：
    dict - 格式为 {"script1": ["time1", "time2"], "script2": [...]}，每个脚本最多保留最新的5条记录
    """
    pattern = re.compile(r'\[(.*?)\]--->\[(.*?)\]')
    result = defaultdict(list)
    
    with open(log_path, 'r') as f:
        for line in f:
            match = pattern.search(line.strip())
            if match:
                timestamp, script = match.groups()
                result[script].append(timestamp)
    
    # 对每个脚本只保留最新的5条记录
    for script in result:
        if len(result[script]) > 5:
            result[script] = result[script][-5:]
                
    return dict(result)





# ✅ ✅ ✅ ✅ 日志相关 ✅ ✅ ✅ ✅ ✅ 
#日志装饰器，对报错函数详细信息进行记录
def error_logging_decorator(isPrintLog=False,log_file_path=""):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = logging.getLogger(func.__name__)
                logger.setLevel(logging.ERROR)
                # 创建一个文件处理器，设置日志级别和日志文件路径(默认设置为ERROR)
                if len(log_file_path) == 0:
                    log_file_path = get_current_directory() + "/error_all.log"
                if not os.path.exists(log_file_path):
                    with open(log_file_path,"w",encoding="utf-8") as f:
                        pass
                file_handler = logging.FileHandler(log_file_path)
                file_handler.setLevel(logging.ERROR)
                # 将文件处理器添加到日志记录器
                logger.addHandler(file_handler)
                strTime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                tb = traceback.extract_tb(e.__traceback__)
                for frame in tb:
                    filename, line_number, function_name, _ = frame
                    if frame == tb[-1]:
                        if isPrintLog:
                            print('-----------------------------Error分割线Error-----------------------------')
                            print(f"产生报错时间：{strTime}")
                            print(f"报错文件路径: {filename}")
                            print(f"报错代码行数：第 {line_number} 行")
                            print(f"报错函数名称:  {function_name}")
                            print(f"函数传入参数: {args}")

                        # 记录错误信息
                        logger.error('-----------------------------Error分割线Error-----------------------------')
                        logger.error(f"产生报错时间：{strTime}")
                        logger.error(f"报错文件路径: {filename}")
                        logger.error(f"报错代码行数：第 {line_number} 行")
                        logger.error(f"报错函数名称:  {function_name}")
                        logger.error(f"函数传入参数: {args}")
                if isPrintLog:
                    print("\n以下是报错详细堆栈细节:")
                    traceback.print_exc()
                logger.error("\n以下是报错详细堆栈细节:")
                logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
                # 移除文件处理器，避免资源泄露
                logger.removeHandler(file_handler)

                return None  # 或者根据需要返回其他默认值、空对象等
        return wrapper
    return decorator

#普通操作写入日志记录
def spiderLogWrite(log_content="",log_file_path=""):
    """对需要记录在日志中的进行记录，可以看成写入log文件的print函数使用"""
    print("log_content-->",log_content)
    if len(log_file_path) == 0:
        log_file_path = get_current_directory() + "/print_all.log"
    if not os.path.exists(log_file_path):
        with open(log_file_path,"w",encoding="utf-8") as f:
            pass
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.info(log_content)
    logger.removeHandler(file_handler)



# ✅ ✅ ✅ ✅ 文件路径与操作相关 ✅ ✅ ✅ ✅ ✅ 
#获取当前文件所在文件夹绝对路径
def get_current_directory():
    current_file_path = os.path.abspath(__file__)
    current_directory = os.path.dirname(os.path.dirname(current_file_path))
    return current_directory.replace("\\",'/')


    
    
# Apollo 配置统一走 config 门面（唯一权威源）
import config


# ✅ ✅ ✅ ✅ 公共解析相关 ✅ ✅ ✅ ✅ ✅ 
#所有公共解析类
class publicParseExe():
    def __init__(self):
        self.parseFunction = ""
    def help(self):
        print("这是关于公共解析函数用法说明")
        helpContent= '''
        这是关于公共解析函数用法说明：
        代码实际调用实例：
            re正则:result = reParse(arg,re_rule)
            beautifulsoup:result = beautifulsoupParse(arg,re_rule)
            xPath:result = xpathParse(arg,re_rule)
            json:result = jsonParse(arg)

            参数说明：
                arg:需要解析的数据字符对象
                re_rule:解析规则(字符转json对象无需规则传入)
            返回值：
                result:解析完结果返回值
        '''
        print(helpContent)

    '''re'''
    def reParse(self,html,re_rule):
        result = re.compile(re_rule,re.S).findall(html)
        return result



    '''xPath'''
    def xpathParse(self,html,xPath_rule):
        if xPath_rule=="":
            return []
        if isinstance(html, str):
            data = etree.HTML(html)
            result = data.xpath(xPath_rule)
        # 如果传入的事xpath对象
        else:
            dataTmp = etree.tostring(html, encoding='unicode')
            data = etree.HTML(dataTmp)
            result = data.xpath(xPath_rule)
        return result

    '''json'''
    def jsonParse(self,html):
        data = json.loads(html)
        return data

    '''read JS File'''
    def jsFromFile(self,file_name):
        with open(file_name,"r", encoding='UTF-8') as file:
            result = file.read()
        return result
    # unicode转字符串
    def decodeUnicodeEscape(self,arg):
        pattern = r'\\u00([0-9a-fA-F]{2})'
        def replace(match):
            hex_value = match.group(1)
            decimal_value = int(hex_value, 16)
            char = chr(decimal_value)
            return char
        decoded_str = re.sub(pattern, replace, arg)
        return decoded_str
    #判断url是否需要转码如果需要则转码,不需要就返回源字符串
    def encodeUrlIfNeeded(self,url):   
        chars_to_encode = set(':/?#[]@!$&\'()*+,;=')  
        for char in url:  
            if char in chars_to_encode:  
                return parse.quote(url, safe='') 
        return url  
    #'''转义URL,解码,不管是不是需要解码，都解码不影响结果'''
    def UnescapeURL(self,strurl):
        if not isinstance(strurl, str):
            raise TypeError
        return parse.unquote(strurl)
    
 
 

# ✅ ✅ ✅ ✅ 数据库相关 ✅ ✅ ✅ ✅ ✅ 

#固定数据库基类---->占位便于扩充
class BaseDBClass:
    def __init__(self, *args, **kwargs):
        pass
    def help(self):
        raise NotImplementedError("基类扩展插口---大概率不需要这个")
    
#"""Mysql"""
class DataBaseMysql(BaseDBClass):
    def __init__(self, conn_params):
        self.pool = PooledDB(pymysql,maxconnections = 50,mincached=5,maxcached=20,  host=conn_params["host"], database=conn_params["dbname"], user=conn_params["user"],password=conn_params["password"],charset='utf8mb4')
        self.db = conn_params["dbname"]
    def help(self):
        return "这是Mysql数据库"

    #Create a database,If databases does not exist
    def createDB(self,dbname):
        try:
            # 每次从池子中取一条新链接 
            conn = self.pool.connection()
            cursor = conn.cursor()
            sql  = "create database If Not Exists {} default character set utf8 collate utf8_general_ci".format(dbname)
            cursor.execute(sql)
            conn.commit()
            # # 关闭游标和连接
            cursor.close()
            conn.close()
        except Exception as e:
            print("创建库报错：",e)
            return False
    #Create a table,If table does not exist
    def createTB(self,tablename,fieldDict):
        try:
            conn = self.pool.connection()
            cursor = conn.cursor()

            cursor.execute('use {}'.format(tablename.split('.')[0]))
            conn.commit()
            create_column = ''
            create_column = ''
            for column in fieldDict.items():
                create_column += (str(column[0]) +' '+str(column[1]) +' default NULL,')
            sql = 'create table If Not Exists {} ({}) default charset=utf8'.format(tablename,create_column[:-1])+';'
            cursor.execute(sql)
            conn.commit()

            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print("创建表报错：",e)
            return False
    
    #insert data
    def insertData(self,tablename,datalist):
        conn = self.pool.connection()
        cursor = conn.cursor()
        try:
            cursor.execute('use {}'.format(self.db))
            conn.commit()
            for data in datalist:
                columns = ''
                value = ''
                for column in [column for column in data.keys()]:
                    columns += (column+',')
                    value += ('\''+data[column]+'\''+',')
                sql = 'insert into {}({}) value({}) '.format(tablename,str(columns[:-1]),str(value[:-1]))+';'
                cursor.execute(sql)
                conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            # print("datalist-->",datalist)
            print('保存到表 %s 时,出现错误 %s', tablename,e)
            cursor.close()
            conn.close()
            return False
    
    #查询数据
    def selectData(self,tablename,columnList):
        conn = self.pool.connection()
        cursor = conn.cursor()
        try:
            cursor.execute('use {}'.format(self.db))
            conn.commit()
            data_columns = ''
            for column_n in columnList:
                data_columns += (column_n+',')
            data_columns = data_columns[:-1]
            sql = "select {} from {}".format(data_columns,tablename)+';'
            cursor.execute(sql)
            rows = cursor.fetchall()
            column_all = []
            for row in rows:
                column_all.append(['NULL' if r is None else r.strip() for r in row])
            cursor.close()
            conn.close()
            return column_all
        except Exception as e:
            print("查找表 %s 时,出现错误 %s",tablename,e)
            cursor.close()
            conn.close()
            return []
    def tableExists(self,table_name):
        conn = self.pool.connection()
        cursor = conn.cursor()
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cursor.fetchone()
        return result is not None
    
    #通用执行sql语句
    def exeSql(self,sql):
        try:
            conn = self.pool.connection()
            cursor = conn.cursor()
            if str(sql).strip().lower()[:6] == 'select':
                cursor.execute(sql)
                results = cursor.fetchall()
                cursor.close()
                conn.close()
                return results
            else:
                cursor.execute(sql)
                conn.commit()
                cursor.close()
                conn.close()
                return None
        except Exception as e:
            print("执行报错：",e)
            return False



#"""Doris"""
class DataBaseDoris(BaseDBClass):
    def __init__(self, conn_params):
        self.pool = PooledDB(pymysql,maxconnections = 10,mincached=5,maxcached=5,  host=conn_params["host"], port=conn_params["port"] ,database=conn_params["dbname"], user=conn_params["user"], password=conn_params["password"],charset='utf8mb4')
        self.db = conn_params["dbname"]
    def help(self):
        return "这是Doris数据库"

    #Create a database,If databases does not exist
    def createDB(self,dbname):
        try:
            # 每次从池子中取一条新链接 
            conn = self.pool.connection()
            cursor = conn.cursor()
            sql  = "create database If Not Exists {} ".format(dbname)
            cursor.execute(sql)
            conn.commit()
            # # 关闭游标和连接
            cursor.close()
            conn.close()
        except Exception as e:
            print("创建库报错：",e)
            return False
    #Create a table,If table does not exist
    def createTB(self,tablename,fieldDict):
        try:
            conn = self.pool.connection()
            cursor = conn.cursor()

            cursor.execute('use {}'.format(tablename.split('.')[0]))
            conn.commit()
            create_column = ''
            create_column = ''
            for column in fieldDict.items():
                create_column += (str(column[0]) +' '+str(column[1]) +' default NULL,')
            sql = 'create table If Not Exists {} ({}) UNIQUE KEY (`{}`)  DISTRIBUTED BY HASH({}) BUCKETS 1;'.format(tablename,create_column[:-1],column[0],column[0])+';'
            cursor.execute(sql)
            conn.commit()

            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print("创建表报错：",e)
            return False
    #insert测试插入
    def insertData2(self,sql,dataList):
        conn = self.pool.connection()
        cursor = conn.cursor()
        
        cursor.executemany(sql, dataList)
        conn.commit()
                

    #insert data
    def insertData(self,tablename,fieldDict):
        conn = self.pool.connection()
        cursor = conn.cursor()
        try:
            if len(fieldDict)==0:
                return 
            QueryFieldsList = fieldDict[0].keys()
            fileds = ",".join(QueryFieldsList)
            values = ",".join(["%s"]*len(QueryFieldsList))
            # 执行插入操作
            sql = "INSERT INTO {} ({}) VALUES ({})".format(str(tablename),str(fileds),str(values))
            
            
            dataList = []
            
            for dataitem in fieldDict:
                dataitemset = list()
                for Field in QueryFieldsList:
                    dataitemset.append(dataitem[Field])
                dataList.append(tuple(dataitemset))
            
            try:
                cursor.executemany(sql, dataList)
                conn.commit()
                
            except Exception as e:
                
                print("insertTable--> %s ,Error--> %s",tablename,e)
                print('-------------------------------------------------------')
                spiderLogWrite("insertTable--> %s ,Error--> %s",tablename,e)
                spiderLogWrite("sql--->",sql)
                spiderLogWrite("dataList--->",dataList)
                print('-------------------------------------------------------')
                return False
            return True
        except Exception as e:
            
            print("插入数据表 %s 时,出现错误 %s",tablename,e)
            spiderLogWrite("插入数据表 %s 时,出现错误 %s",tablename,e)
            
            return False
    
    #查询数据
    def selectData(self,tablename,columnList):
        conn = self.pool.connection()
        cursor = conn.cursor()
        try:
            cursor.execute('use {}'.format(self.db))
            conn.commit()
            data_columns = ''
            for column_n in columnList:
                data_columns += (column_n+',')
            data_columns = data_columns[:-1]
            sql = "select {} from {}".format(data_columns,tablename)+';'
            cursor.execute(sql)
            rows = cursor.fetchall()
            column_all = []
            for row in rows:
                column_all.append(['NULL' if r is None else r.strip() for r in row])
            cursor.close()
            conn.close()
            return column_all
        except Exception as e:
            print("查找表 %s 时,出现错误 %s",tablename,e)
            spiderLogWrite("查找表 %s 时,出现错误 %s",tablename,e)
            cursor.close()
            conn.close()
            return []
    
    #通用执行sql语句
    def exeSql(self,sql):
        try:
            conn = self.pool.connection()
            cursor = conn.cursor()
            if str(sql).strip().lower()[:6] == 'select':
                cursor.execute(sql)
                results = cursor.fetchall()
                cursor.close()
                conn.close()
                return results
            else:
                cursor.execute(sql)
                conn.commit()
                cursor.close()
                conn.close()
                return None
        except Exception as e:
            print("执行报错：",e)
            spiderLogWrite("执行报错：",e)
            return False
    #判断数据库中是否表存在
    def tableExists(self,table_name,copyTable=""):
        conn = self.pool.connection()
        cursor = conn.cursor()
        table_name_tmp = table_name.split(".")[-1].replace("[","").replace("]","")
        query = f"""
            SELECT COUNT(*) AS table_exists 
            FROM information_schema.tables 
            WHERE table_schema = '{self.db}' AND table_name = '{table_name_tmp}';
            """
        cursor.execute(query)
        result = cursor.fetchone()[0]
        if int(result) <= 0:
            CreateSql =  "CREATE TABLE {} LIKE {};".format(str(table_name),str(copyTable))
            cursor.execute(CreateSql)
            conn.commit()


#连接holo查询数据
class HologresClient(BaseDBClass):
    def __init__(self, conn_params):
        """
        初始化Hologres客户端
        @param access_key_id: 阿里云AccessKey ID
        @param access_key_secret: 阿里云AccessKey Secret
        @param endpoint: Hologres端点 (例如: 'hologram.cn-hangzhou.aliyuncs.com')
        @param instance_id: Hologres实例ID
        """
        self.access_key_id = conn_params["access_key_id"]
        self.access_key_secret = conn_params["access_key_secret"]
        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret
        )
        config.endpoint = conn_params["endpoint"]
        self.instance_id = conn_params["instance_id"]
        self.database = conn_params["database"]
        self.client = Hologram20220601Client(config)
    def help(self):
        return "这是Hologres数据库"
    def get_instance_info(self):
        try:
            response = self.client.get_instance(self.instance_id)
            return response
        except Exception as error:
            print(f"获取实例信息出错: {error}")
            return None

    def exeSql(self, sql: str):
        """
        执行SQL查询
        @param sql: SQL查询语句
        @return: 查询结果
        """
        try:
            # 获取实例信息以获取连接信息
            instance_info = self.get_instance_info(self.instance_id)
            if not instance_info or not instance_info.body or not instance_info.body.instance:
                print("无法获取实例信息")
                return None

            # 获取连接端点
            endpoint = None
            for ep in instance_info.body.instance.endpoints:
                if ep.type == "Internet" and ep.enabled:  # 使用公网地址
                    endpoint = ep.endpoint
                    break

            if not endpoint:
                print("未找到可用的连接端点")
                return None
            # print(f"使用连接端点: {endpoint}")
            # 连接数据库
            conn = psycopg2.connect(
                host=endpoint.split(':')[0],
                port=endpoint.split(':')[1],
                database=self.database,
                user=self.access_key_id,
                password=self.access_key_secret
            )

            # 执行查询
            with conn.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
                
                # 获取列名
                column_names = [desc[0] for desc in cursor.description]
                
                # 将结果转换为字典列表
                result_list = []
                for row in results:
                    result_dict = dict(zip(column_names, row))
                    result_list.append(result_dict)

            conn.close()
            return result_list

        except Exception as error:
            print(f"执行查询出错: {error}")
            return None


    def insertData(self, table_name: str, data_list: List[dict]):
        """
        批量插入数据到指定表
        @param instance_id: Hologres实例ID
        @param database: 数据库名称
        @param table_name: 表名
        @param data_list: 数据列表，格式为[{"字段1":"值1"，"字段2":"值2",...},{"字段1":"值1"，"字段2":"值2",...},...]
        @return: 是否成功
        """
        try:
            if not data_list:
                print("数据列表为空，无需插入")
                return True
                
            # 获取实例信息以获取连接信息
            instance_info = self.get_instance_info(self.instance_id)
            if not instance_info or not instance_info.body or not instance_info.body.instance:
                print("无法获取实例信息")
                return False

            # 获取连接端点
            endpoint = None
            for ep in instance_info.body.instance.endpoints:
                if ep.type == "Internet" and ep.enabled:  # 使用公网地址
                    endpoint = ep.endpoint
                    break

            if not endpoint:
                print("未找到可用的连接端点")
                return False

            # 连接数据库
            conn = psycopg2.connect(
                host=endpoint.split(':')[0],
                port=endpoint.split(':')[1],
                database=self.database,
                user=self.access_key_id,
                password=self.access_key_secret
            )
            
            # 获取第一条数据的字段名作为列名
            columns = list(data_list[0].keys())
            
            # 构建插入SQL
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join([f'"{col}"' for col in columns])
            insert_query = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})'
            
            # 准备批量插入的数据
            values = []
            for data in data_list:
                row_values = [data.get(col, None) for col in columns]
                values.append(row_values)
            
            # 执行批量插入
            with conn.cursor() as cursor:
                cursor.executemany(insert_query, values)
            
            # 提交事务
            conn.commit()
            conn.close()
            
            print(f"成功插入 {len(data_list)} 条数据到表 {table_name}")
            return True
            
        except Exception as error:
            print(f"批量插入数据出错: {error}")
            return False


#入口类
class dataBase:
    def help():
        helpContent = """
        连接调用不同数据库,统一传入参数为字典conn_params,参考格式如下写法：
        ----------------------------------------------------------------------------------------------
        conn_params = {"DBType":"数据库类型","host": "主机地址","dbname": "链接数据库","user": "用户名","password": "用户密码"}
        SqlConnetDemo = dataBase.connect(conn_params) 
        
        如果是Hologres,则conn_params中需要存在"endpoint", "access_key_id", "access_key_secret","instance_id","database" 这些
        conn_params = {"DBType":"Hologres","endpoint": "endpoint地址","access_key_id": "access_key_id","access_key_secret": "access_key_secret","instance_id": "instance_id","database": "数据库名称"}
        ----------------------------------------------------------------------------------------------
        所有数据库操作方法一致,参考格式如下写法：
        创建库: SqlConnetDemo.createDB('需要创建的库名')------>ps:SqlConnetDemo.createDB('demoDB')
        创建表: SqlConnetDemo.createTB('表名',字段字典)------->ps:SqlConnetDemo.createTB('demoTB',{'id':'int','name':'varchar(20)'})
        备份表: SqlConnetDemo.backupsData('需要备份的表名')---->ps:SqlConnetDemo.insertData('demoTB')
        查数据: SqlConnetDemo.selectData('表名',需要查询的字段列表)---->ps:SqlConnetDemo.selectData("demoTB",['id','name'])
        插数据: SqlConnetDemo.insertData('表名',需要插入的数据列表)---->ps:SqlConnetDemo.insertData('demoTB',[{'id':'1','name':'大桥未久'},{'id':'2','name':'苍井空'}])
        寻常SQL语句执行: 'SqlConnetDemo.exeSql(需要执行的sql语句)'-----ps:SqlConnetDemo.exeSql(需要执行的sql语句) 如果为查询语句则有返回值，否则无返回值
        ----------------------------------------------------------------------------------------------
        """
        print(helpContent)
    @staticmethod
    def connect(conn_params={}):
        if conn_params["DBType"] == "Mysql":
            return DataBaseMysql(conn_params)
        elif conn_params["DBType"] == "Hologres":
            required_params = ["endpoint", "access_key_id", "access_key_secret","instance_id","database"]
            missing_params = [param for param in required_params if param not in conn_params]
            if missing_params:
                raise ValueError(f"Hologres连接失败: 缺少必要参数 {', '.join(missing_params)}")
            return HologresClient(conn_params)
        elif conn_params["DBType"]  == "Doris":
            return DataBaseDoris(conn_params)
        else:
            raise ValueError(f"无效数据库类型, 当前仅支持DBType类型:'Mysql','Doris', 'Sqlserver', 'Postgresql','Hologres';详细连接方法参考执行 dataBase.help()")

#批量插入中间件,起单线程额外处理数据写入（为保证整体依赖减少，不想链路中再加kafka，加监控脚本入口）
class databaseMiddleInsert(threading.Thread):
    def __init__(self,taskQ,saveDataQ,SqlConnetDemo,getNum = 500,retrievalRefreshTime=30,title=""):
        super().__init__()
        self.taskQ = taskQ
        self.saveDataQ = saveDataQ
        self.retrievalRefreshTime = retrievalRefreshTime
        self.getNum = getNum
        self.SqlConnetDemo = SqlConnetDemo
        self.title = title
    def run(self):
        while True:
            while not self.saveDataQ.empty(): 
                print(self.title,"--->saveDataQ.qsize()--->",self.saveDataQ.qsize())  
                print(self.title,"--->taskQ.qsize()--->",self.taskQ.qsize())      
                init_Data_dict = dict()
                if int(self.saveDataQ.qsize())<=self.getNum:
                    
                    loopNum = int(self.saveDataQ.qsize())
                else:
                    loopNum = self.getNum
                for i in range(loopNum):
                    dataTmp = self.saveDataQ.get()
                    tableName = dataTmp["tableName"]
                    #如果超过一个表,则重新创建一个字典
                    if tableName not in init_Data_dict.keys():
                        init_Data_dict[tableName] = list()
                    del dataTmp["tableName"]
                    init_Data_dict[tableName].append(dataTmp)
                for tbName,insertDataList in init_Data_dict.items():
                    try:
                        self.SqlConnetDemo.insertData(tbName,insertDataList)
                    except:
                        print("insertDataList-->",insertDataList)
            if self.taskQ.empty():
                break
            time.sleep(self.retrievalRefreshTime)

    

# ✅ ✅ ✅ ✅ kafka相关操作 ✅ ✅ ✅ ✅ ✅ 
#kafka相关操作
class KafkaHelper:
    def __init__(self):
        try:
            # Kafka broker 列表已迁移到 Apollo（config 门面），无需 eval
            kafka_server = config.kafka_servers()
            self.producer = KafkaProducer(
                bootstrap_servers=kafka_server,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        except:
            print("kafka连接失败,Apollo 中 kafka.servers 为空或配置错误")
            self.producer = None
        print(self.producer)
    #数据推到kafka    
    def sendToKafka(self,data,topic_name=''):
        self.producer.send(topic_name, value=data)
        self.producer.flush() # 确保所有消息都被发送到Kafka服务器,flush()会阻塞直到所有未完成的消息请求都发送完成


# ✅ ✅ ✅ ✅ IP代理相关 ✅ ✅ ✅ ✅ ✅ 
#IP代理类
proxyList = []
class proxyIpThread(threading.Thread):
    def __init__(self,q,ipRefreshTime=30,mode=2,ipValue=""):
        super().__init__()
        self.q = q
        self.ipRefreshTime = ipRefreshTime
        self.mode = mode
        self.ipValue = ipValue
    #默认IP列表返回,便于调整一次返回多个Ip使用
    def getProxyIp(self):
        dataIPList= []
        # 公司国内代理
        if self.mode == 1:
            # 国内动态代理 URL 已废弃（新 Apollo 无对应 key），离线脚本代理功能不再使用
            pass
                
        # 公司海外静态代理
        elif self.mode == 2:
            # 海外静态代理池已迁移到 Apollo（config 门面）
            dataIPList = config.abroad_proxy_pool()

        # 公司动态代理
        elif self.mode == 3:
            # 海外动态代理 URL 已废弃（新 Apollo 无对应 key），离线脚本代理功能不再使用
            pass
        #预留代理模式
        else:
            print("proxy is error")
        return dataIPList

    def run(self):
        while not self.q.empty():
            # 如果为空则使用来自于阿波罗配置的公司代理
            if self.ipValue == "":
                dataIPList = self.getProxyIp()
                print("proxy number:",str(len(dataIPList)))
                global proxyList
                proxyList = dataIPList
                time.sleep(int(self.ipRefreshTime))
                
            # 如果传入代理为非空则直接使用传入的代理
            else:
                # global proxyList
                proxyList = self.ipValue
     
        
     
# ✅ ✅ ✅ ✅ 进程启动与线程操作相关 ✅ ✅ ✅ ✅ ✅ 
# 进程启动脚本且实时打印
class ProcessManager():
    def __init__(self):
        pass

    def enqueue_output(self,process, output_type, stream, identifier, queue):
        """确保流关闭时线程退出"""
        try:
            for line in iter(stream.readline, ''):  # 自动处理流关闭
                queue.put((identifier, output_type, line.strip()))
        finally:
            stream.close()  # 确保资源释放

    def print_output(self,queue):
        """实时打印队列中的输出"""
        while True:
            try:
                # 非阻塞获取队列内容
                identifier, stream_type, line = queue.get_nowait()
                print(line)
            except Empty:
                break        
    def execute_script(self,script_path, identifier, env=None):
        
        """
        启动单个子进程并捕获输出
        :script_path : 要执行的脚本路径
        :identifier : 子进程标识符
        """
        # 构建子进程环境
        env = env if env else {**os.environ, 'PYTHONUNBUFFERED': '1'}
        # 启动子进程：
        # - stdout/stderr=subprocess.PIPE 启用管道
        # - bufsize=1 行缓冲模式
        # - universal_newlines=True 文本模式
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            env=env,
            universal_newlines=True,
            encoding='utf-8'  # 显式指定编码（可选）
        )

        # 创建线程捕获输出
        output_queue = Queue()
        Thread(target=self.enqueue_output, args=(proc, 'STDOUT', proc.stdout, identifier, output_queue)).start()
        Thread(target=self.enqueue_output, args=(proc, 'STDERR', proc.stderr, identifier, output_queue)).start()
        while True:
            if proc.poll() is  None:  # 子进程已经结束
                self.print_output(output_queue)
            else:
                break
            time.sleep(1)
        # return proc, output_queue
        return "taskOver"
       
#继承多线程类，重构run方法
class Mthread(Thread):
    def __init__(self, q,functionObj):
        self.q = q
        self.functionObj = functionObj
        super(Mthread, self).__init__()#全部继承
    def run(self):
        while not self.q.empty():
            arg = self.q.get()
            #登录账号更新token与deviceId
            try:
                self.functionObj(arg)
            except BaseException as e:
                print("get error:", e)
                print("error class:", type(e))
                traceback.print_exc()

# 启动任务tasks
def ProducerTask(port_info):

    # 初始化进程管理类
    PM = ProcessManager()
    # print("{}-->start".format(str(port_info)))
    # print("脚本路径--->",get_current_directory()+'/OfflineSpider/'+port_info["script"])
    # print("脚本参数--->",str(port_info["argsInfo"]))
    taskFlag = PM.execute_script(get_current_directory()+'/OfflineSpider/'+port_info["script"],str(port_info))
    print(port_info["script"],"--->",taskFlag)
    
     
 
# ✅ ✅ ✅ ✅ 采集相关操作 ✅ ✅ ✅ ✅ ✅ 
# 采集类
class Crawl():
    def __init__(self,procoder=""):
        self.crawlTarget = procoder     
    def help(self):
        helpContent = """
        关于类Crowl使用用法,Crowl基于requests库,包含get、post以及Download文件下载功能,参考格式如下写法：
        ----------------------------------------------------------------------------------------------
        请求源码crawl代码调用:
            html = Crawl().crawl(url,PostData,Method,Referer,User_Agent,Cookie,encoding,proxy,_gzip,_maxtimes,_timeout)
            或(根据实际情况自行填写)
            html = Crawl().crawl(url)
            关于入参说明：
                url:请求的目标url--->必填
                PostData:post请求的参数--->非必填
                Method:请求方式--->非必填,默认为get
                Referer:请求的referer--->非必填
                User_Agent:请求的User_Agent--->非必填,默认值为Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36
                Cookie:请求的cookie--->非必填
                encoding:请求返回的编码格式--->非必填,默认值为utf8
                proxy:是否使用代理--->非必填,默认值为False不使用代理
                _gzip:是否使用gzip解压--->非必填,默认值为True使用gzip解压
                _maxtimes:请求的最大尝试次数--->非必填,默认值为5次
                _timeout:请求的超时时间--->非必填,默认值为30秒
        下载模块download代码调用:
            Crawl().Download(url,filename)
            关于入参说明：
                url:下载的目标url--->必填
                filename:下载的保存文件名路径--->必填
        ----------------------------------------------------------------------------------------------
        """
        print(helpContent)
    @error_logging_decorator(True)
    def crawl(self,url,
              PostData = '',
              Method='GET',
              Cookie='',
              json = {},
              params={},
              encoding='utf8',
              _gzip=True,
              headers ={},
              _maxtimes=5,
              _timeout=15):
        if _gzip:
            headers['Accept-encoding'] = 'gzip'
        times = 0
        while times<_maxtimes:
            try:
                #当代理列表长度大于0，使用代理
                if len(proxyList)>0:
                    auth = ""
                    random.seed()
                    ip = random.choice(proxyList)
                    proxies = { "http":"http://"+ip,"https":"http://"+ip}
                    if str(proxyList[0])=="888":
                        proxies = {'http': 'http://0d54cf087c4c89ec.na.roxlabs.vip:4600'
                                # ,'https': 'http://0d54cf087c4c89ec.na.roxlabs.vip:4600'
                            }
                        # auth = HTTPProxyAuth('user-bin1tecmatl-region-us-sessid-usapNJTPBZ-sesstime-1-keep-true', 'dE7tL9')
                        auth = HTTPProxyAuth('user-bin1tecmatl-region-us', 'dE7tL9')
                        
                    print("使用了代理ip--->",ip)
                    if Method=="GET":
                        if params:
                            if auth:
                                url = url.replace("https:","http:")
                                # print("url--->",url)
                                data = requests.get(url,headers = headers,params=params,cookies=Cookie, proxies=proxies,timeout=_timeout,verify=False,auth=auth)
                            else:
                                data = requests.get(url,headers = headers,params=params,cookies=Cookie, proxies=proxies,timeout=_timeout,verify=False)
                        else:
                            if auth:
                                url = url.replace("https:","http:")
                                # print("url--->",url)
                                data = requests.get(url,headers = headers, cookies=Cookie,proxies=proxies,timeout=_timeout,verify=False,auth=auth)
                            else:
                                data = requests.get(url,headers = headers, cookies=Cookie,proxies=proxies,timeout=_timeout,verify=False)

                    else:
                        if json:
                            data = requests.post(url,json=json,headers=headers,cookies=Cookie,verify=False,timeout=_timeout,proxies=proxies)
                        else:
                            data = requests.post(url,data=PostData,headers=headers,cookies=Cookie,verify=False,timeout=_timeout,proxies=proxies)
                else:
                    print("没有使用了代理ip")
                    if Method=="GET":
                        if params:
                            data = requests.get(url,headers = headers,params=params,cookies=Cookie, timeout=_timeout,verify=False)
                        else:
                            data = requests.get(url,headers = headers,cookies=Cookie, timeout=_timeout,verify=False)
                    else:
                        if json:
                            data = requests.post(url,json=json,cookies=Cookie,headers=headers,verify=False,timeout=_timeout)
                        else:
                            data = requests.post(url,data=PostData,cookies=Cookie,headers=headers,verify=False,timeout=_timeout)
                data.encoding = encoding
                data = data.text

                if _gzip:
                    try:
                        html = gzip.decompress(data)
                    except Exception as e:
                        # spiderLogWrite('解压失败返回原始字符串 错误为:%s' % e)
                        html = data
                times = _maxtimes+1
                return {'url': url, 'html': html, 'crawltime': datetime.now()}
            except Exception as e:
                if str(e).find('连接') > 0:
                    times += 1
                else:
                    spiderLogWrite('抓取 %s 出现错误：%s' % (url, e))
            spiderLogWrite('抓取 {} 次数超过{}次,html返回None'.format(url,_maxtimes))
            return {'url': url, 'html': None, 'ctime': datetime.now()}
    #Download module
    @error_logging_decorator(True)
    def Download(self,url,filename):
        try:
            urllib.request.urlretrieve(url,'%s'%filename)
            return True
        except Exception as e:
            spiderLogWrite('下载 %s 出现错误：%s' % (url, e))
            return False

    @error_logging_decorator(True)
    def download_image_upload_ods(self,url, imgpath):
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(imgpath), exist_ok=True)
            
            # Download image using requests with or without proxy
            if len(proxyList) > 0:
                ip = random.choice(proxyList)
                # print("使用代理ip--->",ip)
                proxies = { "http":"http://"+ip,"https":"http://"+ip}
                response = requests.get(url, verify=False, timeout=30, proxies=proxies)
            else:
                response = requests.get(url, verify=False, timeout=30)
                
            response.raise_for_status()
            
            # Save image to file
            with open(imgpath, 'wb') as f:
                f.write(response.content)
            return True
            
        except Exception as e:
            print(f"Error downloading image from {url}: {str(e)}")
            return False

# ✅ ✅ ✅ ✅ 将字典列表写入 Excel 文件 ✅ ✅ ✅ ✅ ✅ 
# 将字典列表写入 Excel 文件
def save_to_excel(data_list, columns_order, save_path):
    """
    参数：
    data_list: list of dict - 要保存的数据列表
    columns_order: list - 列名顺序列表
    save_path: str - 保存路径（支持.xlsx结尾自动创建）
    
    示例：
    save_to_excel(comment_list, ['用户昵称', '评论内容', '用户IP地址'], 'D:/comments.xlsx')
    """
    # 自动创建目录
    dir_path = os.path.dirname(save_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    # 创建DataFrame并指定列顺序
    df = pd.DataFrame(data_list, columns=columns_order)
    
    # 写入Excel（无索引，自动创建文件）
    df.to_excel(save_path, index=False, engine='openpyxl')
    print(f"文件已保存至：{os.path.abspath(save_path)}")




# ✅ ✅ ✅ ✅ 请求配置相关 ✅ ✅ ✅ ✅ ✅ 

def get_requests_config():
    """动态获取最新的requests_config配置"""
    config_module = importlib.import_module('config')
    importlib.reload(config_module)
    return config_module.requests_config
           
# 配置整理
def generate_api_config(requests_config):
        api_config = {}
        # 遍历每个平台（如 diandian, sensorTower）
        for platform, platform_config in requests_config.items():
            if not isinstance(platform_config, dict):
                continue
                
            platform_entry = {}
            
            # 遍历平台下的每个接口配置（如 STDetail, STRank）
            for endpoint_name, endpoint_config in platform_config.items():
                # 只处理包含 doc 字段的配置
                if not isinstance(endpoint_config, dict) or 'doc' not in endpoint_config:
                    continue
                    
                doc = endpoint_config['doc']
                # 直接返回doc中的字段，而不是嵌套在另一层对象中
                platform_entry[endpoint_name] = {
                    "method": doc.get("method", "POST"),
                    "description": doc.get("description", ""),
                    "endpoint": doc.get("endpoint", ""),
                    "headers": doc.get("headers", {}),
                    "responseFieldDescription": doc.get("responseFieldDescription", {}),
                    "defaultParams": doc.get("defaultParams", {}),
                    "docsLinks": doc.get("docsLinks", [])
                }
            # 只保留有有效配置的平台
            if platform_entry:
                api_config[platform] = platform_entry
        return api_config       
    
    
    
# ✅ ✅ ✅ ✅ 自动函数注册器 ✅ ✅ ✅ ✅ ✅ 
    
# ✅ 自动函数注册器
function_registry = {}    

# ✅ 多轮对话上下文
chat_history = []
def register_function(func):
    sig = inspect.signature(func)
    parameters = {
        name: {
            "type": "integer" if param.annotation == int else "array" if param.annotation == list else "string",
            "description": "参数：" + name
        }
        for name, param in sig.parameters.items()
    }
    schema = {
        "name": func.__name__,
        "description": func.__doc__ or "无描述",
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": list(sig.parameters.keys())
        }
    }
    function_registry[func.__name__] = {
        "func": func,
        "schema": schema
    }
    return func      
        
# ✅ 处理用户消息并调用模型
async def chat_with_model(user_message):
    # 准备 payload，只发送当前用户消息，不包含历史记录
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": user_message+',如果有函数描述中有映射，需要转为映射值'}],
        "tools": [{
            "type": "function",
            "function": f["schema"]
        } for f in function_registry.values()],
        "tool_choice": "auto"
    }

    headers = {
        "Authorization": f"Bearer {MCP_config['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json"
    }

    try:
        print("payload--->",payload)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()  # This will raise an exception for 4XX/5XX responses
            response_data = response.json()
            print("chat_response_data--->",response_data)
            message = response_data["choices"][0]["message"]

            if message.get("tool_calls"):
                function_call = message["tool_calls"][0]["function"]
                function_name = function_call["name"]
                arguments = json.loads(function_call["arguments"])

                func = function_registry[function_name]["func"]
                print("arguments--->",arguments)
                result = func(**arguments)
                return result
            else:
                return message["content"]
    except httpx.ConnectError as e:
        return f"连接错误: 无法连接到API服务器。请检查网络连接和API端点是否正确。错误详情: {str(e)}"
    except httpx.HTTPStatusError as e:
        return f"HTTP错误: 服务器返回了错误状态码 {e.response.status_code}。错误详情: {str(e)}"
    except Exception as e:
        return f"发生错误: {str(e)}"    
    
    
# ✅ ✅ ✅ ✅ 请求中间操作函数 ✅ ✅ ✅ ✅ ✅ 
# 传入请求体，提取公共部分为单独函数
def check_taskItem(taskParams,requests_config):
    # 如果body中有打开网址与检测地址,则默认使用同步模式，无需额外操作-解析-保存动作，直接返回数据
    if taskParams["body"].get("mateUrl"):
        initRequestsData = {
                "mateUrl":taskParams["body"].get("mateUrl"),
                "listenUrl":taskParams["body"].get("listenUrl",""), # 监听的url，默认为空的情况下返回html页面数据
                "addOPExec":"", #页面额外操作,默认为空，为空的时候不做任何额外操作
                "parseFunc":"", #数据解析函数，默认为空，为空表示不需要额外解析
                "saveFunc":"" 
            }
        return initRequestsData
    else:
        initRequestsData = requests_config.get(taskParams["PlatFrom"]).get(taskParams["apiTitle"])
        return initRequestsData 









