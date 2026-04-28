"""评测报告生成和导出模块

支持 JSON、Markdown、CSV 格式输出。
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def export_json(results: list[Any], output_dir: Path) -> Path:
    """导出 JSON 结果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"eval_{timestamp}.json"

    # 转换为 dict
    data = []
    for r in results:
        if hasattr(r, "__dict__"):
            d = r.__dict__
        elif isinstance(r, dict):
            d = r
        else:
            d = {"result": str(r)}
        data.append(d)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


def export_csv(results: list[Any], output_dir: Path) -> Path:
    """导出 CSV 结果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"metrics_{timestamp}.csv"

    if not results:
        return filepath

    # 获取字段
    first = results[0]
    if hasattr(first, "__dict__"):
        fields = list(first.__dict__.keys())
    elif isinstance(first, dict):
        fields = list(first.keys())
    else:
        fields = ["result"]

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for r in results:
            if hasattr(r, "__dict__"):
                writer.writerow(r.__dict__)
            elif isinstance(r, dict):
                writer.writerow(r)
            else:
                writer.writerow({"result": str(r)})

    return filepath


def export_markdown(results: list[Any], report_text: str, output_dir: Path) -> Path:
    """导出 Markdown 报告"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"report_{timestamp}.md"

    content = f"""# Memory Agent LLM-as-Judge 评测报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 评估结果

{report_text}

## 详细数据

### 结果列表

```json
{json.dumps([r.__dict__ if hasattr(r, "__dict__") else r for r in results], ensure_ascii=False, indent=2)[:10000]}
```
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def aggregate_metrics(results: list[Any]) -> dict:
    """聚合指标统计"""
    if not results:
        return {}

    # 提取分数
    decision_scores = []
    content_scores = []
    passed_count = 0

    categories = {}

    for r in results:
        d = r.__dict__ if hasattr(r, "__dict__") else r

        if d.get("decision_overall_score"):
            decision_scores.append(d["decision_overall_score"])

        if d.get("content_overall_score"):
            content_scores.append(d["content_overall_score"])

        if d.get("passed"):
            passed_count += 1

        # 按类别聚合
        name = d.get("scenario_name", d.get("case_id", "unknown"))
        cat = get_category(name)
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0, "decision_scores": []}
        categories[cat]["total"] += 1
        if d.get("decision_overall_score"):
            categories[cat]["decision_scores"].append(d["decision_overall_score"])
        if d.get("passed"):
            categories[cat]["passed"] += 1

    return {
        "total_cases": len(results),
        "passed_count": passed_count,
        "pass_rate": passed_count / len(results) if results else 0,
        "avg_decision_score": sum(decision_scores) / len(decision_scores) if decision_scores else 0,
        "avg_content_score": sum(content_scores) / len(content_scores) if content_scores else 0,
        "categories": {
            cat: {
                "pass_rate": stats["passed"] / stats["total"],
                "avg_score": sum(stats["decision_scores"]) / len(stats["decision_scores"])
                if stats["decision_scores"]
                else 0,
            }
            for cat, stats in categories.items()
        },
    }


def get_category(name: str) -> str:
    """获取场景类别"""
    name_lower = name.lower()
    if "preference" in name_lower or "pref" in name_lower:
        return "偏好类"
    elif "temporary" in name_lower:
        return "临时约束类"
    elif "behavior" in name_lower:
        return "行为模式类"
    elif "session" in name_lower or "summary" in name_lower:
        return "会话摘要类"
    elif "private" in name_lower or "skip" in name_lower or "personal" in name_lower:
        return "应跳过类"
    elif "duplicate" in name_lower or "语义" in name_lower:
        return "去重类"
    elif "chat" in name_lower or "vague" in name_lower or "emoji" in name_lower:
        return "应跳过类"
    else:
        return "其他"


__all__ = [
    "export_json",
    "export_csv",
    "export_markdown",
    "aggregate_metrics",
    "get_category",
]