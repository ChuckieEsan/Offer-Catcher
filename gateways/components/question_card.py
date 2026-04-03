"""可复用的题目卡片组件 - 支持查看、编辑、删除和重新生成答案"""

import streamlit as st
from typing import Optional, List, Callable
from app.models.schemas import QuestionItem


def render_question_card(
    question: QuestionItem,
    expanded: bool = False,
    on_save: Optional[Callable[[str, str, str, str, str], None]] = None,
    on_delete: Optional[Callable[[str], None]] = None,
    on_update_mastery: Optional[Callable[[str, int], None]] = None,
    on_regenerate_answer: Optional[Callable[[QuestionItem], None]] = None,
) -> None:
    """渲染可编辑的题目卡片

    Args:
        question: 题目对象
        expanded: 是否默认展开
        on_save: 保存回调，参数为 (question_id, company, position, question_text, question_answer)
        on_delete: 删除回调，参数为 (question_id,)
        on_update_mastery: 更新熟练度回调，参数为 (question_id, new_level)
        on_regenerate_answer: 重新生成答案回调，参数为 (question,)，返回新答案
    """
    qid = question.question_id

    # 构建标题
    text_preview = question.question_text[:60] + "..." if len(question.question_text) > 60 else question.question_text
    title = f"[{question.company}] {text_preview}"

    with st.expander(title, expanded=expanded):
        # 检查是否有更新标志
        text_updated = st.session_state.get(f"text_updated_{qid}", False)
        if text_updated:
            st.success("✅ 题目已更新，embedding 已重新计算")
            st.session_state[f"text_updated_{qid}"] = False

        # 第一行：岗位、类型、熟练度
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**岗位**: {question.position}")
        with col2:
            st.write(f"**类型**: {question.question_type}")
        with col3:
            mastery_str = ["❌ 未掌握", "⚠️ 熟悉", "✅ 已掌握"][question.mastery_level]
            st.write(f"**熟练度**: {mastery_str}")

        # 知识点（如果有）
        if question.core_entities:
            st.caption(f"**知识点**: {', '.join(question.core_entities)}")

        # 第二行：题目内容
        st.markdown("---")
        st.markdown("**题目内容**")
        st.write(question.question_text[:500] + "..." if len(question.question_text) > 500 else question.question_text)

        # 第三行：答案
        st.markdown("**答案**")
        if question.question_answer:
            with st.expander("查看答案"):
                st.markdown(question.question_answer)
        else:
            st.caption("暂无答案")

        # 第四行：操作按钮
        st.markdown("---")
        col_edit, col_level, col_regen, col_delete = st.columns(4)

        # 初始化编辑状态
        if f"editing_{qid}" not in st.session_state:
            st.session_state[f"editing_{qid}"] = False

        with col_edit:
            if st.session_state[f"editing_{qid}"]:
                if st.button("保存", key=f"save_{qid}", use_container_width=True):
                    new_text = st.session_state.get(f"edit_text_{qid}", question.question_text)
                    new_answer = st.session_state.get(f"edit_answer_{qid}", question.question_answer)

                    if on_save:
                        on_save(qid, question.company, question.position, new_text, new_answer)

                    # 判断是否更新了题目文本（需要重新计算 embedding）
                    if new_text != question.question_text:
                        st.session_state[f"text_updated_{qid}"] = True

                    st.session_state[f"editing_{qid}"] = False
                    st.rerun()
            else:
                if st.button("编辑", key=f"edit_{qid}", use_container_width=True):
                    st.session_state[f"editing_{qid}"] = True
                    st.rerun()

        # 编辑状态下的文本输入
        if st.session_state[f"editing_{qid}"]:
            st.markdown("---")
            st.markdown("#### 编辑题目")
            new_text = st.text_area("题目内容", question.question_text, key=f"edit_text_{qid}", height=100)
            new_answer = st.text_area("答案", question.question_answer or "", key=f"edit_answer_{qid}", height=150)

            if st.button("取消编辑", key=f"cancel_{qid}", use_container_width=True):
                st.session_state[f"editing_{qid}"] = False
                st.rerun()
            st.markdown("---")

        # 熟练度更新
        with col_level:
            new_level = st.selectbox(
                "熟练度",
                [0, 1, 2],
                index=question.mastery_level,
                key=f"level_{qid}"
            )
            if new_level != question.mastery_level:
                if st.button("更新熟练度", key=f"btn_{qid}", use_container_width=True):
                    if on_update_mastery:
                        on_update_mastery(qid, new_level)
                    st.success("✅ 更新成功")
                    st.rerun()

        # 重新生成答案
        with col_regen:
            is_regenerating = st.session_state.get(f"regenerating_{qid}", False)
            btn_label = "🔄 生成中..." if is_regenerating else "重新生成答案"
            if st.button(btn_label, key=f"regen_{qid}", use_container_width=True, disabled=is_regenerating):
                if on_regenerate_answer:
                    st.session_state[f"regenerating_{qid}"] = True
                    st.rerun()

        # 删除
        with col_delete:
            if st.button("删除", key=f"delete_{qid}", use_container_width=True):
                if on_delete:
                    on_delete(qid)
                st.success("✅ 删除成功")
                st.rerun()

        # 处理重新生成答案（如果触发了）
        if f"regenerating_{qid}" in st.session_state and st.session_state[f"regenerating_{qid}"]:
            if on_regenerate_answer:
                try:
                    with st.spinner("正在调用大模型生成答案..."):
                        new_answer = on_regenerate_answer(question)
                    # 将新答案存入编辑框的 session_state，并自动进入编辑模式
                    st.session_state[f"edit_answer_{qid}"] = new_answer or ""
                    st.session_state[f"editing_{qid}"] = True
                    st.success("✅ 答案已生成，请在编辑框中查看并修改")
                except Exception as e:
                    st.error(f"生成失败: {e}")
                finally:
                    st.session_state[f"regenerating_{qid}"] = False
                    st.rerun()


def render_question_list(
    questions: List[QuestionItem],
    on_save: Optional[Callable[[str, str, str, str, str], None]] = None,
    on_delete: Optional[Callable[[str], None]] = None,
    on_update_mastery: Optional[Callable[[str, int], None]] = None,
    on_regenerate_answer: Optional[Callable[[QuestionItem], None]] = None,
    empty_message: str = "暂无题目",
) -> None:
    """渲染题目列表

    Args:
        questions: 题目列表
        on_save: 保存回调，参数为 (question_id, company, position, question_text, question_answer)
        on_delete: 删除回调，参数为 (question_id,)
        on_update_mastery: 更新熟练度回调，参数为 (question_id, new_level)
        on_regenerate_answer: 重新生成答案回调，参数为 (question,)，返回新答案
        empty_message: 空列表时显示的消息
    """
    if not questions:
        st.info(empty_message)
        return

    for q in questions:
        render_question_card(
            question=q,
            on_save=on_save,
            on_delete=on_delete,
            on_update_mastery=on_update_mastery,
            on_regenerate_answer=on_regenerate_answer,
        )


def render_question_compact(
    question: QuestionItem,
    show_company: bool = True,
    show_type: bool = True,
    show_mastery: bool = True,
    max_chars: int = 50,
) -> None:
    """渲染紧凑型题目（用于列表展示）

    Args:
        question: 题目对象
        show_company: 是否显示公司
        show_type: 是否显示类型
        show_mastery: 是否显示熟练度
        max_chars: 题目文本最大显示字符数
    """
    title_parts = []
    if show_company:
        title_parts.append(f"[{question.company}]")
    text_preview = question.question_text[:max_chars] + "..." if len(question.question_text) > max_chars else question.question_text
    title_parts.append(text_preview)

    meta = []
    if show_type:
        meta.append(question.question_type)
    if show_mastery:
        level_map = {0: "🔴", 1: "🟡", 2: "🟢"}
        meta.append(level_map.get(question.mastery_level, "⚪"))

    if meta:
        st.write(" ".join(title_parts) + " | " + " ".join(meta))
    else:
        st.write(" ".join(title_parts))


# ==================== 默认回调实现 ====================

def get_default_handlers(
    question_map: dict,
    qdrant_manager,
    answer_specialist=None,
) -> dict:
    """获取默认的回调函数实现

    Args:
        question_map: question_id -> QuestionItem 的映射
        qdrant_manager: Qdrant 管理器实例
        answer_specialist: Answer Specialist Agent 实例（可选，用于重新生成答案）

    Returns:
        包含 on_save, on_delete, on_update_mastery, on_regenerate_answer 的字典
    """

    def handle_save(question_id: str, company: str, position: str, new_text: str, new_answer: str):
        """保存题目修改"""
        original = question_map.get(question_id)
        if not original:
            return

        is_text_changed = new_text != original.question_text

        if is_text_changed:
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

    def handle_regenerate_answer(question: QuestionItem) -> str:
        """重新生成答案"""
        if not answer_specialist:
            raise ValueError("Answer Specialist 未配置，无法重新生成答案")
        answer = answer_specialist.generate_answer(question)
        # qdrant_manager.update_question(question.question_id, question_answer=answer)
        return answer

    return {
        "on_save": handle_save,
        "on_delete": handle_delete,
        "on_update_mastery": handle_update_mastery,
        "on_regenerate_answer": handle_regenerate_answer,
    }