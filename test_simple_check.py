#!/usr/bin/env python3
"""
简单测试脚本，用于检查基本功能是否正常工作
"""

import sys
import os
import traceback

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Python版本:", sys.version)
print("当前目录:", os.getcwd())
print("Python路径:", sys.path)

# 测试基本导入
try:
    from huey import RedisHuey
    print("✓ RedisHuey 导入成功")
except Exception as e:
    print(f"✗ RedisHuey 导入失败: {e}")
    traceback.print_exc()

# 测试异常处理模块
try:
    from huey.exception_handler import exception_handler
    print("✓ exception_handler 导入成功")
except Exception as e:
    print(f"✗ exception_handler 导入失败: {e}")
    traceback.print_exc()

# 测试参数验证模块
try:
    from huey.validation import validate_args
    print("✓ validate_args 导入成功")
except Exception as e:
    print(f"✗ validate_args 导入失败: {e}")
    traceback.print_exc()

print("\n所有检查完成!")