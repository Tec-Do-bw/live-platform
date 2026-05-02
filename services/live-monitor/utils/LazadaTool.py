import json
import time

import requests
import re
import tldextract
import hashlib
from copy import deepcopy

import random
from utils.wrapper import Wrapper

    
class LazadaTool:
    def __init__(self, ipList=[], tabItemQ=None):
        """
        lazada工具类
        
        Args:
            ipList: IP代理列表
            tabItemQ: 标签页队列
        """
        self.ipList = ipList
        self.tabItemQ = tabItemQ
        self.token = ''
        self.session = requests.Session()
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-self.session": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Google Chrome\";v=\"134\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\""
        }


    def get_lazada_live_url(self,url, proxy):
        headers = deepcopy(self.headers)
        if len(self.ipList)>0 and proxy:
            ip = random.choice(self.ipList)
            proxies = { "http":"http://"+ip,"https":"http://"+ip}
            response = self.session.get(url, headers=headers, proxies=proxies,allow_redirects=False, timeout=3)
        else:
            response = self.session.get(url, headers=headers, allow_redirects=False, timeout=3)
        if response.status_code == 302:
            return {'flv_url': 'error', 'roomId': '', 'message': '直播间不存在', 'filePath': ''}

        lazada_share_info = response.cookies.get("lazada_share_info")
        liveUuid = lazada_share_info.split("Lazlive-1-")[-1]
        return liveUuid


    def generate_sign(self,t,appKey,data_str):
        sign_str = f"{self.token}&{t}&{appKey}&{data_str}"
        m = hashlib.md5()
        # 确保使用 UTF-8 编码
        m.update(sign_str.encode('utf-8'))
        calc_sign = m.hexdigest()
        return calc_sign


    def _make_request(self, liveUuid, suffix, headers, proxy):
        """通用请求方法，支持代理"""
        url = f"https://acs-m.lazada.{suffix}/h5/mtop.lazada.live.query/1.1/"
        t = int(time.time() * 1000)
        appKey = "24677475"
        data = json.dumps({"liveUuid": liveUuid,"action":0}, separators=(',', ':'))
        sign = self.generate_sign(t,appKey,data)
        params = {
            "jsv": "2.6.1",
            "appKey": appKey,
            "t": str(t),
            "sign": sign,
            "api": "mtop.lazada.live.query",
            "v": "1.1",
            "type": "originaljson",
            "isSec": "1",
            "AntiCreep": "true",
            "timeout": "12000",
            "dataType": "json",
            "sessionOption": "AutoLoginOnly",
            "x-i18n-language": "en",
            "x-i18n-regionID": suffix.split(".")[-1].upper()
        }
        data = {'data':data}
        if len(self.ipList)>0 and proxy:
            ip = random.choice(self.ipList)
            proxies = {"http": "http://" + ip, "https": "http://" + ip}
            response = self.session.post(url,params=params,data=data, headers=headers, proxies=proxies, timeout=3)
            # response = curl_cffi.get(url, headers=headers, proxies=proxies, impersonate="chrome")
            # response = self.client.get(url, headers=headers, proxy=proxies)

        else:
            response = self.session.post(url,params=params,data=data, headers=headers, timeout=3)
            # response = curl_cffi.get(url, headers=headers, impersonate="chrome")
            # response = self.client.get(url, headers=headers)

        if response.status_code != 200:
            raise ValueError(f"请求失败，状态码: {response.status_code}")
        return response

    @Wrapper.retry(retries=3, delay=1)
    def init_token(self,liveUuid, suffix, headers, proxy):
        response = self._make_request(liveUuid, suffix, headers, proxy)
        _token = response.cookies.get("_m_h5_tk")
        token = _token.split("_")[0]
        self.token =  token


    @Wrapper.retry(retries=10, delay=1)
    def get_live_data(self, liveUuid, suffix, headers, proxy):
        """获取直播间响应数据"""
        response = self._make_request(liveUuid, suffix, headers, proxy)
        data = response.json().get('data')
        return data
    

    def _format_live_data(self, data):
        """格式化直播数据"""
        if not data:
            return {'flv_url': 'error', 'roomId': '', 'message': 'lazada数据为空', 'filePath': ''}

        port_info = {}

        # 房间与时间信息
        port_info["roomId"] = str(data.get("roomId"))
        port_info["liveUuid"] = data.get("liveUuid")
        port_info["roomStatus"] = data.get("roomStatus")
        port_info["title"] = data.get("title")
        port_info["startTime"] = data.get("startTimestamp") 

        play_urls = []
        best_flv = data.get("bestPullStreamUrl")
        if best_flv:
            play_urls.append(best_flv)

        # streamInfo.liveUrls 里包含不同清晰度的 flv/hls
        stream_info = data.get("streamInfo") or {}
        live_urls = stream_info.get("liveUrls") or []
        for item in live_urls:
            flv_url = item.get("flvUrl")
            hls_url = item.get("hlsUrl") or item.get("h265HlsUrl")
            h265_flv = item.get("h265FlvUrl")
            for url in (flv_url, hls_url, h265_flv):
                if url:
                    play_urls.append(url)
            if not best_flv and flv_url:
                best_flv = flv_url

        # 备用：pullStreamInfo 中的地址
        pull_stream_info = data.get("pullStreamInfo") or []
        for item in pull_stream_info:
            for url in item.get("pullStreamUrls") or []:
                if url:
                    play_urls.append(url)
                    if not best_flv and ".flv" in url:
                        best_flv = url

        # 再退一级使用 streamInfo 的 liveUrl
        if not best_flv:
            alt = stream_info.get("liveUrl") or stream_info.get("liveUrlHls")
            if alt:
                best_flv = alt
                play_urls.insert(0, alt)

        # 去重保序
        dedup_urls = []
        seen = set()
        for url in play_urls:
            if url and url not in seen:
                dedup_urls.append(url)
                seen.add(url)

        port_info["play_urls"] = dedup_urls
        port_info["flv_url"] = best_flv or ''

        # 文件路径：优先店铺名/昵称，其次 liveUuid
        seller_info = data.get("sellerInfo") or {}
        name_for_path = seller_info.get("shopName") or data.get("userNick") or data.get("liveUuid") or ""
        file_path = str(name_for_path).replace(".", "_").replace(" ", "_")
        port_info["filePath"] = file_path

        # 用户信息（始终返回）
        port_info["mediaUserId"] = str(data.get("userId", ""))
        port_info["mediaUserName"] = data.get("userNick") or seller_info.get("shopName", "")

        return port_info


    @Wrapper.retry_until_done(retries=3, delay=.1)
    def get_lazada_live_info(self, url, proxy=True):
        self.session.cookies.clear()
        """传入直播间地址，解析获取真实直播流地址信息"""
        extracted = tldextract.extract(url)
        suffix = extracted.suffix
        try:
            # 1. 获取当前的直播房间号
            liveUuid = self.get_lazada_live_url(url, proxy)
            if isinstance(liveUuid, dict): # 如果为字典 该直播间不存在
                return liveUuid

            # 2. 准备请求头
            headers = deepcopy(self.headers)
            headers['Referer'] = url
            # 3. 初始化获取加密token
            self.init_token(liveUuid, suffix, headers, proxy)
            
            # 4. 获取liveIuid 获取直播间信息
            data = self.get_live_data(liveUuid, suffix, headers, proxy)['data']

            roomStatus = data['roomStatus']
            if roomStatus == 'History':
                # 检查是否有历史直播跳转链接
                if 'onlineLiveJumpUrl' in data:
                    onlineLiveJumpUrl = data['onlineLiveJumpUrl']
                    last_liveUuid = onlineLiveJumpUrl.split("liveuuid=")[-1]
                    data = self.get_live_data(last_liveUuid, suffix, headers, proxy)['data']
                else:
                    # 未开播，返回包含用户信息的错误响应
                    seller_info = data.get('sellerInfo') or {}
                    return {
                        'flv_url': 'error',
                        'roomId': str(data.get('roomId', '')),
                        'message': '当前暂无直播',
                        'filePath': '',
                        'mediaUserId': str(data.get('userId', '')),
                        'mediaUserName': data.get('userNick') or seller_info.get('shopName', '')
                    }

            # 5. 格式化数据并返回
            return self._format_live_data(data)
            
        except Exception as e:
            print(f"获取直播信息失败: {url}, 错误: {str(e)}")
            return None



if __name__ == '__main__':
    import queue
    tabItemQ = queue.Queue()
    #在播短链  https://my.shp.ee/uUT8kkg
    #下播短链  https://my.shp.ee/pWQ78gE
    urls = ['https://s.lazada.co.th/s.Zd2pk4']
    for url in urls:
        lazadaTool = LazadaTool(['1663104-6b176fb7:19545d29-BA_RepublikaSrpska_city_Bijeljina@gate-hk.kkoip.com:17723',
                                 '1663104-6b176fb7:19545d29-BA_RepublikaSrpska_city_Doboj@gate-hk.kkoip.com:17723'],
                                tabItemQ)
        times = []  # 用于保存每次请求耗时

        for i in range(3):
            start_time = time.time()
            try:
                res = lazadaTool.get_lazada_live_info(url, proxy=False)
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

