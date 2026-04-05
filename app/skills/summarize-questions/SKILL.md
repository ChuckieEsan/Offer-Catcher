---
name: summarize-questions
description: 梳理某个公司或岗位的常考知识点。当你需要分析某个公司/岗位的面试题目的类型分布、熟练度分布、热门知识点时使用此 Skill。
---

# 梳理常考知识点

## Overview

此 Skill 用于分析题库数据，梳理某个公司或岗位的常考知识点、题目类型分布、熟练度分布等信息。

## Instructions

### 1. 收集题目数据

使用 Qdrant 检索题目数据：
- 调用 qdrant 的 `scroll_all` 方法获取所有题目
- 根据用户指定的 company 和 position 进行过滤

### 2. 分析数据

统计以下信息：
- 题目总数
- 已作答题目数
- 题目类型分布（knowledge, algorithm, project, behavioral, scenario）
- 熟练度分布（0: 未掌握, 1: 熟悉, 2: 已掌握）
- 热门知识点（core_entities）

### 3. 输出结果

以 Markdown 格式输出分析结果，包含：
- 数据概览表格
- 题目类型分布
- 熟练度分布
- Top 知识点列表

## Example Output

```
📊 数据概览
- 总题目数: 150
- 已作答: 120

📈 题目类型分布
- knowledge: 80 (53.3%)
- algorithm: 50 (33.3%)
- project: 20 (13.3%)

🏷️ Top 10 知识点
- Python: 出现 30 次
- 机器学习: 出现 25 次
- 深度学习: 出现 20 次
```