import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Union, List

_PROXY_MAP: Dict[str, Union[str, List[str]]] = {
    "MY": "socks5://54.kookeey.info:23546:c822ee15:2169010a",
    "ID": "socks5://80.kookeey.info:32583:c822ee15:2169010a",
    "TH": "socks5://75.kookeey.info:27240:c822ee15:2169010a",
    "VN": "socks5://83.kookeey.info:27006:c822ee15:2169010a",
    "BR": "socks5://br293.kookeey.info:25552:c822ee15:2169010a",
    "JP": "socks5://81.kookeey.info:21696:c822ee15:2169010a",
    "US": "socks5://us417.kookeey.info:20810:c822ee15:2169010a",
    "MX": [
        "socks5://mx565.kookeey.info:30067:c822ee15:2169010a",
        "socks5://mx351.kookeey.info:29961:c822ee15:2169010a",
    ],
    "SG": "socks5://57.kookeey.info:24317:c822ee15:2169010a",
}

# ----------------- 配置区 -----------------
# 填入你从 ip2location.io 申请到的真实 API Key
IP2LOCATION_API_KEY = "6A5E80FFB1179DFE09AB743F86BEEC88"


# ------------------------------------------

def format_proxy_url(raw_proxy: str) -> str:
    """
    将 IP:PORT:USER:PASS 格式转换为 requests 支持的 USER:PASS@IP:PORT 格式
    """
    try:
        protocol, rest = raw_proxy.split("://")
        parts = rest.split(":")
        if len(parts) == 4:
            host, port, user, password = parts
            return f"{protocol}://{user}:{password}@{host}:{port}"
    except Exception:
        pass
    return raw_proxy


def check_proxy(country_code: str, proxy_url: str) -> dict:
    formatted_url = format_proxy_url(proxy_url)
    proxies = {"http": formatted_url, "https": formatted_url}
    proxy_host = proxy_url.split('://')[-1].split(':')[0]

    result = {
        "Expected": country_code,
        "Proxy_Host": proxy_host,
        "Outbound_IP": "N/A",
        "IP-API": "N/A",
        "IP2Location": "N/A",
        "IPinfo": "N/A",  # 新增 IPinfo 结果字段
        "Status": "Failed"
    }

    try:
        # 1. IP-API 查询 (通过代理获取出口 IP)
        ipapi_resp = requests.get('http://ip-api.com/json/', proxies=proxies, timeout=15)
        ipapi_resp.raise_for_status()
        ipapi_data = ipapi_resp.json()

        outbound_ip = ipapi_data.get("query", "N/A")
        result["Outbound_IP"] = outbound_ip
        result["IP-API"] = ipapi_data.get("country", "Unknown")
        result["Status"] = "Success"

        # 拿到出口 IP 后，并发去查其他两个库（不走代理，加快速度）

        # 2. IP2Location 查询
        if IP2LOCATION_API_KEY :
            ip2loc_url = f"https://api.ip2location.io/?key={IP2LOCATION_API_KEY}&ip={outbound_ip}"
            ip2loc_resp = requests.get(ip2loc_url, timeout=10)
            if ip2loc_resp.status_code == 200:
                result["IP2Location"] = ip2loc_resp.json().get("country_name", "Unknown")
            elif ip2loc_resp.status_code == 401:
                result["IP2Location"] = "Key无效(401)"
            else:
                result["IP2Location"] = f"Error {ip2loc_resp.status_code}"
        else:
            result["IP2Location"] = "未配置Key"

        # 3. IPinfo.io 查询 (免 Key，免费高额度，补充查验)
        try:
            ipinfo_resp = requests.get(f"https://ipinfo.io/{outbound_ip}/json", timeout=10)
            if ipinfo_resp.status_code == 200:
                result["IPinfo"] = ipinfo_resp.json().get("country", "Unknown")
        except:
            result["IPinfo"] = "Req Timeout"

        return result

    except requests.exceptions.Timeout:
        result["Status"] = "Failed: Timeout"
        return result
    except Exception as e:
        error_msg = str(e).split(":")[-1].strip()[:20]
        result["Status"] = f"Failed: {error_msg}..."
        return result


def main():
    tasks = []
    for country, proxies in _PROXY_MAP.items():
        if isinstance(proxies, list):
            for proxy in proxies:
                tasks.append((country, proxy))
        else:
            tasks.append((country, proxies))

    print(f"开始检测，共计 {len(tasks)} 个代理节点...\n")
    # 调整了打印排版，加入了 IPinfo 字段
    print(
        f"{'预期':<6} | {'代理地址前缀':<18} | {'实际出口IP':<15} | {'IP-API':<12} | {'IP2Loc':<12} | {'IPinfo':<8} | {'状态'}")
    print("-" * 110)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_proxy = {executor.submit(check_proxy, country, proxy): country for country, proxy in tasks}

        for future in as_completed(future_to_proxy):
            res = future.result()
            print(
                f"{res['Expected']:<6} | {res['Proxy_Host']:<18} | {res['Outbound_IP']:<15} | {res['IP-API']:<12} | {res['IP2Location']:<12} | {res['IPinfo']:<8} | {res['Status']}")


if __name__ == "__main__":
    main()