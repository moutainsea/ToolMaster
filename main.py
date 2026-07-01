#!/usr/bin/env python3
"""
ToolMaster - 系统应用程序智能操作工具
入口脚本
"""
import sys
import os

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolmaster.cli import main

if __name__ == "__main__":
    main()
