"""Streamlit Web 交互入口

基于 Streamlit 的 Web 界面，支持以下功能：
- 文本/图片输入 -> Vision Extractor -> 入库 -> 发送异步任务
- 搜索题目（支持按公司、熟练度过滤）
- 查看题目的标准答案
- 更新题目熟练度
- 仪表盘展示
"""

import streamlit as st
from PIL import Image

from app.agents.vision_extractor import get_vision_extractor
from app.pipelines.ingestion import get_ingestion_pipeline
from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.qdrant_client import get_qdrant_manager
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
    ingestion_pipeline = get_ingestion_pipeline()
    retrieval_pipeline = get_retrieval_pipeline()
    qdrant_manager = get_qdrant_manager()
    return vision_extractor, ingestion_pipeline, retrieval_pipeline, qdrant_manager


def main():
    """主函数"""
    st.title("📚 Offer-Catcher - 面经智能体系统")
    st.markdown("面经提取、存储、检索与异步答案生成一体化平台")

    # 初始化组件
    vision_extractor, ingestion_pipeline, retrieval_pipeline, qdrant_manager = init_components()

    # 侧边栏
    with st.sidebar:
        st.header("功能导航")
        page = st.radio(
            "选择功能",
            ["📝 录入面经", "🔍 搜索题目", "📋 题目管理", "📊 仪表盘"]
    )

    if page == "📝 录入面经":
        st.header("📝 录入面经")
        st.markdown("上传面经图片或输入文本，系统将自动提取题目并入库，触发异步答案生成")

        input_type = st.radio("输入类型", ["文本输入", "图片上传"])

        if input_type == "文本输入":
            text_input = st.text_area(
                "面经文本",
                height=150,
                placeholder="请输入面经内容...\n\n例如：字节跳动 Agent开发面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目",
            )

            if st.button("提取并入库", type="primary"):
                if not text_input.strip():
                    st.error("请输入面经内容")
                else:
                    with st.spinner("正在提取面经..."):
                        try:
                            result = vision_extractor.extract(text_input, source_type="text")
                            st.success(f"✅ 提取完成：公司={result.company}, 岗位={result.position}, 共 {len(result.questions)} 道题目")

                            # 显示题目列表
                            st.subheader("提取的题目")
                            for i, q in enumerate(result.questions, 1):
                                with st.expander(f"题目 {i}: [{q.question_type.value}] {q.question_text[:50]}..."):
                                    st.write(f"**类型**: {q.question_type.value}")
                                    st.write(f"**知识点**: {', '.join(q.core_entities) if q.core_entities else '无'}")

                            # 入库
                            if st.button("确认入库"):
                                with st.spinner("正在入库..."):
                                    try:
                                        ingestion_result = ingestion_pipeline.process(result)
                                        st.success(f"✅ 入库成功：处理 {ingestion_result.processed} 条")
                                        if ingestion_result.async_tasks > 0:
                                            st.info(f"📤 已触发 {ingestion_result.async_tasks} 个异步答案生成任务")
                                    except Exception as e:
                                        st.error(f"入库失败: {e}")
                        except Exception as e:
                            st.error(f"提取失败: {e}")

        else:  # 图片上传
            uploaded_file = st.file_uploader("上传面经图片", type=["png", "jpg", "jpeg"])

            if uploaded_file:
                import tempfile
                import os

                # 保存上传的图片到临时文件
                suffix = f".{uploaded_file.name.split('.')[-1]}" if '.' in uploaded_file.name else ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp_path = tmp.name
                    image = Image.open(uploaded_file)
                    image.save(tmp_path)

                st.image(image, caption="预览", width=300)

                if st.button("提取并入库", key="img_process"):
                    with st.spinner("正在提取图片面经..."):
                        try:
                            result = vision_extractor.extract(tmp_path, source_type="image")
                            st.success(f"✅ 提取完成：公司={result.company}, 岗位={result.position}, 共 {len(result.questions)} 道题目")

                            # 显示题目
                            st.subheader("提取的题目")
                            for i, q in enumerate(result.questions, 1):
                                st.write(f"**{i}. [{q.question_type.value}]** {q.question_text[:60]}...")

                            # 入库
                            if st.button("确认入库", key="img_ingest"):
                                with st.spinner("正在入库..."):
                                    try:
                                        ingestion_result = ingestion_pipeline.process(result)
                                        st.success(f"✅ 入库成功：处理 {ingestion_result.processed} 条")
                                        if ingestion_result.async_tasks > 0:
                                            st.info(f"📤 已触发 {ingestion_result.async_tasks} 个异步答案生成任务")
                                    except Exception as e:
                                        st.error(f"入库失败: {e}")
                        except Exception as e:
                            st.error(f"提取失败: {e}")
                        finally:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)

    elif page == "🔍 搜索题目":
        st.header("🔍 搜索题目")
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
                                    qdrant_manager.update_mastery_level(r.question_id, new_level)
                                    st.success("✅ 更新成功")
                                    st.rerun()

    elif page == "📋 题目管理":
        st.header("📋 题目管理")

        # 获取所有题目
        with st.spinner("加载中..."):
            results = retrieval_pipeline.search(query="", k=200)

        if not results:
            st.info("暂无题目数据")
        else:
            # 统计
            col1, col2, col3 = st.columns(3)
            col1.metric("总题目数", len(results))

            by_type = {}
            for r in results:
                t = r.question_type
                by_type[t] = by_type.get(t, 0) + 1

            col2.metric("客观题", by_type.get("knowledge", 0))
            col3.metric("项目题", by_type.get("project", 0))

            # 列表
            st.subheader("题目列表")

            # 过滤
            filter_company = st.selectbox("按公司筛选", ["全部"] + sorted(list(set(r.company for r in results))))

            filtered = results if filter_company == "全部" else [r for r in results if r.company == filter_company]

            for r in filtered:
                mastery_str = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][r.mastery_level] if r.mastery_level < 3 else "?"
                with st.expander(f"[{r.company}] {r.question_text[:40]}... ({mastery_str})"):
                    st.write(f"**ID**: `{r.question_id}`")
                    st.write(f"**岗位**: {r.position}")
                    st.write(f"**类型**: {r.question_type}")
                    st.write(f"**答案**: {'✅ 已生成' if r.question_answer else '⏳ 待生成'}")

                    # 查看答案
                    if r.question_answer:
                        st.markdown("---")
                        st.markdown("**答案**:")
                        st.markdown(r.question_answer)

                    # 更新熟练度
                    new_level = st.selectbox(
                        "更新熟练度",
                        [0, 1, 2],
                        index=r.mastery_level,
                        key=f"manage_{r.question_id}",
                    )
                    if new_level != r.mastery_level:
                        if st.button("确认更新", key=f"upd_{r.question_id}"):
                            qdrant_manager.update_mastery_level(r.question_id, new_level)
                            st.success("✅ 已更新")
                            st.rerun()

    elif page == "📊 仪表盘":
        st.header("📊 数据仪表盘")

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


if __name__ == "__main__":
    main()