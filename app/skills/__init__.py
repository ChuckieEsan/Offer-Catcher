"""Skill 加载器

从文件系统中加载 Skills（基于 LangChain Agent Skills 规范）。
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.utils.logger import logger


class Skill:
    """Skill 定义"""

    def __init__(self, name: str, description: str, content: str):
        self.name = name
        self.description = description
        self.content = content  # 完整的 SKILL.md 内容


class SkillLoader:
    """Skill 加载器"""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            # 默认使用 app/skills 目录
            base_dir = Path(__file__).parent.parent
            skills_dir = base_dir / "skills"
        self.skills_dir = Path(skills_dir)
        self._skills: Dict[str, Skill] = {}

    def load(self) -> Dict[str, Skill]:
        """加载所有 Skills"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return {}

        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = self._load_skill(item)
                if skill:
                    self._skills[skill.name] = skill

        logger.info(f"Loaded {len(self._skills)} skills: {list(self._skills.keys())}")
        return self._skills

    def _load_skill(self, skill_dir: Path) -> Optional[Skill]:
        """加载单个 Skill"""
        skill_md = skill_dir / "SKILL.md"

        try:
            content = skill_md.read_text(encoding="utf-8")

            # 解析 frontmatter
            name, description = self._parse_frontmatter(content)

            return Skill(
                name=name,
                description=description,
                content=content,
            )
        except Exception as e:
            logger.error(f"Failed to load skill from {skill_dir}: {e}")
            return None

    def _parse_frontmatter(self, content: str) -> tuple[str, str]:
        """解析 YAML frontmatter"""
        lines = content.split("\n")

        # 检查是否以 --- 开头
        if not lines[0].strip().startswith("---"):
            return "", ""

        # 找到结束 ---
        yaml_lines = []
        in_yaml = False
        for line in lines[1:]:
            if line.strip().startswith("---"):
                in_yaml = True
                break
            yaml_lines.append(line)

        if not yaml_lines:
            return "", ""

        # 解析 YAML
        try:
            data = yaml.safe_load("\n".join(yaml_lines))
            name = data.get("name", "")
            description = data.get("description", "")
            return name, description
        except Exception as e:
            logger.warning(f"Failed to parse frontmatter: {e}")
            return "", ""

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定 Skill"""
        if not self._skills:
            self.load()
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        """列出所有 Skills"""
        if not self._skills:
            self.load()
        return list(self._skills.values())

    def get_system_prompt_section(self) -> str:
        """获取注入到 Agent system prompt 的 Skills 部分"""
        if not self._skills:
            self.load()

        lines = ["## Available Skills"]
        lines.append("")
        lines.append("You have access to the following skills:")
        lines.append("")

        for skill in self._skills.values():
            lines.append(f"### {skill.name}")
            lines.append(f"{skill.description}")
            lines.append("")

        return "\n".join(lines)


# 全局加载器
_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """获取全局 Skill 加载器"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader


def get_skills_prompt() -> str:
    """获取 Skills prompt 部分"""
    loader = get_skill_loader()
    return loader.get_system_prompt_section()


__all__ = ["Skill", "SkillLoader", "get_skill_loader", "get_skills_prompt"]