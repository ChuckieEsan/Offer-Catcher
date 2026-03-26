"""Streamlit 主入口 - 多页面应用

运行方式：
    streamlit run gateways/cli_chat.py
"""

import nest_asyncio
import streamlit as st

# 修复 Streamlit 在 Jupyter 环境下的兼容性问题
nest_asyncio.apply()

# 页面配置
st.set_page_config(
    page_title="Offer-Catcher - 面经智能体系统",
    page_icon="📚",
    layout="wide",
)

# 页面配置
st.markdown("### 📚 Offer-Catcher")
st.markdown("---")

# 使用 Streamlit 多页面导航
st.navigation([
    st.Page("pages/1_interview_input.py", title="录入面经", icon="📝"),
    st.Page("pages/2_practice.py", title="练习答题", icon="📝"),
    st.Page("pages/3_question_management.py", title="题目管理", icon="📋"),
    st.Page("pages/4_dashboard.py", title="仪表盘", icon="📊"),
]).run()