"""页面4: 仪表盘"""

import streamlit as st

from app.pipelines.retrieval import get_retrieval_pipeline
from app.db.graph_client import get_graph_client


@st.cache_resource
def init_components():
    retrieval_pipeline = get_retrieval_pipeline()
    graph_client = get_graph_client()
    graph_client.connect()
    return retrieval_pipeline, graph_client


st.subheader("📊 数据仪表盘")

retrieval_pipeline, graph_client = init_components()

with st.spinner("加载数据..."):
    results = retrieval_pipeline.search(query="", k=500)

if not results:
    st.info("暂无数据")
    st.stop()

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
    st.markdown("#### 按公司分布")
    if by_company:
        st.bar_chart(by_company)

with col_chart2:
    st.markdown("#### 熟练度分布")
    mastery_data = {
        "未掌握": by_mastery[0],
        "熟悉": by_mastery[1],
        "已掌握": by_mastery[2],
    }
    st.bar_chart(mastery_data)

# 公司详情表格
st.markdown("#### 公司详情")
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

# 图数据库统计
st.markdown("---")
st.markdown("### 📈 图数据库统计（考频分析）")

if not graph_client.is_connected:
    st.warning("Neo4j 图数据库未连接，请在 .env 中配置 NEO4J 相关环境变量")
    st.info("提示：可通过 Docker 启动 Neo4j 容器")
else:
    with st.spinner("同步考点数据到图数据库..."):
        for r in results:
            if r.core_entities:
                graph_client.record_question_entities(r.company, r.core_entities)
        st.success("考点数据已同步")

    # 全局热门考点
    st.markdown("#### 热门考点 TOP 10")
    top_entities = graph_client.get_top_entities(limit=10)
    if top_entities:
        entity_data = {
            e["entity"]: e["count"] for e in top_entities
        }
        st.bar_chart(entity_data)
    else:
        st.info("暂无考点数据")

    # 按公司查看考点
    st.markdown("#### 各公司热门考点")
    companies_with_data = list(by_company.keys())[:5]
    for company in companies_with_data:
        with st.expander(f"{company} 的热门考点"):
            company_top = graph_client.get_top_entities(company=company, limit=5)
            if company_top:
                for e in company_top:
                    st.write(f"- {e['entity']}: {e['count']} 次")
            else:
                st.info("暂无数据")

    # 跨公司通用考点
    st.markdown("#### 跨公司通用考点")
    st.caption("多家公司同时考察的高频知识点")
    cross_company = graph_client.get_cross_company_entities(min_companies=2)
    if cross_company:
        cross_company_data = {
            e["entity"]: e["company_count"] for e in cross_company[:10]
        }
        st.bar_chart(cross_company_data)
        with st.expander("查看详情"):
            for e in cross_company[:10]:
                st.write(f"- **{e['entity']}**: 出现在 {e['company_count']} 家公司, 共 {e['total_count']} 次")
    else:
        st.info("暂无跨公司通用考点数据")