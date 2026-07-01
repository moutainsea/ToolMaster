"""
Skill 基类和注册机制

设计原则：
  - 每个 Skill 封装一个完整的应用操作（而非一个原子动作）
  - Skill 内部使用 executor 的底层方法（_click_element, _type_text 等）
  - Skill 自带 validate/verify/alternatives，提供比原子动作更强的可靠性
  - Agent 可选择调用 Skill 或降级为原子动作
"""
from toolmaster.utils import logger


class SkillResult:
    """Skill 执行结果"""
    
    def __init__(self, success, detail="", data=None, error=None):
        self.success = success
        self.detail = detail
        self.data = data or {}
        self.error = error
    
    def to_dict(self):
        return {
            "success": self.success,
            "detail": self.detail,
            "data": self.data,
            "error": self.error,
        }
    
    def __repr__(self):
        icon = "✓" if self.success else "✗"
        return f"{icon} {self.detail}"


class ApplicationSkill:
    """Skill 基类
    
    每个 Skill 代表一个完整的、有语义的应用操作。
    
    子类必须实现:
      - execute(): 核心执行逻辑
      
    子类可选覆写:
      - validate(): 执行前验证前置条件
      - verify(): 执行后验证结果
      - get_alternatives(): 返回失败时的备选方案
    """
    
    # --- 子类必须定义 ---
    name: str = ""           # Skill 唯一名称（如 "PowerPoint_CreateBlankPresentation"）
    app_name: str = ""       # 所属应用名称
    description: str = ""    # 功能描述（给 Agent 看）
    category: str = ""       # 分类：presentation/document/spreadsheet/general
    
    # --- 可选参数 ---
    timeout: int = 30        # 默认超时时间（秒）
    retry_count: int = 2     # 重试次数
    
    def __init__(self, executor=None):
        """
        Args:
            executor: TaskExecutor 实例（用于调用底层操作）
        """
        self.executor = executor  # 注入 executor，调用其底层方法
    
    def execute(self, **params):
        """
        核心执行逻辑
        
        Args:
            **params: Skill 特定参数
            
        Returns:
            SkillResult
        """
        raise NotImplementedError(f"{self.name} 未实现 execute()")
    
    def validate(self, **params):
        """
        执行前验证前置条件
        
        Returns:
            SkillResult: 验证通过返回 success=True，否则返回失败原因
        """
        return SkillResult(True, "无需前置验证")
    
    def verify(self, **params):
        """
        执行后验证结果
        
        Returns:
            SkillResult: 验证通过返回 success=True
        """
        return SkillResult(True, "无需后置验证")
    
    def get_alternatives(self):
        """
        返回失败时的备选方案列表
        
        Returns:
            list[tuple[str, dict]]: [(方案描述, 参数), ...]
        """
        return []
    
    def run(self, **params):
        """
        完整的 Skill 执行流程：validate → execute → verify
        
        Returns:
            SkillResult
        """
        logger.info(f"[Skill] {self.name} 开始执行 | 参数: {params}")
        
        # 1. 前置验证
        validate_result = self.validate(**params)
        if not validate_result.success:
            logger.warning(f"[Skill] {self.name} 前置验证失败: {validate_result.detail}")
            return validate_result
        
        # 2. 执行
        for attempt in range(self.retry_count + 1):
            result = self.execute(**params)
            if result.success:
                break
            logger.warning(f"[Skill] {self.name} 执行失败 (尝试 {attempt + 1}/{self.retry_count + 1}): {result.error}")
            
            # 尝试备选方案
            if not result.success and attempt < self.retry_count:
                alternatives = self.get_alternatives()
                if alternatives and attempt < len(alternatives):
                    alt_desc, alt_params = alternatives[attempt]
                    logger.info(f"[Skill] {self.name} 尝试备选方案: {alt_desc}")
                    params.update(alt_params)
        
        if not result.success:
            logger.error(f"[Skill] {self.name} 最终失败: {result.error}")
            return result
        
        # 3. 后置验证
        verify_result = self.verify(**params)
        if not verify_result.success:
            logger.warning(f"[Skill] {self.name} 后置验证失败: {verify_result.detail}")
            result.success = False
            result.error = verify_result.detail
            return result
        
        logger.info(f"[Skill] {self.name} 执行成功: {result.detail}")
        return result


class SkillRegistry:
    """Skill 注册中心
    
    管理所有注册的 Skill，支持按名称/应用/分类查询
    """
    
    _instance = None
    
    def __init__(self):
        self._skills: dict[str, ApplicationSkill] = {}
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, skill: ApplicationSkill):
        """注册一个 Skill"""
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' 已存在，将被覆盖")
        self._skills[skill.name] = skill
        logger.info(f"Skill 已注册: {skill.name} (应用: {skill.app_name}, 分类: {skill.category})")
    
    def unregister(self, skill_name: str):
        """注销一个 Skill"""
        if skill_name in self._skills:
            del self._skills[skill_name]
            logger.info(f"Skill 已注销: {skill_name}")
    
    def get(self, skill_name: str):
        """按名称获取 Skill"""
        return self._skills.get(skill_name)
    
    def get_by_app(self, app_name: str):
        """按应用名称获取 Skill 列表"""
        return [s for s in self._skills.values() if s.app_name.lower() == app_name.lower()]
    
    def get_by_category(self, category: str):
        """按分类获取 Skill 列表"""
        return [s for s in self._skills.values() if s.category == category]
    
    def list_all(self):
        """列出所有 Skill"""
        return list(self._skills.values())
    
    def get_skill_vocabulary(self, app_name=None):
        """
        生成 Skill 词汇表（供 Agent 参考）
        
        Args:
            app_name: 可选，只返回特定应用的 Skill
            
        Returns:
            str: 格式化的 Skill 词汇表
        """
        if app_name:
            skills = self.get_by_app(app_name)
            title = f"=== {app_name} 可用 Skill ==="
        else:
            skills = self.list_all()
            title = "=== 全部可用 Skill ==="
        
        if not skills:
            return title + "\n（暂无注册的 Skill）\n"
        
        lines = [title]
        
        # 按分类分组
        by_category = {}
        for s in skills:
            by_category.setdefault(s.category, []).append(s)
        
        for cat, cat_skills in by_category.items():
            lines.append(f"\n[{cat}]")
            for s in cat_skills:
                lines.append(f"  {s.name}")
                lines.append(f"    描述: {s.description}")
                lines.append(f"    应用: {s.app_name}")
        
        return "\n".join(lines)
    
    def get_count(self):
        return len(self._skills)


# 全局注册中心实例
skill_registry = SkillRegistry.get_instance()
