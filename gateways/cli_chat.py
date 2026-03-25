"""Streamlit Web 交互入口

基于 Streamlit 的 Web 界面，支持以下功能：
- 文本/图片输入 -> Vision Extractor -> 入库 -> 发送异步任务
- 搜索题目（支持按公司、熟练度过滤）
- 练习答题（使用 Scorer Agent 评分）
- 查看题目的标准答案
- 更新题目熟练度
- 仪表盘展示（图数据库统计）
"""

import asyncio
import os
import tempfile

import nest_asyncio
import streamlit as st
from PIL import Image

# 修复 Streamlit 在 Jupyter 环境下的兼容性问题
nest_asyncio.apply()

from app.agents.vision_extractor import get_vision_extractor
from app.agents.router import get_router_agent
from app.agents.scorer import get_scorer_agent
from app.pipelines.ingestion import get_ingestion_pipeline
from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.qdrant_client import get_qdrant_manager
from app.db.graph_client import get_graph_client
from app.utils.logger import logger


# 页面配置
st.set_page_config(
    page_title="Offer-Catcher - 面经智能体系统",
    page_icon="📚",
    layout="wide",
)


@st.cache_resource
def init_components():
    """初始化组件（缓存）"""
    vision_extractor = get_vision_extractor(provider="dashscope")
    router_agent = get_router_agent(provider="dashscope")
    scorer_agent = get_scorer_agent(provider="dashscope")
    ingestion_pipeline = get_ingestion_pipeline()
    retrieval_pipeline = get_retrieval_pipeline()
    qdrant_manager = get_qdrant_manager()
    graph_client = get_graph_client()

    # 确保 Qdrant 集合存在
    qdrant_manager.create_collection_if_not_exists()

    # 尝试连接 Neo4j
    graph_client.connect()

    return vision_extractor, router_agent, scorer_agent, ingestion_pipeline, retrieval_pipeline, qdrant_manager, graph_client


def get_ingestion_strategy(question_text: str, core_entities: list[str], qdrant_manager) -> dict:
    """获取入库策略

    Returns:
        dict: {
            "strategy": "reuse" | "new",
            "message": "已存在答案，将自动复用" | "新题目，将发往 MQ 异步生成",
            "similar_score": 0.95,
            "similar_text": "相似题目文本"
        }
    """
    # 创建 embedding 上下文
    entities = core_entities or []
    entities_str = ",".join(entities) if entities else "综合"
    context = f"考点标签：{entities_str} | 题目：{question_text}"

    try:
        from app.tools.embedding import get_embedding_tool
        embedding_tool = get_embedding_tool()
        query_vector = embedding_tool.embed_text(context)

        similar = qdrant_manager.search(
            query_vector=query_vector,
            limit=1,
            score_threshold=0.95,
        )

        if similar and similar[0].question_answer:
            return {
                "strategy": "reuse",
                "message": "✅ 已存在答案，将自动复用 (省 Token)",
                "similar_score": similar[0].score,
                "similar_text": similar[0].question_text,
            }
        else:
            return {
                "strategy": "new",
                "message": "🚀 新题目，将发往 MQ 异步生成",
                "similar_score": similar[0].score if similar else 0,
                "similar_text": similar[0].question_text if similar else None,
            }
    except Exception:
        return {
            "strategy": "new",
            "message": "🚀 新题目，将发往 MQ 异步生成",
            "similar_score": 0,
            "similar_text": None,
        }


@st.dialog("确认入库")
def confirm_text_ingest(result):
    """确认入库对话框"""
    st.write(f"确定要入库 **{result.company}** 的 **{result.position}** 面经吗？")
    st.write(f"共 **{len(result.questions)}** 道题目")
    col1, col2 = st.columns(2)
    if col1.button("确认入库", key="text_confirm_yes"):
        st.session_state.confirm_result = True
        st.session_state.confirm_data = result
        st.rerun()
    if col2.button("取消", key="text_confirm_no"):
        st.session_state.confirm_result = False
        st.rerun()


def display_extracted_questions(result, qdrant_manager):
    """显示提取的题目列表（文本输入和图片上传共用）

    Args:
        result: VisionExtractor 的提取结果
        qdrant_manager: Qdrant 管理器实例
    """
    # 显示题目列表
    st.success(f"✅ 提取完成：公司={result.company}, 岗位={result.position}, 共 {len(result.questions)} 道题目")
    st.info("💡 点击题目可查看入库策略")

    st.subheader("提取的题目")
    for i, q in enumerate(result.questions, 1):
        # 延迟加载：仅在展开时计算入库策略
        with st.expander(f"题目 {i}: [{q.question_type.value}] {q.question_text[:50]}..."):
            st.write(f"**完整题目**: {q.question_text}")
            st.write(f"**类型**: {q.question_type.value}")
            st.write(f"**知识点**: {', '.join(q.core_entities) if q.core_entities else '无'}")

            # 延迟加载入库策略
            with st.spinner("计算入库策略..."):
                strategy = get_ingestion_strategy(
                    q.question_text,
                    q.core_entities,
                    qdrant_manager
                )

            st.write("---")
            st.write(f"**入库策略**: {strategy['message']}")
            if strategy.get("similar_text"):
                st.caption(f"相似题目: {strategy['similar_text'][:40]}... (相似度: {strategy['similar_score']:.3f})")


async def main():
    """主函数"""
    # 初始化组件
    vision_extractor, router_agent, scorer_agent, ingestion_pipeline, retrieval_pipeline, qdrant_manager, graph_client = init_components()

    # 侧边栏
    with st.sidebar:
        st.markdown("### 📚 Offer-Catcher")
        st.markdown("---")
        page = st.radio(
            "选择功能",
            ["📝 录入面经", "🔍 搜索题目", "📝 练习答题", "📋 题目管理", "📊 仪表盘"]
    )

    if page == "📝 录入面经":
        st.subheader("📝 录入面经")
        st.markdown("上传面经图片或输入文本，系统将自动提取题目并入库，触发异步答案生成")

        input_type = st.radio("输入类型", ["文本输入", "图片上传"])

        if input_type == "文本输入":
            text_input = st.text_area(
                "面经文本",
                height=150,
                placeholder="请输入面经内容...\n\n例如：字节跳动 Agent开发面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目",
            )

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if st.button("提取并入库", type="primary", key="btn_extract_text"):
                    if not text_input.strip():
                        st.error("请输入面经内容")
                    else:
                        with st.spinner("正在提取面经..."):
                            try:
                                result = vision_extractor.extract(text_input, source_type="text")
                                st.session_state.extracted_result = result
                                st.session_state.input_type = "text"
                                st.session_state.extraction_done = True
                                st.rerun()
                            except Exception as e:
                                st.error(f"提取失败: {e}")
            with col_btn2:
                # 确认入库按钮（仅在提取完成后显示）
                if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "text":
                    if st.button("确认入库", key="btn_confirm_text", type="secondary"):
                        result = st.session_state.extracted_result
                        confirm_text_ingest(result)

            # 入库（使用 session state 保存的结果）
            if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "text":
                result = st.session_state.extracted_result
                display_extracted_questions(result, qdrant_manager)

            # 处理确认入库结果
            if st.session_state.get("confirm_result") and st.session_state.get("confirm_data"):
                result = st.session_state.confirm_data
                with st.spinner("正在入库..."):
                    try:
                        ingestion_result = await ingestion_pipeline.process(result)
                        st.success(f"✅ 入库成功：处理 {ingestion_result.processed} 条")
                        if ingestion_result.async_tasks > 0:
                            st.info(f"📤 已触发 {ingestion_result.async_tasks} 个异步答案生成任务")
                        # 清理状态
                        st.session_state.extracted_result = None
                        st.session_state.extraction_done = False
                        st.session_state.input_type = None
                        st.session_state.confirm_result = None
                        st.session_state.confirm_data = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"入库失败: {e}")

        else:  # 图片上传
            uploaded_file = st.file_uploader("上传面经图片", type=["png", "jpg", "jpeg"])

            if uploaded_file:
                # 保存上传的图片到临时文件
                suffix = f".{uploaded_file.name.split('.')[-1]}" if '.' in uploaded_file.name else ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp_path = tmp.name
                    image = Image.open(uploaded_file)
                    image.save(tmp_path)

                st.image(image, caption="预览", width=300)

                col_btn1, col_btn2 = st.columns([3, 1])
                with col_btn1:
                    if st.button("提取并入库", key="btn_extract_img"):
                        with st.spinner("正在提取图片面经..."):
                            try:
                                result = vision_extractor.extract(tmp_path, source_type="image")
                                st.session_state.extracted_result = result
                                st.session_state.input_type = "image"
                                st.session_state.extraction_done = True
                                st.rerun()
                            except Exception as e:
                                st.error(f"提取失败: {e}")
                            finally:
                                if os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                with col_btn2:
                    # 确认入库按钮（仅在提取完成后显示）
                    if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "image":
                        if st.button("确认入库", key="btn_confirm_img", type="secondary"):
                            result = st.session_state.extracted_result
                            confirm_text_ingest(result)

                # 入库（使用 session state 保存的结果）
                if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "image":
                    result = st.session_state.extracted_result

                    display_extracted_questions(result, qdrant_manager)

                    # 显示确认信息
                    st.info(f"共提取 {len(result.questions)} 道题目，确认无误后点击下方按钮入库")

                    # 点击按钮弹出确认对话框
                    if st.button("确认入库", key="img_ingest", type="primary"):
                        # 显示确认对话框
                        confirm_text_ingest(result)

    elif page == "🔍 搜索题目":
        st.subheader("🔍 搜索题目")
        st.markdown("支持语义搜索和条件过滤")

        col1, col2, col3 = st.columns(3)
        with col1:
            query = st.text_input("搜索内容", placeholder="输入搜索关键词...")

        with col2:
            company_filter = st.selectbox("公司过滤", ["全部", "字节跳动", "腾讯", "阿里", "美团", "百度", "快手", "小红书", "拼多多"])

        with col3:
            mastery_filter = st.selectbox(
                "熟练度",
                ["全部", "未掌握(0)", "熟悉(1)", "已掌握(2)"],
                index=0,
            )

        mastery_map = {"全部": None, "未掌握(0)": 0, "熟悉(1)": 1, "已掌握(2)": 2}
        mastery = mastery_map[mastery_filter]

        # 搜索
        if st.button("🔍 搜索", type="primary"):
            with st.spinner("搜索中..."):
                results = retrieval_pipeline.search(
                    query=query or "",
                    company=company_filter if company_filter != "全部" else None,
                    mastery_level=mastery,
                    k=20,
                )

                if not results:
                    st.info("未找到匹配的题目")
                else:
                    st.success(f"找到 {len(results)} 条结果")

                    # 显示结果
                    for r in results:
                        with st.expander(f"[{r.company}] {r.question_text[:50]}..."):
                            st.write(f"**岗位**: {r.position}")
                            st.write(f"**类型**: {r.question_type}")
                            mastery_str = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][r.mastery_level] if r.mastery_level < 3 else "未知"
                            st.write(f"**熟练度**: {mastery_str}")
                            st.write(f"**相似度**: {r.score:.3f}")

                            # 答案区域
                            if r.question_answer:
                                st.markdown("---")
                                st.markdown("**答案**:")
                                st.markdown(r.question_answer)
                            else:
                                st.info("答案待生成（异步任务处理中）")

                            # 更新熟练度
                            st.write("**更新熟练度**:")
                            col_a, col_b = st.columns(2)
                            with col_a:
                                new_level = st.selectbox(
                                    "选择熟练度",
                                    [0, 1, 2],
                                    index=r.mastery_level,
                                    key=f"level_{r.question_id}",
                                )
                            with col_b:
                                if st.button("更新", key=f"btn_{r.question_id}"):
                                    qdrant_manager.update_question(r.question_id, mastery_level=new_level)
                                    st.success("✅ 更新成功")
                                    st.rerun()

    elif page == "📝 练习答题":
        st.subheader("📝 练习答题")
        st.markdown("选择一道题目进行练习，提交答案后获取 AI 评分和改进建议")

        # 获取题目列表供选择
        with st.spinner("加载题目..."):
            practice_questions = retrieval_pipeline.search(query="", k=100)

        if not practice_questions:
            st.info("暂无题目数据，请先录入题目")
        else:
            # 过滤有答案的题目才能练习
            available_questions = [q for q in practice_questions if q.question_answer]

            if not available_questions:
                st.warning("暂无带答案的题目，请等待异步答案生成完成")
            else:
                # 题目选择器
                question_options = {
                    f"[{q.company}] {q.question_text[:40]}...": q
                    for q in available_questions
                }
                selected_label = st.selectbox(
                    "选择题目",
                    list(question_options.keys()),
                    key="practice_select"
                )

                if selected_label:
                    selected_q = question_options[selected_label]

                    # 显示题目
                    st.markdown("---")
                    st.markdown("### 题目")
                    st.write(f"**公司**: {selected_q.company}")
                    st.write(f"**岗位**: {selected_q.position}")
                    st.write(f"**类型**: {selected_q.question_type}")

                    with st.expander("查看题目详情"):
                        st.write(selected_q.question_text)
                        if selected_q.core_entities:
                            st.write(f"**知识点**: {', '.join(selected_q.core_entities)}")

                    # 答案输入
                    st.markdown("### 你的答案")
                    user_answer = st.text_area(
                        "请在此输入你的答案",
                        height=200,
                        placeholder="请用自己的话回答这道题目...",
                        key="practice_answer"
                    )

                    # 提交评分
                    if st.button("提交评分", type="primary", key="submit_score"):
                        if not user_answer.strip():
                            st.error("请输入答案")
                        else:
                            with st.spinner("AI 评分中..."):
                                try:
                                    score_result = asyncio.run(
                                        scorer_agent.score(
                                            question_id=selected_q.question_id,
                                            user_answer=user_answer
                                        )
                                    )

                                    # 显示评分结果
                                    st.markdown("---")
                                    st.markdown("### 评分结果")

                                    # 分数和等级
                                    col_score1, col_score2, col_score3 = st.columns(3)
                                    with col_score1:
                                        st.metric("得分", f"{score_result.score}/100")
                                    with col_score2:
                                        level_emoji = ["❌", "⚠️", "✅"]
                                        level_name = ["未掌握", "熟悉", "已掌握"]
                                        st.metric(
                                            "熟练度",
                                            f"{level_emoji[score_result.mastery_level.value]} {level_name[score_result.mastery_level.value]}"
                                        )
                                    with col_score3:
                                        st.metric("标准答案", "已提供" if score_result.standard_answer else "待生成")

                                    # 优点
                                    if score_result.strengths:
                                        st.markdown("#### 优点")
                                        for s in score_result.strengths:
                                            st.success(f"✓ {s}")

                                    # 改进建议
                                    if score_result.improvements:
                                        st.markdown("#### 改进建议")
                                        for imp in score_result.improvements:
                                            st.warning(f"→ {imp}")

                                    # 综合反馈
                                    if score_result.feedback:
                                        st.markdown("#### 综合反馈")
                                        st.info(score_result.feedback)

                                    # 显示标准答案（可选）
                                    with st.expander("查看标准答案"):
                                        if score_result.standard_answer:
                                            st.markdown(score_result.standard_answer)
                                        else:
                                            st.info("标准答案待生成")

                                except Exception as e:
                                    st.error(f"评分失败: {e}")

    elif page == "📋 题目管理":
        st.subheader("📋 题目管理")

        # 获取所有题目
        with st.spinner("加载中..."):
            results = retrieval_pipeline.search(query="", k=500)

        if not results:
            st.info("暂无题目数据")
        else:
            # ==================== 统计区域 ====================
            st.subheader("📊 数据统计")

            # 按类型统计
            by_type = {}
            by_mastery = {0: 0, 1: 0, 2: 0}
            by_answer = {"已生成": 0, "待生成": 0}
            companies = set()
            positions = set()

            for r in results:
                # 类型
                t = r.question_type or "unknown"
                by_type[t] = by_type.get(t, 0) + 1
                # 熟练度
                by_mastery[r.mastery_level] = by_mastery.get(r.mastery_level, 0) + 1
                # 答案状态
                if r.question_answer:
                    by_answer["已生成"] += 1
                else:
                    by_answer["待生成"] += 1
                # 公司和岗位
                if r.company:
                    companies.add(r.company)
                if r.position:
                    positions.add(r.position)

            # 统计卡片
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("总题目", len(results))
            col2.metric("公司数", len(companies))
            col3.metric("已生成答案", by_answer["已生成"])
            col4.metric("未掌握", by_mastery.get(0, 0))
            col5.metric("已掌握", by_mastery.get(2, 0))

            # 按类型分布
            col_types = st.columns(4)
            for i, (qtype, count) in enumerate(sorted(by_type.items())):
                type_name = {"knowledge": "客观题", "project": "项目题", "behavioral": "行为题", "scenario": "场景题", "algorithm": "算法题"}.get(qtype, qtype)
                col_types[i % 4].metric(type_name, count)

            st.markdown("---")

            # ==================== 筛选区域 ====================
            st.subheader("🔍 筛选条件")

            # 横向排列筛选条件
            f1, f2, f3, f4, f5 = st.columns(5)

            with f1:
                filter_company = st.selectbox(
                    "按公司",
                    ["全部"] + sorted(list(companies)),
                    key="filter_company"
                )

            with f2:
                filter_position = st.selectbox(
                    "按岗位",
                    ["全部"] + sorted(list(positions)),
                    key="filter_position"
                )

            with f3:
                filter_type = st.selectbox(
                    "按类型",
                    ["全部", "knowledge", "project", "behavioral", "scenario", "algorithm"],
                    key="filter_type"
                )
                type_map = {"knowledge": "客观题", "project": "项目题", "behavioral": "行为题", "scenario": "场景题", "algorithm": "算法题"}

            with f4:
                filter_mastery = st.selectbox(
                    "按熟练度",
                    ["全部", "0", "1", "2"],
                    key="filter_mastery"
                )
                mastery_map = {"0": "未掌握", "1": "熟悉", "2": "已掌握"}

            with f5:
                filter_answer = st.selectbox(
                    "按答案",
                    ["全部", "已生成", "待生成"],
                    key="filter_answer"
                )

            # 关键词搜索
            search_keyword = st.text_input("🔎 关键词搜索（题目内容）", placeholder="输入关键词...")

            # ==================== 过滤数据 ====================
            filtered = results

            if filter_company != "全部":
                filtered = [r for r in filtered if r.company == filter_company]

            if filter_position != "全部":
                filtered = [r for r in filtered if r.position == filter_position]

            if filter_type != "全部":
                filtered = [r for r in filtered if r.question_type == filter_type]

            if filter_mastery != "全部":
                filtered = [r for r in filtered if r.mastery_level == int(filter_mastery)]

            if filter_answer == "已生成":
                filtered = [r for r in filtered if r.question_answer]
            elif filter_answer == "待生成":
                filtered = [r for r in filtered if not r.question_answer]

            if search_keyword:
                keyword = search_keyword.lower()
                filtered = [r for r in filtered if keyword in (r.question_text or "").lower()]

            st.markdown("---")

            # ==================== 题目列表 ====================
            st.subheader(f"📋 题目列表 ({len(filtered)} 条)")

            if not filtered:
                st.info("没有符合条件的题目")
            else:
                # 分页显示，每页 20 条
                page_size = 20
                total_pages = (len(filtered) - 1) // page_size + 1

                if total_pages > 1:
                    page_num = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="page_num")
                    start_idx = (page_num - 1) * page_size
                    end_idx = min(start_idx + page_size, len(filtered))
                    display_results = filtered[start_idx:end_idx]
                    st.caption(f"显示第 {start_idx + 1}-{end_idx} 条，共 {len(filtered)} 条")
                else:
                    display_results = filtered

                for r in display_results:
                    mastery_str = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][r.mastery_level] if r.mastery_level < 3 else "?"
                    type_str = type_map.get(r.question_type, r.question_type)

                    with st.expander(f"[{r.company}] {r.question_text[:40]}... ({mastery_str})"):
                        # 基本信息
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.write(f"**ID**: `{r.question_id}`")
                            st.write(f"**公司**: {r.company}")
                            st.write(f"**岗位**: {r.position}")
                        with col_info2:
                            st.write(f"**类型**: {type_str}")
                            st.write(f"**熟练度**: {mastery_str}")
                            st.write(f"**答案**: {'✅ 已生成' if r.question_answer else '⏳ 待生成'}")

                        # 知识点
                        if r.core_entities:
                            st.write(f"**知识点**: {', '.join(r.core_entities)}")

                        # 查看答案
                        if r.question_answer:
                            st.markdown("---")
                            st.markdown("**答案**:")
                            st.markdown(r.question_answer)
                        else:
                            st.info("⏳ 答案待生成")

                        # 操作按钮
                        st.markdown("---")
                        col_edit, col_del = st.columns(2)
                        with col_edit:
                            if st.button("✏️ 修改", key=f"edit_{r.question_id}"):
                                st.session_state[f"editing_{r.question_id}"] = True
                        with col_del:
                            if st.button("🗑️ 删除", key=f"del_{r.question_id}"):
                                qdrant_manager.delete_question(r.question_id)
                                st.warning("🗑️ 已删除")
                                st.rerun()

                        # 修改表单
                        if st.session_state.get(f"editing_{r.question_id}", False):
                            st.markdown("---")
                            st.markdown("✏️ 修改题目")

                            col_row1, col_row2 = st.columns(2)
                            with col_row1:
                                new_company = st.text_input(
                                    "公司",
                                    value=r.company or "",
                                    key=f"company_{r.question_id}",
                                )
                            with col_row2:
                                new_position = st.text_input(
                                    "岗位",
                                    value=r.position or "",
                                    key=f"position_{r.question_id}",
                                )

                            new_text = st.text_area(
                                "题目内容",
                                value=r.question_text,
                                key=f"text_{r.question_id}",
                            )

                            col_row3, col_row4 = st.columns(2)
                            with col_row3:
                                new_type = st.selectbox(
                                    "题目类型",
                                    ["knowledge", "project", "behavioral", "scenario", "algorithm"],
                                    index=["knowledge", "project", "behavioral", "scenario", "algorithm"].index(r.question_type)
                                    if r.question_type in ["knowledge", "project", "behavioral", "scenario", "algorithm"] else 0,
                                    key=f"type_{r.question_id}",
                                )
                            with col_row4:
                                new_level = st.selectbox(
                                    "熟练度",
                                    [0, 1, 2],
                                    index=r.mastery_level,
                                    key=f"level_{r.question_id}",
                                )

                            new_entities = st.text_input(
                                "知识点（逗号分隔）",
                                value=",".join(r.core_entities) if r.core_entities else "",
                                key=f"entities_{r.question_id}",
                            )

                            new_answer = st.text_area(
                                "答案",
                                value=r.question_answer or "",
                                height=150,
                                key=f"answer_{r.question_id}",
                            )

                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.button("💾 保存", key=f"save_{r.question_id}"):
                                    entities_list = [e.strip() for e in new_entities.split(",") if e.strip()]
                                    qdrant_manager.update_question(
                                        r.question_id,
                                        question_text=new_text,
                                        question_type=new_type,
                                        core_entities=entities_list,
                                        company=new_company,
                                        position=new_position,
                                        question_answer=new_answer if new_answer.strip() else None,
                                        mastery_level=new_level,
                                    )
                                    st.success("✅ 已保存")
                                    st.session_state[f"editing_{r.question_id}"] = False
                                    st.rerun()
                            with col_cancel:
                                if st.button("❌ 取消", key=f"cancel_{r.question_id}"):
                                    st.session_state[f"editing_{r.question_id}"] = False
                                    st.rerun()

    elif page == "📊 仪表盘":
        st.subheader("📊 数据仪表盘")

        with st.spinner("加载数据..."):
            results = retrieval_pipeline.search(query="", k=500)

        if not results:
            st.info("暂无数据")
            return

        # 统计卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总题目数", len(results))

        # 按公司统计
        by_company = {}
        by_mastery = {0: 0, 1: 0, 2: 0}
        has_answer = 0

        for r in results:
            by_company[r.company] = by_company.get(r.company, 0) + 1
            if r.mastery_level in by_mastery:
                by_mastery[r.mastery_level] += 1
            if r.question_answer:
                has_answer += 1

        col2.metric("公司数", len(by_company))
        col3.metric("已掌握", by_mastery[2])
        col4.metric("已生成答案", has_answer)

        # 图表
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.subheader("按公司分布")
            if by_company:
                st.bar_chart(by_company)

        with col_chart2:
            st.subheader("熟练度分布")
            mastery_data = {
                "未掌握": by_mastery[0],
                "熟悉": by_mastery[1],
                "已掌握": by_mastery[2],
            }
            st.bar_chart(mastery_data)

        # 公司详情表格
        st.subheader("公司详情")
        company_data = []
        for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
            company_results = [r for r in results if r.company == company]
            mastery_2 = sum(1 for r in company_results if r.mastery_level == 2)
            has_ans = sum(1 for r in company_results if r.question_answer)
            company_data.append({
                "公司": company,
                "题目数": count,
                "已掌握": mastery_2,
                "已生成答案": has_ans,
            })

        st.table(company_data)

        # 图数据库统计
        st.markdown("---")
        st.subheader("📈 图数据库统计（考频分析）")

        if not graph_client.is_connected:
            st.warning("Neo4j 图数据库未连接，请在 .env 中配置 NEO4J 相关环境变量")
            st.info("提示：可通过 Docker 启动 Neo4j 容器")
        else:
            # 记录考点到图数据库
            with st.spinner("同步考点数据到图数据库..."):
                for r in results:
                    if r.core_entities:
                        graph_client.record_question_entities(r.company, r.core_entities)
                st.success("考点数据已同步")

            # 全局热门考点
            st.markdown("#### 热门考点 TOP 10")
            top_entities = graph_client.get_top_entities(limit=10)
            if top_entities:
                entity_data = {
                    e["entity"]: e["count"] for e in top_entities
                }
                st.bar_chart(entity_data)
            else:
                st.info("暂无考点数据")

            # 按公司查看考点
            st.markdown("#### 各公司热门考点")
            companies_with_data = list(by_company.keys())[:5]  # 最多显示5个公司
            for company in companies_with_data:
                with st.expander(f"{company} 的热门考点"):
                    company_top = graph_client.get_top_entities(company=company, limit=5)
                    if company_top:
                        for e in company_top:
                            st.write(f"- {e['entity']}: {e['count']} 次")
                    else:
                        st.info("暂无数据")


if __name__ == "__main__":
    asyncio.run(main())