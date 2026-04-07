"use client";

import { useState, useEffect } from "react";
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Typography,
  Spin,
  message,
} from "antd";
import {
  FileTextOutlined,
  BankOutlined,
  CheckCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import MainLayout from "@/components/MainLayout";
import { getOverviewStats, getCompanyStats, getEntityStats } from "@/lib/api";
import type { CompanyStats, EntityStats } from "@/types";

const { Title } = Typography;

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<{
    total_questions: number;
    total_companies: number;
    has_answer: number;
    no_answer: number;
  } | null>(null);
  const [companies, setCompanies] = useState<CompanyStats[]>([]);
  const [entities, setEntities] = useState<EntityStats[]>([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [overviewData, companyData, entityData] = await Promise.all([
        getOverviewStats(),
        getCompanyStats(),
        getEntityStats(undefined, 10),
      ]);
      setOverview(overviewData);
      setCompanies(companyData);
      setEntities(entityData);
    } catch (error) {
      message.error("加载数据失败");
    } finally {
      setLoading(false);
    }
  };

  const companyColumns = [
    { title: "公司", dataIndex: "company", key: "company" },
    { title: "题目数", dataIndex: "count", key: "count" },
    { title: "已掌握", dataIndex: "mastered", key: "mastered" },
    { title: "已生成答案", dataIndex: "has_answer", key: "has_answer" },
  ];

  const entityColumns = [
    { title: "知识点", dataIndex: "entity", key: "entity" },
    { title: "出现次数", dataIndex: "count", key: "count" },
  ];

  if (loading) {
    return (
      <MainLayout>
        <div style={{ textAlign: "center", padding: 100 }}>
          <Spin size="large" />
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <Title level={3}>数据仪表盘</Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总题目数"
              value={overview?.total_questions || 0}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="公司数"
              value={overview?.total_companies || 0}
              prefix={<BankOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="已生成答案"
              value={overview?.has_answer || 0}
              prefix={<RobotOutlined />}
              valueStyle={{ color: "#3f8600" }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="待生成答案"
              value={overview?.no_answer || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: "#cf1322" }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="热门考点 TOP 10">
            <Table
              dataSource={entities}
              columns={entityColumns}
              rowKey="entity"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="各公司统计">
            <Table
              dataSource={companies.slice(0, 10)}
              columns={companyColumns}
              rowKey="company"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>
    </MainLayout>
  );
}