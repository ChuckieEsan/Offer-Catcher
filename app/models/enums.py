"""枚举类定义模块"""

from enum import Enum


class QuestionType(str, Enum):
    """题目类型枚举

    - knowledge: 客观基础题（八股文）
    - project: 项目深挖题（针对个人简历）
    - behavioral: 行为题（软技能）
    - scenario: 场景题（和企业业务场景相关的题目）
    """

    KNOWLEDGE = "knowledge"
    PROJECT = "project"
    BEHAVIORAL = "behavioral"
    SCENARIO = "scenario"


class MasteryLevel(int, Enum):
    """熟练度等级枚举

    - LEVEL_0: 完全不会/未复习
    - LEVEL_1: 比较熟悉
    - LEVEL_2: 已掌握
    """

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2