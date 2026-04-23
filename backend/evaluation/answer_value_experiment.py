"""答案价值实验（真实 RAG 流程 + Rubric 评测）

核心问题：检索结果中包含"标准答案"时，LLM 生成的回答质量是否更好？

实验设计：
1. 从 JSON 文件加载用户 Query（数据驱动，Agent 开发最佳实践）
2. 向量检索 → 召回前 top_k 条相关题目
3. 对照组：检索结果只有题目（无答案）
   实验组：检索结果包含题目 + 答案
4. LLM 基于检索 context 生成回答
5. 用 Rubric 评测回答质量（正确性、完整性、专业性）

评测方式：使用 LLM-as-Judge + 自定义 Rubric 评分标准

实验假设：
- H1: 有答案时回答正确性更高
- H2: 有答案时回答完整性更高
- H3: 有答案时回答专业性更高
"""

import asyncio
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import DomainSpecificRubrics

from app.infrastructure.adapters.llm_adapter import get_llm
from app.infrastructure.adapters.embedding_adapter import get_embedding_adapter
from app.infrastructure.persistence.qdrant.question_repository import get_question_repository
from app.infrastructure.config.settings import get_settings
from langchain_core.messages import HumanMessage


# ============================================================================
# 提示词模板（模拟 RAG 流程）
# ============================================================================

RAG_PROMPT_TEMPLATE = """你是一位专业的面试辅导助手。用户提出了一个面试相关问题。

请基于以下检索到的参考资料，给出专业、准确的回答。

用户问题：
{question}

参考资料：
{context}

请给出完整、专业的回答。如果参考资料不充分，可以适当补充相关知识，但要确保准确性。"""


# ============================================================================
# Rubric 评分标准定义
# ============================================================================

# 整体回答质量评分（有 reference）
ANSWER_QUALITY_RUBRIC = {
    "score1_description": "回答完全错误，技术概念理解有根本性偏差，与参考答案完全不符",
    "score2_description": "回答部分正确，但关键技术点有重大错误或遗漏，与参考答案差异较大",
    "score3_description": "回答基本正确，覆盖主要概念，但缺乏深度、细节不够充分",
    "score4_description": "回答准确清晰，覆盖关键要点，有一定的深度分析，与参考答案基本一致",
    "score5_description": "回答完全准确、全面深入，覆盖所有关键要点并提供实践见解，优于参考答案",
}

# 正确性评分维度
CORRECTNESS_RUBRIC = {
    "score1_description": "技术概念完全错误，存在根本性的理解偏差",
    "score2_description": "部分技术点正确，但关键概念有重大错误",
    "score3_description": "大部分技术概念正确，但有轻微不准确之处",
    "score4_description": "技术概念准确，只有极细微的不精确",
    "score5_description": "所有技术概念完全准确无误",
}

# 完整性评分维度
COMPLETENESS_RUBRIC = {
    "score1_description": "回答几乎没有任何实质内容，严重不完整",
    "score2_description": "只覆盖了很少的关键点，大部分重要内容缺失",
    "score3_description": "覆盖了主要关键点，但缺少重要的细节或扩展",
    "score4_description": "覆盖了大部分关键点和必要细节",
    "score5_description": "全面覆盖所有关键点，并提供了充分的细节和扩展",
}

# 专业性评分维度
PROFESSIONALISM_RUBRIC = {
    "score1_description": "回答非常业余，缺乏专业术语和系统性",
    "score2_description": "表达不够专业，术语使用不当或结构混乱",
    "score3_description": "表达较为专业，术语使用基本正确，结构尚可",
    "score4_description": "表达专业，术语使用恰当，结构清晰有条理",
    "score5_description": "表达高度专业，术语精准，结构完美，体现深厚经验",
}


def extract_metric_value(result) -> float:
    """从 MetricResult 或 float 中提取数值"""
    if result is None:
        return 0.5
    if hasattr(result, 'value'):
        return float(result.value)
    try:
        return float(result)
    except (TypeError, ValueError):
        return 0.5


def extract_metric_reason(result) -> str:
    """从 MetricResult 中提取评分理由"""
    if result is None:
        return ""
    if hasattr(result, 'reason'):
        return str(result.reason) if result.reason else ""
    return ""


@dataclass
class UserQuery:
    """用户 Query 数据结构"""
    id: int
    query: str
    category: str
    domain: str
    difficulty: str
    expected_retrieval: str


@dataclass
class ExperimentResult:
    """实验结果"""
    # 基本信息
    query_id: int
    user_query: str
    query_category: str
    query_domain: str
    retrieved_questions: list[str] = field(default_factory=list)
    reference_answer: str = ""  # 检索到的参考答案

    # 对照组（检索结果无答案）
    context_without_answer: str = ""
    response_without_answer: str = ""
    rubric_score_without: float = 0.0
    correctness_without: float = 0.0
    completeness_without: float = 0.0
    professionalism_without: float = 0.0
    rubric_reason_without: str = ""

    # 实验组（检索结果有答案）
    context_with_answer: str = ""
    response_with_answer: str = ""
    rubric_score_with: float = 0.0
    correctness_with: float = 0.0
    completeness_with: float = 0.0
    professionalism_with: float = 0.0
    rubric_reason_with: str = ""

    # 元数据
    metadata: dict = field(default_factory=dict)


def load_user_queries() -> list[UserQuery]:
    """从 JSON 文件加载用户 Query 数据"""
    data_path = Path(__file__).parent / "data" / "user_queries.json"

    if not data_path.exists():
        print(f"警告: Query 数据文件不存在: {data_path}")
        return []

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    queries = []
    for item in data.get("queries", []):
        queries.append(UserQuery(
            id=item["id"],
            query=item["query"],
            category=item["category"],
            domain=item["domain"],
            difficulty=item["difficulty"],
            expected_retrieval=item["expected_retrieval"],
        ))

    print(f"加载 Query 数据: {len(queries)} 条")
    print(f"数据版本: {data.get('version', 'unknown')}")
    return queries


class RAGExperiment:
    """RAG 流程实验"""

    def __init__(self, provider: str = "deepseek", top_k: int = 5):
        self.top_k = top_k

        # 加载 Query 数据
        self.user_queries = load_user_queries()

        # 生成用的 LLM（使用 LangChain）
        self.generator_llm = get_llm(provider, "chat")

        # ragas 评测用的 LLM
        settings = get_settings()
        self.ragas_llm = llm_factory(
            model="deepseek-chat",
            client=AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com",
                timeout=120.0,
            ),
            max_tokens=8192,
        )

        # Rubric 评测指标
        self.quality_metric = DomainSpecificRubrics(
            llm=self.ragas_llm,
            rubrics=ANSWER_QUALITY_RUBRIC,
            with_reference=True,
        )
        self.correctness_metric = DomainSpecificRubrics(
            llm=self.ragas_llm,
            rubrics=CORRECTNESS_RUBRIC,
            with_reference=False,
        )
        self.completeness_metric = DomainSpecificRubrics(
            llm=self.ragas_llm,
            rubrics=COMPLETENESS_RUBRIC,
            with_reference=False,
        )
        self.professionalism_metric = DomainSpecificRubrics(
            llm=self.ragas_llm,
            rubrics=PROFESSIONALISM_RUBRIC,
            with_reference=False,
        )

        self.repo = get_question_repository()
        self.embedding_adapter = get_embedding_adapter()

        self.results_dir = Path(__file__).parent / "experiment_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def search_relevant_questions(self, query: str) -> list:
        """向量检索，召回前 top_k 条相关题目"""
        query_embedding = self.embedding_adapter.embed(query)
        results = self.repo.search(query_embedding, limit=self.top_k)
        return [q for q, _ in results]

    def build_context_without_answer(self, questions: list) -> str:
        """构建对照组的 context（只有题目，无答案）"""
        contexts = []
        for i, q in enumerate(questions, 1):
            contexts.append(
                f"[{i}] 题目：{q.question_text}\n"
                f"    公司：{q.company} | 岗位：{q.position}"
            )
        return "\n\n".join(contexts)

    def build_context_with_answer(self, questions: list) -> str:
        """构建实验组的 context（题目 + 答案）"""
        contexts = []
        for i, q in enumerate(questions, 1):
            contexts.append(
                f"[{i}] 题目：{q.question_text}\n"
                f"    公司：{q.company} | 岗位：{q.position}\n"
                f"    参考答案：{q.answer if q.answer else ''}"
            )
        return "\n\n".join(contexts)

    def get_reference_answer(self, questions: list) -> str:
        """获取检索到的参考答案（用于评测）"""
        answers = []
        for i, q in enumerate(questions, 1):
            if q.answer:
                answers.append(f"[{i}] {q.answer}")
        return "\n\n".join(answers) if answers else ""

    def generate_response(self, user_query: str, context: str) -> str:
        """LLM 基于检索 context 生成回答"""
        prompt = RAG_PROMPT_TEMPLATE.format(
            question=user_query,
            context=context
        )

        response = self.generator_llm.invoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, 'content') else str(response)
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        return content

    async def evaluate_with_rubric(
        self,
        user_query: str,
        response: str,
        reference: str = "",
    ) -> dict:
        """使用 Rubric 评测回答质量"""
        try:
            # 整体质量评分（有 reference）
            quality_result = await self.quality_metric.ascore(
                user_input=user_query,
                response=response,
                reference=reference,
            )

            # 多维度评分（无 reference）
            correctness_result = await self.correctness_metric.ascore(
                user_input=user_query,
                response=response,
            )
            completeness_result = await self.completeness_metric.ascore(
                user_input=user_query,
                response=response,
            )
            professionalism_result = await self.professionalism_metric.ascore(
                user_input=user_query,
                response=response,
            )

            return {
                "quality_score": extract_metric_value(quality_result),
                "quality_reason": extract_metric_reason(quality_result),
                "correctness": extract_metric_value(correctness_result),
                "completeness": extract_metric_value(completeness_result),
                "professionalism": extract_metric_value(professionalism_result),
            }
        except Exception as e:
            print(f"    Rubric 评测失败: {e}")
            return {
                "quality_score": 3.0,
                "quality_reason": f"评测失败: {e}",
                "correctness": 3.0,
                "completeness": 3.0,
                "professionalism": 3.0,
            }

    async def run_experiment(self) -> list[ExperimentResult]:
        """运行实验"""
        print(f"\n{'='*70}")
        print(f"答案价值实验（真实 RAG 流程 + Rubric 评测）")
        print(f"{'='*70}")
        print(f"用户 Query 数量: {len(self.user_queries)}")
        print(f"检索数量: {self.top_k} 条")
        print(f"评测方式: LLM-as-Judge + Rubric 评分")
        print(f"评分维度: 整体质量、正确性、完整性、专业性")
        print(f"实验设计: 对照组(无答案) vs 实验组(有答案)")

        if not self.user_queries:
            print("警告: 没有 Query 数据，实验终止")
            return []

        results = []

        for user_query in self.user_queries:
            print(f"\n[{user_query.id}/{len(self.user_queries)}] 处理 Query...")
            print(f"  Query: {user_query.query}")
            print(f"  类别: {user_query.category} | 领域: {user_query.domain}")

            # 1. 向量检索 → 召回前 top_k 条相关题目
            print(f"  检索相关题目（top_k={self.top_k})...")
            retrieved = self.search_relevant_questions(user_query.query)
            retrieved_ids = [rq.question_id for rq in retrieved]
            print(f"  检索到: {len(retrieved)} 条")

            if not retrieved:
                print(f"  警告: 未检索到相关题目，跳过")
                continue

            # 获取参考答案（用于评测）
            reference_answer = self.get_reference_answer(retrieved)

            result = ExperimentResult(
                query_id=user_query.id,
                user_query=user_query.query,
                query_category=user_query.category,
                query_domain=user_query.domain,
                retrieved_questions=retrieved_ids,
                reference_answer=reference_answer,
            )

            # 2. 对照组：检索 context（无答案）
            print("  [对照组] 构建 context（无答案）...")
            context_without = self.build_context_without_answer(retrieved)
            result.context_without_answer = context_without

            print("  [对照组] LLM 生成回答...")
            response_without = self.generate_response(user_query.query, context_without)
            result.response_without_answer = response_without

            print("  [对照组] Rubric 评测...")
            scores_without = await self.evaluate_with_rubric(
                user_query.query, response_without, reference_answer
            )
            result.rubric_score_without = scores_without["quality_score"]
            result.correctness_without = scores_without["correctness"]
            result.completeness_without = scores_without["completeness"]
            result.professionalism_without = scores_without["professionalism"]
            result.rubric_reason_without = scores_without["quality_reason"]

            # 3. 实验组：检索 context（有答案）
            print("  [实验组] 构建 context（有答案）...")
            context_with = self.build_context_with_answer(retrieved)
            result.context_with_answer = context_with

            print("  [实验组] LLM 生成回答...")
            response_with = self.generate_response(user_query.query, context_with)
            result.response_with_answer = response_with

            print("  [实验组] Rubric 评测...")
            scores_with = await self.evaluate_with_rubric(
                user_query.query, response_with, reference_answer
            )
            result.rubric_score_with = scores_with["quality_score"]
            result.correctness_with = scores_with["correctness"]
            result.completeness_with = scores_with["completeness"]
            result.professionalism_with = scores_with["professionalism"]
            result.rubric_reason_with = scores_with["quality_reason"]

            results.append(result)

            # 打印对比结果
            print(f"  结果对比:")
            print(f"    整体质量: {result.rubric_score_without:.1f} → {result.rubric_score_with:.1f}")
            print(f"    正确性: {result.correctness_without:.1f} → {result.correctness_with:.1f}")
            print(f"    完整性: {result.completeness_without:.1f} → {result.completeness_with:.1f}")
            print(f"    专业性: {result.professionalism_without:.1f} → {result.professionalism_with:.1f}")

        return results

    def analyze_results(self, results: list[ExperimentResult]) -> dict:
        """分析实验结果"""
        if not results:
            return {}

        n = len(results)
        metrics = ["rubric_score", "correctness", "completeness", "professionalism"]

        # 按类别统计
        category_stats = {}
        for r in results:
            cat = r.query_category
            if cat not in category_stats:
                category_stats[cat] = []
            category_stats[cat].append(r)

        analysis = {
            "num_queries": n,
            "top_k": self.top_k,
            "evaluation_method": "LLM-as-Judge + Rubric",
            "metrics": {},
            "by_category": {},
        }

        # 整体指标统计
        for metric in metrics:
            without_values = [getattr(r, f"{metric}_without") for r in results]
            with_values = [getattr(r, f"{metric}_with") for r in results]

            without_values = [v for v in without_values if v is not None]
            with_values = [v for v in with_values if v is not None]

            if not without_values or not with_values:
                continue

            without_mean = sum(without_values) / len(without_values)
            with_mean = sum(with_values) / len(with_values)
            diff = with_mean - without_mean

            analysis["metrics"][metric] = {
                "without_mean": round(without_mean, 2),
                "with_mean": round(with_mean, 2),
                "diff": round(diff, 2),
                "improvement_pct": round(diff / without_mean * 100 if without_mean > 0 else 0, 1),
                "wins": sum(1 for w, h in zip(without_values, with_values) if h > w),
                "losses": sum(1 for w, h in zip(without_values, with_values) if h < w),
                "ties": sum(1 for w, h in zip(without_values, with_values) if h == w),
            }

        # 按类别统计
        for cat, cat_results in category_stats.items():
            analysis["by_category"][cat] = {}
            for metric in metrics:
                without_values = [getattr(r, f"{metric}_without") for r in cat_results]
                with_values = [getattr(r, f"{metric}_with") for r in cat_results]
                without_values = [v for v in without_values if v is not None]
                with_values = [v for v in with_values if v is not None]
                if without_values and with_values:
                    without_mean = sum(without_values) / len(without_values)
                    with_mean = sum(with_values) / len(with_values)
                    analysis["by_category"][cat][metric] = {
                        "without_mean": round(without_mean, 2),
                        "with_mean": round(with_mean, 2),
                        "diff": round(with_mean - without_mean, 2),
                    }

        return analysis

    def save_results(self, results: list[ExperimentResult], analysis: dict) -> Path:
        """保存结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = self.results_dir / f"rag_answer_value_{timestamp}.json"

        data = {
            "experiment": "rag_answer_value_with_rubric",
            "design": "JSON Query 数据 + 向量检索 + Rubric 评测",
            "data_source": "evaluation/data/user_queries.json",
            "evaluation_method": "LLM-as-Judge + Custom Rubric",
            "rubrics": {
                "answer_quality": ANSWER_QUALITY_RUBRIC,
                "correctness": CORRECTNESS_RUBRIC,
                "completeness": COMPLETENESS_RUBRIC,
                "professionalism": PROFESSIONALISM_RUBRIC,
            },
            "top_k": self.top_k,
            "timestamp": timestamp,
            "analysis": analysis,
            "samples": [
                {
                    "query_id": r.query_id,
                    "user_query": r.user_query,
                    "query_category": r.query_category,
                    "query_domain": r.query_domain,
                    "retrieved_questions": r.retrieved_questions,
                    "reference_answer": r.reference_answer,

                    "context_without": r.context_without_answer,
                    "response_without": r.response_without_answer,
                    "rubric_score_without": r.rubric_score_without,
                    "correctness_without": r.correctness_without,
                    "completeness_without": r.completeness_without,
                    "professionalism_without": r.professionalism_without,
                    "rubric_reason_without": r.rubric_reason_without,

                    "context_with": r.context_with_answer,
                    "response_with": r.response_with_answer,
                    "rubric_score_with": r.rubric_score_with,
                    "correctness_with": r.correctness_with,
                    "completeness_with": r.completeness_with,
                    "professionalism_with": r.professionalism_with,
                    "rubric_reason_with": r.rubric_reason_with,
                }
                for r in results
            ]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    def print_summary(self, analysis: dict) -> None:
        """打印摘要"""
        print(f"\n{'='*70}")
        print(f"实验摘要")
        print(f"{'='*70}")
        print(f"Query 数量: {analysis['num_queries']}, 检索数量: {analysis['top_k']}")
        print(f"评测方式: {analysis['evaluation_method']}")

        metrics_display = {
            "rubric_score": "整体质量",
            "correctness": "正确性",
            "completeness": "完整性",
            "professionalism": "专业性",
        }

        print(f"\n{'指标':<15} {'无答案':<10} {'有答案':<10} {'提升':<10} {'胜/负/平':<12}")
        print("-" * 70)

        for metric, label in metrics_display.items():
            if metric not in analysis["metrics"]:
                continue
            data = analysis["metrics"][metric]
            wins = data.get("wins", 0)
            losses = data.get("losses", 0)
            ties = data.get("ties", 0)
            diff = data["diff"]
            sign = "+" if diff >= 0 else ""
            print(f"{label:<15} {data['without_mean']:<10.2f} {data['with_mean']:<10.2f} "
                  f"{sign}{diff:<9.2f} {wins}/{losses}/{ties}")

        # 按类别打印
        if analysis.get("by_category"):
            print(f"\n{'='*70}")
            print(f"按类别统计")
            print(f"{'='*70}")
            for cat, cat_data in analysis["by_category"].items():
                print(f"\n[{cat}]")
                for metric, values in cat_data.items():
                    label = metrics_display.get(metric, metric)
                    diff = values['diff']
                    sign = "+" if diff >= 0 else ""
                    print(f"  {label}: {values['without_mean']:.2f} → {values['with_mean']:.2f} ({sign}{diff:.2f})")

        print(f"\n{'='*70}")
        print(f"实验结论")
        print(f"{'='*70}")

        for metric, data in analysis.get("metrics", {}).items():
            label = metrics_display.get(metric, metric)
            diff = data["diff"]
            wins = data.get("wins", 0)
            n = analysis["num_queries"]

            if diff > 0.5:
                print(f"✓ 有答案显著提升 {label} (+{diff:.2f}, 胜率 {wins}/{n})")
            elif diff > 0.2:
                print(f"○ 有答案轻微提升 {label} (+{diff:.2f}, 胜率 {wins}/{n})")
            elif diff < -0.2:
                print(f"✗ 有答案降低 {label} ({diff:.2f})")
            else:
                sign = "+" if diff >= 0 else ""
                print(f"- {label} 无显著差异 ({sign}{diff:.2f})")


def main():
    """入口"""
    import argparse

    parser = argparse.ArgumentParser(description="答案价值实验（真实 RAG + Rubric 评测）")
    parser.add_argument("--top-k", type=int, default=5, help="检索数量")

    args = parser.parse_args()

    experiment = RAGExperiment(top_k=args.top_k)
    results = asyncio.run(experiment.run_experiment())

    if results:
        analysis = experiment.analyze_results(results)
        filepath = experiment.save_results(results, analysis)
        experiment.print_summary(analysis)
        print(f"\n详细结果: {filepath}")


if __name__ == "__main__":
    main()