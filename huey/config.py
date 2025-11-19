# Huey 异常处理配置文件
# 智能异常分类与动态重试机制配置
EXCEPTIONS_CONFIG = {
    # 异常特征库扩展
    'additional_signatures': [],
    
    # 重试策略配置
    'retry_strategies': {
        'NETWORK': {
            'max_retries': 8,
            'initial_delay': 1,
            'max_delay': 30,
            'backoff_factor': 2,
            'status_check': True
        },
        'NULL_POINTER': {
            'max_retries': 2,
            'initial_delay': 0.5,
            'param_validation': True
        },
        'RESOURCE_EXHAUSTION': {
            'max_retries': 5,
            'initial_delay': 5,
            'resource_monitor_check': True
        }
    },
    
    # 任务优先级配置
    'priority_settings': {
        'critical': {
            'max_retries': 16
        }
    }
}

# 分布式任务执行防护屏障配置
PROTECTION_CONFIG = {
    # 空指针溯源防护配置
    'null_pointer_protection': {
        'enabled': True,
        'default_validator': 'not_none_validator',
        'static_analysis': True
    },
    
    # 网络超时自适应控制配置
    'network_timeout': {
        'default_connect_timeout': 3,
        'default_read_timeout': 10,
        'dynamic_timeout_factor': 1.5,
        'max_timeout': 60,
        'fallback_storage': None  # 备用存储配置
    }
}

# 任务执行状态自愈系统配置
SELF_HEALING_CONFIG = {
    # 分布式死锁检测与解除配置
    'deadlock_detection': {
        'enabled': True,
        'lock_ttl': 300,  # 锁超时时间（秒）
        'check_interval': 60,  # 检查间隔（秒）
        'max_contention': 5,  # 最大竞争次数
        'contention_window': 10  # 竞争检测时间窗口（秒）
    },
    
    # 资源泄露防护配置
    'resource_protection': {
        'enabled': True,
        'max_memory': None,  # 最大内存占用（MB）
        'max_file_handles': None,  # 最大文件句柄数
        'scan_interval': 300,  # 资源扫描间隔（秒）
        'isolation_enabled': True  # 是否启用任务执行环境隔离
    }
}

# 异常处理可观测性与调试增强配置
OBSERVABILITY_CONFIG = {
    # 异常全景日志配置
    'exception_logging': {
        'enabled': True,
        'json_format': False,
        'include_stacktrace': True,
        'include_task_params': True
    },
    
    # 实时监控与告警配置
    'monitoring': {
        'enabled': True,
        'metrics_enabled': True,
        'alert_threshold': 0.05,  # 异常率告警阈值
        'new_exception_alert': True,
        'alert_channels': []  # 告警渠道配置
    },
    
    # 故障模拟配置
    'fault_injection': {
        'enabled': False,
        'default_rate': 0.1
    }
}

# 全局配置开关
GLOBAL_CONFIG = {
    'enabled': True,
    'performance_threshold': 10  # 最大额外开销（毫秒）
}

def load_config(config_module=None):
    """
    加载配置
    
    :param config_module: 自定义配置模块
    :return: 合并后的配置
    """
    import sys
    import importlib
    
    config = {
        'exceptions': EXCEPTIONS_CONFIG.copy(),
        'protection': PROTECTION_CONFIG.copy(),
        'self_healing': SELF_HEALING_CONFIG.copy(),
        'observability': OBSERVABILITY_CONFIG.copy(),
        'global': GLOBAL_CONFIG.copy()
    }
    
    if config_module:
        if isinstance(config_module, str):
            # 从字符串加载模块
            if config_module in sys.modules:
                module = sys.modules[config_module]
            else:
                module = importlib.import_module(config_module)
        else:
            # 直接使用模块对象
            module = config_module
        
        # 合并配置
        if hasattr(module, 'EXCEPTIONS_CONFIG'):
            config['exceptions'].update(module.EXCEPTIONS_CONFIG)
        if hasattr(module, 'PROTECTION_CONFIG'):
            config['protection'].update(module.PROTECTION_CONFIG)
        if hasattr(module, 'SELF_HEALING_CONFIG'):
            config['self_healing'].update(module.SELF_HEALING_CONFIG)
        if hasattr(module, 'OBSERVABILITY_CONFIG'):
            config['observability'].update(module.OBSERVABILITY_CONFIG)
        if hasattr(module, 'GLOBAL_CONFIG'):
            config['global'].update(module.GLOBAL_CONFIG)
    
    return config
