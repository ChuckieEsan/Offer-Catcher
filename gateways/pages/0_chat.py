"""页面 0: AI 聊天助手主界面

功能：
- 左侧：历史对话列表
- 中间：核心聊天区域
- 支持短期记忆（Redis）和长期记忆（PostgreSQL）
"""

import streamlit as st
from datetime import datetime

from app.db.redis_client import get_redis_client
from app.db.postgres_client import get_postgres_client


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
    return redis_client, postgres_client


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


def render_chat_area(redis_client, postgres_client, user_id: str):
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

    # 聊天输入
    if prompt := st.chat_input("请输入你的问题..."):
        # 显示用户消息
        with st.chat_message("user"):
            st.write(prompt)

        # 添加到短期记忆
        chat_context.append({"role": "user", "content": prompt})

        # 保存到数据库
        postgres_client.add_message(user_id, conversation_id, "user", prompt)

        # 如果是第一句话，自动生成标题
        if len(messages) == 0 and len(chat_context) == 1:
            title = prompt[:50] + "..." if len(prompt) > 50 else prompt
            postgres_client.update_conversation_title(user_id, conversation_id, title)

        # 模拟 AI 回复（TODO: 后续接入真正的 Agent）
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                # TODO: 这里后续接入 Chat Agent
                response = "我收到了你的消息！🎉\n\n这是 AI 面试助手的测试回复。后续我会接入真正的 Agent 来回答你的问题。\n\n你可以问我一些关于面试的问题，比如：\n- 帮我梳理一下 XXX 公司的常考知识点\n- 生成几道 XXX 岗位的面试题"

        # 添加 AI 回复到上下文
        chat_context.append({"role": "assistant", "content": response})

        # 保存到数据库
        postgres_client.add_message(user_id, conversation_id, "assistant", response)

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
    redis_client, postgres_client = init_clients()

    # 分栏布局
    col_sidebar, col_main = st.columns([1, 3])

    with col_sidebar:
        render_sidebar(redis_client, postgres_client, user_id)

    with col_main:
        render_chat_area(redis_client, postgres_client, user_id)


if __name__ == "__main__":
    main()