"use client";

import { useState, useEffect } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Drawer,
  Typography,
  Space,
  App,
  Popconfirm,
  Statistic,
  Row,
  Col,
  Empty,
  Spin,
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  StarFilled,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { getFavorites, removeFavorite, getQuestion } from "@/lib/api";
import type { FavoriteItem, Question } from "@/types";

const { Title, Paragraph } = Typography;

export default function FavoritesPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [questions, setQuestions] = useState<Record<number, Question>>({});
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 查看 Drawer
  const [viewDrawer, setViewDrawer] = useState<{
    visible: boolean;
    question: Question | null;
  }>({ visible: false, question: null });

  useEffect(() => {
    loadFavorites();
  }, [page, pageSize]);

  const loadFavorites = async () => {
    setLoading(true);
    try {
      const res = await getFavorites();
      setFavorites(res.favorites);

      // 批量获取题目详情
      const questionDetails: Record<number, Question> = {};
      for (const item of res.favorites) {
        try {
          const question = await getQuestion(item.questionId);
          questionDetails[item.questionId] = question;
        } catch (error) {
          console.error(`Failed to load question ${item.questionId}`);
        }
      }
      setQuestions(questionDetails);
    } catch (error) {
      message.error("加载收藏列表失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFavorite = async (favoriteId: number, questionId: number) => {
    try {
      await removeFavorite(favoriteId);
      message.success("已取消收藏");
      setFavorites((prev) => prev.filter((f) => f.favoriteId !== favoriteId));
      setQuestions((prev) => {
        const next = { ...prev };
        delete next[questionId];
        return next;
      });
    } catch (error) {
      message.error("操作失败");
    }
  };

  const handleView = (questionId: number) => {
    const question = questions[questionId];
    if (question) {
      setViewDrawer({ visible: true, question });
    }
  };

  const getMasteryTag = (level: number) => {
    const config: Record<number, { color: string; text: string }> = {
      0: { color: "red", text: "未掌握" },
      1: { color: "orange", text: "熟悉" },
      2: { color: "green", text: "已掌握" },
    };
    return <Tag color={config[level]?.color || "default"}>{config[level]?.text || level}</Tag>;
  };

  const columns = [
    {
      title: "公司",
      dataIndex: "questionId",
      key: "company",
      width: 140,
      render: (questionId: number) => {
        const question = questions[questionId];
        return question ? (
          <Tag color="blue">{question.company}</Tag>
        ) : (
          <Tag>加载中...</Tag>
        );
      },
    },
    {
      title: "题目",
      dataIndex: "questionId",
      key: "questionText",
      ellipsis: true,
      render: (questionId: number) => {
        const question = questions[questionId];
        return question ? (
          <a onClick={() => handleView(questionId)} style={{ color: "#1890ff" }}>
            {question.questionText}
          </a>
        ) : (
          "加载中..."
        );
      },
    },
    {
      title: "类型",
      dataIndex: "questionId",
      key: "questionType",
      width: 100,
      render: (questionId: number) => {
        const question = questions[questionId];
        return question ? <Tag>{question.questionType}</Tag> : null;
      },
    },
    {
      title: "熟练度",
      dataIndex: "questionId",
      key: "masteryLevel",
      width: 100,
      render: (questionId: number) => {
        const question = questions[questionId];
        return question ? getMasteryTag(question.masteryLevel) : null;
      },
    },
    {
      title: "收藏时间",
      dataIndex: "createdAt",
      key: "createdAt",
      width: 180,
      render: (createdAt: string) => new Date(createdAt).toLocaleString(),
    },
    {
      title: "操作",
      key: "actions",
      width: 150,
      fixed: "right" as const,
      render: (_: unknown, record: FavoriteItem) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleView(record.questionId)}
            disabled={!questions[record.questionId]}
          >
            查看
          </Button>
          <Popconfirm
            title="确定取消收藏？"
            onConfirm={() => handleRemoveFavorite(record.favoriteId, record.questionId)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <MainLayout>
      <Title level={3}>
        <StarFilled style={{ color: "#faad14", marginRight: 8 }} />
        我的收藏
      </Title>

      {/* 统计卡片 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={8}>
            <Statistic title="收藏总数" value={favorites.length} suffix="道题目" />
          </Col>
          <Col span={8}>
            <Statistic
              title="有答案"
              value={Object.values(questions).filter((q) => q.questionAnswer).length}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="未掌握"
              value={Object.values(questions).filter((q) => q.masteryLevel === 0).length}
            />
          </Col>
        </Row>
      </Card>

      {/* 收藏列表 */}
      <Card>
        {loading ? (
          <div style={{ textAlign: "center", padding: 40 }}>
            <Spin size="large" />
          </div>
        ) : favorites.length === 0 ? (
          <Empty description="暂无收藏题目" />
        ) : (
          <Table
            dataSource={favorites}
            columns={columns}
            rowKey="favoriteId"
            loading={loading}
            scroll={{ x: 800 }}
          />
        )}
      </Card>

      {/* 查看 Drawer */}
      <Drawer
        title="题目详情"
        placement="right"
        size="large"
        open={viewDrawer.visible}
        onClose={() => setViewDrawer({ visible: false, question: null })}
      >
        {viewDrawer.question && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag color="blue">{viewDrawer.question.company}</Tag>
              <Tag>{viewDrawer.question.questionType}</Tag>
              {getMasteryTag(viewDrawer.question.masteryLevel)}
            </Space>

            {viewDrawer.question.coreEntities && viewDrawer.question.coreEntities.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Title level={5}>知识点</Title>
                <div>
                  {viewDrawer.question.coreEntities.map((e) => (
                    <Tag key={e} color="geekblue" style={{ margin: 4 }}>
                      {e}
                    </Tag>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginBottom: 16 }}>
              <Title level={5}>题目内容</Title>
              <Paragraph style={{ background: "#f5f5f5", padding: 12, borderRadius: 4 }}>
                {viewDrawer.question.questionText}
              </Paragraph>
            </div>

            <div>
              <Title level={5}>答案</Title>
              {viewDrawer.question.questionAnswer ? (
                <div
                  style={{
                    background: "#f5f5f5",
                    padding: 12,
                    borderRadius: 4,
                    maxHeight: 400,
                    overflow: "auto",
                  }}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {viewDrawer.question.questionAnswer}
                  </ReactMarkdown>
                </div>
              ) : (
                <Paragraph type="secondary">暂无答案</Paragraph>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </MainLayout>
  );
}