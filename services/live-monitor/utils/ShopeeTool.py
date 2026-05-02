import time

import requests
import re
import random
from utils.wrapper import Wrapper

    
class ShopeeTool:
    def __init__(self, ipList=[]):
        """
        Shopee工具类
        
        Args:
            ipList: IP代理列表
            tabItemQ: 标签页队列
        """
        self.ipList = ipList
        self.ua = ['Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.4212.1239 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.83 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.53 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.1116.1701 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.3478.1899 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.7838.1157 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.9263.1769 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.53 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.3438.1313 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/197.0.424131953 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.8555.1919 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.4694.1946 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.6505.1614 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.9846.1973 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/295.0.590048842 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2597.1073 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.6448.1339 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.7513.1954 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/342.0.693598186 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.7 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/121.0.6167.138 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/134.0.6998.99 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/123.0.6312.52 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.8.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.3814.1083 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.8 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/359.2.735510536 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/137.0  Mobile/15E148 Safari/605.1.15', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0.6778.134 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/134.0.6998.33 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/133.0.6943.120 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.7355.1228 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/362.0.741018905 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.83 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1 Ddg/18.3', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.83 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.7457.1189 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3402.1865 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/132.0.6834.78 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.83 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.6347.1389 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.8897.1426 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/358.1.731895952 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.6084.1869 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/363.0.743255906 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.83 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.7271.1311 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/133.0.6943.33 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.9962.1259 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1 Ddg/18.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.53 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.53 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.6110.1156 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5.2 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/362.0.741018905 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.3457.1289 Mobile Safari/537.36', 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/135.0.7049.53 Mobile/15E148 Safari/604.1']


    # 获取Shopee直播URL
    def get_shopee_live_url(self,url, proxy):
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'referer': 'https://live.shopee.sg/share?from=live&session=802458&share_user_id=',
            'user-agent': 'ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))',
        }


        if len(self.ipList)>0 and proxy:
            ip = random.choice(self.ipList)
            proxies = { "http":"http://"+ip,"https":"http://"+ip}
            response = requests.get(url, headers=headers, proxies=proxies,allow_redirects=False, timeout=3)
        else:
            response = requests.get(url, headers=headers, allow_redirects=False, timeout=3)
            
        # response = requests.get(url, headers=headers, allow_redirects=False)
        # print(f"Response Content: {response.text}")
        # Extract href value from the response
        href_match = re.search(r'href="([^"]*)"', response.text)
        if href_match:
            href_url = href_match.group(1)
            # Decode HTML entities
            href_url = href_url.replace('&amp;', '&')
            # Extract session ID from the href URL
            session_match = re.search(r'session=(\d+)', href_url)
            if session_match:
                session_id = session_match.group(1)
                
                # Extract host from href URL
                host_match = re.search(r'https://([^/]+)', href_url)
                if host_match:
                    host = host_match.group(1)
                    
                    # Construct the API URL
                    api_url = f"https://{host}/api/v1/session/{session_id}"
                    return api_url
        
        print("没有正常解析到虾皮直播会话链接")
        return None
    def _make_request(self, url, headers, proxy):
        """通用请求方法，支持代理"""
        headers["user-agent"] =  random.choice(self.ua)
        if len(self.ipList)>0 and proxy:
            ip = random.choice(self.ipList)
            proxies = {"http": "http://" + ip, "https": "http://" + ip}

            response = requests.get(url, headers=headers, proxies=proxies, timeout=3)
            # response = curl_cffi.get(url, headers=headers, proxies=proxies, impersonate="chrome")
            # response = self.client.get(url, headers=headers, proxy=proxies)

        else:
            response = requests.get(url, headers=headers, timeout=3)
            # response = curl_cffi.get(url, headers=headers, impersonate="chrome")
            # response = self.client.get(url, headers=headers)

        if response.status_code != 200:
            raise ValueError(f"请求失败，状态码: {response.status_code}")
        return response
    
    @Wrapper.retry(retries=10, delay=1)
    def _get_session_data(self, session_url, headers, proxy):
        """获取直播间session数据"""
        response = self._make_request(session_url, headers, proxy)
        data = response.json().get('data')
        if not data:
            raise ValueError("获取session数据失败")
        return data
    
    @Wrapper.retry(retries=3, delay=1)
    def _get_ongoing_live_session_id(self, host, uid, headers, proxy):
        """获取正在进行的直播间session_id"""
        ongoing_url = f"https://{host}/api/v1/shop_page/live/ongoing?uid={uid}"

        response = self._make_request(ongoing_url, headers, proxy)
        ongoing_data = response.json()

        # 获取第一个replay的session_id
        if ongoing_data.get('err_code') == 0:
            ongoing_live = ongoing_data.get('data', {}).get('ongoing_live', {})
            return ongoing_live.get('session_id') if ongoing_live else None
        return None
    
    def _format_live_data(self, data):
        """格式化直播数据"""
        play_url = data.get('session', {}).get('play_url') if data else None
        if play_url:
            data["play_urls"] = [play_url]
            data["flv_url"] = play_url
        
        filePath = data.get('session', {}).get('username', '').replace(".", "_")
        data["filePath"] = filePath
        data["startTime"] = data.get('session', {}).get('start_time')
        return data
    
    @Wrapper.retry_until_done(retries=3, delay=.1, desc="获取Shopee直播信息")
    def get_shopee_live_info(self, url, proxy=True):
        """传入直播间地址，解析获取真实直播流地址信息"""
        try:
            # 1. 获取初始session_url
            session_url = self.get_shopee_live_url(url, proxy)
            if not session_url:
                return None
            # 2. 准备请求头
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            }
            
            # 3. 获取初始session数据
            data = self._get_session_data(session_url, headers, proxy)
            
            # # 4. 获取uid并查询最新的直播间
            uid = data.get('session', {}).get('uid')
            if uid:
                # 从session_url中提取host
                host_match = re.search(r'https://([^/]+)', session_url)
                if host_match:
                    host = host_match.group(1)

                    # 获取最新的session_id
                    latest_session_id = self._get_ongoing_live_session_id(host, uid, headers, proxy)
                    # 如果有最新的session_id，则获取最新的直播间数据
                    if latest_session_id:
                        latest_session_url = f"https://{host}/api/v1/session/{latest_session_id}"
                        data = self._get_session_data(latest_session_url, headers, proxy)
            
            # 5. 格式化数据并返回
            return self._format_live_data(data)
            
        except Exception as e:
            print(f"获取直播信息失败: {url}, 错误: {str(e)}")
            return None



if __name__ == '__main__':
    import queue
    tabItemQ = queue.Queue()
    shopeeTool = ShopeeTool(['1663104-6b176fb7:19545d29-BA_RepublikaSrpska_city_Bijeljina@gate-hk.kkoip.com:17723','1663104-6b176fb7:19545d29-BA_RepublikaSrpska_city_Doboj@gate-hk.kkoip.com:17723'], tabItemQ)
    #在播短链  https://my.shp.ee/uUT8kkg
    #下播短链  https://my.shp.ee/pWQ78gE
    urls = ['https://my.shp.ee/ar13BZk']
    for url in urls:

        times = []  # 用于保存每次请求耗时

        for i in range(100):
            start_time = time.time()
            try:
                res = shopeeTool.get_shopee_live_info(url, proxy=False)
                print(res)
            except:
                print("解析错误", url)
            finally:
                cost = time.time() - start_time
                times.append(cost)
                print(f"耗时:{cost:.2f}")

        # 统计平均耗时和最大耗时
        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"平均请求耗时: {avg_time:.2f}秒")
        print(f"最长请求耗时: {max_time:.2f}秒")

