"""
Skill 模块

混合方案的核心：Skill 封装领域知识，Executor 提供底层执行能力。

使用方式：
  from toolmaster.skills import init_skills, skill_registry, SkillResult
  
  init_skills(executor)  # 注册所有 Skill 并注入 executor
  skill = skill_registry.get("PowerPoint_CreateBlankPresentation")
  result = skill.run()
"""
from toolmaster.skills.base import (
    ApplicationSkill, SkillResult, SkillRegistry, skill_registry
)
from toolmaster.skills.powerpoint import POWERPOINT_SKILLS
from toolmaster.skills.general import GENERAL_SKILLS


# 所有内置 Skill
ALL_SKILLS = POWERPOINT_SKILLS + GENERAL_SKILLS


def init_skills(executor=None):
    """
    初始化所有 Skill：注册到注册中心，注入 executor
    
    Args:
        executor: TaskExecutor 实例
        
    Returns:
        SkillRegistry: 注册中心实例
    """
    for skill in ALL_SKILLS:
        if executor:
            skill.executor = executor
        skill_registry.register(skill)
    
    from toolmaster.utils import logger
    logger.info(f"已初始化 {skill_registry.get_count()} 个 Skill")
    
    return skill_registry


__all__ = [
    "ApplicationSkill", "SkillResult", "SkillRegistry", "skill_registry",
    "POWERPOINT_SKILLS", "GENERAL_SKILLS", "ALL_SKILLS",
    "init_skills",
]
