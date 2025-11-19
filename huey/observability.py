import json
import logging
import time
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger('huey.observability')

# 异常统计
exception_stats = {
    'total': 0,
    'by_category': {},  # key: category, value: count
    'by_type': {},      # key: exception type, value: count
    'recoveries': 0,
    'failed': 0
}

# 告警配置
alert_config = {
    'exception_rate_threshold': 0.05,  # 5%
    'new_exception_alert': True,
    'alert_channels': []  # 支持邮件、Slack、Webhook等
}

class ExceptionLogger:
    """
    异常日志记录器
    记录异常处理全链路日志
    """
    def __init__(self):
        self.enable_json_logging = False
    
    def log_exception(self, task_id: str, exception: Exception, traceback_str: str, 
                     retry_count: int, recovery_strategy: Dict[str, Any], 
                     execution_node: str = 'local'):
        """
        记录异常日志
        
        :param task_id: 任务ID
        :param exception: 异常对象
        :param traceback_str: 堆栈跟踪
        :param retry_count: 重试次数
        :param recovery_strategy: 恢复策略
        :param execution_node: 执行节点
        """
        exception_info = {
            'timestamp': time.time(),
            'task_id': task_id,
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'traceback': traceback_str,
            'retry_count': retry_count,
            'recovery_strategy': recovery_strategy,
            'execution_node': execution_node,
            'error_category': recovery_strategy.get('category', 'UNKNOWN')
        }
        
        # 更新异常统计
        self._update_stats(exception_info)
        
        if self.enable_json_logging:
            logger.error(json.dumps(exception_info))
        else:
            logger.error(f"任务 {task_id} 执行异常: {type(exception).__name__}: {exception}, 重试次数: {retry_count}, 恢复策略: {recovery_strategy}")
            logger.debug(f"完整堆栈跟踪: {traceback_str}")
    
    def _update_stats(self, exception_info: Dict[str, Any]):
        """
        更新异常统计
        """
        exception_stats['total'] += 1
        
        # 按异常类型统计
        exc_type = exception_info['exception_type']
        exception_stats['by_type'][exc_type] = exception_stats['by_type'].get(exc_type, 0) + 1
        
        # 按异常分类统计
        category = exception_info['error_category']
        exception_stats['by_category'][category] = exception_stats['by_category'].get(category, 0) + 1
    
    def log_recovery(self, task_id: str, exception_type: str, retry_count: int):
        """
        记录恢复成功日志
        """
        exception_stats['recoveries'] += 1
        logger.info(f"任务 {task_id} 已从异常 {exception_type} 中恢复，重试次数: {retry_count}")

def get_exception_stats() -> Dict[str, Any]:
    """
    获取异常统计信息
    """
    return exception_stats.copy()

def get_metrics() -> Dict[str, float]:
    """
    获取监控指标
    """
    total = exception_stats['total'] or 1
    success_ratio = exception_stats['recoveries'] / total
    return {
        'huey_exceptions_total': exception_stats['total'],
        'huey_recoveries_success_ratio': success_ratio,
        'huey_failed_tasks': exception_stats['failed']
    }

def check_alert_conditions() -> List[str]:
    """
    检查告警条件
    """
    alerts = []
    
    # 检查异常率
    total = exception_stats['total']
    if total > 0:
        exception_rate = (total - exception_stats['recoveries']) / total
        if exception_rate > alert_config['exception_rate_threshold']:
            alerts.append(f"异常率超过阈值: {exception_rate:.2f} > {alert_config['exception_rate_threshold']:.2f}")
    
    return alerts

def inject_fault(exception_type: str, rate: float = 1.0, message: str = "Fault injection"):
    """
    注入故障
    
    :param exception_type: 异常类型
    :param rate: 注入率（0-1）
    :param message: 异常消息
    """
    import random
    if random.random() < rate:
        # 根据异常类型注入异常
        exception_map = {
            'NullPointerException': TypeError("'NoneType' object has no attribute 'xxx'"),
            'ConnectionTimeout': TimeoutError("Connection timed out"),
            'OutOfMemoryError': MemoryError("Out of memory"),
            'FileNotFoundError': FileNotFoundError("File not found"),
            'ValueError': ValueError("Invalid value"),
            'TypeError': TypeError("Invalid type")
        }
        
        if exception_type in exception_map:
            raise exception_map[exception_type]
        else:
            raise Exception(f"Injected fault: {message}")

exception_logger = ExceptionLogger()
