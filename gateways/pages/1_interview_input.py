"""页面1: 录入面经"""

import asyncio
import os
import tempfile

import nest_asyncio
import streamlit as st
from PIL import Image

nest_asyncio.apply()

from app.agents.vision_extractor import get_vision_extractor
from app.pipelines.ingestion import get_ingestion_pipeline
from app.db.qdrant_client import get_qdrant_manager
from app.utils.logger import logger


@st.cache_resource
def init_components():
    vision_extractor = get_vision_extractor(provider="dashscope")
    ingestion_pipeline = get_ingestion_pipeline()
    qdrant_manager = get_qdrant_manager()
    qdrant_manager.create_collection_if_not_exists()
    return vision_extractor, ingestion_pipeline, qdrant_manager


def get_ingestion_strategy(question_text: str, core_entities: list, qdrant_manager) -> dict:
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
    st.success(f"✅ 提取完成：公司={result.company}, 岗位={result.position}, 共 {len(result.questions)} 道题目")
    st.info("💡 点击题目可查看入库策略")

    st.subheader("提取的题目")
    for i, q in enumerate(result.questions, 1):
        with st.expander(f"题目 {i}: [{q.question_type.value}] {q.question_text[:50]}..."):
            st.write(f"**完整题目**: {q.question_text}")
            st.write(f"**类型**: {q.question_type.value}")
            st.write(f"**知识点**: {', '.join(q.core_entities) if q.core_entities else '无'}")

            with st.spinner("计算入库策略..."):
                strategy = get_ingestion_strategy(q.question_text, q.core_entities, qdrant_manager)

            st.write("---")
            st.write(f"**入库策略**: {strategy['message']}")
            if strategy.get("similar_text"):
                st.caption(f"相似题目: {strategy['similar_text'][:40]}... (相似度: {strategy['similar_score']:.3f})")


# 主页面
st.subheader("📝 录入面经")
st.caption("上传面经图片或输入文本，系统将自动提取题目并入库")

vision_extractor, ingestion_pipeline, qdrant_manager = init_components()

input_type = st.radio("输入类型", ["文本输入", "图片上传"], horizontal=True, label_visibility="collapsed")

if input_type == "文本输入":
    text_input = st.text_area(
        "面经文本", height=100,
        placeholder="例如：字节跳动 Agent开发面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目",
        label_visibility="collapsed"
    )

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        if st.button("提取并入库", type="primary", key="btn_extract_text", use_container_width=True):
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
        if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "text":
            if st.button("确认入库", key="btn_confirm_text", type="secondary", use_container_width=True):
                result = st.session_state.extracted_result
                confirm_text_ingest(result)

    if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "text":
        result = st.session_state.extracted_result
        display_extracted_questions(result, qdrant_manager)

    if st.session_state.get("confirm_result") and st.session_state.get("confirm_data"):
        result = st.session_state.confirm_data
        with st.spinner("正在入库..."):
            try:
                ingestion_result = asyncio.run(ingestion_pipeline.process(result))
                st.success(f"✅ 入库成功：处理 {ingestion_result.processed} 条")
                if ingestion_result.async_tasks > 0:
                    st.info(f"📤 已触发 {ingestion_result.async_tasks} 个异步答案生成任务")
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
            if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "image":
                if st.button("确认入库", key="btn_confirm_img", type="secondary"):
                    result = st.session_state.extracted_result
                    confirm_text_ingest(result)

        if st.session_state.get("extraction_done") and st.session_state.get("input_type") == "image":
            result = st.session_state.extracted_result
            display_extracted_questions(result, qdrant_manager)

        if st.session_state.get("confirm_result") and st.session_state.get("confirm_data"):
            result = st.session_state.confirm_data
            with st.spinner("正在入库..."):
                try:
                    ingestion_result = asyncio.run(ingestion_pipeline.process(result))
                    st.success(f"✅ 入库成功：处理 {ingestion_result.processed} 条")
                    if ingestion_result.async_tasks > 0:
                        st.info(f"📤 已触发 {ingestion_result.async_tasks} 个异步答案生成任务")
                    st.session_state.extracted_result = None
                    st.session_state.extraction_done = False
                    st.session_state.input_type = None
                    st.session_state.confirm_result = None
                    st.session_state.confirm_data = None
                    st.rerun()
                except Exception as e:
                    st.error(f"入库失败: {e}")