# -*- coding: utf-8 -*-
import requests
import re
import json
import random
import time
import execjs
import queue
from utils.db_pool import db_pool
from utils.logger import Logings

logger = Logings().get_logger()


class TiktokTool:
    def __init__(self, ipList=[], tabItemQ=None):
        """
        TikTok工具类

        Args:
            ipList: IP代理列表
            tabItemQ: 标签页队列
        """
        self.ipList = ipList
        self.tabItemQ = tabItemQ
        self.All_country = ['CN', 'US', 'CA', 'FR', 'GB', 'DE', 'ES', 'IT', 'RU', 'AU', 'UA', 'AR', 'MX', 'BR', 'TR',
                            'CO',
                            'ZA', 'CL', 'TH', 'VN', 'MY', 'MM', 'IN', 'ID', 'SG', 'PH', 'BD', 'JP', 'KR', 'PK', 'SA',
                            'UZ',
                            'PY', 'EC', 'AT', 'CZ', 'DK', 'PL', 'PE', 'LT', 'SE', 'HU', 'BG', 'IL', 'AE', 'SD', 'RO',
                            'QA',
                            'NG', 'NL', 'NP', 'KZ', 'GH', 'EG', 'UG', 'ZM', 'KE', 'FI', 'NO', 'CH', 'MG', 'NZ', 'PT',
                            'GR',
                            'IE', 'DZ', 'MN', 'LK', 'TN', 'AF', 'AL', 'AD', 'AO', 'AG', 'AM', 'AZ', 'BS', 'BH', 'BB',
                            'BY',
                            'BE', 'BZ', 'BJ', 'BT', 'BO', 'BW', 'BN', 'BF', 'BI', 'KH', 'CM', 'CV', 'CF', 'TD', 'CG',
                            'CK',
                            'CR', 'CI', 'HR', 'CU', 'DJ', 'TL', 'SV', 'GQ', 'EE', 'ET', 'FJ', 'GA', 'GM', 'PS', 'GE',
                            'GD',
                            'GT', 'GN', 'GW', 'GY', 'HT', 'HN', 'IS', 'IQ', 'IR', 'JM', 'JO', 'KI', 'KW', 'KG', 'LA',
                            'LV',
                            'LB', 'LS', 'LR', 'LY', 'LI', 'LU', 'MK', 'MW', 'MV', 'ML', 'MH', 'MR', 'MU', 'FM', 'MD',
                            'MC',
                            'MA', 'MZ', 'NA', 'NR', 'NI', 'NE', 'NU', 'OM', 'PW', 'PA', 'PG', 'RW', 'LC', 'ST', 'SN',
                            'RS',
                            'SC', 'SL', 'SK', 'SI', 'SB', 'SO', 'SS', 'SR', 'SZ', 'SY', 'TJ', 'TZ', 'TG', 'TO', 'TV',
                            'UY',
                            'VE', 'YE', 'ZW', 'DO', 'BA']

    def get_dynamic_proxy(self):
        ip = f"http://7758105-0c83c22f:26394524-US@gate-hk.kkoip.com:19187"
        proxies = {
            'http': ip,
            'https': ip,
        }
        return proxies

    # 获取动态cookies列表
    def get_cookie_list(self,
                        getLiveCookiessql="SELECT cookies FROM live_account_info where cookies like '%true%'  order by id desc limit 20"):
        """
        从数据库获取cookie列表（使用连接池）

        Args:
            getLiveCookiessql: 查询SQL语句

        Returns:
            cookies字符串列表
        """
        try:
            # ✅ 使用连接池查询
            dd = db_pool.execute_query(getLiveCookiessql)

            if not dd:
                logger.warning("未查询到任何cookies记录")
                return []

            cookies_string_list = []
            for d in dd:
                try:
                    # 处理cookie数据
                    cookiesArgsList = eval(d[0].replace("true", "True").replace("false", "False"))
                    cookie = {}
                    for i in cookiesArgsList:
                        cookie[i['name']] = i['value']
                    cookies_string = '; '.join([f"{key}={value}" for key, value in cookie.items()])
                    if cookies_string not in cookies_string_list:
                        cookies_string_list.append(cookies_string)
                except Exception as parse_error:
                    logger.error(f"解析单条cookie失败: {parse_error}")
                    continue

            logger.info(f"成功获取cookies列表 | 数量={len(cookies_string_list)}")
            return cookies_string_list

        except Exception as e:
            logger.error(f"获取动态cookies列表时出错: {e}", exc_info=True)
            return []

    def get_cookies_dict(self, cookies_str):
        # 将cookies字符串转换为字典
        cookies_dict = {}
        for item in cookies_str.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                cookies_dict[key.strip()] = value.strip()

        return cookies_dict

    def _extract_json_from_html(self, html_str):
        """
        从HTML中提取TikTok直播数据JSON。
        优先提取SIGI_STATE；若其中无LiveRoom，则补充提取__UNIVERSAL_DATA_FOR_REHYDRATION__。
        """
        if 'UNEXPECTED_EOF_WHILE_READING' in html_str:
            return None

        json_data = None
        try:
            json_str = re.findall(
                '<script id="SIGI_STATE" type="application/json">(.*?)</script>',
                html_str, re.DOTALL
            )[0]
            json_data = json.loads(json_str)
        except Exception:
            pass

        if json_data and json_data.get("LiveRoom"):
            return json_data

        return None

    def get_tiktok_stream_data_requests(self, url, cookie_list):
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'close',
            'Pragma': 'no-cache',
            'Referer': 'https://www.tiktok.com/@poseshoes/live',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }

        js = '''
            function SHA256() {
                this._buf = new Array(64);
                this._W = new Array(64);
                this._pad = new Array(64);
                this._k = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
                this._pad[0] = 0x80;
                for (var i = 1; i < 64; ++i) {
                    this._pad[i] = 0
                }
                this.reset()
            }
            SHA256.prototype.reset = function() {
                this._chain = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
                this._inbuf = 0;
                this._total = 0
            }
            ;
            SHA256.prototype._compress = function(buf) {
                var W = this._W;
                var k = this._k;
                var _rotr = function(w, r) {
                    return ((w << (32 - r)) | (w >>> r))
                };
                for (var i = 0; i < 64; i += 4) {
                    var w = (buf[i] << 24) | (buf[i + 1] << 16) | (buf[i + 2] << 8) | (buf[i + 3]);
                    W[i / 4] = w
                }
                for (var i = 16; i < 64; ++i) {
                    var s0 = _rotr(W[i - 15], 7) ^ _rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
                    var s1 = _rotr(W[i - 2], 17) ^ _rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
                    W[i] = (W[i - 16] + s0 + W[i - 7] + s1) & 0xffffffff
                }
                var A = this._chain[0];
                var B = this._chain[1];
                var C = this._chain[2];
                var D = this._chain[3];
                var E = this._chain[4];
                var F = this._chain[5];
                var G = this._chain[6];
                var H = this._chain[7];
                for (var i = 0; i < 64; ++i) {
                    var S0 = _rotr(A, 2) ^ _rotr(A, 13) ^ _rotr(A, 22);
                    var maj = (A & B) ^ (A & C) ^ (B & C);
                    var t2 = (S0 + maj) & 0xffffffff;
                    var S1 = _rotr(E, 6) ^ _rotr(E, 11) ^ _rotr(E, 25);
                    var ch = (E & F) ^ ((~E) & G);
                    var t1 = (H + S1 + ch + k[i] + W[i]) & 0xffffffff;
                    H = G;
                    G = F;
                    F = E;
                    E = (D + t1) & 0xffffffff;
                    D = C;
                    C = B;
                    B = A;
                    A = (t1 + t2) & 0xffffffff
                }
                this._chain[0] += A;
                this._chain[1] += B;
                this._chain[2] += C;
                this._chain[3] += D;
                this._chain[4] += E;
                this._chain[5] += F;
                this._chain[6] += G;
                this._chain[7] += H
            }
            ;
            SHA256.prototype.update = function(bytes, opt_length) {
                if (!opt_length) {
                    opt_length = bytes.length
                }
                this._total += opt_length;
                for (var n = 0; n < opt_length; ++n) {
                    this._buf[this._inbuf++] = bytes[n];
                    if (this._inbuf == 64) {
                        this._compress(this._buf);
                        this._inbuf = 0
                    }
                }
            }
            ;
            SHA256.prototype.updateRange = function(bytes, start, end) {
                this._total += (end - start);
                for (var n = start; n < end; ++n) {
                    this._buf[this._inbuf++] = bytes[n];
                    if (this._inbuf == 64) {
                        this._compress(this._buf);
                        this._inbuf = 0
                    }
                }
            }
            ;
            SHA256.prototype.digest = function(var_args) {
                for (var i = 0; i < arguments.length; ++i) {
                    this.update(arguments[i])
                }
                var digest = new Array(32);
                var totalBits = this._total * 8;
                if (this._inbuf < 56) {
                    this.update(this._pad, 56 - this._inbuf)
                } else {
                    this.update(this._pad, 64 - (this._inbuf - 56))
                }
                for (var i = 63; i >= 56; --i) {
                    this._buf[i] = totalBits & 255;
                    totalBits >>>= 8
                }
                this._compress(this._buf);
                var n = 0;
                for (var i = 0; i < 8; ++i) {
                    for (var j = 24; j >= 0; j -= 8) {
                        digest[n++] = (this._chain[i] >> j) & 255
                    }
                }
                return digest
            }
            ;
            function s256(s1, s2) {
                let enc = new TextEncoder();
                let s = enc.encode(s2);
                let sha = new SHA256();
                sha.update(s1);
                sha.update(s);
                return sha.digest().map((v)=>{
                    var res = [];
                    var c = v < 0 ? v + 256 : v;
                    res.push((c >>> 4).toString(16));
                    res.push((c & 0xf).toString(16));
                    return res.join("")
                }
                ).join("")
            }
            function b64tohex(b) {
                return [...atob(b)].map(c=>c.charCodeAt(0).toString(16).padStart(2, 0)).join('')
            }
            function b64tou8a(b) {
                return Uint8Array.from(atob(b), c=>c.charCodeAt(0))
            }
            function get_cookie(cs){
                var wci = "_wafchallengeid";
                var c = JSON.parse(atob(cs));
                var prefix = b64tou8a(c.v.a);
                var expect = b64tohex(c.v.c);
                var i = 0;
                while (1){
                if (expect === s256(prefix, i.toString())) {
                    c.d = btoa(i.toString());
                    cookie = wci + "=" + btoa(JSON.stringify(c)) + "; Max-Age=1";
                    console.log(cookie)
                    return cookie
                }
                i++;}
            }
            '''

        ress = requests.session()
        cookies = self.get_cookies_dict(random.choice(cookie_list))

        for _ in range(3):
            try:
                if len(self.ipList) > 0:
                    # ip = random.choice(self.ipList)
                    # proxies = { "http":"http://"+ip,"https":"http://"+ip}
                    proxies = self.get_dynamic_proxy()
                    doc1 = ress.get(url, headers=headers, proxies=proxies, timeout=5).text
                    # # 如果doc1中存在WAF反爬情况，则需要解密获取生成_wafchallengeid
                    if "Please wait" in doc1:
                        _wafchallengeid = re.findall('class="(eyJ.*?)">', doc1, re.S)[0]
                        # print("_wafchallengeid--->",_wafchallengeid)
                        execS = execjs.compile(js)

                        cookie = execS.call('get_cookie', _wafchallengeid)
                        # print('cookie-->',cookie)
                        headers.update({"cookie": cookie})
                        doc2 = ress.get(url, headers=headers, proxies=proxies, timeout=15).text
                        html_str = doc2
                    else:
                        html_str = doc1
                else:
                    doc1 = ress.get(url=url, headers=headers, timeout=15).text
                    # # 如果doc1中存在WAF反爬情况，则需要解密获取生成_wafchallengeid
                    if "Please wait" in doc1:
                        _wafchallengeid = re.findall('class="(eyJ.*?)">', doc1, re.S)[0]
                        exec = execjs.compile(js)
                        cookie = exec.call('get_cookie', _wafchallengeid)
                        # print('cookie-->',cookie)
                        headers.update({"cookie": cookie})
                        doc2 = ress.get(url, headers=headers, cookies=cookies).text
                        html_str = doc2
                    else:
                        html_str = doc1
                json_data = self._extract_json_from_html(html_str)
                if json_data is not None:
                    return json_data
                else:
                    print("没有正常解析到对应数据,解析直播间地址为:" + url)
                    return 0

            except Exception as e:
                # print(f"请求发生异常，正在重试... 异常信息: {e}")
                continue

        return 0

    def getPageinfo_selenium(self, mateUrl, OP):
        """
        使用 selenium 获取页面信息
        ✅ 添加队列获取超时机制，防止无限阻塞
        """
        try:
            # ✅ 添加30秒超时，防止队列为空时无限阻塞
            tabItems = self.tabItemQ.get(timeout=30)
            logger.debug(f"成功获取浏览器标签页资源 | url={mateUrl}")
        except queue.Empty:
            logger.warning(f"⚠️ 获取浏览器标签页超时(30s) | url={mateUrl}")
            return None

        tabItem = tabItems.get("tab")

        try:
            tabItem = OP.browser_request(tabItem, mateUrl=mateUrl)
            time.sleep(10)
            page_source = tabItem.html
            tabItem.get("about:blank")
            self.tabItemQ.put(tabItems)
            json_data = self._extract_json_from_html(page_source)
            if json_data is not None:
                return json_data
            else:
                print("没有正常解析到对应数据,解析直播间地址为:" + mateUrl)
            return None
        except Exception as e:
            logger.error(f"selenium获取页面失败 | url={mateUrl} error={e}")
            try:
                tabItem.get("about:blank")
                self.tabItemQ.put(tabItems)
            except Exception:
                pass  # 确保资源释放不会再抛异常
            return None

            # 解析获取到的数据

    def parse_json_data(self, json_data, record_url):
        port_info = {}

        if json_data.get("LiveRoom", ''):
            liveRoomUserInfo = json_data.get("LiveRoom", '').get("liveRoomUserInfo")
            liveRoom = liveRoomUserInfo.get("liveRoom")
            startTime = liveRoom.get("startTime")
            port_info["startTime"] = str(startTime)

            try:
                stream_data = liveRoom.get("streamData").get("pull_data").get("stream_data")
            except:
                port_info["flv_url"] = "error"
            try:
                json_data2 = json.loads(stream_data)
                flv_url = json_data2.get("data").get("origin").get("main").get("flv")
                if str(liveRoom["status"]) == '2':
                    port_info["flv_url"] = flv_url
                else:
                    port_info["flv_url"] = ''
            except:
                port_info["flv_url"] = ""
            user = liveRoomUserInfo.get("user")
            port_info["secUid"] = str(user.get("secUid"))
            port_info["uniqueId"] = str(user.get("uniqueId"))
            port_info["roomId"] = str(user.get("roomId"))
            port_info["signature"] = str(user.get("signature"))
            port_info["id"] = str(user.get("id"))
            port_info["nickname"] = str(user.get("nickname"))
            port_info["url"] = record_url
            filePath = re.compile("@(.*?)/live").findall(record_url)[0].replace(".", "_")
            port_info["filePath"] = filePath
            return port_info

        elif json_data.get("UniversalData"):
            universal = json_data["UniversalData"]
            user = universal.get("__DEFAULT_SCOPE__", {}) \
                            .get("webapp.app-context", {}) \
                            .get("user", {})
            if not user:
                return {"flv_url": "", "roomId": "", "message": "直播间不存在", "url": record_url}

            port_info["flv_url"] = ""
            port_info["startTime"] = ""
            port_info["secUid"] = str(user.get("secUid", ""))
            port_info["uniqueId"] = str(user.get("uniqueId", ""))
            port_info["roomId"] = str(user.get("roomId", ""))
            port_info["signature"] = str(user.get("signature", ""))
            port_info["id"] = str(user.get("uid", ""))
            port_info["nickname"] = str(user.get("nickName", ""))
            port_info["url"] = record_url
            filePath = re.compile("@(.*?)/live").findall(record_url)[0].replace(".", "_")
            port_info["filePath"] = filePath
            return port_info

        else:
            port_info = {"flv_url": "", "roomId": "", "message": "直播间不存在", "url": record_url}
            return port_info

    # 传入直播间地址，解析获取真实直播流地址信息
    def getLiveStreamInfo_requests(self, record_url, cookie_list, OP=None):
        json_data = 0
        # 尝试直接解密获取
        try:
            json_data = self.get_tiktok_stream_data_requests(url=record_url, cookie_list=cookie_list)
            # print("json_data-->",json_data)
        except Exception as e:
            print("getLiveStreamInfo_requests11111111:e-->", e)
            json_data = 0

        # # 防止WAF修改解密规则，导致错误直接使用浏览器获取
        # if json_data == 0 or json_data is None or str(json_data) == "None":
        #     print("使用自动化获取直播地址", record_url)
        #     try:
        #         json_data = self.getPageinfo_selenium(record_url, OP)
        #     except Exception as e:
        #         json_data = 0
        #         print("getPageinfo_selenium获取数据失败", e, record_url)

        # 如果存在开始解析
        if json_data:
            try:
                end_port_info = self.parse_json_data(json_data, record_url)
                return end_port_info
            except Exception as e:
                import traceback
                error_info = traceback.print_exc()
                logger.error(f"解析parse_json_data数据出错 | url={record_url} | error={error_info}")
                print("解析parse_json_data数据出错", e)
                return {'flv_url': 'error', 'roomId': '', 'message': 'tk采集异常', 'filePath': ''}

        else:
            return {'flv_url': 'error', 'roomId': '', 'message': 'tk采集异常', 'filePath': ''}


if __name__ == '__main__':
    import queue

    tabItemQ = queue.Queue()
    ipList = ['senspower:T9u_SCK5Bezq@96.62.57.99:2333', 'senspower:T9u_SCK5Bezq@96.62.57.98:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.41:2333', 'senspower:T9u_SCK5Bezq@96.62.57.38:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.37:2333', 'senspower:T9u_SCK5Bezq@96.62.57.35:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.34:2333', 'senspower:T9u_SCK5Bezq@96.62.57.33:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.31:2333', 'senspower:T9u_SCK5Bezq@96.62.57.25:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.24:2333', 'senspower:T9u_SCK5Bezq@96.62.57.226:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.187:2333', 'senspower:T9u_SCK5Bezq@96.62.57.18:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.130:2333', 'senspower:T9u_SCK5Bezq@96.62.57.129:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.128:2333', 'senspower:T9u_SCK5Bezq@96.62.57.127:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.124:2333', 'senspower:T9u_SCK5Bezq@96.62.57.112:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.111:2333', 'senspower:T9u_SCK5Bezq@96.62.57.108:2333',
              'senspower:T9u_SCK5Bezq@96.62.57.107:2333', 'senspower:T9u_SCK5Bezq@96.62.57.105:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.99:2333', 'senspower:T9u_SCK5Bezq@96.62.151.66:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.249:2333', 'senspower:T9u_SCK5Bezq@96.62.151.228:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.218:2333', 'senspower:T9u_SCK5Bezq@96.62.151.217:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.216:2333', 'senspower:T9u_SCK5Bezq@96.62.151.215:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.214:2333', 'senspower:T9u_SCK5Bezq@96.62.151.211:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.210:2333', 'senspower:T9u_SCK5Bezq@96.62.151.21:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.184:2333', 'senspower:T9u_SCK5Bezq@96.62.151.182:2333',
              'senspower:T9u_SCK5Bezq@96.62.151.130:2333', 'senspower:T9u_SCK5Bezq@96.62.151.128:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.239:2333', 'senspower:T9u_SCK5Bezq@96.62.149.238:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.237:2333', 'senspower:T9u_SCK5Bezq@96.62.149.236:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.234:2333', 'senspower:T9u_SCK5Bezq@96.62.149.233:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.231:2333', 'senspower:T9u_SCK5Bezq@96.62.149.23:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.229:2333', 'senspower:T9u_SCK5Bezq@96.62.149.222:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.186:2333', 'senspower:T9u_SCK5Bezq@96.62.149.159:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.158:2333', 'senspower:T9u_SCK5Bezq@96.62.149.157:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.156:2333', 'senspower:T9u_SCK5Bezq@96.62.149.155:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.153:2333', 'senspower:T9u_SCK5Bezq@96.62.149.152:2333',
              'senspower:T9u_SCK5Bezq@96.62.149.151:2333', 'senspower:T9u_SCK5Bezq@96.62.149.150:2333',
              'senspower:T9u_SCK5Bezq@96.62.10.10:2333', 'senspower:T9u_SCK5Bezq@95.135.223.246:2333',
              'senspower:T9u_SCK5Bezq@95.135.104.30:2333', 'senspower:T9u_SCK5Bezq@95.135.104.17:2333',
              'senspower:T9u_SCK5Bezq@95.134.80.5:2333', 'senspower:T9u_SCK5Bezq@95.134.80.15:2333',
              'senspower:T9u_SCK5Bezq@95.134.79.143:2333', 'senspower:T9u_SCK5Bezq@95.134.202.9:2333',
              'senspower:T9u_SCK5Bezq@95.134.202.13:2333', 'senspower:T9u_SCK5Bezq@94.241.137.48:2333',
              'senspower:T9u_SCK5Bezq@94.241.137.47:2333', 'senspower:T9u_SCK5Bezq@94.241.137.27:2333',
              'senspower:T9u_SCK5Bezq@94.241.137.138:2333', 'senspower:T9u_SCK5Bezq@94.241.136.97:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.196:2333', 'senspower:T9u_SCK5Bezq@94.241.136.167:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.16:2333', 'senspower:T9u_SCK5Bezq@94.241.136.152:2333',
              'senspower:T9u_SCK5Bezq@94.241.136.146:2333', 'senspower:T9u_SCK5Bezq@93.114.88.84:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.82:2333', 'senspower:T9u_SCK5Bezq@93.114.88.62:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.57:2333', 'senspower:T9u_SCK5Bezq@93.114.88.43:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.236:2333', 'senspower:T9u_SCK5Bezq@93.114.88.214:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.123:2333', 'senspower:T9u_SCK5Bezq@93.114.88.118:2333',
              'senspower:T9u_SCK5Bezq@93.114.88.106:2333', 'senspower:T9u_SCK5Bezq@88.216.247.99:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.31:2333', 'senspower:T9u_SCK5Bezq@82.29.99.225:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.22:2333', 'senspower:T9u_SCK5Bezq@82.29.99.21:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.162:2333', 'senspower:T9u_SCK5Bezq@82.29.99.142:2333',
              'senspower:T9u_SCK5Bezq@82.29.99.107:2333', 'senspower:T9u_SCK5Bezq@82.29.7.91:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.68:2333', 'senspower:T9u_SCK5Bezq@82.29.7.65:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.36:2333', 'senspower:T9u_SCK5Bezq@82.29.7.250:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.233:2333', 'senspower:T9u_SCK5Bezq@82.29.7.202:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.19:2333', 'senspower:T9u_SCK5Bezq@82.29.7.189:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.163:2333', 'senspower:T9u_SCK5Bezq@82.29.7.154:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.143:2333', 'senspower:T9u_SCK5Bezq@82.29.7.13:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.123:2333', 'senspower:T9u_SCK5Bezq@82.29.7.119:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.114:2333', 'senspower:T9u_SCK5Bezq@82.29.7.111:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.110:2333', 'senspower:T9u_SCK5Bezq@82.29.7.101:2333',
              'senspower:T9u_SCK5Bezq@82.29.7.10:2333', 'senspower:T9u_SCK5Bezq@82.29.68.47:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.37:2333', 'senspower:T9u_SCK5Bezq@82.29.68.35:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.25:2333', 'senspower:T9u_SCK5Bezq@82.29.68.241:2333',
              'senspower:T9u_SCK5Bezq@82.29.68.168:2333', 'senspower:T9u_SCK5Bezq@82.29.55.9:2333',
              'senspower:T9u_SCK5Bezq@82.29.55.175:2333', 'senspower:T9u_SCK5Bezq@82.29.150.35:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.254:2333', 'senspower:T9u_SCK5Bezq@82.29.150.192:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.187:2333', 'senspower:T9u_SCK5Bezq@82.29.150.155:2333',
              'senspower:T9u_SCK5Bezq@82.29.150.102:2333', 'senspower:T9u_SCK5Bezq@68.64.156.94:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.5:2333', 'senspower:T9u_SCK5Bezq@68.64.156.44:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.3:2333', 'senspower:T9u_SCK5Bezq@68.64.156.242:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.222:2333', 'senspower:T9u_SCK5Bezq@68.64.156.208:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.176:2333', 'senspower:T9u_SCK5Bezq@68.64.156.141:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.121:2333', 'senspower:T9u_SCK5Bezq@68.64.156.107:2333',
              'senspower:T9u_SCK5Bezq@68.64.156.10:2333', 'senspower:T9u_SCK5Bezq@66.93.30.58:2333',
              'senspower:T9u_SCK5Bezq@45.207.128.202:2333', 'senspower:T9u_SCK5Bezq@45.207.128.116:2333',
              'senspower:T9u_SCK5Bezq@45.196.195.15:2333', 'senspower:T9u_SCK5Bezq@45.194.24.74:2333',
              'senspower:T9u_SCK5Bezq@45.192.239.8:2333', 'senspower:T9u_SCK5Bezq@45.192.239.46:2333',
              'senspower:T9u_SCK5Bezq@45.192.238.12:2333', 'senspower:T9u_SCK5Bezq@38.30.200.61:2333',
              'senspower:T9u_SCK5Bezq@38.213.58.170:2333', 'senspower:T9u_SCK5Bezq@38.213.253.128:2333',
              'senspower:T9u_SCK5Bezq@38.213.252.214:2333', 'senspower:T9u_SCK5Bezq@38.213.139.158:2333',
              'senspower:T9u_SCK5Bezq@38.213.122.216:2333', 'senspower:T9u_SCK5Bezq@31.59.187.65:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.60:2333', 'senspower:T9u_SCK5Bezq@31.59.187.58:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.5:2333', 'senspower:T9u_SCK5Bezq@31.59.187.245:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.216:2333', 'senspower:T9u_SCK5Bezq@31.59.187.199:2333',
              'senspower:T9u_SCK5Bezq@31.59.187.180:2333', 'senspower:T9u_SCK5Bezq@31.59.187.135:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.92:2333', 'senspower:T9u_SCK5Bezq@31.59.113.9:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.89:2333', 'senspower:T9u_SCK5Bezq@31.59.113.57:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.52:2333', 'senspower:T9u_SCK5Bezq@31.59.113.43:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.40:2333', 'senspower:T9u_SCK5Bezq@31.59.113.245:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.239:2333', 'senspower:T9u_SCK5Bezq@31.59.113.236:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.185:2333', 'senspower:T9u_SCK5Bezq@31.59.113.182:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.174:2333', 'senspower:T9u_SCK5Bezq@31.59.113.169:2333',
              'senspower:T9u_SCK5Bezq@31.59.113.134:2333', 'senspower:T9u_SCK5Bezq@31.59.113.130:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.85:2333', 'senspower:T9u_SCK5Bezq@31.59.112.68:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.233:2333', 'senspower:T9u_SCK5Bezq@31.59.112.220:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.213:2333', 'senspower:T9u_SCK5Bezq@31.59.112.202:2333',
              'senspower:T9u_SCK5Bezq@31.59.112.166:2333', 'senspower:T9u_SCK5Bezq@31.59.112.103:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.47:2333', 'senspower:T9u_SCK5Bezq@31.57.133.236:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.194:2333', 'senspower:T9u_SCK5Bezq@31.57.133.180:2333',
              'senspower:T9u_SCK5Bezq@31.57.133.155:2333', 'senspower:T9u_SCK5Bezq@31.56.201.84:2333',
              'senspower:T9u_SCK5Bezq@31.56.201.68:2333', 'senspower:T9u_SCK5Bezq@31.56.201.177:2333',
              'senspower:T9u_SCK5Bezq@31.56.201.115:2333', 'senspower:T9u_SCK5Bezq@217.147.165.167:2333',
              'senspower:T9u_SCK5Bezq@217.147.165.154:2333', 'senspower:T9u_SCK5Bezq@217.147.165.128:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.5:2333', 'senspower:T9u_SCK5Bezq@209.213.202.45:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.233:2333', 'senspower:T9u_SCK5Bezq@209.213.202.230:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.224:2333', 'senspower:T9u_SCK5Bezq@209.213.202.222:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.211:2333', 'senspower:T9u_SCK5Bezq@209.213.202.198:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.193:2333', 'senspower:T9u_SCK5Bezq@209.213.202.187:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.174:2333', 'senspower:T9u_SCK5Bezq@209.213.202.14:2333',
              'senspower:T9u_SCK5Bezq@209.213.202.105:2333', 'senspower:T9u_SCK5Bezq@195.86.51.38:2333',
              'senspower:T9u_SCK5Bezq@195.86.30.56:2333', 'senspower:T9u_SCK5Bezq@195.86.30.30:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.246:2333', 'senspower:T9u_SCK5Bezq@192.200.211.245:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.240:2333', 'senspower:T9u_SCK5Bezq@192.200.211.236:2333',
              'senspower:T9u_SCK5Bezq@192.200.211.233:2333', 'senspower:T9u_SCK5Bezq@188.209.143.81:2333',
              'senspower:T9u_SCK5Bezq@188.209.143.187:2333', 'senspower:T9u_SCK5Bezq@172.121.61.89:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.86:2333', 'senspower:T9u_SCK5Bezq@172.121.61.85:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.84:2333', 'senspower:T9u_SCK5Bezq@172.121.61.82:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.81:2333', 'senspower:T9u_SCK5Bezq@172.121.61.80:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.63:2333', 'senspower:T9u_SCK5Bezq@172.121.61.58:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.48:2333', 'senspower:T9u_SCK5Bezq@172.121.61.47:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.245:2333', 'senspower:T9u_SCK5Bezq@172.121.61.154:2333',
              'senspower:T9u_SCK5Bezq@172.121.61.119:2333', 'senspower:T9u_SCK5Bezq@172.121.53.47:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.46:2333', 'senspower:T9u_SCK5Bezq@172.121.53.45:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.43:2333', 'senspower:T9u_SCK5Bezq@172.121.53.41:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.246:2333', 'senspower:T9u_SCK5Bezq@172.121.53.220:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.149:2333', 'senspower:T9u_SCK5Bezq@172.121.53.148:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.146:2333', 'senspower:T9u_SCK5Bezq@172.121.53.145:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.144:2333', 'senspower:T9u_SCK5Bezq@172.121.53.140:2333',
              'senspower:T9u_SCK5Bezq@172.121.53.14:2333', 'senspower:T9u_SCK5Bezq@172.121.53.102:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.39:2333', 'senspower:T9u_SCK5Bezq@172.120.245.37:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.36:2333', 'senspower:T9u_SCK5Bezq@172.120.245.35:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.34:2333', 'senspower:T9u_SCK5Bezq@172.120.245.32:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.31:2333', 'senspower:T9u_SCK5Bezq@172.120.245.3:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.220:2333', 'senspower:T9u_SCK5Bezq@172.120.245.160:2333',
              'senspower:T9u_SCK5Bezq@172.120.245.141:2333', 'senspower:T9u_SCK5Bezq@167.148.104.79:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.76:2333', 'senspower:T9u_SCK5Bezq@167.148.104.72:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.54:2333', 'senspower:T9u_SCK5Bezq@167.148.104.254:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.252:2333', 'senspower:T9u_SCK5Bezq@167.148.104.225:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.182:2333', 'senspower:T9u_SCK5Bezq@167.148.104.172:2333',
              'senspower:T9u_SCK5Bezq@167.148.104.151:2333', 'senspower:T9u_SCK5Bezq@154.83.108.43:2333',
              'senspower:T9u_SCK5Bezq@154.83.108.215:2333', 'senspower:T9u_SCK5Bezq@151.242.8.187:2333',
              'senspower:T9u_SCK5Bezq@151.242.121.64:2333', 'senspower:T9u_SCK5Bezq@149.87.190.232:2333',
              'senspower:T9u_SCK5Bezq@149.87.172.196:2333', 'senspower:T9u_SCK5Bezq@149.87.172.100:2333',
              'senspower:T9u_SCK5Bezq@149.51.127.23:2333', 'senspower:T9u_SCK5Bezq@104.234.185.96:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.38:2333', 'senspower:T9u_SCK5Bezq@104.234.185.251:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.243:2333', 'senspower:T9u_SCK5Bezq@104.234.185.237:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.234:2333', 'senspower:T9u_SCK5Bezq@104.234.185.23:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.214:2333', 'senspower:T9u_SCK5Bezq@104.234.185.191:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.183:2333', 'senspower:T9u_SCK5Bezq@104.234.185.173:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.160:2333', 'senspower:T9u_SCK5Bezq@104.234.185.157:2333',
              'senspower:T9u_SCK5Bezq@104.234.185.116:2333']
    tiktokTool = TiktokTool(ipList)
    #
    # import time
    #
    # times = []  # 用于保存每次请求耗时
    #
    # for i in range(1):
    #     start_time = time.time()
    #     try:
    #         # room_url = "https://www.tiktok.com/@greameofficialstore/live" #18岁禁止
    #         room_url = "https://www.tiktok.com/@daddy.mockingbird/live" #正常
    #         # room_url = "https://www.tiktok.com/@koh.gen.do.my/live" #没有直播
    #         port_info = tiktokTool.getLiveStreamInfo_requests(room_url, ipList, tabItemQ) or {}
    #         print(port_info)
    #     except:
    #         print("解析错误", room_url)
    #     finally:
    #         cost = time.time() - start_time
    #         times.append(cost)
    #         print(f"耗时:{cost:.2f}")
    #
    # # 统计平均耗时和最大耗时
    # avg_time = sum(times) / len(times)
    # max_time = max(times)
    #
    # print(f"平均请求耗时: {avg_time:.2f}秒")
    # print(f"最长请求耗时: {max_time:.2f}秒")

    # 多线程测试
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 假设你的 tiktokTool, ipList, tabItemQ 已经在上方定义完毕
    room_url = "https://www.tiktok.com/@daddy.mockingbird/live"
    times = []


    # 1. 把单次请求的逻辑封装成一个函数
    def fetch_stream_data(url):
        start_time = time.time()
        try:
            port_info = tiktokTool.getLiveStreamInfo_requests(url, ipList, tabItemQ) or {}
            print(port_info)
        except Exception as e:
            print("解析错误", url, e)
        finally:
            cost = time.time() - start_time
            print(f"耗时:{cost:.2f}")
            return cost  # 返回耗时用于后续统计


    # 2. 使用线程池进行并发请求
    # max_workers 是并发的线程数，你可以根据你的代理池大小和目标网站的限制来调整 (比如 10 到 20)
    max_workers = 10
    print(f"开始并发请求，线程数: {max_workers}...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交 100 个任务到线程池
        futures = [executor.submit(fetch_stream_data, room_url) for _ in range(200)]

        # 获取结果 (as_completed 会在任务完成时立刻生成结果)
        for future in as_completed(futures):
            cost = future.result()
            times.append(cost)

    # 3. 统计平均耗时和最大耗时
    if times:
        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"总计完成请求数: {len(times)}")
        print(f"平均请求耗时: {avg_time:.2f}秒")
        print(f"最长请求耗时: {max_time:.2f}秒")
    else:
        print("未能记录到任何有效数据。")
