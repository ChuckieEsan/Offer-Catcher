"""页面 0: AI 聊天助手主界面

功能：
- 左侧：历史对话列表
- 中间：核心聊天区域
- 支持短期记忆（Redis）和长期记忆（PostgreSQL）
- Chat Agent 流式输出
- 支持图片上传（提取面经题目）
"""

import base64
import os
import tempfile
import uuid
import streamlit as st

from langchain_core.messages import HumanMessage, AIMessage

from app.db.redis_client import get_redis_client
from app.db.postgres_client import get_postgres_client
from app.agents.chat_agent import get_chat_agent
from app.utils.ocr import ocr_images
from app.utils.telemetry import set_request_id, set_session_id


# 页面配置
st.set_page_config(
    page_title="AI 面试助手",
    page_icon="💬",
    layout="wide",
)


def get_user_id() -> str:
    """获取用户 ID

    TODO: 后续接入登录系统后，从登录态获取
    目前使用固定 user_id 用于测试
    """
    if "user_id" not in st.session_state:
        st.session_state.user_id = "test_user_001"
    return st.session_state.user_id


def init_clients():
    """初始化客户端"""
    redis_client = get_redis_client()
    postgres_client = get_postgres_client()
    chat_agent = get_chat_agent(provider="dashscope")
    return redis_client, postgres_client, chat_agent


def render_sidebar(redis_client, postgres_client, user_id: str):
    """渲染左侧边栏 - 历史对话列表（不依赖 st.sidebar）"""
    # st.title("💬 历史对话")

    # 新建对话按钮
    if st.button("➕ 新建对话", use_container_width=True):
        # 创建新对话
        conversation = postgres_client.create_conversation(
            user_id=user_id,
            title="新对话",
        )
        st.session_state.current_conversation_id = conversation.id
        # 清除短期记忆
        redis_client.delete_short_term_memory(user_id, conversation.id)
        st.rerun()

    st.markdown("---")

    # 获取历史对话列表
    conversations = postgres_client.get_conversations(user_id)

    if not conversations:
        st.info("暂无历史对话")
    else:
        # 当前选中的对话
        current_id = st.session_state.get("current_conversation_id")

        for conv in conversations:
            # 显示标题（截断）
            title = conv.title[:30] + "..." if len(conv.title) > 30 else conv.title

            # 时间格式化
            time_str = conv.updated_at.strftime("%m-%d %H:%M")

            # 选中状态
            is_selected = current_id == conv.id

            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(
                    f"📝 {title}",
                    key=f"conv_{conv.id}",
                    use_container_width=True,
                ):
                    st.session_state.current_conversation_id = conv.id
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{conv.id}"):
                    postgres_client.delete_conversation(user_id, conv.id)
                    if current_id == conv.id:
                        st.session_state.current_conversation_id = None
                    st.rerun()

            if is_selected:
                st.caption(f"⏰ {time_str}")


def render_chat_area(redis_client, postgres_client, chat_agent, user_id: str):
    """渲染核心聊天区域"""
    st.title("💬 AI 面试助手")

    # 获取当前对话 ID
    conversation_id = st.session_state.get("current_conversation_id")

    # 如果没有当前对话，提示创建或选择
    if not conversation_id:
        st.info("👈 请在左侧选择或创建新对话")

        # 提供一个默认对话（如果没有历史）
        if st.button("开始新对话"):
            conversation = postgres_client.create_conversation(
                user_id=user_id,
                title="新对话",
            )
            st.session_state.current_conversation_id = conversation.id
            st.rerun()
        return

    # 加载当前对话的消息
    messages = postgres_client.get_messages(user_id, conversation_id)

    # 加载短期记忆
    short_term_memory = redis_client.get_short_term_memory(user_id, conversation_id)
    chat_context = short_term_memory.get("context", []) if short_term_memory else []

    # 如果数据库有消息，但短期记忆为空，从数据库恢复
    if not chat_context and messages:
        for msg in messages:
            chat_context.append({"role": msg.role, "content": msg.content})

    # 显示对话标题
    conversation = postgres_client.get_conversation(user_id, conversation_id)
    if conversation:
        st.subheader(f"📝 {conversation.title}")

        # 允许编辑标题
        with st.expander("编辑对话标题"):
            new_title = st.text_input("标题", value=conversation.title)
            if new_title != conversation.title and st.button("保存标题"):
                postgres_client.update_conversation_title(user_id, conversation_id, new_title)
                st.rerun()

    # 显示聊天记录
    for msg in chat_context:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 底部区域：图片上传 + 发送表单
    # 使用 st.form 确保用户点击发送后才处理
    with st.form("chat_form", clear_on_submit=True):
        col_upload, col_input, col_button = st.columns([1, 4, 1])

        with col_upload:
            # 图片上传按钮
            uploaded_file = st.file_uploader(
                "📎",
                type=["png", "jpg", "jpeg", "webp"],
                help="上传面经图片，自动提取题目",
                label_visibility="collapsed",
            )

            # 处理图片为 Base64（仅预览，不处理）
            attachments = []
            if uploaded_file:
                img_bytes = uploaded_file.getvalue()
                b64_img = base64.b64encode(img_bytes).decode()
                attachments.append(b64_img)
                # 预览已上传的图片
                st.image(uploaded_file, width=60, caption=uploaded_file.name)

        with col_input:
            # 聊天输入框
            prompt = st.text_area(
                "请输入你的问题，或上传面经图片自动提取题目...",
                height=70,
                label_visibility="collapsed",
            )

        with col_button:
            st.write("")
            st.write("")
            submitted = st.form_submit_button("发送", type="primary")

    # ========== 处理提交 ==========
    if submitted:
        # 设置 Request ID 和 Session ID（用于全链路追踪）
        request_id = set_request_id(str(uuid.uuid4())[:8])
        set_session_id(str(conversation_id))
        st.caption(f"🔗 Request ID: {request_id}")

        has_text = prompt is not None and prompt.strip() != "" if prompt else False
        has_image = len(attachments) > 0

        if not has_text and not has_image:
            st.warning("请输入问题或上传图片")
        else:
            # ========== Step 1: 图片 OCR 预处理 ==========
            ocr_message = None
            if has_image:
                tmp_paths = []
                for b64_img in attachments:
                    img_bytes = base64.b64decode(b64_img)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        tmp.write(img_bytes)
                        tmp_paths.append(tmp.name)

                try:
                    ocr_message = ocr_images(tmp_paths)
                    st.caption(f"📝 OCR 识别完成，共 {len(attachments)} 张图片")
                finally:
                    for tmp_path in tmp_paths:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

            # ========== Step 2: 构建消息内容 ==========
            img_count = len(attachments)
            display_content = prompt if has_text else f"[{img_count} 张图片]"
            with st.chat_message("user"):
                st.write(display_content)

            # 添加到短期记忆
            chat_context.append({"role": "user", "content": display_content})

            # 保存到数据库
            postgres_client.add_message(user_id, conversation_id, "user", display_content)

            # 如果是第一句话，自动生成标题
            if len(messages) == 0 and len(chat_context) == 1 and has_text:
                title = prompt[:50] + "..." if len(prompt) > 50 else prompt
                postgres_client.update_conversation_title(user_id, conversation_id, title)

            # ========== Step 3: 调用 Agent 处理 ==========
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""

                # 将历史消息 dict 转换为 LangChain BaseMessage
                # 注意：history_messages 只包含历史消息，不包括当前用户输入
                # 当前用户输入会通过 message 参数传入，由 chat_agent 内部追加
                history_messages = []
                # chat_context 已包含当前用户消息，所以取[:-1]排除当前消息
                for msg in chat_context[:-1]:
                    if msg["role"] == "user":
                        history_messages.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        history_messages.append(AIMessage(content=msg["content"]))

                # 如果有图片附件，追加 OCR 结果到历史
                if has_image and ocr_message:
                    history_messages.append(ocr_message)

                # 调用 Agent 处理
                try:
                    # 使用新的流式方法
                    user_input = prompt if has_text else "请分析这张图片"
                    for chunk in chat_agent.chat_streaming(
                        message=user_input,
                        history=history_messages,  # 只传历史消息，不含当前消息
                        session_id=str(conversation_id)
                    ):
                        full_response += chunk
                        response_placeholder.write(full_response)

                    if full_response:
                        response_placeholder.write(full_response)
                except Exception as e:
                    full_response = f"抱歉，我遇到了问题: {e}"
                    response_placeholder.write(full_response)

                # 添加 AI 回复到上下文
                chat_context.append({"role": "assistant", "content": full_response})

                # 保存到数据库
                postgres_client.add_message(user_id, conversation_id, "assistant", full_response)

                # 更新短期记忆
                redis_client.set_short_term_memory(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    context=chat_context,
                )

                st.rerun()


def main():
    """主函数"""
    # 初始化
    user_id = get_user_id()
    redis_client, postgres_client, chat_agent = init_clients()

    # 分栏布局
    col_sidebar, col_main = st.columns([1, 3])

    with col_sidebar:
        render_sidebar(redis_client, postgres_client, user_id)

    with col_main:
        render_chat_area(redis_client, postgres_client, chat_agent, user_id)


if __name__ == "__main__":
    main()