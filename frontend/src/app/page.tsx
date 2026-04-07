"use client";

import MainLayout from "@/components/MainLayout";
import { Typography, Card, Row, Col, Statistic } from "antd";
import {
  FileTextOutlined,
  BankOutlined,
  CheckCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";

const { Title, Paragraph } = Typography;

export default function HomePage() {
  return (
    <MainLayout>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <Title level={2}>欢迎使用 Offer-Catcher</Title>
        <Paragraph type="secondary">
          面试准备智能助手 - 基于 Multi-Agent 架构与混合 RAG
        </Paragraph>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="功能特性"
              value="Multi-Agent"
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="向量检索"
              value="RAG"
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="图数据库"
              value="Neo4j"
              prefix={<BankOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="异步处理"
              value="RabbitMQ"
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginTop: 24 }}>
        <Title level={4}>开始使用</Title>
        <Paragraph>
          1. <strong>AI 对话</strong>：与 AI 进行对话，支持面经提取、题目搜索、知识问答
        </Paragraph>
        <Paragraph>
          2. <strong>录入面经</strong>：上传文本或图片，自动提取题目并入库
        </Paragraph>
        <Paragraph>
          3. <strong>练习答题</strong>：选择题目进行练习，AI 实时评分
        </Paragraph>
        <Paragraph>
          4. <strong>题目管理</strong>：查看、编辑、删除已录入的题目
        </Paragraph>
        <Paragraph>
          5. <strong>数据仪表盘</strong>：查看统计数据和考频分析
        </Paragraph>
      </Card>
    </MainLayout>
  );
}