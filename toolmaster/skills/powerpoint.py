"""
PowerPoint Skill 集合

封装 PowerPoint 操作的领域知识和最佳实践。
内部使用 executor 的底层 UIA 方法，对外暴露语义化接口。
"""
import os
import time
from toolmaster.skills.base import ApplicationSkill, SkillResult
from toolmaster.utils import logger

# 尝试导入 UIA
try:
    import uiautomation as auto
    HAS_UIA = True
except ImportError:
    HAS_UIA = False


class PowerPoint_Launch(ApplicationSkill):
    """启动 PowerPoint 应用程序"""
    
    name = "PowerPoint_Launch"
    app_name = "PowerPoint"
    description = "启动PowerPoint应用程序，并等待界面完全加载。包含欢迎页/启动页的等待。"
    category = "presentation"
    timeout = 30
    
    def execute(self, **params):
        try:
            import subprocess
            subprocess.Popen("start powerpnt", shell=True)
            time.sleep(5)  # 等待 PowerPoint 完全加载
            
            if HAS_UIA:
                window = auto.WindowControl(searchDepth=1, SubName="PowerPoint")
                if window.Exists(maxSearchSeconds=3):
                    return SkillResult(True, "PowerPoint 已启动")
                else:
                    return SkillResult(False, "PowerPoint 窗口未出现", error="WindowNotFound")
            return SkillResult(True, "PowerPoint 启动命令已发送")
        except Exception as e:
            return SkillResult(False, "启动失败", error=str(e))
    
    def get_alternatives(self):
        return [
            ("使用完整路径启动", {}),  # 可扩展
        ]


class PowerPoint_CreateBlankPresentation(ApplicationSkill):
    """创建空白演示文稿
    
    启动后必须执行此操作才能进入编辑状态。
    支持中英文界面。
    """
    
    name = "PowerPoint_CreateBlankPresentation"
    app_name = "PowerPoint"
    description = "在PowerPoint启动后创建一个新的空白演示文稿。需要先完成启动（PowerPoint_Launch）。支持中英文界面。"
    category = "presentation"
    timeout = 15
    
    # 领域知识：中英文模板名称映射
    TEMPLATE_NAMES = [
        "空白演示文稿",    # 中文
        "Blank Presentation",  # 英文
        "空白文档",         # 备选中文
    ]
    
    def execute(self, **params):
        if not self.executor or not HAS_UIA:
            return SkillResult(False, "UIA 未安装或 executor 未注入", error="NoExecutor")
        
        # 等待启动页加载
        time.sleep(2)
        
        # 尝试多种方式定位空白模板
        for template_name in self.TEMPLATE_NAMES:
            element = self.executor._find_element(template_name)
            if element:
                try:
                    element.Click()
                    time.sleep(2)
                    
                    # 验证：检查是否进入编辑状态（标题占位符应该可见）
                    title_placeholder = self.executor._find_element("标题占位符") or \
                                        self.executor._find_element("Title placeholder")
                    if title_placeholder:
                        return SkillResult(True, f"空白演示文稿已创建（通过点击'{template_name}'）")
                    else:
                        return SkillResult(True, f"已点击'{template_name}'（验证受限）")
                except Exception as e:
                    logger.warning(f"点击 '{template_name}' 失败: {e}")
                    continue
        
        # 方案2：尝试 Ctrl+N 快捷键
        try:
            self.executor._send_hotkey("ctrl+n")
            time.sleep(2)
            title_placeholder = self.executor._find_element("标题占位符") or \
                                self.executor._find_element("Title placeholder")
            if title_placeholder:
                return SkillResult(True, "通过 Ctrl+N 创建了空白演示文稿")
        except:
            pass
        
        return SkillResult(False, "无法创建空白演示文稿", error="TemplateNotFound")
    
    def get_alternatives(self):
        return [
            ("使用快捷键 Ctrl+N", {"use_hotkey": True}),
            ("通过文件菜单新建", {"use_menu": True}),
        ]


class PowerPoint_TypeInPlaceholder(ApplicationSkill):
    """在占位符中输入文本
    
    包含完整的 点击→聚焦→输入→验证 流程。
    """
    
    name = "PowerPoint_TypeInPlaceholder"
    app_name = "PowerPoint"
    description = "在指定的占位符中输入文本。可用于标题、副标题、内容等占位符。输入后会验证内容是否成功写入。"
    category = "presentation"
    timeout = 10
    
    # 领域知识：占位符名称映射（中英文）
    PLACEHOLDER_MAPPING = {
        "标题": ["标题占位符", "Title placeholder", "Title"],
        "副标题": ["副标题占位符", "Subtitle placeholder", "Subtitle"],
        "内容": ["内容占位符", "Content placeholder", "Content"],
    }
    
    def execute(self, **params):
        placeholder_type = params.get("placeholder_type", "标题")
        text = params.get("text", "")
        
        if not text:
            return SkillResult(False, "未指定要输入的文本", error="NoText")
        if not self.executor or not HAS_UIA:
            return SkillResult(False, "UIA 未安装或 executor 未注入", error="NoExecutor")
        
        # 1. 根据占位符类型查找目标
        target_names = self.PLACEHOLDER_MAPPING.get(placeholder_type, [placeholder_type])
        
        element = None
        found_name = None
        for name in target_names:
            element = self.executor._find_element(name)
            if element:
                found_name = name
                break
        
        if not element:
            # 最后尝试直接用传入的名称查找
            element = self.executor._find_element(placeholder_type)
            if element:
                found_name = placeholder_type
        
        if not element:
            return SkillResult(False, f"未找到占位符: {placeholder_type}", 
                            error="PlaceholderNotFound")
        
        # 2. 点击占位符获得焦点
        try:
            element.Click()
            time.sleep(0.3)
        except Exception as e:
            return SkillResult(False, f"点击占位符失败: {e}", error="ClickFailed")
        
        # 3. 输入文本
        try:
            if hasattr(element, 'SetFocus'):
                element.SetFocus()
                time.sleep(0.1)
            if hasattr(element, 'SendKeys'):
                # 先清空已有内容
                element.SendKeys("{ctrl}a")
                time.sleep(0.1)
                element.SendKeys(text)
                time.sleep(0.3)
            else:
                return SkillResult(False, "元素不支持输入操作", error="NoSendKeys")
        except Exception as e:
            return SkillResult(False, f"输入文本失败: {e}", error="TypeFailed")
        
        # 4. 验证输入
        try:
            actual = ""
            if hasattr(element, 'Name'):
                actual = element.Name
            elif hasattr(element, 'GetValue'):
                actual = element.GetValue()
            
            if text.strip() in actual:
                return SkillResult(True, f"已向'{placeholder_type}'输入: {text[:30]}")
            else:
                return SkillResult(False, f"文本验证失败，预期'{text[:20]}'，实际'{actual[:50]}'",
                                error="VerifyFailed")
        except:
            return SkillResult(True, f"已向'{placeholder_type}'输入（跳过验证）: {text[:30]}")


class PowerPoint_CreateSlide(ApplicationSkill):
    """创建新幻灯片
    
    选择指定的版式（标题幻灯片、标题和内容、空白等）。
    """
    
    name = "PowerPoint_CreateSlide"
    app_name = "PowerPoint"
    description = "在当前演示文稿中创建一张新幻灯片。可以指定版式（title/title_and_content/blank等）。"
    category = "presentation"
    timeout = 10
    
    LAYOUT_MAPPING = {
        "title": "标题幻灯片",
        "title_and_content": "标题和内容",
        "section_header": "节标题",
        "two_content": "两栏内容",
        "comparison": "比较",
        "blank": "空白",
    }
    
    def execute(self, **params):
        layout = params.get("layout", "title_and_content")
        layout_name = self.LAYOUT_MAPPING.get(layout, layout)
        
        if not self.executor or not HAS_UIA:
            return SkillResult(False, "UIA 未安装或 executor 未注入", error="NoExecutor")
        
        # 方案1：点击 Ribbon 上的"新建幻灯片"按钮
        try:
            # 查找并点击"新建幻灯片"按钮
            new_slide_btn = self.executor._find_element("新建幻灯片") or \
                           self.executor._find_element("New Slide")
            if new_slide_btn:
                new_slide_btn.Click()
                time.sleep(1)
                
                # 选择版式
                layout_element = self.executor._find_element(layout_name)
                if layout_element:
                    layout_element.Click()
                    time.sleep(1)
                    return SkillResult(True, f"已创建幻灯片（版式: {layout}）")
                else:
                    return SkillResult(True, "已点击新建幻灯片（版式选择未执行）")
        except Exception as e:
            logger.warning(f"通过按钮创建幻灯片失败: {e}")
        
        # 方案2：Ctrl+M 新建幻灯片，Ctrl+N 版式选择
        try:
            self.executor._send_hotkey("ctrl+m")
            time.sleep(1)
            return SkillResult(True, f"通过 Ctrl+M 创建了新幻灯片")
        except Exception as e:
            return SkillResult(False, f"创建幻灯片失败: {e}", error="CreateFailed")
    
    def get_alternatives(self):
        return [
            ("使用快捷键 Ctrl+M", {"use_hotkey": True}),
            ("通过右键菜单新建", {"use_context_menu": True}),
        ]


class PowerPoint_SavePresentation(ApplicationSkill):
    """保存演示文稿
    
    处理新文档和已有文档的不同保存逻辑。
    """
    
    name = "PowerPoint_SavePresentation"
    app_name = "PowerPoint"
    description = "保存当前的PowerPoint演示文稿。新文档会弹出另存为对话框，已有文档直接覆盖保存。"
    category = "presentation"
    timeout = 15
    
    def execute(self, **params):
        filename = params.get("filename", "演示文稿.pptx")
        save_path = params.get("save_path", "")
        
        if not self.executor or not HAS_UIA:
            return SkillResult(False, "UIA 未安装或 executor 未注入", error="NoExecutor")
        
        try:
            # Ctrl+S
            self.executor._send_hotkey("ctrl+s")
            time.sleep(2)
            
            # 检查是否弹出另存为对话框
            save_dialog = auto.WindowControl(searchDepth=1, Name="另存为")
            if save_dialog.Exists(maxSearchSeconds=2):
                # 新文档：填写文件名和路径
                filename_input = save_dialog.EditControl(searchDepth=3, ClassName="Edit")
                if filename_input.Exists():
                    filename_input.SetFocus()
                    time.sleep(0.3)
                    filename_input.SendKeys("{ctrl}a")
                    filename_input.SendKeys(filename)
                    time.sleep(0.5)
                
                # 点击保存按钮
                save_btn = save_dialog.ButtonControl(searchDepth=3, Name="保存(S)") or \
                          save_dialog.ButtonControl(searchDepth=3, Name="保存")
                if save_btn.Exists():
                    save_btn.Click()
                    time.sleep(1)
                    
                    # 检查是否有覆盖确认
                    confirm_btn = auto.ButtonControl(searchDepth=2, Name="是(Y)")
                    if confirm_btn.Exists(maxSearchSeconds=1):
                        confirm_btn.Click()
                        time.sleep(0.5)
                    
                    return SkillResult(True, f"演示文稿已保存: {filename}")
                else:
                    return SkillResult(False, "未找到保存按钮", error="SaveButtonNotFound")
            else:
                # 已有文档：直接保存成功
                return SkillResult(True, "演示文稿已保存（覆盖原有文件）")
        except Exception as e:
            return SkillResult(False, f"保存失败: {e}", error=str(e))
    
    def verify(self, **params):
        """验证文件是否保存成功"""
        filename = params.get("filename", "")
        if not filename:
            return SkillResult(True, "跳过文件验证")
        
        # 检查常见保存位置
        common_paths = [
            os.path.expanduser("~\\Documents"),
            os.path.expanduser("~\\Desktop"),
            os.getcwd(),
        ]
        for path in common_paths:
            full = os.path.join(path, filename)
            if os.path.exists(full):
                return SkillResult(True, f"文件验证通过: {full}")
        
        return SkillResult(False, f"未在常见位置找到文件: {filename}")


class PowerPoint_Close(ApplicationSkill):
    """关闭 PowerPoint"""
    
    name = "PowerPoint_Close"
    app_name = "PowerPoint"
    description = "关闭PowerPoint应用程序。如果文档未保存会触发保存提示。"
    category = "presentation"
    timeout = 10
    
    def execute(self, **params):
        save_before_close = params.get("save", False)
        
        if save_before_close and self.executor:
            # 先保存再关闭
            self.executor._send_hotkey("ctrl+s")
            time.sleep(1)
        
        try:
            import subprocess
            subprocess.run("taskkill /f /im POWERPNT.EXE", shell=True, capture_output=True)
            time.sleep(1)
            
            if HAS_UIA:
                window = auto.WindowControl(searchDepth=1, SubName="PowerPoint")
                if not window.Exists(maxSearchSeconds=2):
                    return SkillResult(True, "PowerPoint 已关闭")
                else:
                    return SkillResult(True, "PowerPoint 关闭命令已发送")
            return SkillResult(True, "PowerPoint 关闭命令已发送")
        except Exception as e:
            return SkillResult(False, f"关闭失败: {e}", error=str(e))


# ===== 注册所有 PowerPoint Skill =====

POWERPOINT_SKILLS = [
    PowerPoint_Launch(),
    PowerPoint_CreateBlankPresentation(),
    PowerPoint_TypeInPlaceholder(),
    PowerPoint_CreateSlide(),
    PowerPoint_SavePresentation(),
    PowerPoint_Close(),
]
