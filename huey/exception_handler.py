import re
import time
import logging
import traceback
import datetime
import threading
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict, List, Optional, Tuple, Any

from huey.exceptions import RetryTask
from huey.utils import normalize_time

logger = logging.getLogger('huey.exception_handler')

# 异常特征类型
exception_signature = Dict[str, Any]

class ExceptionHandler:
    """
    智能异常处理中心
    管理异常特征库、重试策略和自愈机制
    """
    def __init__(self):
        self._exception_signatures = {}
        self._custom_validators = defaultdict(list)
        self._resource_monitors = {}
        
        # 初始化内置异常特征
        self._init_builtin_signatures()
    
    def _init_builtin_signatures(self):
        """
        初始化内置的20+常见异常特征
        """
        # 网络类异常
        self.add_exception_signature(
            pattern=r'(ConnectionTimeout|ReadTimeout|SocketTimeout|TimeoutError)',
            category='NETWORK',
            recovery_strategy={
                'retry_type': 'exponential_backoff',
                'initial_delay': 1,
                'max_delay': 30,
                'max_retries': 8,
                'pre_retry_check': 'network_status'
            }
        )
        
        # 空指针异常
        self.add_exception_signature(
            pattern=r'(NullPointerException|NoneType)',
            category='NULL_POINTER',
            recovery_strategy={
                'retry_type': 'fixed_delay',
                'delay': 0.5,
                'max_retries': 2,
                'pre_retry_check': 'param_validation'
            }
        )
        
        # 资源耗尽异常
        self.add_exception_signature(
            pattern=r'(OutOfMemoryError|MemoryError|TooManyConnections|ResourceExhaustedError)',
            category='RESOURCE_EXHAUSTION',
            recovery_strategy={
                'retry_type': 'delayed_with_monitor',
                'delay': 5,
                'max_retries': 5,
                'resource_monitor': 'memory_usage'
            }
        )
        
        # IO异常
        self.add_exception_signature(
            pattern=r'(IOError|OSError|FileNotFoundError|PermissionError)',
            category='IO',
            recovery_strategy={
                'retry_type': 'fixed_delay',
                'delay': 2,
                'max_retries': 3
            }
        )
        
        # 数据库异常
        self.add_exception_signature(
            pattern=r'(DatabaseError|IntegrityError|OperationalError|ProgrammingError)',
            category='DATABASE',
            recovery_strategy={
                'retry_type': 'exponential_backoff',
                'initial_delay': 1,
                'max_delay': 10,
                'max_retries': 5
            }
        )
        
        # 并发异常
        self.add_exception_signature(
            pattern=r'(ConcurrentModificationException|TaskLockedException|LockTimeoutException)',
            category='CONCURRENCY',
            recovery_strategy={
                'retry_type': 'exponential_backoff',
                'initial_delay': 0.1,
                'max_delay': 5,
                'max_retries': 10
            }
        )
        
        # 其他常见异常
        self.add_exception_signature(
            pattern=r'(ValueError|TypeError|IndexError|KeyError|AttributeError)',
            category='VALIDATION',
            recovery_strategy={
                'retry_type': 'no_retry'
            }
        )
    
    def add_exception_signature(self, pattern: str, category: str, recovery_strategy: Dict[str, Any]):
        """
        添加异常特征
        
        :param pattern: 正则表达式模式，用于匹配异常堆栈信息
        :param category: 异常分类
        :param recovery_strategy: 恢复策略配置
        """
        self._exception_signatures[pattern] = {
            'category': category,
            'strategy': recovery_strategy
        }
    
    def register_validator(self, category: str, validator: Callable):
        """
        注册参数验证器
        """
        self._custom_validators[category].append(validator)
    
    def register_resource_monitor(self, name: str, monitor: Callable[[], bool]):
        """
        注册资源监控器
        """
        self._resource_monitors[name] = monitor
    
    def detect_exception_type(self, exception: Exception, traceback_str: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        检测异常类型并返回相应的恢复策略
        
        :param exception: 异常对象
        :param traceback_str: 完整的堆栈跟踪
        :return: (异常分类, 恢复策略) 或 (None, None) if no match found
        """
        exception_info = f"{type(exception).__name__}: {exception}"
        full_info = f"{exception_info}\n{traceback_str}"
        
        for pattern, sig in self._exception_signatures.items():
            if re.search(pattern, full_info):
                return sig['category'], sig['strategy']
        
        return None, None
    
    def should_retry(self, exception: Exception, traceback_str: str, retry_count: int, task_metadata: Dict[str, Any]) -> Tuple[bool, Optional[float]]:
        """
        决定是否重试任务以及重试延迟
        
        :param exception: 异常对象
        :param traceback_str: 完整的堆栈跟踪
        :param retry_count: 当前重试次数
        :param task_metadata: 任务元数据
        :return: (是否重试, 重试延迟秒数或None)
        """
        try:
            category, strategy = self.detect_exception_type(exception, traceback_str)
            
            if not strategy:
                logger.debug(f"任务 {task_metadata.get('id')} 发生未知异常, 不重试")
                return False, None
            
            # 获取最大重试次数，优先使用任务元数据中的配置
            max_retries = strategy.get('max_retries', 0)
            if 'max_retries' in task_metadata:
                max_retries = task_metadata['max_retries']
            elif 'retries' in task_metadata:
                max_retries = task_metadata['retries']  # 兼容TaskWrapper的retries参数
            
            if retry_count >= max_retries:
                logger.debug(f"任务 {task_metadata.get('id')} 重试次数已达上限 ({retry_count}/{max_retries}), 不再重试")
                return False, None
            
            retry_type = strategy.get('retry_type', 'fixed_delay')
            delay = None
            
            # 根据重试类型计算延迟
            if retry_type == 'exponential_backoff':
                initial_delay = strategy.get('initial_delay', 1)
                max_delay = strategy.get('max_delay', 30)
                # 指数退避: 1s, 2s, 4s, 8s, ..., max_delay
                delay = min(initial_delay * (2 ** retry_count), max_delay)
            elif retry_type == 'fixed_delay':
                delay = strategy.get('delay', 1)
            elif retry_type == 'delayed_with_monitor':
                delay = strategy.get('delay', 5)
                # 检查资源监控
                monitor_name = strategy.get('resource_monitor')
                if monitor_name and monitor_name in self._resource_monitors:
                    if not self._resource_monitors[monitor_name]():
                        logger.debug(f"任务 {task_metadata.get('id')} 资源监控 {monitor_name} 检查失败, 不重试")
                        return False, None
            
            # 检查预重试条件
            pre_retry_check = strategy.get('pre_retry_check')
            if pre_retry_check:
                if pre_retry_check == 'network_status':
                    # 简单的网络状态检查示例
                    if not self._check_network_status():
                        logger.debug(f"任务 {task_metadata.get('id')} 网络状态检查失败, 不重试")
                        return False, None
                elif pre_retry_check == 'param_validation':
                    # 参数验证修复
                    if not self._fix_parameters(task_metadata):
                        logger.debug(f"任务 {task_metadata.get('id')} 参数验证修复失败, 不重试")
                        return False, None
            
            logger.debug(f"任务 {task_metadata.get('id')} 将重试 (第 {retry_count+1} 次), 延迟 {delay} 秒")
            return True, delay
        except Exception as e:
            logger.error(f"异常处理模块出错: {e}")
            # 模块故障时回退到基本重试逻辑
            retry_count = task_metadata.get('retry_count', 0)
            max_retries = task_metadata.get('max_retries', 3) or task_metadata.get('retries', 3)
            if retry_count >= max_retries:
                return False, None
            # 默认指数退避重试
            delay = min(1 * (2 ** retry_count), 30)
            logger.debug(f"任务 {task_metadata.get('id')} 异常处理模块故障, 回退到默认重试策略")
            return True, delay
    
    def _check_network_status(self) -> bool:
        """
        简单的网络状态检查
        """
        try:
            import socket
            socket.create_connection(('8.8.8.8', 53), timeout=1)
            return True
        except (socket.timeout, socket.error):
            return False
    
    def _fix_parameters(self, task_metadata: Dict[str, Any]) -> bool:
        """
        修复可能导致空指针的参数
        """
        # 简单的示例：过滤None值并添加默认参数
        args = task_metadata.get('args', [])
        kwargs = task_metadata.get('kwargs', {})
        
        # 过滤args中的None值
        fixed_args = [arg for arg in args if arg is not None]
        
        # 为kwargs中的None值添加默认值
        fixed_kwargs = {}
        for key, value in kwargs.items():
            if value is None:
                fixed_kwargs[key] = self._get_default_value(key)
            else:
                fixed_kwargs[key] = value
        
        task_metadata['args'] = fixed_args
        task_metadata['kwargs'] = fixed_kwargs
        return True
    
    def _get_default_value(self, param_name: str) -> Any:
        """
        获取参数的默认值
        """
        # 简单的默认值映射
        defaults = {
            'url': '',
            'timeout': 3,
            'retries': 3,
            'data': {},
            'headers': {},
        }
        return defaults.get(param_name, None)

def safe_call(default_return: Callable = lambda: None):
    """
    安全调用装饰器，自动捕获并处理空指针等异常
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (AttributeError, TypeError, KeyError) as e:
                logger.warning(f"安全调用捕获到异常: {e}, 返回默认值")
                return default_return()
        return wrapper
    return decorator

exception_handler = ExceptionHandler()
