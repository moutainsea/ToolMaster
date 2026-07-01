"""
应用管理模块 (Application Manager Module)

功能：
  - 管理已扫描分析的系统应用，记录窗口名称和文件位置到 application_directory.txt
  - 展示当前正在使用的应用程序信息（窗口名称、文件位置、正在执行的任务）
"""
import os
from datetime import datetime
from toolmaster.utils import (
    logger, write_text_file, read_text_file,
    safe_filename, file_exists_and_nonempty
)
from toolmaster.config import DATA_DIR

DIRECTORY_FILE = os.path.join(DATA_DIR, "application_directory.txt")


class ApplicationManager:
    """应用管理器：维护应用目录，追踪当前工作状态"""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._ensure_directory_file()
        self._current_app = None   # 当前正在操作的应用
        self._current_task = None  # 当前正在执行的任务描述

    def _ensure_directory_file(self):
        """确保应用目录文件存在"""
        if not file_exists_and_nonempty(DIRECTORY_FILE):
            write_text_file(DIRECTORY_FILE, self._build_header())

    def _build_header(self):
        header = (
            "# ToolMaster 应用目录\n"
            "# 此文件记录所有已扫描、已分析的系统应用\n"
            "# 格式: 窗口名称 | 扫描文件 | 分析文件 | 添加时间\n"
            "# 生成时间: {}\n"
            "{}\n"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "-" * 80,
        )
        return header

    def register_application(self, window_name, scan_file, detail_file=None):
        """
        注册一个已扫描分析的应用到目录

        Args:
            window_name: 应用程序窗口名称
            scan_file: 扫描结果文件路径
            detail_file: 详细分析文件路径（可选）
        """
        # 检查是否已存在
        existing = self._find_entry(window_name)
        if existing:
            logger.info(f"应用 '{window_name}' 已存在于目录中，更新记录")
            self._update_entry(window_name, scan_file, detail_file)
            return

        detail_file_str = os.path.basename(detail_file) if detail_file else "N/A"
        entry = (
            f"{window_name} | "
            f"{os.path.basename(scan_file)} | "
            f"{detail_file_str} | "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\n"
        )
        # 读取现有内容并追加
        with open(DIRECTORY_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"已注册应用: '{window_name}' -> {DIRECTORY_FILE}")

    def _find_entry(self, window_name):
        """在目录中查找应用条目，返回行号(从1开始)和行内容"""
        content = read_text_file(DIRECTORY_FILE)
        for i, line in enumerate(content.split("\n"), 1):
            if line.startswith(window_name + " |"):
                return i, line
        return None, None

    def _update_entry(self, window_name, scan_file, detail_file):
        """更新已有应用的目录条目"""
        content = read_text_file(DIRECTORY_FILE)
        lines = content.split("\n")
        detail_file_str = os.path.basename(detail_file) if detail_file else "N/A"
        new_entry = (
            f"{window_name} | "
            f"{os.path.basename(scan_file)} | "
            f"{detail_file_str} | "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        )

        for i, line in enumerate(lines):
            if line.startswith(window_name + " |"):
                lines[i] = new_entry
                break

        write_text_file(DIRECTORY_FILE, "\n".join(lines))

    def get_directory(self):
        """获取应用目录的内容"""
        return read_text_file(DIRECTORY_FILE)

    def list_registered_apps(self):
        """列出所有已注册的应用名称列表"""
        content = read_text_file(DIRECTORY_FILE)
        apps = []
        for line in content.split("\n"):
            if " | " in line and not line.startswith("#") and not line.startswith("-"):
                parts = line.split(" | ")
                if parts:
                    apps.append(parts[0].strip())
        return apps

    def get_app_info(self, window_name):
        """获取指定应用的目录信息"""
        _, line = self._find_entry(window_name)
        if line:
            parts = line.split(" | ")
            if len(parts) >= 4:
                return {
                    "window_name": parts[0].strip(),
                    "scan_file": parts[1].strip(),
                    "detail_file": parts[2].strip(),
                    "registered_at": parts[3].strip(),
                }
        return None

    def set_current_working(self, app_name, task_description):
        """
        设置当前正在进行的工作状态

        Args:
            app_name: 当前正在操作的应用程序名称
            task_description: 正在执行的任务描述
        """
        self._current_app = app_name
        self._current_task = task_description
        logger.info(f"当前工作状态: [{app_name}] {task_description}")
        self._save_working_state()

    def clear_current_working(self):
        """清除当前工作状态"""
        self._current_app = None
        self._current_task = None
        self._save_working_state()

    def get_current_working(self):
        """获取当前工作状态"""
        return {
            "app_name": self._current_app,
            "task": self._current_task,
        }

    def _save_working_state(self):
        """将当前工作状态写入文件"""
        state_file = os.path.join(DATA_DIR, "current_working.txt")
        if self._current_app:
            content = (
                f"# 当前工作状态\n"
                f"# 更新时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"当前应用程序: {self._current_app}\n"
                f"当前任务: {self._current_task}\n"
            )
        else:
            content = (
                f"# 当前工作状态\n"
                f"# 更新时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"当前无正在执行的任务\n"
            )
        write_text_file(state_file, content)

    def show_status(self):
        """以文本形式返回当前管理模块的整体状态"""
        current = self.get_current_working()
        registered = self.list_registered_apps()

        status = [
            "=" * 50,
            "  ToolMaster 应用管理模块 - 状态概览",
            "=" * 50,
            "",
            f"已注册应用数: {len(registered)}",
        ]
        if registered:
            status.append("已注册应用列表:")
            for app in registered:
                status.append(f"  - {app}")

        status.append("")
        status.append("--- 当前工作状态 ---")
        if current["app_name"]:
            status.append(f"  应用程序: {current['app_name']}")
            status.append(f"  任务: {current['task']}")
        else:
            status.append("  当前无正在执行的任务")
        status.append("")
        return "\n".join(status)


# 模块级别便捷函数
_instance = None

def get_manager():
    """获取 ApplicationManager 单例"""
    global _instance
    if _instance is None:
        _instance = ApplicationManager()
    return _instance
