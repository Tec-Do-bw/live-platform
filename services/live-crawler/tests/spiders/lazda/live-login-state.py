#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2026/4/13 下午3:52
# @Author     : XBW
# @File       : live-login-state.py
# @Description: 测试LazLive 直播后台 的登录态
import requests

proxy = {
    "http": "socks5://c822ee15:2169010a@75.kookeey.info:27240",
    "https": "socks5://c822ee15:2169010a@75.kookeey.info:27240",
}


headers = {
    "accept": "application/json",
    "accept-language": "th,en-US;q=0.9,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://live.lazada.co.th",
    "priority": "u=1, i",
    "referer": "https://live.lazada.co.th/",
    "sec-ch-ua": "\"Google Chrome\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
}
cookies = {
    "JSID": "12833a7964153d22e523f6d9221c2547",
    "TID": "c859cba376dbe61fb4fe192d52161ceb",
    "CSRFT": "e6eaaf3ea9556",
    "_lang": "th_TH",
    "asc_uid": "101419424107",
    "asc_uid.sig": "KSmPxfN_8orZmQLoFZeGzwcVAKaBjH8HD4yDhZL7Mkc",
    "asc_uid_enc": "MTAxNDE5NDI0MTA3",
    "asc_uid_enc.sig": "RjPi65AyrEaRh-lwHtBgEiKBYv4ikJCve3Bosj-75Zo",
    "asc_seller_mp_type": "ASC_V2",
    "t_fv": "1776065826452",
    "t_uid": "Odzm8j0dY7ueNquGeHTtz7yRDy9Gx8eb",
    "t_sid": "j9OzLiUjE9B2ryR5an4suSSDELF9zqDV",
    "utm_channel": "NA",
    "_m_h5_tk": "6a4d141ae711ce3a9c470a1a924bfd66_1776074106933",
    "_m_h5_tk_enc": "46f8912c0169fb2ab3fbead6a7a4b0fb",
    "cna": "IotjInDMMkcCAa30NJ4Z8CM8",
    "xlly_s": "1",
    "lwrid": "AgGdhcY5TVgLkqVxA0SXX39uI13Q",
    "lwrtk": "AAIEad0Nwhkpxg06jz9a1LpqkeXDP3lU9whnlkMs2WabJoVktSdf7WA=",
    "lzd_cid": "98823e9b-2348-4a23-a0bb-7c9260e82933",
    "lzd_sid": "1e75e242a31bdefd2e2d1a479cdc2d1a",
    "_tb_token_": "5df507e335ee1",
    "epssw": "12*apE2R0wGGIHw20GGIGGGIJpgVJdDJRd8NT3hrsXFGGRzl-5z4UbF4yohX7IQKJbmGGGGH_eTAFsYf3jrjrjzpbEyb74YA3hpkuGkX1pPYMw2QhdsaJe7-KIrr9qOq-eSb7MIQrOOluqPZXjSvC3r6FtGGXetMFzLaHVnlDGtRGGGZO3teLOO7A8jZt0hR6xhmDGg5xxGss4GGMQFyWc_nGGGyDaxGGGUwn7rJ9q5swz2_fnsU3ptRItfPdlzRcnkmwITOnpMpFBV9zB09hoSgs4M7OVeQbLVhrGP1wKCuq_RJoRmfC40rP-1j0..",
    "isg": "BNTUgU7uQVtKHdVk3g5i_3ulpRJGLfgXP4XSXm61bd_iWXSjlj3ZpqvbXUlBpzBv",
    "tfstk": "gcSjcIVGOjcfloyY6jyrF-8E5mK1c8reMA9OKOnqBnKv6c1lwZJai-b6B6WwWhzm7h91_QS2gOdZC_1NBCo2DIo_C_fBQICw0fZ1NnLGuCR21h6GO8PUYkWcnhYTTWrEKLJIVhATbhUy2igkRRFUYkWAljqPkW7qt9wyIdK9HIKOe89Hhh39W1dJyppEMhKO689JCpp9BIdx2TpBwCK9X1B8FdAJHhKO6TeWIxn-NdzXBtwOAyAmQDANHQitXiUDlB6I7cnOVKTfYtd53tSWhEOp5A_5EiCPBiSDrSGvjT7C1NCLaqRARp1W8ZNIc61DB_pRgRuMFN6OxnYmQc5Bc1TdDUMtA9KDM39RvRuHagOV6iT8LDTw2M8pDazugF-Xd1IcGAiO6nAv0i8Sa4XD-QT1VUGbaC7FUiL597o5sF_O03IYwksrNDRQP_0sFem6FBy7FV0MPjfMssTtMvTvEKEUF8GSSXmtbxy7F2JXkLvA88wSNVf.."
}
url = "https://acs-m.lazada.co.th/h5/mtop.lazada.live.querylivesbystatus/1.0/"
params = {
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1776066687292",
    "sign": "de78be4763657c7c82ad78fe794d293a",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.querylivesbystatus",
    "type": "originaljson",
    "method": "POST",
    "api": "mtop.lazada.live.querylivesbystatus",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH"
}
data = {
    "data": "{\"_timezone\":-7,\"pageNum\":2,\"pageSize\":10,\"roomStatus\":\"Notice,Online,End,History\",\"orderByRoomStatus\":\"Notice,Online,End,History\"}"
}
response = requests.post(url, headers=headers, cookies=cookies, params=params, data=data, proxies=proxy)

print(response.text)
print(response)