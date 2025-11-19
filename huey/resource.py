import time
import logging
import threading
import resource
from typing import Dict, Any, Optional

logger = logging.getLogger('huey.resource')

class ResourceMonitor:
    """
    资源监控与防护
    监控和限制任务的资源使用
    """
    def __init__(self, max_memory: Optional[int] = None, max_file_handles: Optional[int] = None, 
                 scan_interval: int = 300):
        """
        初始化资源监控器
        
        :param max_memory: 最大内存占用（MB）
        :param max_file_handles: 最大文件句柄数
        :param scan_interval: 扫描间隔（秒）
        """
        self.max_memory = max_memory * 1024 * 1024 if max_memory else None  # 转换为字节
        self.max_file_handles = max_file_handles
        self.scan_interval = scan_interval
        self._running = False
        self._thread = None
        
    def start(self):
        """
        启动资源监控器
        """
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._scan_resources, daemon=True)
        self._thread.start()
        logger.info("资源监控器已启动")
    
    def stop(self):
        """
        停止资源监控器
        """
        self._running = False
        if self._thread:
            self._thread.join()
        logger.info("资源监控器已停止")
    
    def _scan_resources(self):
        """
        定期扫描资源使用情况
        """
        while self._running:
            try:
                self._check_resources()
            except Exception as e:
                logger.exception("资源扫描过程中出错: %s", e)
            
            # 等待下一次扫描
            for _ in range(self.scan_interval):
                if not self._running:
                    break
                time.sleep(1)
    
    def _check_resources(self):
        """
        检查资源使用情况
        """
        logger.debug("开始检查资源使用情况...")
        
        # 检查内存使用
        if self.max_memory:
            current_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if current_memory > self.max_memory:
                logger.warning(f"内存使用超过限制: {current_memory} bytes > {self.max_memory} bytes")
                # 尝试回收资源
                self._reclaim_resources()
        
        # 检查文件句柄
        if self.max_file_handles:
            try:
                file_handles = len(open('/proc/self/fd').readlines())
                if file_handles > self.max_file_handles:
                    logger.warning(f"文件句柄数超过限制: {file_handles} > {self.max_file_handles}")
            except Exception as e:
                logger.debug("无法获取文件句柄数: %s", e)
        
        logger.debug("资源检查完成")
    
    def _reclaim_resources(self):
        """
        尝试回收资源
        """
        logger.debug("尝试回收资源...")
        # 简单的资源回收实现，实际需要更复杂的逻辑
        # 例如：清理临时文件、关闭闲置连接等
        
    def check_resource_limits(self) -> bool:
        """
        检查资源是否在限制范围内
        """
        if self.max_memory:
            current_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if current_memory > self.max_memory:
                return False
        return True

def with_resource_limit(max_memory: Optional[int] = None, max_file_handles: Optional[int] = None):
    """
    资源限制装饰器
    
    :param max_memory: 最大内存占用（MB）
    :param max_file_handles: 最大文件句柄数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = ResourceMonitor(max_memory, max_file_handles, scan_interval=60)
            monitor.start()
            
            try:
                result = func(*args, **kwargs)
                monitor.stop()
                return result
            except Exception as e:
                monitor.stop()
                raise
        return wrapper
    return decorator

def isolate_task_execution(func):
    """
    任务执行环境隔离装饰器
    使用进程池隔离CPU密集型任务
    """
    def wrapper(*args, **kwargs):
        import multiprocessing
        with multiprocessing.Pool(processes=1) as pool:
            result = pool.apply(func, args, kwargs)
        return result
    return wrapper
