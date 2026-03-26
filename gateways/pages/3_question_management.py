"""页面3: 题目管理"""

import streamlit as st

from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.qdrant_client import get_qdrant_manager


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
    # 统计区域
    st.subheader("📊 数据统计")

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

    # 题目列表
    st.subheader("题目列表")

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

    for r in filtered[start_idx:end_idx]:
        with st.expander(f"[{r.company}] {r.question_text[:60]}..."):
            # 检查是否有更新标志（题目文本被修改）
            text_updated = st.session_state.get(f"text_updated_{r.question_id}", False)
            if text_updated:
                st.success("✅ 题目已更新，embedding 已重新计算")
                st.session_state[f"text_updated_{r.question_id}"] = False

            # 第一行：岗位、类型、熟练度
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**岗位**: {r.position}")
            with col2:
                st.write(f"**类型**: {r.question_type}")
            with col3:
                mastery_str = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][r.mastery_level]
                st.write(f"**熟练度**: {mastery_str}")

            # 知识点（如果有）
            if r.core_entities:
                st.caption(f"**知识点**: {', '.join(r.core_entities)}")

            # 第二行：题目内容
            st.markdown("---")
            st.markdown("**题目内容**")
            st.write(r.question_text[:500] + "..." if len(r.question_text) > 500 else r.question_text)

            # 第三行：答案
            st.markdown("**答案**")
            if r.question_answer:
                with st.expander("查看答案"):
                    st.markdown(r.question_answer)
            else:
                st.caption("暂无答案")

            # 第四行：操作按钮
            st.markdown("---")
            col_edit, col_level, col_delete = st.columns(3)

            # 编辑模式
            if f"editing_{r.question_id}" not in st.session_state:
                st.session_state[f"editing_{r.question_id}"] = False

            with col_edit:
                if st.session_state[f"editing_{r.question_id}"]:
                    if st.button("保存", key=f"save_{r.question_id}", use_container_width=True):
                        new_text = st.session_state.get(f"edit_text_{r.question_id}", r.question_text)
                        new_answer = st.session_state.get(f"edit_answer_{r.question_id}", r.question_answer)

                        # 判断是否更新了题目文本（需要重新计算 embedding）
                        if new_text != r.question_text:
                            qdrant_manager.update_question_with_reembedding(
                                question_id=r.question_id,
                                company=r.company,
                                position=r.position,
                                question_text=new_text,
                                question_answer=new_answer,
                            )
                            st.session_state[f"text_updated_{r.question_id}"] = True
                        else:
                            qdrant_manager.update_question(
                                r.question_id,
                                question_text=new_text,
                                question_answer=new_answer,
                            )

                        st.session_state[f"editing_{r.question_id}"] = False
                        st.rerun()
                else:
                    if st.button("编辑", key=f"edit_{r.question_id}", use_container_width=True):
                        st.session_state[f"editing_{r.question_id}"] = True
                        st.rerun()

            # 编辑状态下的文本输入
            if st.session_state[f"editing_{r.question_id}"]:
                st.markdown("---")
                st.markdown("#### 编辑题目")
                new_text = st.text_area("题目内容", r.question_text, key=f"edit_text_{r.question_id}", height=100)
                new_answer = st.text_area("答案", r.question_answer or "", key=f"edit_answer_{r.question_id}", height=150)

                col_cancel_edit = st.columns(1)[0]
                with col_cancel_edit:
                    if st.button("取消编辑", key=f"cancel_{r.question_id}", use_container_width=True):
                        st.session_state[f"editing_{r.question_id}"] = False
                        st.rerun()
                st.markdown("---")

            # 熟练度更新
            with col_level:
                new_level = st.selectbox(
                    "熟练度",
                    [0, 1, 2],
                    index=r.mastery_level,
                    key=f"level_{r.question_id}"
                )
                if new_level != r.mastery_level:
                    if st.button("更新熟练度", key=f"btn_{r.question_id}", use_container_width=True):
                        qdrant_manager.update_question(r.question_id, mastery_level=new_level)
                        st.success("✅ 更新成功")
                        st.rerun()

            # 删除
            with col_delete:
                if st.button("删除", key=f"delete_{r.question_id}", use_container_width=True):
                    qdrant_manager.delete_question(r.question_id)
                    st.success("✅ 删除成功")
                    st.rerun()