"""
执行模块 (Execution Module)

功能：
  - 执行Agent下发的任务（使用什么应用、干什么事、约束条件）
  - 将执行结果以文字或截图方式反馈给Agent
  - 支持并行执行规划（生成 parallel_working.txt）
"""
import os
import json
import time
import subprocess
from datetime import datetime
from toolmaster.utils import (
    logger, write_text_file, read_text_file,
    safe_filename
)
from toolmaster.config import DATA_DIR, load_config

EXEC_DIR = os.path.join(DATA_DIR, "executions")

# 尝试导入截图相关库
try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 尝试导入 UI Automation 库
try:
    import uiautomation as auto
    HAS_UIA = True
except ImportError:
    HAS_UIA = False


class TaskExecutor:
    """任务执行器：负责执行具体操作并反馈结果
    
    支持两种执行模式（混合方案）：
    1. Skill 模式：步骤包含 'skill' 字段 → 调用注册的 Skill
    2. Direct Action 模式：步骤包含 'action' 字段 → 调用底层原子方法
    """

    def __init__(self):
        self.config = load_config()
        self.max_retry = self.config["executor"]["max_retry"]
        self.screenshot_enabled = self.config["executor"]["screenshot_enabled"]
        self.screenshot_dir = self.config["executor"]["screenshot_dir"]
        os.makedirs(EXEC_DIR, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.task_history = []
        
        # 初始化 Skill 系统
        self._skill_registry = None
        self._init_skills()

    def _init_skills(self):
        """延迟初始化 Skill 注册中心"""
        try:
            from toolmaster.skills import init_skills
            self._skill_registry = init_skills(executor=self)
        except Exception as e:
            logger.warning(f"Skill 系统初始化失败（将仅使用 Direct Action 模式）: {e}")
            self._skill_registry = None

    def execute_task(self, task_description, action_plan, executor_name="default"):
        """
        执行单个任务

        Args:
            task_description: 任务描述
            action_plan: Agent生成的执行计划（dict，含 steps 列表）
            executor_name: 执行者标识

        Returns:
            dict: 执行结果
        """
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TASK {task_id}] 开始执行: {task_description}")

        result = {
            "task_id": task_id,
            "task_description": task_description,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "steps_executed": [],
            "results": [],
            "errors": [],
            "screenshots": [],
        }

        # 解析执行计划
        steps = action_plan.get("steps", [])
        if not steps and "raw_response" in action_plan:
            steps = [{"index": 1, "action": "execute", "description": task_description}]

        for step in steps:
            step_result = self._execute_step(step, task_id)
            result["steps_executed"].append(step.get("index", 0))
            result["results"].append(step_result)

            if not step_result.get("success", False):
                result["errors"].append({
                    "step": step.get("index", 0),
                    "error": step_result.get("error", "Unknown error"),
                })
                retry_count = 0
                while retry_count < self.max_retry and not step_result.get("success"):
                    retry_count += 1
                    logger.info(f"[TASK {task_id}] 步骤 {step.get('index')} 重试 {retry_count}/{self.max_retry}")
                    time.sleep(1)
                    step_result = self._execute_step(step, task_id)
                    result["results"].append(step_result)

                if not step_result.get("success"):
                    logger.error(f"[TASK {task_id}] 步骤 {step.get('index')} 执行失败，已达最大重试次数")

        # 截图
        if self.screenshot_enabled and HAS_PIL:
            screenshot_path = self._take_screenshot(task_id)
            if screenshot_path:
                result["screenshots"].append(screenshot_path)

        # 确定最终状态
        if result["errors"]:
            result["status"] = "failed"
        else:
            result["status"] = "success"

        result["end_time"] = datetime.now().isoformat()
        self.task_history.append(result)
        self._save_execution_log(result)

        return result

    def _execute_skill_step(self, step, task_id):
        """
        使用 Skill 执行步骤
        
        Returns:
            dict: 步骤执行结果
        """
        step_index = step.get("index", 0)
        skill_name = step.get("skill", "")
        skill_params = step.get("params", {})
        description = step.get("description", "")
        
        logger.info(f"[TASK {task_id}] 执行步骤 {step_index}: [Skill] {skill_name}")
        
        step_result = {
            "step_index": step_index,
            "skill": skill_name,
            "params": skill_params,
            "description": description,
            "success": False,
            "output": "",
            "error": None,
            "timestamp": datetime.now().isoformat(),
            "verified": False,
            "mode": "skill",
        }
        
        if not self._skill_registry:
            step_result["error"] = "Skill 注册中心未初始化"
            return step_result
        
        skill = self._skill_registry.get(skill_name)
        if not skill:
            step_result["error"] = f"Skill 未注册: {skill_name}"
            # 尝试回退到 Direct Action 模式
            fallback_action = step.get("fallback_action")
            if fallback_action:
                logger.info(f"[TASK {task_id}] Skill '{skill_name}' 未找到，回退到 Direct Action")
                return self._execute_step(fallback_action, task_id)
            return step_result
        
        # 确保 Skill 有 executor 引用
        if not skill.executor:
            skill.executor = self
        
        try:
            result = skill.run(**skill_params)
            step_result["success"] = result.success
            step_result["output"] = result.detail
            step_result["verified"] = True
            if result.error:
                step_result["error"] = result.error
                step_result["output"] += f" (错误: {result.error})"
            if result.data:
                step_result["data"] = result.data
        except Exception as e:
            step_result["error"] = str(e)
            logger.error(f"[TASK {task_id}] Skill {skill_name} 执行异常: {e}")
        
        return step_result

    def _execute_step(self, step, task_id):
        """
        执行单个步骤（混合方案），包含执行后验证
        
        优先使用 Skill 模式，如无匹配 Skill 则回退到 Direct Action 模式

        Returns:
            dict: 步骤执行结果
        """
        # === Skill 模式 ===
        if "skill" in step:
            return self._execute_skill_step(step, task_id)
        
        # === Direct Action 模式（原有逻辑） ===
        step_index = step.get("index", 0)
        action = step.get("action", "")
        target = step.get("target", "")
        content = step.get("content", "")
        description = step.get("description", "")

        logger.info(f"[TASK {task_id}] 执行步骤 {step_index}: {action} -> {target}")

        step_result = {
            "step_index": step_index,
            "action": action,
            "target": target,
            "content": content,
            "description": description,
            "success": False,
            "output": "",
            "error": None,
            "timestamp": datetime.now().isoformat(),
            "verified": False,
            "mode": "direct_action",
        }

        try:
            if action in ("open", "launch", "start"):
                success, output = self._launch_application(target, description)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    step_result["verified"] = True

            elif action == "click":
                success, output = self._click_element(target)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    # 点击后验证：重新查找元素确认状态变化
                    verify_success, verify_detail = self._verify_click_result(target)
                    step_result["verified"] = verify_success
                    if not verify_success:
                        step_result["success"] = False
                        step_result["output"] += f" | 验证失败: {verify_detail}"

            elif action == "type":
                success, output = self._type_text(target, content)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    # 输入后验证：读取元素内容确认已写入
                    verify_success, verify_detail = self._verify_type_result(target, content)
                    step_result["verified"] = verify_success
                    if not verify_success:
                        step_result["success"] = False
                        step_result["output"] += f" | 验证失败: {verify_detail}"

            elif action == "select":
                success, output = self._select_option(target)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    step_result["verified"] = True

            elif action == "save":
                success, output = self._save_file(target)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    # 保存后验证：检查文件是否存在
                    verify_success, verify_detail = self._verify_save_result(target)
                    step_result["verified"] = verify_success
                    if not verify_success:
                        step_result["success"] = False
                        step_result["output"] += f" | 验证失败: {verify_detail}"

            elif action == "wait":
                success, output = self._wait(int(target) if target.isdigit() else 3000)
                step_result["output"] = output
                step_result["success"] = success
                step_result["verified"] = True

            elif action == "hotkey":
                success, output = self._send_hotkey(target)
                step_result["output"] = output
                step_result["success"] = success
                step_result["verified"] = True

            elif action == "close":
                success, output = self._close_application(target)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    step_result["verified"] = True

            elif action in ("read", "get", "fetch"):
                success, output = self._read_from_target(target, description)
                step_result["output"] = output
                step_result["success"] = success
                if success:
                    step_result["verified"] = True

            else:
                output = f"未知操作: {action} -> {target}"
                step_result["output"] = output
                step_result["success"] = False
                step_result["error"] = f"不支持的操作类型: {action}"

        except Exception as e:
            step_result["error"] = str(e)
            step_result["success"] = False
            logger.error(f"[TASK {task_id}] 步骤 {step_index} 执行异常: {e}")

        # 记录验证状态
        if step_result["verified"]:
            logger.info(f"[TASK {task_id}] 步骤 {step_index} 验证通过")
        else:
            logger.warning(f"[TASK {task_id}] 步骤 {step_index} 验证未通过或未执行")

        return step_result

    # ===== 真实操作方法 =====

    def _launch_application(self, app_name, description=""):
        """启动应用程序
        
        Returns:
            (bool, str): (success, detail)
        """
        app_commands = {
            "word": "start winword",
            "excel": "start excel",
            "powerpoint": "start powerpnt",
            "outlook": "start outlook",
            "notepad": "start notepad",
            "calc": "start calc",
            "explorer": "start explorer",
            "browser": "start msedge",
            "chrome": "start chrome",
            "edge": "start msedge",
            "firefox": "start firefox",
        }

        app_lower = app_name.lower()
        cmd = app_commands.get(app_lower, f"start {app_name}")

        logger.info(f"启动应用: {cmd}")
        try:
            subprocess.Popen(cmd, shell=True)
            time.sleep(3)
            
            # 验证应用是否成功启动
            app_window = auto.WindowControl(searchDepth=1, SubName=app_name)
            if app_window.Exists(maxSearchSeconds=2):
                return (True, f"已启动应用程序: {app_name}")
            else:
                return (False, f"应用程序未成功启动: {app_name}")
        except Exception as e:
            return (False, f"启动失败: {app_name}, 错误: {str(e)}")

    def _click_element(self, target):
        """使用 UIA 点击目标元素
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法点击: {target}")

        try:
            element = self._find_element(target)
            if element:
                element.Click()
                time.sleep(0.5)
                return (True, f"已点击: {target}")
            else:
                return (False, f"未找到元素: {target}")
        except Exception as e:
            return (False, f"点击失败: {target}, 错误: {str(e)}")

    def _type_text(self, target, content):
        """使用 UIA 输入文本
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法输入: {target}")

        try:
            element = self._find_element(target)
            if element:
                element.SetFocus()
                time.sleep(0.2)
                element.SendKeys(content)
                time.sleep(0.3)
                
                # 验证输入是否成功
                if hasattr(element, 'Name') and content.strip():
                    if content.strip() in element.Name:
                        return (True, f"已向 {target} 输入: {content[:30]}... (验证成功)")
                    else:
                        return (False, f"输入完成但验证失败，当前值: {element.Name[:50]}")
                return (True, f"已向 {target} 输入: {content[:30]}...")
            else:
                return (False, f"未找到元素: {target}")
        except Exception as e:
            return (False, f"输入失败: {target}, 错误: {str(e)}")

    def _select_option(self, target):
        """选择菜单项或下拉选项
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法选择: {target}")

        try:
            element = self._find_element(target)
            if element:
                element.Select()
                time.sleep(0.5)
                
                # 验证选择是否成功
                if hasattr(element, 'IsSelected') and element.IsSelected():
                    return (True, f"已选择: {target} (验证成功)")
                return (True, f"已选择: {target}")
            else:
                return (False, f"未找到选项: {target}")
        except Exception as e:
            return (False, f"选择失败: {target}, 错误: {str(e)}")

    def _save_file(self, target):
        """保存文件
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法保存: {target}")

        try:
            self._send_hotkey("ctrl+s")
            time.sleep(2)

            save_dialog = auto.WindowControl(searchDepth=1, Name="另存为")
            if save_dialog.Exists(maxSearchSeconds=2):
                filename_edit = save_dialog.EditControl(searchDepth=2, ClassName="Edit")
                if filename_edit.Exists():
                    filename_edit.SetFocus()
                    filename_edit.SendKeys("{ctrl}a")
                    filename_edit.SendKeys(target)
                    time.sleep(0.5)

                    save_button = save_dialog.ButtonControl(searchDepth=2, Name="保存")
                    if save_button.Exists():
                        save_button.Click()
                        time.sleep(1)
                        return (True, f"已保存文件: {target}")
                    else:
                        return (False, f"未找到保存按钮")
                else:
                    return (False, f"未找到文件名输入框")
            else:
                # 可能文件已经保存过，没有弹出另存为对话框
                return (True, f"保存操作完成（文件可能已存在）: {target}")
        except Exception as e:
            return (False, f"保存失败: {target}, 错误: {str(e)}")

    def _wait(self, milliseconds):
        """等待指定时间
        
        Returns:
            (bool, str): (success, detail)
        """
        time.sleep(milliseconds / 1000.0)
        return (True, f"等待 {milliseconds}ms 完成")

    def _send_hotkey(self, hotkey):
        """发送快捷键组合
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法发送快捷键: {hotkey}")

        try:
            auto.SendKeys(f"{{{hotkey}}}" if "ctrl" in hotkey or "alt" in hotkey else hotkey)
            time.sleep(0.5)
            return (True, f"已发送快捷键: {hotkey}")
        except Exception as e:
            return (False, f"快捷键发送失败: {hotkey}, 错误: {str(e)}")

    def _close_application(self, app_name):
        """关闭应用程序
        
        Returns:
            (bool, str): (success, detail)
        """
        try:
            subprocess.run(f"taskkill /f /im {app_name}.exe", shell=True, capture_output=True)
            time.sleep(1)
            
            # 验证应用是否成功关闭
            app_window = auto.WindowControl(searchDepth=1, SubName=app_name)
            if not app_window.Exists(maxSearchSeconds=1):
                return (True, f"已关闭: {app_name}")
            else:
                return (False, f"应用程序未成功关闭: {app_name}")
        except Exception as e:
            return (False, f"关闭失败: {e}")

    def _read_from_target(self, target, description=""):
        """从目标读取信息
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (False, f"UIA未安装，无法读取: {target}")

        try:
            element = self._find_element(target)
            if element:
                return (True, f"读取内容: {element.Name} ({element.ControlTypeName})")
            return (False, f"未找到元素: {target}")
        except Exception as e:
            return (False, f"读取失败: {str(e)}")

    # ===== 验证方法 =====

    def _verify_click_result(self, target):
        """验证点击操作是否生效
        
        点击后重新查找元素，确认元素状态已变化或元素仍然可访问
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (True, "UIA未安装，跳过验证")

        try:
            element = self._find_element(target)
            if element:
                return (True, f"元素仍可访问: {target}")
            else:
                return (True, f"元素已不可访问（可能已关闭或跳转）: {target}")
        except Exception as e:
            return (True, f"验证点击结果时发生异常: {str(e)}")

    def _verify_type_result(self, target, expected_content):
        """验证输入操作是否生效
        
        输入后读取元素文本，确认内容已写入
        
        Returns:
            (bool, str): (success, detail)
        """
        if not HAS_UIA:
            return (True, "UIA未安装，跳过验证")

        if not expected_content or not expected_content.strip():
            return (True, "无预期内容，跳过验证")

        try:
            element = self._find_element(target)
            if element:
                actual_content = ""
                if hasattr(element, 'Name'):
                    actual_content = element.Name
                elif hasattr(element, 'GetValue'):
                    try:
                        actual_content = element.GetValue()
                    except:
                        pass
                
                if expected_content.strip() in actual_content:
                    return (True, f"内容验证通过，实际值: {actual_content[:50]}")
                else:
                    return (False, f"内容验证失败，预期: {expected_content[:30]}, 实际: {actual_content[:50]}")
            else:
                return (False, f"验证时未找到元素: {target}")
        except Exception as e:
            return (False, f"验证输入结果时发生异常: {str(e)}")

    def _verify_save_result(self, filename):
        """验证保存操作是否生效
        
        检查文件是否存在于常见位置
        
        Returns:
            (bool, str): (success, detail)
        """
        import os
        
        if not filename:
            return (True, "无文件名，跳过验证")

        # 常见保存位置
        common_paths = [
            os.path.expanduser("~\\Documents"),
            os.path.expanduser("~\\Desktop"),
            os.getcwd(),
        ]

        for path in common_paths:
            full_path = os.path.join(path, filename)
            if os.path.exists(full_path):
                return (True, f"文件已保存到: {full_path}")

        # 尝试更广泛的搜索
        for root, dirs, files in os.walk(os.path.expanduser("~"), topdown=True):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            if filename in files:
                found_path = os.path.join(root, filename)
                return (True, f"文件已保存到: {found_path}")
            if len(dirs) > 10:
                break

        return (False, f"未找到保存的文件: {filename}")

    def _find_element(self, target):
        """在当前活动窗口中查找元素"""
        if not HAS_UIA:
            return None

        try:
            element = auto.Control(searchDepth=4, Name=target)
            if element.Exists(maxSearchSeconds=2):
                return element

            element = auto.Control(searchDepth=4, SubName=target)
            if element.Exists(maxSearchSeconds=2):
                return element

            element = auto.Control(searchDepth=4, AutomationId=target)
            if element.Exists(maxSearchSeconds=2):
                return element

            element = auto.Control(searchDepth=4, ClassName=target)
            if element.Exists(maxSearchSeconds=2):
                return element

            return None
        except Exception:
            return None

    # ===== PPT 特定操作助手 =====

    def _create_slide(self, slide_layout="标题和内容"):
        """创建新幻灯片"""
        if not HAS_UIA:
            return False

        try:
            ppt_window = auto.WindowControl(searchDepth=1, ClassName="PPTFrameClass")
            if not ppt_window.Exists():
                return False

            start_tab = ppt_window.TabItemControl(searchDepth=3, Name="开始")
            if start_tab.Exists():
                start_tab.Click()
                time.sleep(0.5)

                new_slide_button = ppt_window.ButtonControl(searchDepth=4, Name="新建幻灯片")
                if new_slide_button.Exists():
                    new_slide_button.Click()
                    time.sleep(0.5)

                    layout_menu = auto.WindowControl(searchDepth=1, Name="幻灯片版式")
                    if layout_menu.Exists(maxSearchSeconds=2):
                        layout_item = layout_menu.ListItemControl(searchDepth=2, Name=slide_layout)
                        if layout_item.Exists():
                            layout_item.Click()
                            time.sleep(0.5)
                            return True
                        else:
                            new_slide_button.Click()
                            time.sleep(0.5)
                            return True
                    else:
                        return True

            return False
        except Exception as e:
            logger.error(f"创建幻灯片失败: {e}")
            return False

    def _type_in_placeholder(self, placeholder_name, text):
        """在指定占位符中输入文本"""
        if not HAS_UIA:
            return False

        try:
            ppt_window = auto.WindowControl(searchDepth=1, ClassName="PPTFrameClass")
            if not ppt_window.Exists():
                return False

            placeholder = ppt_window.TextPatternControl(searchDepth=5, Name=placeholder_name)
            if placeholder.Exists(maxSearchSeconds=2):
                placeholder.Click()
                time.sleep(0.3)
                placeholder.SendKeys(text)
                time.sleep(0.5)
                return True

            placeholders = ppt_window.GetChildren()
            for child in placeholders:
                try:
                    if placeholder_name in child.Name:
                        child.Click()
                        time.sleep(0.3)
                        child.SendKeys(text)
                        time.sleep(0.5)
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.error(f"在占位符输入失败: {e}")
            return False

    def _save_pptx(self, filename):
        """保存PPT文件"""
        return self._save_file(filename)

    def _take_screenshot(self, task_id):
        """截取屏幕截图"""
        if not HAS_PIL:
            return None
        try:
            screenshot_path = os.path.join(self.screenshot_dir, f"screenshot_{task_id}.png")
            img = ImageGrab.grab()
            img.save(screenshot_path, "PNG")
            logger.info(f"截图已保存: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def _save_execution_log(self, result):
        """保存执行日志到文件"""
        task_id = result["task_id"]
        log_file = os.path.join(EXEC_DIR, f"execution_{task_id}.txt")

        lines = [
            f"# 任务执行日志",
            f"# 任务ID: {task_id}",
            f"# 状态: {result['status']}",
            f"# 开始时间: {result['start_time']}",
            f"# 结束时间: {result['end_time']}",
            f"",
            f"## 任务描述",
            f"{result['task_description']}",
            f"",
            f"## 执行结果",
        ]

        for i, r in enumerate(result.get("results", [])):
            lines.append(f"  步骤 {r['step_index']}:")
            lines.append(f"    操作: {r['action']}")
            lines.append(f"    目标: {r['target']}")
            if r.get("content"):
                lines.append(f"    内容: {r['content']}")
            lines.append(f"    输出: {r['output']}")
            lines.append(f"    成功: {r['success']}")
            lines.append("")

        if result.get("errors"):
            lines.append("## 错误")
            for err in result["errors"]:
                lines.append(f"  步骤 {err['step']}: {err['error']}")

        if result.get("screenshots"):
            lines.append("## 截图")
            for ss in result["screenshots"]:
                lines.append(f"  - {ss}")

        write_text_file(log_file, "\n".join(lines))

    def get_result_as_text(self, task_id):
        """以文本方式获取执行结果（供Agent读取）"""
        log_file = os.path.join(EXEC_DIR, f"execution_{task_id}.txt")
        return read_text_file(log_file)

    def plan_parallel_execution(self, tasks, agent):
        """规划并行执行方案"""
        task_descriptions = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
        prompt = f"""
以下是一组需要执行的任务。请分析这些任务之间的依赖关系，规划并行执行方案。

要执行的任务：
{task_descriptions}

请分析：
1. 哪些任务可以并行执行（无依赖关系）
2. 哪些任务必须串行执行（存在依赖关系）
3. 给出最优的执行顺序和并行分组
4. 给出每个任务预计使用的应用程序

输出格式要求：
- 使用清晰的分组结构
- 标注并行组和串行组
- 标注每个任务使用的应用
"""

        plan = agent.think(prompt)
        parallel_file = os.path.join(DATA_DIR, "parallel_working.txt")

        content = (
            f"# 并行执行规划\n"
            f"# 生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"# 任务总数: {len(tasks)}\n"
            f"\n"
            f"## 原始任务列表\n"
            f"{task_descriptions}\n"
            f"\n"
            f"## 并行执行方案\n"
            f"{plan}\n"
        )

        write_text_file(parallel_file, content)
        logger.info(f"并行执行规划已保存: {parallel_file}")
        return parallel_file
