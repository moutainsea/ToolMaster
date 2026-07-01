"""
配置模块 - 管理项目全局配置
"""
import os
import json

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据存储目录
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# 配置文件路径
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "config.json")

# 默认配置
DEFAULT_CONFIG = {
    "agent": {
        "api_type": "cloud",           # cloud 或 local
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_key": "",                  # 用户需自行填入
        "model": "gpt-4",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "scanner": {
        "max_recursion_depth": 10,      # 窗口元素递归扫描最大深度
        "scan_delay_ms": 100,           # 扫描间隔(毫秒)
        "save_format": "txt",           # 扫描结果保存格式
    },
    "executor": {
        "max_retry": 3,                 # 任务执行最大重试次数
        "screenshot_enabled": True,     # 是否启用截图反馈
        "screenshot_dir": os.path.join(DATA_DIR, "screenshots"),
    },
    "cli": {
        "prompt_prefix": "ToolMaster > ",
        "max_history": 50,              # 最大历史命令数
    },
}

def load_config():
    """加载配置文件，若不存在则创建默认配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # 合并默认配置（保证新增字段有默认值）
            merged = DEFAULT_CONFIG.copy()
            _deep_merge(merged, config)
            return merged
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """保存配置到文件"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def _deep_merge(base, override):
    """深度合并两个字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
