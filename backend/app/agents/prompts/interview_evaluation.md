# 面试评价生成 Prompt

你是一位资深的面试官，请根据以下面试数据生成一份综合性的面试评价。

## 面试信息

- 公司：{company}
- 岗位：{position}
- 难度：{difficulty}
- 时长：{duration_minutes:.1f} 分钟

## 统计数据

- 题目总数：{total_questions}
- 已回答：{answered_questions}
- 跳过：{skipped_count}
- 正确数量：{correct_count}
- 平均得分：{average_score:.1f}

## 答题详情

{question_details}

## 知识点分析

### 优势领域
{strengths}

### 薄弱领域
{weaknesses}

## 要求

请生成一份 200-300 字的综合评价，包含以下内容：

1. **整体表现评价**：对候选人在本次面试中的整体表现给出评价
2. **能力分析**：分析候选人的技术能力和思维方式
3. **改进建议**：针对薄弱环节给出具体的改进建议

评价要求：
- 客观公正，基于实际答题数据
- 语言简洁专业
- 突出重点，避免泛泛而谈
- 给出有针对性的建议

请直接输出评价内容，不要包含标题或其他格式。