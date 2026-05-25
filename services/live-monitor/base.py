import requests
from DrissionPage import Chromium,ChromiumOptions,SessionPage
import os
import random
import json
import time
from pathlib import Path
from io import BytesIO
from base64 import b64decode
from DrissionPage.common import Actions
from kafka import KafkaProducer
import threading
import psutil

# 多线程控制
class MyThread(threading.Thread):
    def __init__(self, target, args=()):
        super().__init__()
        self.target = target
        self.args = args
        self.result = None  # 存储结果的属性
    def run(self):
        self.result = self.target(*self.args)  # 执行目标函数并保存结果

# AdsPowerHelper类--相关操作
class AdsPowerHelper:
    def __init__(self,adsPort=50325,user_id_list = []):
        self.adsPort = adsPort
        self.user_id_list = user_id_list
    # 检测浏览器状态
    def active_browser(self,user_id='ksohxk8'):
        # 定义URL
        url = "http://localhost:"+str(self.adsPort)+"/api/v1/browser/active"
        # 发送GET请求
        response = requests.get(url, params={'user_id': user_id})
        time.sleep(1)
        responseJson = response.json()
        # print("responseJson-->>>",responseJson)
        # {'code': 0, 'msg': 'success', 'data': {'status': 'Active', 'ws': {'puppeteer': 'ws://127.0.0.1:7786/devtools/browser/98b1536a-0683-42aa-afe8-a4a1eb97bdb2', 'selenium': '127.0.0.1:7786'}, 'debug_port': '7786', 'webdriver': 'C:\\Users\\spider.wei\\AppData\\Roaming\\adspower_global\\cwd_global\\chrome_131\\chromedriver.exe'}}
        if responseJson["data"]["status"]=="Active":
            return True,responseJson 
        else:
            return False,responseJson
    # 打开浏览器
    def start_browser(self,user_id='ksohxk8'):
        # 定义URL
        url = "http://localhost:"+str(self.adsPort)+"/api/v1/browser/start"
        # 发送GET请求
        response = requests.get(url, params={'user_id': user_id})
        return response.json()

    # 关闭浏览器
    def stop_browser(self,user_id='ksohxk8'):
        # 定义URL
        url = "http://localhost:"+str(self.adsPort)+"/api/v1/browser/stop"
        # 发送GET请求
        response = requests.get(url, params={'user_id': user_id})
        st = response.json()
        if st["code"]==0:
            print("成功关闭浏览器")
        return st    
        
    # 启动所有爬虫
    def start_browser_all(self):
        returnData = list()
        newData = list()
        for user_id in self.user_id_list:
            flag,stData = self.active_browser(user_id)
            # 如果浏览器没有启动，则启动浏览器
            if not flag:
                stData = self.start_browser(user_id)
                tmpNew = {
                "selenium":stData["data"]["ws"]["selenium"],
                "port":stData["data"]["debug_port"],
                "user_id":user_id
                }
                newData.append(tmpNew)
                
            tmp = {
                "selenium":stData["data"]["ws"]["selenium"],
                "port":stData["data"]["debug_port"],
                "user_id":user_id
            }
            returnData.append(tmp)
        return returnData,newData

    # 承接所有启动的浏览器，并返回操作对象
    def init_browser_all_obj(self,isCheck=False):
        returnData,newData = self.start_browser_all()
        time.sleep(2)
        browserObjs = []
        
        # print("returnData,newData---->",returnData,newData)
        # 如果是哨兵检测,只需要返回新的浏览器对象
            # 如果不是新增的直接赋值
            # 如果是新增的需要额外创建
        if isCheck:
            
            for i in returnData:
                browserObj = dict()
                port = i["port"]
                browserinit = Chromium(int(port))
                browserObj["tabs"] = browserinit.get_tabs()
                browserObj[str(port)] = browserinit
                browserObjs.append(browserObj)   
        else:    
            for i in returnData:
                browserObj = dict()
                port = i["port"]
                browserinit = Chromium(int(port))
                # if i["port"] in [p["port"] for p in newData]:
                #先获取旧的所有tab
                tabs_old = browserinit.get_tabs()
                #创建新的tab
                browserObj["tabs"] = [browserinit.new_tab()]
                # 再关闭初始化或者旧的tab
                browserinit.close_tabs(tabs_or_ids=tabs_old) 
                # 浏览器对象添加到返回对象中
                browserObj[str(port)] = browserinit
                browserObjs.append(browserObj)

        return browserObjs
     
# ChromiumHelper类--相关操作
class ChromiumHelper:
    def __init__(self):
        pass
    # 不同进程浏览器，启动多个标签页,并返回标签页对象
    def start_init_tab(self,browserObj,tabNum=1):
        '''
        browserObj:浏览器对象{"prod":浏览器对象}
        tabNum:需要打开的标签页数
        '''
        browser = [v for v in browserObj.values()][0]
        tabs_old = browser.get_tabs()
        browserObj["tabs"] = []
        for _ in range(tabNum):        
            newtabTmpObj = browser.new_tab()
            browserObj["tabs"].append(newtabTmpObj)
        browser.close_tabs(tabs_or_ids=tabs_old)   
        return browserObj
    # 启动多个浏览器，如果该端口浏览器打开则接手，没有打开该端口浏览器则创建启动 
    def init_browser_all_obj(self,initNum=1,tabNum=1,isheadless=False,proxyItem = [],timeOuts=15,isincognito=False,extensionPath="",downloadPath="download"):
        '''
        initNum: 启动浏览器数量,默认为3个浏览器 
        isheadless: 是否无头模式，默认为否 
        isincognito: 是否匿名无痕模式，默认为否 
        extensionPath: 加载插件路径，默认为空 
        downloadPath: 文件下载保存地址,默认为download文件夹 
        proxyItem: 代理设置，默认为空 
        timeOuts: 默认为15秒
        '''
        browserObjList = []
        portlist = [i for i in range(9333, 9383)]
        for n in range(initNum):  
            browserObj = {}      
            # 为每个浏览器设置单独的用户文件夹，防止出现冲突
            user_data_path = os.path.dirname(os.path.abspath(__file__)).replace("\\",'/')+'/user/'+str(portlist[n])
            coTmp = ChromiumOptions().set_paths(local_port=portlist[n], user_data_path=user_data_path)
            # 默认打开元素等待/页面加载/JavaScript运行超时时间阈值,默认15秒
            coTmp.set_timeouts(base=timeOuts,page_load=timeOuts,script=timeOuts)
            # 链接超时重试次数，默认尝试3次，每次重试间隔3秒
            coTmp.set_retry(times=3,interval=3)
            # 忽略证书错误
            coTmp.ignore_certificate_errors()
            # 禁用沙盒模式
            coTmp.set_argument('--no-sandbox') 
            # 设置文件下载保存地址,默认为同级目录下的download文件夹
            if not os.path.exists(user_data_path+'/'+downloadPath):
                os.makedirs(user_data_path+'/'+downloadPath)
            coTmp.set_download_path(path=user_data_path+'/'+downloadPath)
            # 浏览器设置设置代理,默认无代理,接收str|list类型，str格式为ip:port，list格式为[ip:port,ip:port]
            # 如果代理为字符串直接设置，如果为list则随机选择一个代理
            if len(proxyItem)>0:
                if isinstance(proxyItem, str):
                    coTmp.set_proxy(proxyItem)
                elif isinstance(proxyItem, list):
                    if len(proxyItem)>initNum:
                        coTmp.set_proxy(proxyItem[n])
                    else:
                        coTmp.set_proxy(random.choice(proxyItem))        
            # 匿名无痕模式启动浏览器
            if isincognito:
                coTmp.incognito()
            # 无头模式
            if isheadless:
                coTmp.headless()
            # 加载插件
            if extensionPath: 
                print("加载插件extensionPath-->",extensionPath)   
                coTmp.add_extension(path=extensionPath)
            browserObj[str(portlist[n])] = Chromium(addr_or_opts=coTmp)
            browserObj_addTabs = self.start_init_tab(browserObj,tabNum=tabNum)
            browserObjList.append(browserObj_addTabs)
        return browserObjList
  
# BrowserManager类--入口类
class MainHelper:
    def __init__(self,brower_config,useType="Chromium"):
        self.useType = useType
        self.brower_config = brower_config

    def init_browser_all_obj(self):
        if self.useType == "AdsPower":
            helper = AdsPowerHelper(adsPort=self.brower_config["AdsPower"]["adsPort"], user_id_list=self.brower_config["AdsPower"]["user_id_list"])
            return helper.init_browser_all_obj()
        elif self.useType == "Chromium":
            helper = ChromiumHelper()
            brower_config_Chromium = self.brower_config["Chromium"]
            return helper.init_browser_all_obj(initNum=brower_config_Chromium["initNum"], 
                                               tabNum=brower_config_Chromium["tabNum"], 
                                               isheadless=brower_config_Chromium["isheadless"], 
                                               proxyItem=brower_config_Chromium["proxyItem"], 
                                               timeOuts=brower_config_Chromium["timeOuts"], 
                                               isincognito=brower_config_Chromium["isincognito"], 
                                               extensionPath=brower_config_Chromium["extensionPath"], 
                                               downloadPath=brower_config_Chromium["downloadPath"])
        else:
            raise ValueError("Invalid useType. Supported types: 'AdsPower', 'Chromium'")
         
# 浏览器所有动态操作类--相关操作
class OperateHelper:
    def __init__(self,brower_config,useType):
        self.brower_config = brower_config
        self.useType = useType
    
    #切换到指定标签页
    def change_tabs(self,browserObj,tabid):
        browserObj.activate_tab(tabid)

    #关闭指定tab页面
    def close_tabs_id(self,browserObj,tabid):
        # browserObj.new_tab()
        browserObj.close_tabs(tabid)

    # 打开网页监听指定网址，返回对应数据包:请求网址与监控网络包
    def browser_request(self,tabItem,mateUrl,listenUrl="",isInitTab=True):
        '''
        tabItem:标签页对象
        mateUrl:需要打开的网址
        listenUrl:监听网址,默认为空,为空则监听mateUrl
        isInitTab:初始化标签页,默认为是,为否则不初始化标签页
        '''
        if len(listenUrl)==0:
            tabItem.get(mateUrl, retry=1, interval=10, timeout=30)
            
        else:
            print("开始监听。。。。")
            tabItem.listen.start(targets=listenUrl,is_regex=True)
            tabItem.get(mateUrl, retry=1, interval=10, timeout=30)
        return tabItem 
    # 获取网页源代码
    def get_source_html(self,args):
        # print("args-------->",args)
        tabItem = args[0]
        # 判断是否为持续网络监控
        if args[1]>0:
            
            try:
                resList = []
                for res in tabItem.listen.steps():
                    # print("res--->",res.response.body)
                    resList.append(res.response.body)
                    
                # res = tabItem.listen.wait()
                # resList.append(res.response.body)
                return resList
            except:
                return tabItem.html
        else:
            return tabItem.html
    #点击指定text的按钮或文字
    def clickText(self,tabItem,Text="导出"):
        ele = tabItem.ele('text={}'.format(Text)) 
        ele.click()

    #获取指定className的Value值或txt值
    def getValues(self,tabItem,className="",isValue=True):
        ele = tabItem.ele('@class={}'.format(className)) 
        if isValue:
            return ele.value
        else:
            return ele.text

    # 获取指定tabItem的cookies
    def getCookies(self,tabItem):
        cookies = tabItem.cookies().as_dict()
        return cookies
    
    # 滚轮向下滚动拖动
    def page_scoll_to_bottom(self,tabItem,numberPX = 10000):
        ac = Actions(tabItem)
        if numberPX<1000:
            ac.scroll(delta_y=numberPX)
        else:
            number = int(numberPX/1000)
            for i in range(number):
                print("下拉",str(i))
                ac.scroll(delta_y=1000)
                time.sleep(1)
            ac.scroll(delta_y=int(numberPX%1000))
        return True
        
    # 保存canvas 渲染生成的图片       
    def save_multiple_canvas(self,tabItem, wrapper_selector_List: list, save_dir: str):
        """
        批量保存同一父容器下的多个canvas元素
        :param tabItem: MixTab标签页对象
        :param wrapper_selector_List: 包含canvas的父元素选择器(例如:['.canvas-wrapper'])
        :param save_dir: 图片保存目录
        :return: 成功保存的数量
        """
        # 创建保存目录
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        success_count_list = []
        for wrapper_selector in wrapper_selector_List:
            # 获取所有包含canvas的父容器
            wrappers = tabItem.eles(wrapper_selector)
            if not wrappers:
                print(f"未找到父元素：{wrapper_selector}")
                continue
                # return 0
            for index, wrapper in enumerate(wrappers, 1):
                try:
                    #获取父容器ttitle
                    title = wrapper.text.replace('\n', ' ').strip()
                    pngName = title.replace(' ', '_')
                    # 在父容器内查找canvas元素
                    canvas = wrapper.ele('tag:canvas', timeout=2)
                    if not canvas:
                        print(f"第 {index} 个容器中未找到canvas")
                        continue
                    # 获取canvas内容
                    js = """
                    const canvas = arguments[0];
                    return canvas.toDataURL('image/png');
                    """
                    img_data = tabItem.run_js(js, canvas)
                    # 处理base64数据
                    if not img_data.startswith('data:image/png;base64,'):
                        print(f"第 {index} 个canvas数据格式异常")
                        continue
                    # 生成唯一文件名
                    file_path = save_dir+ '/{}.png'.format(pngName)
                    # 保存文件
                    img_bytes = b64decode(img_data.split(',')[1])
                    with open(file_path, 'wb') as f:
                        f.write(img_bytes)  
                    # print(f"成功保存：{file_path}")
                    success_count_list.append({"title":title,"imgPath":file_path})
                except Exception as e:
                    print(f"第 {index} 个canvas保存失败：{str(e)}")
        return success_count_list
    


# kafka相关操作/推送到kafka
class KafkaHelper:
    def __init__(self):
        configurations = fetch_apollo_config()
        kafka_server = list(eval(configurations["kafkaAddress"]))
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_server,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    #数据推到kafka    
    def sendToKafka(self,data,topic_name=''):
        self.producer.send(topic_name, value=data)
        self.producer.flush()


#apollo获取配置
def fetch_apollo_config():
    istest = 0
    APOLLO_URL = str(os.environ.get('APOLLO_URL',None)).strip()
    APOLLOID = str(os.environ.get('APOLLOID',None)).strip()
    print(APOLLO_URL,APOLLOID)
    APOLLOID = None
    APOLLO_URL = None
    #本地直接测试
    if APOLLO_URL is None and APOLLOID is None:
        APOLLO_URL = 'http://dev-apollo.tec-develop.com'
        APOLLOID = 'app-spider'
        istest = 1
    #真测试环境    
    if APOLLO_URL=="http://dev-apollo.tec-develop.com":
        istest = 1
        
    if istest == 1:
        url = "{}/configs/{}/DEV/app-spider".format(str(APOLLO_URL),str(APOLLOID))
    else:
        url = "{}/configs/{}/PRO-HWSG/app-spider".format(str(APOLLO_URL),str(APOLLOID))
        
    config_data = {}
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查响应是否成功
        config_data = response.json()
    except Exception as err:
        print(f"An error occurred: {err}")
    configurations = config_data["configurations"]
    return  configurations


# 查找已经打开的调试端口
def find_debug_port():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if 'chrome' in proc.info['name'].lower():
            cmdline = proc.info['cmdline']
            for arg in cmdline:
                if '--remote-debugging-port' in arg:
                    return int(arg.split('=')[1])
    return None


