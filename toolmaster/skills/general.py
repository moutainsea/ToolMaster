"""
通用 Skill 集合

跨应用的通用操作 Skill，不与特定应用绑定。
"""
import os
import time
import shutil
from toolmaster.skills.base import ApplicationSkill, SkillResult
from toolmaster.utils import logger


class General_WaitForCondition(ApplicationSkill):
    """等待指定条件满足
    
    通用等待操作，支持等待时间、等待元素出现等。
    """
    
    name = "General_Wait"
    app_name = "通用"
    description = "等待指定的时间或条件。可用于等待应用加载、对话框出现等场景。"
    category = "general"
    timeout = 60
    
    def execute(self, **params):
        condition_type = params.get("type", "time")
        
        if condition_type == "time":
            ms = params.get("milliseconds", 2000)
            time.sleep(ms / 1000.0)
            return SkillResult(True, f"等待 {ms}ms 完成")
        
        elif condition_type == "element":
            target = params.get("target", "")
            if not target or not self.executor:
                return SkillResult(False, "缺少目标元素或 executor")
            
            timeout_sec = params.get("timeout", 10)
            for i in range(timeout_sec * 2):
                element = self.executor._find_element(target)
                if element:
                    return SkillResult(True, f"元素已出现: {target}")
                time.sleep(0.5)
            return SkillResult(False, f"等待超时，未找到元素: {target}")
        
        else:
            return SkillResult(False, f"不支持的等待类型: {condition_type}")


class General_TakeScreenshot(ApplicationSkill):
    """截取当前屏幕截图"""
    
    name = "General_TakeScreenshot"
    app_name = "通用"
    description = "截取当前屏幕的截图并保存到指定路径。"
    category = "general"
    timeout = 5
    
    def execute(self, **params):
        save_path = params.get("save_path", "")
        filename = params.get("filename", f"screenshot_{int(time.time())}.png")
        
        try:
            from PIL import ImageGrab
        except ImportError:
            return SkillResult(False, "Pillow 未安装，无法截图", error="NoPIL")
        
        if not save_path:
            save_path = os.path.join(os.getcwd(), "data", "screenshots")
        
        os.makedirs(save_path, exist_ok=True)
        full_path = os.path.join(save_path, filename)
        
        try:
            img = ImageGrab.grab()
            img.save(full_path)
            return SkillResult(True, f"截图已保存: {full_path}", data={"path": full_path})
        except Exception as e:
            return SkillResult(False, f"截图失败: {e}", error=str(e))


class General_FileCopy(ApplicationSkill):
    """复制文件到指定位置"""
    
    name = "General_FileCopy"
    app_name = "通用"
    description = "将文件从源路径复制到目标路径。支持覆盖选项。"
    category = "general"
    timeout = 10
    
    def execute(self, **params):
        src = params.get("source", "")
        dst = params.get("destination", "")
        overwrite = params.get("overwrite", True)
        
        if not src or not dst:
            return SkillResult(False, "缺少源路径或目标路径", error="MissingPath")
        
        if not os.path.exists(src):
            return SkillResult(False, f"源文件不存在: {src}", error="SourceNotFound")
        
        try:
            if overwrite or not os.path.exists(dst):
                shutil.copy2(src, dst)
                return SkillResult(True, f"文件已复制: {src} -> {dst}")
            else:
                return SkillResult(False, f"目标文件已存在且不允许覆盖: {dst}", error="FileExists")
        except Exception as e:
            return SkillResult(False, f"复制失败: {e}", error=str(e))


class General_ExecuteCommand(ApplicationSkill):
    """执行系统命令"""
    
    name = "General_ExecuteCommand"
    app_name = "通用"
    description = "执行一条系统命令或脚本。可用于启动程序、运行批处理等。"
    category = "general"
    timeout = 60
    
    def execute(self, **params):
        command = params.get("command", "")
        shell = params.get("shell", True)
        capture = params.get("capture_output", True)
        
        if not command:
            return SkillResult(False, "未指定命令", error="NoCommand")
        
        try:
            import subprocess
            result = subprocess.run(
                command, shell=shell, 
                capture_output=capture,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                return SkillResult(True, f"命令执行成功: {command[:50]}", 
                                data={"stdout": result.stdout, "stderr": result.stderr})
            else:
                return SkillResult(False, f"命令返回非零: {result.returncode}",
                                data={"stdout": result.stdout, "stderr": result.stderr},
                                error=f"ExitCode={result.returncode}")
        except subprocess.TimeoutExpired:
            return SkillResult(False, f"命令超时（{self.timeout}s）", error="Timeout")
        except Exception as e:
            return SkillResult(False, f"命令执行失败: {e}", error=str(e))


class General_ReadTextFile(ApplicationSkill):
    """读取文本文件内容"""
    
    name = "General_ReadTextFile"
    app_name = "通用"
    description = "读取指定路径的文本文件内容。可用于读取日志、配置文件等。"
    category = "general"
    timeout = 5
    
    def execute(self, **params):
        filepath = params.get("path", "")
        encoding = params.get("encoding", "utf-8")
        max_lines = params.get("max_lines", 500)
        
        if not filepath:
            return SkillResult(False, "未指定文件路径", error="NoPath")
        
        if not os.path.exists(filepath):
            return SkillResult(False, f"文件不存在: {filepath}", error="FileNotFound")
        
        try:
            with open(filepath, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            content = "".join(lines[:max_lines])
            
            if total_lines > max_lines:
                content += f"\n... (共 {total_lines} 行，仅显示前 {max_lines} 行)"
            
            return SkillResult(True, f"已读取 {total_lines} 行",
                            data={"content": content, "total_lines": total_lines})
        except Exception as e:
            return SkillResult(False, f"读取失败: {e}", error=str(e))


class General_WriteTextFile(ApplicationSkill):
    """写入文本文件"""
    
    name = "General_WriteTextFile"
    app_name = "通用"
    description = "将文本内容写入指定文件路径。支持追加模式。"
    category = "general"
    timeout = 5
    
    def execute(self, **params):
        filepath = params.get("path", "")
        content = params.get("content", "")
        mode = params.get("mode", "w")  # w=覆盖, a=追加
        encoding = params.get("encoding", "utf-8")
        
        if not filepath or not content:
            return SkillResult(False, "缺少文件路径或内容", error="MissingParams")
        
        try:
            dirpath = os.path.dirname(filepath)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            
            with open(filepath, mode, encoding=encoding) as f:
                f.write(content)
            
            return SkillResult(True, f"文件已写入: {filepath} ({len(content)} 字符)")
        except Exception as e:
            return SkillResult(False, f"写入失败: {e}", error=str(e))


# ===== 注册所有通用 Skill =====

GENERAL_SKILLS = [
    General_WaitForCondition(),
    General_TakeScreenshot(),
    General_FileCopy(),
    General_ExecuteCommand(),
    General_ReadTextFile(),
    General_WriteTextFile(),
]
