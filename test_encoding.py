# -*- coding: utf-8 -*-
import sys
import os
print(f"Python版本: {sys.version}")
print(f"默认编码: {sys.getdefaultencoding()}")
print(f"文件系统编码: {sys.getfilesystemencoding()}")

# 检查当前目录
print(f"当前目录: {os.getcwd()}")
print(f"目录内容: {os.listdir('.')}")

# 尝试简单的导入
try:
    import huey
    print("huey导入成功")
except Exception as e:
    print(f"huey导入失败: {e}")
    import traceback
    traceback.print_exc()