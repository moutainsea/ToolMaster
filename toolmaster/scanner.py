"""
窗口扫描模块 (Window Scanner Module)

功能：
  - 扫描特定名称窗口的UI元素，递归遍历子组件
  - 保存扫描结果到 xxx(窗口名称)_scan_element.txt
  - 调用Agent对扫描结果进行分析，生成 xxx(窗口名称)_scan_element_detail.txt
  - 支持多页面扫描：手动切换页面后扫描，自动识别不同页面并保存为 Page_xxx
"""
import os
import time
import json
import hashlib
from datetime import datetime
from toolmaster.utils import (
    logger, write_text_file, read_text_file,
    safe_filename, file_exists_and_nonempty
)
from toolmaster.config import DATA_DIR, load_config

# Windows UI Automation 相关库
try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import uiautomation as auto
    HAS_UIA = True
except ImportError:
    HAS_UIA = False

SCAN_DIR = os.path.join(DATA_DIR, "scans")
PAGE_DIR = os.path.join(DATA_DIR, "pages")  # 多页面扫描结果目录

# 页面重合度阈值（超过此值认为是同一页面）
PAGE_OVERLAP_THRESHOLD = 0.95


class WindowScanner:
    """窗口扫描器：扫描Windows窗口的UI元素树"""

    def __init__(self):
        self.config = load_config()
        self.max_depth = self.config["scanner"]["max_recursion_depth"]
        self.scan_delay_ms = self.config["scanner"]["scan_delay_ms"]
        os.makedirs(SCAN_DIR, exist_ok=True)
        os.makedirs(PAGE_DIR, exist_ok=True)
        
        # 多页面扫描状态
        self._multi_page_mode = False
        self._multi_page_app_name = None
        self._multi_page_count = 0
        self._multi_page_history = []  # 存储已扫描页面的元素指纹

    # ===== 元素指纹与重合度比较 =====

    def _get_element_fingerprint(self, elements):
        """
        获取元素的唯一指纹（用于比较两个页面的相似度）
        
        基于元素的 Name + AutomationId + ClassName + ControlType 生成哈希
        """
        fingerprints = set()
        for elem in elements:
            # 忽略位置信息（depth, rect），只关注元素标识
            fp_str = f"{elem.get('name', '')}|{elem.get('automation_id', '')}|{elem.get('class_name', '')}|{elem.get('control_type', '')}"
            if fp_str.strip("|"):  # 跳过空指纹
                fingerprints.add(fp_str)
        return fingerprints

    def _calculate_overlap_ratio(self, elements1, elements2):
        """
        计算两个元素集合的重合度
        
        Returns:
            float: 0.0-1.0 的重合度，1.0 表示完全相同
        """
        fp1 = self._get_element_fingerprint(elements1)
        fp2 = self._get_element_fingerprint(elements2)
        
        if not fp1 and not fp2:
            return 1.0  # 两个都为空，视为相同
        if not fp1 or not fp2:
            return 0.0  # 一个为空一个不为空，完全不同
        
        intersection = len(fp1 & fp2)
        union = len(fp1 | fp2)
        
        return intersection / union if union > 0 else 0.0

    def _is_same_page(self, elements1, elements2):
        """
        判断两个页面是否相同（重合度超过阈值）
        
        Returns:
            tuple: (is_same, overlap_ratio, details)
        """
        overlap = self._calculate_overlap_ratio(elements1, elements2)
        is_same = overlap >= PAGE_OVERLAP_THRESHOLD
        
        fp1 = self._get_element_fingerprint(elements1)
        fp2 = self._get_element_fingerprint(elements2)
        unique1 = len(fp1 - fp2)
        unique2 = len(fp2 - fp1)
        
        details = f"重合度: {overlap:.1%}, 元素1独有: {unique1}, 元素2独有: {unique2}"
        
        return is_same, overlap, details

    def list_windows(self):
        """列出当前所有可见的顶层窗口"""
        windows = []
        if not HAS_WIN32:
            logger.warning("pywin32 未安装，无法枚举窗口")
            return windows

        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    results.append({
                        "hwnd": hwnd,
                        "title": title,
                        "class_name": win32gui.GetClassName(hwnd),
                    })

        win32gui.EnumWindows(enum_callback, windows)
        return windows

    def find_window_by_title(self, title_keyword):
        """根据标题关键字查找窗口"""
        for win in self.list_windows():
            if title_keyword.lower() in win["title"].lower():
                return win
        return None

    def scan_window_elements(self, window_title, use_uia=True):
        """
        扫描指定窗口的所有UI元素，递归遍历子组件

        Args:
            window_title: 窗口标题（关键字匹配）
            use_uia: 是否使用 UI Automation 进行深度扫描

        Returns:
            list[dict]: 扫描到的元素列表，每个元素包含其属性和层级信息
        """
        logger.info(f"开始扫描窗口: '{window_title}'")

        elements = []

        if use_uia and HAS_UIA:
            elements = self._scan_with_uia(window_title)
        else:
            elements = self._scan_with_win32(window_title)

        # 保存原始扫描结果
        safe_name = safe_filename(window_title)
        scan_file = os.path.join(SCAN_DIR, f"{safe_name}_scan_element.txt")
        self._save_scan_result(elements, scan_file)

        logger.info(f"窗口 '{window_title}' 扫描完成，共发现 {len(elements)} 个元素")

        return elements, scan_file

    def _scan_with_uia(self, window_title):
        """使用 UI Automation 进行深度扫描"""
        elements = []
        try:
            target = auto.WindowControl(searchDepth=1, Name=window_title)
            if not target.Exists(maxSearchSeconds=3):
                # 尝试部分匹配
                target = auto.WindowControl(searchDepth=1, SubName=window_title)
                if not target.Exists(maxSearchSeconds=2):
                    logger.warning(f"未找到匹配窗口: '{window_title}'")
                    return elements

            self._scan_control_recursive(target, elements, depth=0)
        except Exception as e:
            logger.error(f"UIA 扫描失败: {e}")
        return elements

    def _scan_control_recursive(self, control, elements, depth):
        """递归扫描控件树"""
        if depth > self.max_depth:
            return

        # 获取控件基本属性
        try:
            element_info = {
                "depth": depth,
                "control_type": str(control.ControlTypeName) if hasattr(control, 'ControlTypeName') else str(type(control).__name__),
                "name": control.Name if hasattr(control, 'Name') else "",
                "automation_id": control.AutomationId if hasattr(control, 'AutomationId') else "",
                "class_name": control.ClassName if hasattr(control, 'ClassName') else "",
                "rect": str(control.BoundingRectangle) if hasattr(control, 'BoundingRectangle') else "",
                "is_enabled": control.IsEnabled if hasattr(control, 'IsEnabled') else False,
                "is_visible": control.IsOffscreen == False if hasattr(control, 'IsOffscreen') else True,
            }
            elements.append(element_info)
        except Exception:
            # 某些控件可能无法获取完整属性
            element_info = {
                "depth": depth,
                "control_type": str(type(control).__name__),
                "name": "",
                "automation_id": "",
                "class_name": "",
            }
            elements.append(element_info)

        # 递归扫描子控件
        try:
            children = control.GetChildren() if hasattr(control, 'GetChildren') else []
            for child in children:
                time.sleep(self.scan_delay_ms / 1000.0)
                self._scan_control_recursive(child, elements, depth + 1)
        except Exception:
            pass

    def _scan_with_win32(self, window_title):
        """使用 win32gui 进行基础扫描（不递归子控件）"""
        elements = []
        win = self.find_window_by_title(window_title)
        if not win:
            logger.warning(f"未找到窗口: '{window_title}'")
            return elements

        hwnd = win["hwnd"]
        elements.append({
            "depth": 0,
            "control_type": "Window",
            "name": win["title"],
            "hwnd": hwnd,
            "class_name": win["class_name"],
        })

        # 枚举子窗口作为基础扫描
        def enum_child_callback(child_hwnd, results):
            results.append({
                "depth": 1,
                "control_type": "ChildWindow",
                "name": win32gui.GetWindowText(child_hwnd),
                "hwnd": child_hwnd,
                "class_name": win32gui.GetClassName(child_hwnd),
            })

        sub_elements = []
        win32gui.EnumChildWindows(hwnd, enum_child_callback, sub_elements)
        elements.extend(sub_elements)
        return elements

    def _save_scan_result(self, elements, filepath):
        """将扫描结果保存为结构化的文本文件"""
        lines = [
            f"# 窗口元素扫描结果",
            f"# 扫描时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"# 元素总数: {len(elements)}",
            f"",
        ]

        for i, elem in enumerate(elements, 1):
            indent = "  " * elem.get("depth", 0)
            lines.append(f"{indent}[元素 {i}]")
            for key, value in elem.items():
                if key != "depth":
                    lines.append(f"{indent}  {key}: {value}")
            lines.append("")

        write_text_file(filepath, "\n".join(lines))

    def analyze_scanned_elements(self, window_title, scan_file, agent):
        """
        调用Agent对扫描结果进行分析，生成详细解释文件

        Args:
            window_title: 窗口名称
            scan_file: 扫描结果文件路径
            agent: Agent实例（用于调用LLM分析）
        """
        safe_name = safe_filename(window_title)
        detail_file = os.path.join(SCAN_DIR, f"{safe_name}_scan_element_detail.txt")

        scan_content = read_text_file(scan_file)
        if not scan_content:
            logger.warning(f"扫描文件为空: {scan_file}")
            return detail_file

        prompt = f"""
请分析以下应用程序窗口UI元素的扫描结果，为每个元素提供详细解释。

窗口名称: {window_title}

分析要求：
1. 对每个元素，解释其【含义】是什么（例如：按钮、输入框、下拉菜单等）
2. 对每个元素，解释其【作用】是什么（这个元素在应用程序中负责什么功能）
3. 判断该元素【是否需要配合其它组件使用】（例如：输入框需要配合"提交"按钮）
4. 如果多个元素之间存在协作关系，请指出

扫描结果：
{scan_content}

请以结构化的方式输出分析结果，每个元素单独一个段落。
"""

        # 调用Agent进行思考分析
        analysis = agent.think(prompt)

        result_lines = [
            f"# 窗口元素详细分析",
            f"# 窗口名称: {window_title}",
            f"# 分析时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"# 原始扫描: {os.path.basename(scan_file)}",
            f"",
            analysis,
        ]

        write_text_file(detail_file, "\n".join(result_lines))
        logger.info(f"元素详细分析已保存: {detail_file}")
        return detail_file

    # ===== 多页面扫描功能 =====

    def start_multi_page_scan(self, app_name):
        """
        开始多页面扫描模式
        
        Args:
            app_name: 应用程序名称
            
        Returns:
            dict: 扫描会话信息
        """
        self._multi_page_mode = True
        self._multi_page_app_name = safe_filename(app_name)
        self._multi_page_count = 0
        self._multi_page_history = []
        
        logger.info(f"开始多页面扫描: {app_name}")
        
        return {
            "mode": "multi_page",
            "app_name": app_name,
            "page_count": 0,
            "instructions": [
                "1. 输入 'scan-next' 扫描当前页面",
                "2. 手动切换到下一个页面",
                "3. 重复步骤1-2直到扫描完成",
                "4. 输入 'scan-done' 结束扫描",
                f"重合度阈值: {PAGE_OVERLAP_THRESHOLD:.0%}",
            ]
        }

    def scan_next_page(self, window_title):
        """
        扫描下一个页面（多页面模式）
        
        执行重合度比较，如果与已有页面重合度超过阈值则不保存
        
        Args:
            window_title: 窗口标题
            
        Returns:
            dict: 扫描结果，包含 is_new_page, overlap_ratio 等信息
        """
        if not self._multi_page_mode:
            logger.warning("未启用多页面扫描模式，请先执行 start-multi-scan")
            return {
                "success": False,
                "error": "未启用多页面扫描模式",
                "is_new_page": False,
            }
        
        # 执行扫描
        elements, scan_file = self.scan_window_elements(window_title, use_uia=True)
        
        if not elements:
            return {
                "success": False,
                "error": f"未找到窗口 '{window_title}' 或其UI元素",
                "is_new_page": False,
            }
        
        self._multi_page_count += 1
        fingerprint = self._get_element_fingerprint(elements)
        
        result = {
            "success": True,
            "page_index": self._multi_page_count,
            "elements_count": len(elements),
            "fingerprint_count": len(fingerprint),
            "is_new_page": False,
            "overlap_ratio": 0.0,
            "details": "",
        }
        
        # 与历史页面比较
        for i, history in enumerate(self._multi_page_history):
            is_same, overlap, details = self._is_same_page(elements, history["elements"])
            result["overlap_ratio"] = max(result["overlap_ratio"], overlap)
            result["details"] = details
            
            if is_same:
                result["is_new_page"] = False
                result["same_as_page"] = i + 1
                logger.info(f"页面{self._multi_page_count}与页面{i+1}重合度{overlap:.1%}，判定为同一页面，跳过保存")
                break
        else:
            # 没有找到重合页面，这是一个新页面
            result["is_new_page"] = True
        
        if result["is_new_page"]:
            # 保存为新页面
            page_filename = f"{self._multi_page_app_name}_Page_{self._multi_page_count}.txt"
            page_file = os.path.join(PAGE_DIR, page_filename)
            
            self._save_scan_result(elements, page_file)
            
            # 保存指纹到历史
            self._multi_page_history.append({
                "page_index": self._multi_page_count,
                "elements": elements,
                "fingerprint": fingerprint,
                "file": page_file,
            })
            
            result["page_file"] = page_file
            result["message"] = f"新页面！已保存为 Page_{self._multi_page_count}"
            logger.info(f"页面{self._multi_page_count}判定为新页面，已保存: {page_file}")
        else:
            result["message"] = f"与已有页面重合度{result['overlap_ratio']:.1%}，跳过保存"
        
        return result

    def finish_multi_page_scan(self):
        """
        结束多页面扫描模式
        
        Returns:
            dict: 扫描汇总信息
        """
        if not self._multi_page_mode:
            return {"error": "未启用多页面扫描模式"}
        
        summary = {
            "mode": "multi_page",
            "app_name": self._multi_page_app_name,
            "total_scans": self._multi_page_count,
            "new_pages_saved": len(self._multi_page_history),
            "pages": [],
        }
        
        for history in self._multi_page_history:
            summary["pages"].append({
                "page_index": history["page_index"],
                "file": history["file"],
                "fingerprint_count": len(history["fingerprint"]),
            })
        
        # 保存汇总文件
        summary_file = os.path.join(PAGE_DIR, f"{self._multi_page_app_name}_pages_summary.txt")
        lines = [
            f"# 多页面扫描汇总",
            f"# 应用名称: {self._multi_page_app_name}",
            f"# 扫描时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"# 总扫描次数: {self._multi_page_count}",
            f"# 识别页面数: {len(self._multi_page_history)}",
            f"# 重合度阈值: {PAGE_OVERLAP_THRESHOLD:.0%}",
            f"",
        ]
        for p in summary["pages"]:
            lines.append(f"Page {p['page_index']}: {p['file']} ({p['fingerprint_count']} 个唯一元素)")
        
        write_text_file(summary_file, "\n".join(lines))
        summary["summary_file"] = summary_file
        
        # 重置状态
        self._multi_page_mode = False
        self._multi_page_app_name = None
        self._multi_page_count = 0
        self._multi_page_history = []
        
        logger.info(f"多页面扫描完成，共识别 {len(summary['pages'])} 个不同页面")
        
        return summary

    def get_multi_page_status(self):
        """获取当前多页面扫描状态"""
        return {
            "mode": "multi_page" if self._multi_page_mode else "single",
            "app_name": self._multi_page_app_name,
            "scan_count": self._multi_page_count,
            "saved_pages": len(self._multi_page_history),
        }


# 模块级别的便捷函数
def scan_window(window_title, agent=None, use_uia=True):
    """扫描指定窗口并（可选）进行分析"""
    scanner = WindowScanner()
    elements, scan_file = scanner.scan_window_elements(window_title, use_uia=use_uia)
    detail_file = None

    if agent and elements:
        detail_file = scanner.analyze_scanned_elements(window_title, scan_file, agent)

    return {
        "elements": elements,
        "scan_file": scan_file,
        "detail_file": detail_file,
    }

def list_available_windows():
    """列出所有可扫描的窗口"""
    scanner = WindowScanner()
    return scanner.list_windows()
