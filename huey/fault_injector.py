#!/usr/bin/env python
"""
Huey 故障注入工具
用于测试异常处理机制的有效性
"""

import argparse
import sys
import os
import random
import importlib

# 添加项目路径到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from huey.observability import inject_fault

def main():
    parser = argparse.ArgumentParser(description='Huey 故障注入工具')
    
    parser.add_argument('--inject', metavar='EXCEPTION_TYPE', type=str, required=True,
                        help='要注入的异常类型（如：NullPointerException、ConnectionTimeout）')
    
    parser.add_argument('--rate', metavar='RATE', type=float, default=1.0,
                        help='注入率（0-1，默认：1.0）')
    
    parser.add_argument('--message', metavar='MESSAGE', type=str, default='Fault injection',
                        help='异常消息')
    
    parser.add_argument('--test', action='store_true',
                        help='测试模式，不实际注入异常，只验证配置')
    
    args = parser.parse_args()
    
    if args.test:
        print(f"测试模式：将注入 {args.inject} 异常，注入率 {args.rate}")
        return 0
    
    try:
        # 注入异常
        inject_fault(args.inject, args.rate, args.message)
        print(f"成功注入 {args.inject} 异常")
        return 0
    except Exception as e:
        print(f"注入异常失败：{e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
