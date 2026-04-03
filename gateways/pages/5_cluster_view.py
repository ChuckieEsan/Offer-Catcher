"""页面5: 考点聚类查看"""

import streamlit as st
from collections import defaultdict

from app.db.qdrant_client import get_qdrant_manager


@st.cache_resource
def init_components():
    qdrant_manager = get_qdrant_manager()
    return qdrant_manager


st.subheader("🏷️ 考点聚类")
st.caption("查看所有考点簇及其包含的题目")

qdrant_manager = init_components()

with st.spinner("加载题目数据..."):
    all_questions = qdrant_manager.scroll_all()

if not all_questions:
    st.info("暂无题目数据，请先录入题目并运行聚类")
    st.code("PYTHONPATH=. uv run python workers/clustering_worker.py --run-now", language="bash")
else:
    # 按 cluster_ids 分组统计
    cluster_data = defaultdict(list)
    for q in all_questions:
        if q.cluster_ids:
            for cluster_id in q.cluster_ids:
                cluster_data[cluster_id].append(q)
        else:
            cluster_data["未分类"].append(q)

    # 按题目数排序
    sorted_clusters = sorted(cluster_data.items(), key=lambda x: len(x[1]), reverse=True)
    cluster_names = ["全部"] + [c[0] for c in sorted_clusters]

    # 统计信息
    col1, col2, col3 = st.columns(3)
    col1.metric("考点簇", len([c for c in cluster_data.keys() if c != "未分类"]))
    col2.metric("总题目", len(all_questions))
    col3.metric("已分类", sum(len(qs) for cid, qs in cluster_data.items() if cid != "未分类"))

    st.markdown("---")

    # 聚类筛选
    selected_cluster = st.selectbox(
        "选择考点簇",
        cluster_names,
        format_func=lambda x: "全部" if x == "全部" else x.replace("cluster_", "").replace("_", " / ")
    )

    # 过滤题目
    if selected_cluster == "全部":
        filtered_questions = all_questions
    else:
        filtered_questions = cluster_data.get(selected_cluster, [])

    # 答案筛选
    answer_filter = st.radio("答案筛选", ["全部", "有答案", "待生成"], horizontal=True, key="cluster_answer_filter")

    if answer_filter == "有答案":
        filtered_questions = [q for q in filtered_questions if q.question_answer]
    elif answer_filter == "待生成":
        filtered_questions = [q for q in filtered_questions if not q.question_answer]

    total_count = len(filtered_questions)
    st.caption(f"共 {total_count} 道题目")

    if not filtered_questions:
        st.info("没有符合条件的题目")
    else:
        # 分页
        page_size = 20
        total_pages = (total_count + page_size - 1) // page_size
        if total_pages > 1:
            page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, key="cluster_page")
        else:
            page = 1

        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_count)

        # 显示题目列表
        for i, q in enumerate(filtered_questions[start_idx:end_idx]):
            with st.expander(
                f"[{q.company}] {q.question_text[:60]}...",
                expanded=False
            ):
                # 题目信息
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.markdown(f"**岗位**: {q.position}")
                with col_info2:
                    st.markdown(f"**类型**: {q.question_type}")
                with col_info3:
                    level_emoji = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][q.mastery_level]
                    st.markdown(f"**熟练度**: {level_emoji}")

                # 知识点
                if q.core_entities:
                    st.caption(f"📌 知识点: {', '.join(q.core_entities)}")

                # 考点簇
                if q.cluster_ids:
                    st.caption(f"🏷️ 考点簇: {', '.join([c.replace('cluster_', '') for c in q.cluster_ids])}")

                # 题目内容
                st.markdown("---")
                st.markdown("**题目内容**")
                st.write(q.question_text)

                # 答案
                st.markdown("---")
                if q.question_answer:
                    st.markdown("**答案**")
                    st.markdown(q.question_answer)
                else:
                    st.caption("⏳ 答案待生成")

                st.markdown("---")

    # 底部：运行聚类按钮
    st.markdown("---")
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("🔄 重新运行聚类", use_container_width=True):
            with st.spinner("正在运行聚类..."):
                from app.services.clustering_service import get_clustering_service
                service = get_clustering_service()
                result = service.run_clustering()
                st.success(f"聚类完成: {result.cluster_count} 个簇, {result.clustered_count} 道题")
                st.rerun()
    with col_btn2:
        st.caption("如果题目数量有变化，可以重新运行聚类")