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

# 预先加载所有组件（启动时初始化）
from app.agents.vision_extractor import get_vision_extractor
from app.agents.scorer import get_scorer_agent
from app.pipelines.ingestion import get_ingestion_pipeline
from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.qdrant_client import get_qdrant_manager
from app.db.graph_client import get_graph_client
from app.services.clustering_service import get_clustering_service

# 初始化所有组件（懒加载到 session_state）
if "components_initialized" not in st.session_state:
    with st.spinner("正在初始化组件..."):
        # 核心组件
        get_vision_extractor(provider="dashscope")
        get_scorer_agent(provider="dashscope")
        get_ingestion_pipeline()
        get_retrieval_pipeline()
        get_qdrant_manager()
        get_clustering_service()

        # 连接图数据库
        graph_client = get_graph_client()
        graph_client.connect()

        st.session_state.components_initialized = True
    st.rerun()

# 页面配置
# st.markdown("### 📚 Offer-Catcher")
# st.markdown("---")

# 使用 Streamlit 多页面导航
st.navigation([
    st.Page("pages/0_chat.py", title="AI 聊天", icon="💬"),
    st.Page("pages/1_interview_input.py", title="录入面经", icon="📝"),
    st.Page("pages/2_practice.py", title="练习答题", icon="📝"),
    st.Page("pages/3_question_management.py", title="题目管理", icon="📋"),
    st.Page("pages/4_dashboard.py", title="仪表盘", icon="📊"),
    st.Page("pages/5_cluster_view.py", title="考点聚类", icon="🏷️"),
]).run()