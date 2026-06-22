"""
数据库连接池管理
解决单连接超时和线程安全问题
"""
from dbutils.pooled_db import PooledDB
import pymysql
from typing import Optional, Any, Tuple, List
from contextlib import contextmanager
from .logger import Logings

logger = Logings().get_logger()


class DatabasePool:
    """
    数据库连接池管理器
    
    特性：
    - 连接池复用，避免频繁创建/销毁连接
    - 自动重连机制
    - 线程安全
    - 上下文管理器支持
    """
    
    _instance: Optional['DatabasePool'] = None
    _pool: Optional[PooledDB] = None
    
    def __new__(cls):
        """单例模式，确保全局只有一个连接池实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(
        self,
        host: str,
        user: str,
        password: str,
        database: str,
        port: int = 3306,
        charset: str = 'utf8mb4',
        max_connections: int = 10,
        min_cached: int = 2,
        max_cached: int = 5,
        max_shared: int = 3,
        blocking: bool = True,
        max_usage: int = 0,
        ping: int = 1,
        use_dict_cursor: bool = False
    ):
        """
        初始化数据库连接池
        
        Args:
            host: 数据库主机地址
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名
            port: 数据库端口
            charset: 字符集
            max_connections: 最大连接数
            min_cached: 最小缓存连接数
            max_cached: 最大缓存连接数
            max_shared: 最大共享连接数
            blocking: 连接数达到最大时是否阻塞等待
            max_usage: 单个连接最大使用次数（0表示无限制）
            ping: 连接检查频率（0=不检查, 1=默认检查, 2=使用时检查, 4=提交时检查, 7=所有时候检查）
            use_dict_cursor: 是否使用字典游标（False=返回元组，True=返回字典）
        """
        if self._pool is not None:
            logger.warning("数据库连接池已经初始化，跳过重复初始化")
            return
        
        try:
            # ✅ 根据参数选择游标类型（默认返回元组以保持向后兼容）
            cursor_class = pymysql.cursors.DictCursor if use_dict_cursor else pymysql.cursors.Cursor
            
            self._pool = PooledDB(
                creator=pymysql,
                maxconnections=max_connections,
                mincached=min_cached,
                maxcached=max_cached,
                maxshared=max_shared,
                blocking=blocking,
                maxusage=max_usage,
                ping=ping,
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset=charset,
                cursorclass=cursor_class  # 根据参数选择返回格式
            )
            logger.info(
                f"数据库连接池初始化成功 | "
                f"host={host} database={database} "
                f"max_connections={max_connections}"
            )
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {e}", exc_info=True)
            raise
    
    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）
        
        使用示例:
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
                result = cursor.fetchall()
        
        Yields:
            数据库连接对象
        """
        if self._pool is None:
            raise RuntimeError("数据库连接池未初始化，请先调用 initialize()")
        
        conn = None
        try:
            conn = self._pool.connection()
            yield conn
        except Exception as e:
            logger.error(f"数据库连接获取失败: {e}", exc_info=True)
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    conn.close()  # 归还连接到池中
                except Exception as e:
                    logger.error(f"关闭数据库连接失败: {e}")
    
    def execute_query(
        self,
        sql: str,
        params: Optional[Tuple] = None,
        fetch_one: bool = False
    ) -> Optional[Any]:
        """
        执行查询SQL（SELECT）
        
        Args:
            sql: SQL查询语句
            params: 查询参数（使用 %s 占位符）
            fetch_one: 是否只返回一条记录
            
        Returns:
            查询结果（字典列表或单个字典）
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            
            if fetch_one:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()
            
            cursor.close()
            return result
    
    def execute_update(
        self,
        sql: str,
        params: Optional[Tuple] = None
    ) -> int:
        """
        执行更新SQL（INSERT/UPDATE/DELETE）
        
        Args:
            sql: SQL更新语句
            params: 更新参数（使用 %s 占位符）
            
        Returns:
            受影响的行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            affected_rows = cursor.execute(sql, params)
            conn.commit()
            cursor.close()
            return affected_rows
    
    def close(self):
        """关闭连接池"""
        if self._pool:
            try:
                self._pool.close()
                logger.info("数据库连接池已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接池失败: {e}")
            finally:
                self._pool = None


# 全局单例实例
db_pool = DatabasePool()
