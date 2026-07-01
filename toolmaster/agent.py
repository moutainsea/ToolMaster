"""
Agent模块 - 连接云端/本地大模型API，进行思考（理解、分析、规划、决策）和行动（执行）

功能：
  - 连接云端/本地大模型API
  - think(): 理解、分析、规划、决策
  - act(): 生成执行指令
  - 记忆模块：结构化记录应用操作经验
"""
import os
import json
from datetime import datetime
from toolmaster.utils import (
    logger, write_text_file, read_text_file,
    safe_filename, file_exists_and_nonempty
)
from toolmaster.config import DATA_DIR, load_config

EXPERIENCE_DIR = os.path.join(DATA_DIR, "experience")


class Agent:
    """智能Agent：负责思考和生成执行指令"""

    def __init__(self):
        self.config = load_config()
        self.agent_config = self.config["agent"]
        self.conversation_history = []
        os.makedirs(EXPERIENCE_DIR, exist_ok=True)

    def think(self, prompt, context=None):
        """
        向大模型发送思考请求

        Args:
            prompt: 思考的提示词
            context: 附加上下文信息（可选）

        Returns:
            str: 模型返回的思考结果
        """
        api_url = self.agent_config["api_url"]
        api_key = self.agent_config.get("api_key", "")
        model = self.agent_config["model"]
        max_tokens = self.agent_config.get("max_tokens", 4096)
        temperature = self.agent_config.get("temperature", 0.7)

        # 构建消息
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个智能操作助手 ToolMaster 的思考核心。"
                    "你的职责是：\n"
                    "1. 理解用户意图和应用程序UI元素\n"
                    "2. 分析扫描到的窗口元素\n"
                    "3. 规划应用程序操作步骤\n"
                    "4. 做出操作决策\n"
                    "请始终以结构化、可执行的方式回复。"
                ),
            },
        ]

        if context:
            messages.append({"role": "system", "content": f"上下文信息:\n{context}"})

        messages.append({"role": "user", "content": prompt})

        # 调用API
        if not api_key:
            return self._mock_think(prompt)

        try:
            import requests
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            data = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            response = requests.post(
                api_url, headers=headers, json=data, timeout=60
            )
            response.raise_for_status()
            result = response.json()
            reply = result["choices"][0]["message"]["content"]
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            logger.error(f"Agent API 调用失败: {e}")
            return self._mock_think(prompt)

    def _mock_think(self, prompt):
        """
        当API不可用时的模拟思考（本地回退）
        用于开发调试阶段
        """
        logger.info("使用本地模拟模式进行思考")
        # 简单回显，实际部署时替换为真实API调用
        response = (
            f"[模拟思考模式] 收到提示: {prompt[:200]}...\n\n"
            "由于API未配置，此为模拟回复。请配置 config.json 中的 API 密钥以启用真实AI思考。"
        )
        return response

    def act(self, task_description, context=None, app_name=None):
        """
        生成执行指令：将任务描述转换为可执行的操作步骤（混合方案）
        
        支持两种步骤类型：
        1. Skill 调用：{ "skill": "SkillName", "params": {...}, "description": "..." }
        2. Direct Action：{ "action": "click", "target": "...", "description": "..." }

        Args:
            task_description: 任务描述
            context: 上下文（如窗口元素信息）
            app_name: 目标应用名称（用于加载扫描结果和 Skill 词汇表）

        Returns:
            dict: 包含操作步骤的结构化指令
        """
        # 自动加载应用的扫描结果作为上下文
        scan_context = context
        if app_name and not scan_context:
            scan_file = os.path.join(
                DATA_DIR, "scans", f"{safe_filename(app_name)}_scan_element_detail.txt"
            )
            if file_exists_and_nonempty(scan_file):
                scan_context = read_text_file(scan_file)
                logger.info(f"已加载应用 '{app_name}' 的扫描结果作为上下文")

        # 获取 Skill 词汇表
        skill_vocabulary = ""
        try:
            from toolmaster.skills import skill_registry
            skill_vocabulary = skill_registry.get_skill_vocabulary(app_name=app_name)
        except Exception:
            pass

        action_vocabulary = """
=== 操作词汇表（必须使用以下action值，不能使用自然语言）===
open       - 启动应用程序（target=应用名称，如"PowerPoint"）
click      - 点击UI元素（target=扫描到的元素名称或AutomationId）
type       - 输入文本（target=目标元素，content=要输入的文本）
select     - 选择菜单项或下拉选项（target=选项名称）
save       - 保存文件（target=文件路径或文件名）
wait       - 等待一段时间（target=等待毫秒数，如"3000"）
hotkey     - 按下快捷键（target=快捷键组合，如"ctrl+s"）
close      - 关闭窗口或应用（target=应用名称或窗口标题）
"""

        skill_section = ""
        if skill_vocabulary and skill_vocabulary.strip():
            skill_section = f"""
=== Skill 调用格式（优先使用）===
如果任务中的某个操作匹配以下 Skill，请优先使用 Skill 格式，而非手写 action：
{skill_vocabulary}

Skill 格式步骤示例：
{{
  "index": 序号,
  "type": "skill",
  "skill": "Skill名称（从上面选择）",
  "params": {{ "参数名": "参数值" }},
  "description": "步骤描述",
  "expected_result": "预期结果"
}}
"""

        prompt = f"""
请根据以下任务描述生成详细的、可执行的操作步骤。

任务: {task_description}

{action_vocabulary}
{skill_section}

=== 步骤格式要求（必须严格遵守）===

【优先】Skill 格式（当有匹配 Skill 时使用）：
{{
  "index": 步骤序号（从1开始）,
  "type": "skill",
  "skill": "Skill名称",
  "params": {{ "key": "value" }},
  "description": 步骤的文字描述,
  "expected_result": 执行后预期看到的结果
}}

【回退】Direct Action 格式（无匹配 Skill 时使用）：
{{
  "index": 步骤序号（从1开始）,
  "type": "action",
  "action": 操作类型（必须从上面的词汇表中选择）,
  "target": 操作目标（UI元素名称、AutomationId或应用名称）,
  "content": 输入内容（仅type操作需要，其他操作设为""）,
  "description": 步骤的文字描述,
  "expected_result": 执行后预期看到的结果
}}

=== 重要规则 ===
1. **优先使用 Skill 格式**：如果 Skill 词汇表中有适用的 Skill，必须优先使用
2. **无匹配 Skill 时使用 Direct Action**：作为回退方案
3. 对于type操作，必须在content字段中提供要输入的实际文本内容
4. 步骤之间要有合理的等待
5. 保存文件时，save操作的target设为文件名（不含路径）

"""

        if scan_context:
            prompt += f"""

=== 可用的UI元素（从扫描结果中获取）===
{scan_context}

请参考以上元素来选择合适的target。如果找不到匹配的元素，可以使用描述性名称。
"""

        result = self.think(prompt)

        # 尝试解析JSON（支持多种格式）
        try:
            if result:
                cleaned = result.replace("```json", "").replace("```", "").strip()

                # 先尝试直接解析整个字符串
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict) and "steps" in parsed:
                        return parsed
                    elif isinstance(parsed, list):
                        return {"steps": parsed}
                except json.JSONDecodeError:
                    pass

                # 格式1: [{...}] 数组格式（先检查数组，避免被对象格式误匹配）
                arr_start = cleaned.find("[")
                arr_end = cleaned.rfind("]") + 1
                if arr_start >= 0 and arr_end > arr_start:
                    json_str = cleaned[arr_start:arr_end]
                    try:
                        parsed = json.loads(json_str)
                        if isinstance(parsed, list):
                            return {"steps": parsed}
                    except json.JSONDecodeError:
                        pass

                # 格式2: {"steps": [...]} 对象格式
                json_start = cleaned.find("{")
                json_end = cleaned.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = cleaned[json_start:json_end]
                    try:
                        parsed = json.loads(json_str)
                        if isinstance(parsed, dict) and "steps" in parsed:
                            return parsed
                        elif isinstance(parsed, list):
                            return {"steps": parsed}
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.warning(f"JSON解析失败: {e}")

        # 解析失败，返回原始结果
        return {"raw_response": result, "steps": []}

    # ---- 记忆模块 ----

    def record_experience(self, app_name, task, result, lessons_learned):
        """
        记录应用操作经验到 xxx(应用名称)_experience.txt

        Args:
            app_name: 应用名称
            task: 执行的任务描述
            result: 执行结果
            lessons_learned: 经验教训总结
        """
        safe_name = safe_filename(app_name)
        exp_file = os.path.join(EXPERIENCE_DIR, f"{safe_name}_experience.txt")

        # 去重：检查是否已有类似经验
        if file_exists_and_nonempty(exp_file):
            existing = read_text_file(exp_file)
            if task in existing or lessons_learned[:50] in existing:
                logger.info(f"经验已存在，跳过重复写入: {app_name}")
                return exp_file

        new_entry = (
            f"\n{'=' * 60}\n"
            f"记录时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"应用名称: {app_name}\n"
            f"执行任务: {task}\n"
            f"执行结果: {result}\n"
            f"经验总结: {lessons_learned}\n"
            f"{'=' * 60}\n"
        )

        if file_exists_and_nonempty(exp_file):
            content = read_text_file(exp_file)
        else:
            content = (
                f"# {app_name} 操作经验记录\n"
                f"# 创建时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"# 此文件记录对 {app_name} 的操作经验和最佳实践\n\n"
            )

        write_text_file(exp_file, content + new_entry)
        logger.info(f"经验已记录: {exp_file}")
        return exp_file

    def query_experience(self, app_name, query_hint=None):
        """
        查询与应用相关的历史经验

        Args:
            app_name: 应用名称
            query_hint: 查询关键词提示（可选）

        Returns:
            str: 经验内容
        """
        safe_name = safe_filename(app_name)
        exp_file = os.path.join(EXPERIENCE_DIR, f"{safe_name}_experience.txt")

        if not file_exists_and_nonempty(exp_file):
            logger.info(f"应用 '{app_name}' 暂无经验记录")
            return ""

        content = read_text_file(exp_file)

        if query_hint:
            # 按关键字搜索相关经验
            relevant = []
            for section in content.split("=" * 60):
                if query_hint.lower() in section.lower():
                    relevant.append(section)
            if relevant:
                return "\n".join(relevant)
            else:
                return f"未找到与 '{query_hint}' 相关的经验，以下是全部经验：\n\n{content}"

        return content

    def get_all_experiences(self):
        """列出所有已记录经验的应用"""
        experiences = []
        if not os.path.exists(EXPERIENCE_DIR):
            return experiences
        for fname in os.listdir(EXPERIENCE_DIR):
            if fname.endswith("_experience.txt"):
                app_name = fname.replace("_experience.txt", "")
                filepath = os.path.join(EXPERIENCE_DIR, fname)
                size = os.path.getsize(filepath)
                experiences.append({"app_name": app_name, "file": fname, "size": size})
        return experiences
