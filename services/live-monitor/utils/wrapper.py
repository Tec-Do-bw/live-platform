# -*- coding: UTF-8 -*-
# @author: xbw
# @file: wrapper
# @time: 2025/1/9
# @desc:
import time
import traceback
import hashlib
from functools import wraps
from collections import OrderedDict
from typing import TypeVar, Callable, Optional, Any, cast
from utils.logger import Logings

logger = Logings('wrapper_error').get_logger()

def dict2hash(d: dict):
    """将字典转换为哈希值"""
    d_str = str(sorted(d.items()))
    return hashlib.md5(d_str.encode()).hexdigest()


class WrapperKeyCache(OrderedDict):
    def __init__(self, max_size):
        super().__init__()
        self.max_size = max_size

    def get(self, key):
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def set(self, key, value):
        if key in self:
            self.move_to_end(key)
            return
        if len(self) >= self.max_size:
            self.popitem(last=False)
        self[key] = value


class Wrapper:
    F = TypeVar('F', bound=Callable[..., Optional[Any]])
    __cache = WrapperKeyCache(100)

    @staticmethod
    def no_error(default_value=None):
        """不异常"""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except:
                    return default_value

            return cast(Wrapper.F, wrapper)

        return decorator

    @staticmethod
    def save_error_log(func):
        @wraps(func)
        def wrap_func(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logger.info(traceback.format_exc())
                raise e
            else:
                return result

        return cast(Wrapper.F, wrap_func)

    @staticmethod
    def retry(retries=3, delay=0, *, save_error_log: bool = False):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                error = None
                for attempt in range(retries):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if save_error_log:
                            logger.info(traceback.format_exc())
                        if delay > 0:
                            time.sleep(delay)
                        error = e
                raise error

            return cast(Wrapper.F, wrapper)

        return decorator

    @staticmethod
    def cache_with_expiration(cache_time: int = 5):
        """缓存装饰器，缓存的过期时间以分钟为单位"""

        def decorator(func):
            cache = {}

            @wraps(func)
            def wrapper(*args, **kwargs):
                key = (args, dict2hash(kwargs))
                if key in cache:
                    result, timestamp = cache[key]
                    if time.time() - timestamp < cache_time * 60:
                        return result
                result = func(*args, **kwargs)
                cache[key] = (result, time.time())
                return result

            return cast(Wrapper.F, wrapper)

        return decorator

    @staticmethod
    def retry_until_done(retries=3, delay=10, *, desc: str = None):
        """
        装饰器：在指定次数内尝试调用被装饰的函数，每次尝试之间有指定的停留时间。
        :param retries: 尝试次数
        :param delay: 每次尝试后的停留时间（秒）
        :param desc: 没有正确返回的返回值的简述提示
        """
        _desc = desc or 'None'

        def decorator(func):
            cache_key = hashlib.md5(f"{id(func)}-{retries}-{delay}".encode('utf-8')).hexdigest()
            if cache_key in Wrapper.__cache:
                return Wrapper.__cache.get(cache_key)

            @wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(retries):
                    result: Optional[Any] = func(*args, **kwargs)
                    if result is None:
                        time.sleep(delay)
                        continue
                    return result
                logger.info(f"简述: {_desc};")
                raise ValueError(f"函数没有返回有效值; 简述: {_desc};")

            ww = cast(Wrapper.F, wrapper)
            Wrapper.__cache.set(cache_key, ww)
            return ww

        return decorator


if __name__ == '__main__':
    pass
