"""页面2: 练习答题"""

import asyncio
import random
import streamlit as st

from app.agents.scorer import get_scorer_agent
from app.config.settings import create_llm
from app.db.graph_client import get_graph_client
from app.db.qdrant_client import get_qdrant_manager
from app.pipelines.retrieval import get_retrieval_pipeline
from langchain_core.messages import HumanMessage, AIMessage


@st.cache_resource
def init_components():
    scorer_agent = get_scorer_agent(provider="dashscope")
    retrieval_pipeline = get_retrieval_pipeline()
    qdrant_manager = get_qdrant_manager()
    graph_client = get_graph_client()
    graph_client.connect()
    return scorer_agent, retrieval_pipeline, qdrant_manager, graph_client


st.subheader("📝 练习答题")
st.caption("选择一道题目进行练习，提交答案后获取 AI 评分")

scorer_agent, retrieval_pipeline, qdrant_manager, graph_client = init_components()

# 抽题模式选择 - 紧凑布局
col_mode1, col_mode2 = st.columns([1, 3])

with col_mode1:
    practice_mode = st.selectbox(
        "抽题模式",
        ["随机抽题", "按公司抽题", "按知识点抽题", "按熟练度抽题（未掌握）", "语义搜索抽题", "快速搜索（查看答案）"],
        label_visibility="collapsed",
        key="practice_mode",
    )

# 根据不同模式获取题目
available_questions = []
query_text = ""

with col_mode2:
    if practice_mode == "随机抽题":
        with st.spinner("加载题目..."):
            all_questions = retrieval_pipeline.search(query="", k=200)
            available_questions = [q for q in all_questions if q.question_answer]
        col_info, col_btn = st.columns([2, 1])
        with col_info:
            st.caption(f"共 {len(available_questions)} 道带答案的题目")
        with col_btn:
            if st.button("🎲 随机抽题", key="random_pick", use_container_width=True):
                if available_questions:
                    selected_q = random.choice(available_questions)
                    st.session_state.practice_select = f"[{selected_q.company}] {selected_q.question_text[:40]}..."
                    st.session_state.selected_for_practice = selected_q
                    st.rerun()
                else:
                    st.warning("暂无带答案的题目")

    elif practice_mode == "按公司抽题":
        company_input = st.text_input("输入公司名称", placeholder="如：字节跳动", key="practice_company", label_visibility="collapsed")
        if company_input:
            with st.spinner("搜索中..."):
                results = retrieval_pipeline.search(query="", company=company_input, k=50)
                available_questions = [q for q in results if q.question_answer]
            st.caption(f"找到 {len(available_questions)} 道带答案的题目")

    elif practice_mode == "按知识点抽题":
        with st.spinner("加载知识点..."):
            top_entities = graph_client.get_top_entities(limit=30)
            entity_options = [e["entity"] for e in top_entities]
        if entity_options:
            selected_entities = st.multiselect("选择知识点", entity_options, key="practice_entities", label_visibility="collapsed")
            if selected_entities:
                with st.spinner("搜索中..."):
                    results = retrieval_pipeline.search(query="", core_entities=selected_entities, k=50)
                    available_questions = [q for q in results if q.question_answer]
                st.caption(f"找到 {len(available_questions)} 道带答案的题目")
        else:
            st.caption("暂无知识点数据")

    elif practice_mode == "按熟练度抽题（未掌握）":
        with st.spinner("加载未掌握题目..."):
            results = retrieval_pipeline.search(query="", mastery_level=0, k=50)
            available_questions = [q for q in results if q.question_answer]
        st.caption(f"找到 {len(available_questions)} 道未掌握的题目")

    elif practice_mode == "语义搜索抽题":
        query_text = st.text_input("输入搜索关键词", placeholder="如：RAG、Agent", key="practice_query", label_visibility="collapsed")
        if query_text:
            with st.spinner("搜索中..."):
                results = retrieval_pipeline.search(query=query_text, k=50)
                available_questions = [q for q in results if q.question_answer]
            st.caption(f"找到 {len(available_questions)} 道相关题目")

    elif practice_mode == "快速搜索（查看答案）":
        query_text = st.text_input("输入搜索关键词", placeholder="如：RAG、Agent", key="fast_query", label_visibility="collapsed")
        if query_text:
            with st.spinner("搜索中..."):
                results = retrieval_pipeline.search(query=query_text, k=20)
            if results:
                st.caption(f"找到 {len(results)} 道题目")
                for r in results:
                    with st.expander(f"[{r.company}] {r.question_text[:50]}..."):
                        st.caption(f"**岗位**: {r.position} | **类型**: {r.question_type}")
                        if r.question_answer:
                            st.markdown("**答案**:")
                            st.markdown(r.question_answer[:300] + "..." if len(r.question_answer) > 300 else r.question_answer)
                        else:
                            st.caption("答案待生成")
                        col_upd1, col_upd2 = st.columns([2, 1])
                        with col_upd1:
                            new_lvl = st.selectbox("熟练度", [0, 1, 2], index=r.mastery_level, key=f"quick_{r.question_id}")
                        with col_upd2:
                            if st.button("更新", key=f"upd_{r.question_id}"):
                                qdrant_manager.update_question(r.question_id, mastery_level=new_lvl)
                                st.success("✅ 已更新")
                available_questions = []
                st.session_state.current_practice_question_id = None

# 如果没有可用题目
if not available_questions:
    if practice_mode not in ["随机抽题", "快速搜索（查看答案）"]:
        st.warning("暂无带答案的题目，请尝试其他抽题方式")
else:
    question_options = {
        f"[{q.company}] {q.question_text[:40]}...": q
        for q in available_questions
    }

    # 检查是否有通过随机抽题选中的题目
    if "selected_for_practice" in st.session_state and st.session_state.selected_for_practice:
        selected_q = st.session_state.selected_for_practice
        # 如果换了题目，清空评分结果
        if st.session_state.get("current_practice_question_id") != selected_q.question_id:
            st.session_state.current_score_result = None
            st.session_state.current_user_answer = None
        st.session_state.current_practice_question_id = selected_q.question_id
        st.session_state.selected_for_practice = None
    elif "current_practice_question_id" in st.session_state and st.session_state.current_practice_question_id:
        saved_id = st.session_state.current_practice_question_id
        selected_q = next((q for q in available_questions if q.question_id == saved_id), None)
        if not selected_q:
            st.session_state.current_practice_question_id = None
            st.session_state.current_score_result = None
    else:
        selected_label = st.selectbox(
            "选择题目",
            list(question_options.keys()),
            key="practice_select"
        )
        selected_q = question_options.get(selected_label) if selected_label else None
        if selected_q:
            # 如果换了题目，清空评分结果
            if st.session_state.get("current_practice_question_id") != selected_q.question_id:
                st.session_state.current_score_result = None
                st.session_state.current_user_answer = None
            st.session_state.current_practice_question_id = selected_q.question_id

    if selected_q:
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

        # 展示相似题目
        st.markdown("#### 相似题目推荐")
        with st.spinner("查找相似题目..."):
            similar_results = retrieval_pipeline.search(
                query=selected_q.question_text,
                k=5,
                score_threshold=0.5
            )
            similar_questions = [s for s in similar_results if s.question_id != selected_q.question_id]

        if similar_questions:
            for sq in similar_questions:
                with st.expander(f"相似: [{sq.company}] {sq.question_text[:30]}..."):
                    st.write(sq.question_text[:100] + "..." if len(sq.question_text) > 100 else sq.question_text)
                    if sq.core_entities:
                        st.caption(f"知识点: {', '.join(sq.core_entities)}")
        else:
            st.caption("暂无相似题目")

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

                        # 保存评分结果到 session state（持久化）
                        st.session_state.current_score_result = {
                            "score": score_result.score,
                            "mastery_level": score_result.mastery_level,
                            "standard_answer": score_result.standard_answer,
                            "strengths": score_result.strengths,
                            "improvements": score_result.improvements,
                            "feedback": score_result.feedback,
                        }
                        st.session_state.current_user_answer = user_answer

                        st.rerun()
                    except Exception as e:
                        st.error(f"评分失败: {e}")

        # ============================================
        # 显示评分结果（如果已评分）
        # ============================================
        if st.session_state.get("current_score_result"):
            score_result = st.session_state.current_score_result
            user_answer = st.session_state.get("current_user_answer", user_answer)

            st.markdown("---")
            st.markdown("### 评分结果")

            col_score1, col_score2, col_score3 = st.columns(3)
            with col_score1:
                st.metric("得分", f"{score_result['score']}/100")
            with col_score2:
                level_emoji = ["❌", "⚠️", "✅"]
                level_name = ["未掌握", "熟悉", "已掌握"]
                st.metric(
                    "熟练度",
                    f"{level_emoji[score_result['mastery_level'].value]} {level_name[score_result['mastery_level'].value]}"
                )
            with col_score3:
                st.metric("标准答案", "已提供" if score_result['standard_answer'] else "待生成")

            if score_result.get("strengths"):
                st.markdown("#### 优点")
                for s in score_result["strengths"]:
                    st.success(f"✓ {s}")

            if score_result.get("improvements"):
                st.markdown("#### 改进建议")
                for imp in score_result["improvements"]:
                    st.warning(f"→ {imp}")

            if score_result.get("feedback"):
                st.markdown("#### 综合反馈")
                st.info(score_result["feedback"])

            with st.expander("查看标准答案"):
                if score_result.get("standard_answer"):
                    st.markdown(score_result["standard_answer"])
                else:
                    st.info("标准答案待生成")

        # ============================================
        # AI 追问对话功能（常驻显示）
        # ============================================
        st.markdown("---")
        st.markdown("### 💬 针对这道题追问 AI")
        st.caption("可以随时针对这道题提问，AI 会根据题目和答案帮助你理解")

        # 初始化对话历史
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = {}
        chat_key = f"chat_{selected_q.question_id}"

        # 如果换了题目，清空之前题目的对话，但保留当前题目的
        if st.session_state.get("last_chat_question_id") != selected_q.question_id:
            if chat_key not in st.session_state.chat_history:
                st.session_state.chat_history[chat_key] = []
            st.session_state.last_chat_question_id = selected_q.question_id

        if chat_key not in st.session_state.chat_history:
            st.session_state.chat_history[chat_key] = []

        chat_history = st.session_state.chat_history[chat_key]

        # 显示对话历史
        if chat_history:
            for msg in chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # 获取当前上下文（如果有评分结果就用评分的，否则用题目本身的）
        current_context = None
        if st.session_state.get("current_score_result"):
            score_result = st.session_state.get("current_score_result")
            current_context = f"""
当前题目：公司 {selected_q.company} | 岗位 {selected_q.position} | 类型 {selected_q.question_type}
题目内容：{selected_q.question_text}
标准答案：{score_result.get('standard_answer') or '暂无'}
你的答案：{st.session_state.get('current_user_answer') or '暂无'}
评分结果：{score_result.get('score')}/100，{score_result.get('mastery_level').name if score_result.get('mastery_level') else '未知'}
"""
        else:
            current_context = f"""
当前题目：公司 {selected_q.company} | 岗位 {selected_q.position} | 类型 {selected_q.question_type}
题目内容：{selected_q.question_text}
"""

        # 用户输入追问问题
        follow_up_question = st.chat_input(
            "针对这道题提问（按回车发送）",
            key=f"follow_up_chat_{selected_q.question_id}"
        )

        if follow_up_question:
            # 先显示用户的消息
            chat_history.append({"role": "user", "content": follow_up_question})

            with st.spinner("AI 思考中..."):
                try:
                    llm = create_llm("dashscope", "chat")
                    messages = [HumanMessage(content=current_context + "\n\n" + follow_up_question)]
                    for msg in chat_history[:-1]:
                        if msg["role"] == "user":
                            messages.append(HumanMessage(content=msg["content"]))
                        else:
                            messages.append(AIMessage(content=msg["content"]))

                    response = llm.invoke(messages)
                    ai_response = response.content if hasattr(response, 'content') else str(response)

                    # 添加 AI 回答到历史（不需要 rerun，st.chat_input 会自动触发更新）
                    chat_history.append({"role": "assistant", "content": ai_response})
                except Exception as e:
                    st.error(f"追问失败: {e}")

        # 清空对话按钮
        col_send, col_clear = st.columns([3, 1])
        with col_clear:
            if st.button("清空对话", key=f"clear_chat_{selected_q.question_id}", use_container_width=True):
                st.session_state.chat_history[chat_key] = []
                st.rerun()