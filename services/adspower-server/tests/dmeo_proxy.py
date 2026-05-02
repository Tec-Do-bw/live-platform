import requests


def get_proxy_string(country_code):
    """
    模拟从 API 获取代理字符串的函数
    这里复用你之前的请求逻辑
    """
    url = "https://www.kkoip.com/pickdynamicips"
    params = {
        "auth": "pwd",
        "format": "4",  # 假设返回格式为 IP:Port:User:Pass (具体取决于format定义)
        "n": "1",
        "p": "socks5",  # 使用 socks5 协议
        "gate": "gate-hk.kkoip.com:14376",
        "g": country_code,  # 国家
        "r": "1440",  # 24小时
        "type": "txt",
        "sign": "043aeed6e29af919f54ba2fbead2b32e",  # 注意：切换国家可能需要重新计算签名
        "accessid": "1687631",
        "dl": "\\r\\n"
    }

    try:
        res = requests.get(url, params=params, verify=False)
        if res.status_code == 200 and "code" not in res.text:
            # 去除首尾空白符
            return res.text.strip()
        else:
            print(f"API请求失败: {res.text}")
            return None
    except Exception as e:
        print(f"API请求异常: {e}")
        return None


def verify_proxy(proxy_str):
    """
    验证代理是否可用
    :param proxy_str: 格式通常为 IP:Port:User:Pass
    """
    if not proxy_str:
        return

    print(f"1. 从API获取到的原始数据: {proxy_str}")

    # --- 关键步骤：解析代理字符串 ---
    # Kookeey format=4 通常返回: IP:Port:Username:Password
    try:
        parts = proxy_str.split(':')
        if len(parts) == 4:
            ip, port, user, pwd = parts
            # 构造 SOCKS5 代理 URL
            # 格式: socks5://user:pass@ip:port
            proxy_url = f"socks5://{user}:{pwd}@{ip}:{port}"
        elif len(parts) == 2:
            ip, port = parts
            # 无密码格式
            proxy_url = f"socks5://{ip}:{port}"
        else:
            print("代理格式无法识别，请检查 format 参数")
            return

        # 构造 requests 需要的字典
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        print(f"2. 构造的代理配置: {proxies}")

    except Exception as e:
        print(f"解析代理字符串出错: {e}")
        return

    # --- 验证步骤 ---
    print("3. 开始验证 IP...")
    try:
        # 访问 icanhazip.com 查看当前 IP
        # timeout 设置为 10 秒，防止代理不通导致程序卡死
        res = requests.get('http://icanhazip.com', proxies=proxies, timeout=15)

        if res.status_code == 200:
            current_ip = res.text.strip()
            print(f"✅ 代理验证成功！")
            print(f"   当前出口IP: {current_ip}")
            print(f"   目标代理IP: {parts[0]}")

            if current_ip == parts[0]:
                print("   (IP一致，隐匿成功)")
            else:
                print("   (IP不一致，可能是出口IP与入口IP不同)")
        else:
            print(f"❌ 代理连接通了，但状态码异常: {res.status_code}")

    except requests.exceptions.ProxyError:
        print("❌ 代理连接失败 (ProxyError): 请检查账号密码或IP白名单")
    except requests.exceptions.ConnectTimeout:
        print("❌ 连接超时 (Timeout): 代理网络可能不稳定")
    except Exception as e:
        print(f"❌ 发生其他错误: {e}")


if __name__ == "__main__":
    # 1. 获取 (假设获取美国代理)
    raw_proxy = get_proxy_string("US")

    # 2. 验证
    verify_proxy(raw_proxy)