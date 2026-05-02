#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/12/8 下午2:44
# @Author     : XBW
# @File       : lazada.py
# @Description: 
import hashlib

# 1. 签名要素
token = "fdba1df1951a3c469ebc4689a752b516"  #为ck的_m_h5_tk获取
t = "1765522908013"
appKey = "24677475"
# 确保 data 字符串精确匹配，无多余空格
data_str = '{"liveUuid":"fb1962b5-3dbe-470f-9348-b5f0b21cc879","action":0}'
target_sign = "0d5c44824666be9d05d585ee3591a169"

# 2. 拼接
sign_str = f"{token}&{t}&{appKey}&{data_str}"

# 3. MD5 加密
m = hashlib.md5()
# 确保使用 UTF-8 编码
m.update(sign_str.encode('utf-8'))
calc_sign = m.hexdigest()

print(f"拼接字符串长度: {len(sign_str)} 字节")
print(f"拼接字符串: {sign_str}")
print("---")
print(f"计算出的 Sign: {calc_sign}")
print(f"目标 Sign:    {target_sign}")

if calc_sign == target_sign:
    print("\n✅ 恭喜！签名验证成功。")
else:
    print("\n❌ 签名验证失败。请检查时间戳或 Data 字符串是否有微小差异。")