#!/usr/bin/env python3
"""
简单测试脚本，用于调试Huey的基本功能
"""

import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试基本导入try:
    from huey import RedisHuey
    from huey.exception_handler import ExceptionHandler
    print("✓ 基本模块导入成功")
except Exception as e:
    print(f"✗ 基本模块导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)

# 测试ExceptionHandler
try:
    eh = ExceptionHandler()
    print("✓ ExceptionHandler初始化成功")
    
    # 测试异常分类
    test_exception = ConnectionError("网络连接失败")
    task_metadata = {
        'task_name': 'test_task',
        'args': [],
        'kwargs': {},
        'retry_count': 0
    }
    should_retry, delay = eh.should_retry(test_exception, task_metadata)
    print(f"  - 异常分类测试: 连接异常是否重试? {should_retry}, 延迟: {delay}s")
except Exception as e:
    print(f"✗ ExceptionHandler测试失败: {e}")
    traceback.print_exc()

# 测试参数验证try:
    from huey.validation import validate_args, analyze_function_for_null_pointer
    print("✓ 参数验证模块导入成功")
    
    def test_func(x, y, z=None):
        return x + y + z if z else x + y
    
    issues = analyze_function_for_null_pointer(test_func)
    print(f"  - 空指针分析测试: {issues}")
except Exception as e:
    print(f"✗ 参数验证模块测试失败: {e}")
    traceback.print_exc()

print("\n=== 测试完成 ===")