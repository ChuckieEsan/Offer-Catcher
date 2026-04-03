"""页面3: 题目管理"""

import streamlit as st

from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.qdrant_client import get_qdrant_manager
from app.agents.answer_specialist import get_answer_specialist
from gateways.components import render_editable_question_list


@st.cache_resource
def init_components():
    retrieval_pipeline = get_retrieval_pipeline()
    qdrant_manager = get_qdrant_manager()
    return retrieval_pipeline, qdrant_manager


st.subheader("📋 题目管理")

retrieval_pipeline, qdrant_manager = init_components()

with st.spinner("加载中..."):
    results = retrieval_pipeline.search(query="", k=500)

if not results:
    st.info("暂无题目数据")
else:
    # 准备统计数据
    by_type = {}
    by_mastery = {0: 0, 1: 0, 2: 0}
    by_answer = {"已生成": 0, "待生成": 0}
    companies = set()
    positions = set()

    for r in results:
        t = r.question_type or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
        by_mastery[r.mastery_level] = by_mastery.get(r.mastery_level, 0) + 1
        if r.question_answer:
            by_answer["已生成"] += 1
        else:
            by_answer["待生成"] += 1
        if r.company:
            companies.add(r.company)
        if r.position:
            positions.add(r.position)


    # 过滤
    col_filter1, col_filter2, col_filter3 = st.columns(3)
    with col_filter1:
        filter_company = st.selectbox("公司过滤", ["全部"] + sorted(list(companies)))
    with col_filter2:
        filter_type = st.selectbox("类型过滤", ["全部", "knowledge", "project", "behavioral", "scenario", "algorithm"])
    with col_filter3:
        filter_mastery = st.selectbox("熟练度过滤", ["全部", 0, 1, 2])

    # 应用过滤
    filtered = results
    if filter_company != "全部":
        filtered = [r for r in filtered if r.company == filter_company]
    if filter_type != "全部":
        filtered = [r for r in filtered if r.question_type == filter_type]
    if filter_mastery != "全部":
        filtered = [r for r in filtered if r.mastery_level == filter_mastery]

    st.caption(f"显示 {len(filtered)} / {len(results)} 道题目")

    # 分页显示
    page_size = 20
    total_pages = (len(filtered) + page_size - 1) // page_size
    page = st.number_input("页码", min_value=1, max_value=total_pages, value=1)
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(filtered))

    # 定义回调函数
    def handle_save(question_id: str, company: str, position: str, new_text: str, new_answer: str):
        """保存题目修改"""
        # 判断是否更新了题目文本（需要重新计算 embedding）
        if new_text != question.question_text:
            qdrant_manager.update_question_with_reembedding(
                question_id=question_id,
                company=company,
                position=position,
                question_text=new_text,
                question_answer=new_answer,
            )
            st.session_state[f"text_updated_{question_id}"] = True
        else:
            qdrant_manager.update_question(
                question_id,
                question_text=new_text,
                question_answer=new_answer,
            )

    def handle_delete(question_id: str):
        """删除题目"""
        qdrant_manager.delete_question(question_id)

    def handle_update_mastery(question_id: str, new_level: int):
        """更新熟练度"""
        qdrant_manager.update_question(question_id, mastery_level=new_level)

    def handle_regenerate_answer(question):
        """重新生成答案"""
        agent = get_answer_specialist(provider="dashscope")
        answer = agent.generate_answer(question)
        qdrant_manager.update_question(question.question_id, question_answer=answer)

    # 使用可编辑题目列表组件
    render_editable_question_list(
        questions=filtered[start_idx:end_idx],
        on_save=handle_save,
        on_delete=handle_delete,
        on_update_mastery=handle_update_mastery,
        on_regenerate_answer=handle_regenerate_answer,
    )