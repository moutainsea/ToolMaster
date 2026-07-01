"""
工具模块 - 提供日志、文件操作等通用能力
"""
import os
import logging
from datetime import datetime
from toolmaster.config import DATA_DIR

def setup_logger(name="toolmaster", log_file=None):
    """创建统一的日志记录器"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 文件输出
    if log_file is None:
        log_dir = os.path.join(DATA_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"toolmaster_{datetime.now():%Y%m%d}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(module)s:%(lineno)d]: %(message)s"
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

def read_text_file(filepath):
    """读取文本文件内容，不存在则返回空字符串"""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def write_text_file(filepath, content):
    """写入文本文件，自动创建父目录"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def append_text_file(filepath, content):
    """追加内容到文本文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(content)

def safe_filename(name):
    """将字符串转换为安全的文件名（替换非法字符）"""
    illegal_chars = '<>:"/\\|?*'
    for ch in illegal_chars:
        name = name.replace(ch, "_")
    return name.strip()

def file_exists_and_nonempty(filepath):
    """检查文件是否存在且非空"""
    return os.path.exists(filepath) and os.path.getsize(filepath) > 0
