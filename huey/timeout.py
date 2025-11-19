import time
import datetime
import logging
from functools import wraps
from typing import Callable, Dict, Optional

logger = logging.getLogger('huey.timeout')

# 存储任务历史执行时间
task_execution_history = {}  # key: task name, value: list of execution times in seconds

class TimeoutManager:
    """
    网络超时管理器
    提供多层超时控制和动态超时调整
    """
    def __init__(self):
        self.default_connect_timeout = 3
        self.default_read_timeout = 10
        self.default_task_timeout = 60
        
    def set_default_timeouts(self, connect_timeout: int = 3, read_timeout: int = 10, task_timeout: int = 60):
        """
        设置默认超时
        """
        self.default_connect_timeout = connect_timeout
        self.default_read_timeout = read_timeout
        self.default_task_timeout = task_timeout
    
    def get_dynamic_read_timeout(self, task_name: str) -> float:
        """
        根据历史执行数据动态计算读写超时
        
        :param task_name: 任务名称
        :return: 动态计算的读写超时时间
        """
        if task_name not in task_execution_history:
            return self.default_read_timeout
        
        # 计算最近3次执行的平均时间
        recent_executions = task_execution_history[task_name][-3:]
        if not recent_executions:
            return self.default_read_timeout
        
        average_time = sum(recent_executions) / len(recent_executions)
        # 使用1.5倍的平均时间作为超时
        return min(average_time * 1.5, self.default_read_timeout * 5)  # 上限为默认值的5倍
    
    def record_execution_time(self, task_name: str, duration: float):
        """
        记录任务执行时间
        """
        if task_name not in task_execution_history:
            task_execution_history[task_name] = []
        
        task_execution_history[task_name].append(duration)
        # 只保留最近20次执行记录
        if len(task_execution_history[task_name]) > 20:
            task_execution_history[task_name].pop(0)

def task_timeout(timeout: Optional[int] = None):
    """
    任务超时装饰器
    
    :param timeout: 任务超时时间（秒）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from huey.timeout import timeout_manager
            
            task_timeout_value = timeout or timeout_manager.default_task_timeout
            
            def timeout_func():
                raise TimeoutError(f"任务执行超时（超过 {task_timeout_value} 秒）")
            
            import threading
            timer = threading.Timer(task_timeout_value, timeout_func)
            timer.start()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                timer.cancel()
        return wrapper
    return decorator

def network_timeout(connect_timeout: Optional[int] = None, read_timeout: Optional[int] = None):
    """
    网络操作超时装饰器
    
    :param connect_timeout: 连接超时时间（秒）
    :param read_timeout: 读写超时时间（秒）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from huey.timeout import timeout_manager
            
            # 获取超时设置
            conn_timeout = connect_timeout or timeout_manager.default_connect_timeout
            rw_timeout = read_timeout or timeout_manager.default_read_timeout
            
            # 简单的超时实现，实际应该集成到具体的网络库中
            start_time = time.time()
            
            result = func(*args, **kwargs)
            
            # 检查总耗时
            total_time = time.time() - start_time
            if total_time > rw_timeout:
                raise TimeoutError(f"网络操作超时（总耗时 {total_time:.2f} 秒）")
            
            return result
        return wrapper
    return decorator
timeout_manager = TimeoutManager()
