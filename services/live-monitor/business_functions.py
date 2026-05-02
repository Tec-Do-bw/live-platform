import requests
from threading import Thread 
import time




# ✅ ✅ ✅ ✅ 求和测试 ✅ ✅ ✅ ✅ ✅ 
# 测试一组数据求和
def sum_numbers(numbers: list):
    """对一组数字进行求和"""
    return sum(numbers)

# 自动注册所有业务函数:不要在这个列表中添加非业务函数
business_functions = [
    sum_numbers
] 




