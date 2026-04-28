"use client";

import { useState, useEffect } from "react";
import {
  Table,
  Card,
  Select,
  Button,
  Tag,
  Modal,
  Drawer,
  Input,
  App,
  Popconfirm,
  Typography,
  Space,
  Descriptions,
  Spin,
  Row,
  Col,
  Statistic,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  EyeOutlined,
  StarOutlined,
  StarFilled,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { getQuestions, getCompanyStats, getClusterStats, getOverviewStats, updateQuestion, deleteQuestion, regenerateAnswer, addFavorite, removeFavoriteByQuestionId, checkFavorites } from "@/lib/api";
import type { Question, CompanyStats, ClusterStats, OverviewStats } from "@/types";

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * 格式化 cluster_id 为可读名称
 * cluster_qlora_memory_optimization -> qlora / memory / optimization
 */
function formatClusterName(clusterId: string): string {
  if (!clusterId || clusterId === "未分类") return "未分类";
  return clusterId
    .replace(/^cluster_/, "")
    .replace(/_/g, " / ");
}

export default function QuestionsPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 公司列表
  const [companies, setCompanies] = useState<CompanyStats[]>([]);

  // 聚类列表
  const [clusters, setClusters] = useState<ClusterStats[]>([]);

  // 全局统计
  const [overviewStats, setOverviewStats] = useState<OverviewStats | null>(null);

  // 过滤器
  const [filterCompany, setFilterCompany] = useState<string | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterMastery, setFilterMastery] = useState<number | undefined>();
  const [filterCluster, setFilterCluster] = useState<string | undefined>();
  const [searchKeyword, setSearchKeyword] = useState<string | undefined>();
  const [filterFavorite, setFilterFavorite] = useState<boolean | undefined>();

  // 收藏状态
  const [favoriteStatus, setFavoriteStatus] = useState<Record<string, boolean>>({});

  // 查看 Drawer
  const [viewDrawer, setViewDrawer] = useState<{
    visible: boolean;
    question: Question | null;
  }>({ visible: false, question: null });

  // 编辑弹窗
  const [editModal, setEditModal] = useState<{
    visible: boolean;
    question: Question | null;
    editText: string;
    editAnswer: string;
    editMastery: number;
  }>({ visible: false, question: null, editText: "", editAnswer: "", editMastery: 0 });

  // 重新生成状态
  const [regenerating, setRegenerating] = useState<string | null>(null);

  // 答案预览 Modal
  const [previewModal, setPreviewModal] = useState<{
    visible: boolean;
    questionId: string;
    questionText: string;
    newAnswer: string;
  }>({ visible: false, questionId: "", questionText: "", newAnswer: "" });

  useEffect(() => {
    loadCompanies();
    loadClusters();
    loadOverviewStats();
  }, []);

  useEffect(() => {
    loadQuestions();
  }, [page, pageSize, filterCompany, filterType, filterMastery, filterCluster, searchKeyword, filterFavorite]);

  const loadCompanies = async () => {
    try {
      const res = await getCompanyStats();
      setCompanies(res);
    } catch (error) {
      console.error("加载公司列表失败");
    }
  };

  const loadClusters = async () => {
    try {
      const res = await getClusterStats();
      setClusters(res);
    } catch (error) {
      console.error("加载聚类列表失败");
    }
  };

  const loadOverviewStats = async () => {
    try {
      const res = await getOverviewStats();
      setOverviewStats(res);
    } catch (error) {
      console.error("加载全局统计失败");
    }
  };

  const loadQuestions = async () => {
    setLoading(true);
    try {
      const res = await getQuestions({
        company: filterCompany,
        questionType: filterType,
        masteryLevel: filterMastery,
        clusterId: filterCluster,
        keyword: searchKeyword,
        page,
        pageSize,
      });

      // 如果有收藏过滤，只显示收藏的题目
      let filteredItems = res.questions;
      if (filterFavorite) {
        // 先检查所有题目的收藏状态
        const questionIds = res.questions.map((q) => String(q.id));
        const { favorited } = await checkFavorites(questionIds);
        filteredItems = res.questions.filter((q) => favorited[String(q.id)]);
        setFavoriteStatus(favorited);
      } else {
        // 检查当前页题目的收藏状态
        if (res.questions.length > 0) {
          const questionIds = res.questions.map((q) => String(q.id));
          const { favorited } = await checkFavorites(questionIds);
          setFavoriteStatus(favorited);
        }
      }

      setQuestions(filteredItems);
      setTotal(filterFavorite ? filteredItems.length : res.total);
    } catch (error) {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleFavorite = async (questionId: string) => {
    try {
      if (favoriteStatus[questionId]) {
        await removeFavoriteByQuestionId(questionId);
        setFavoriteStatus((prev) => ({ ...prev, [questionId]: false }));
        message.success("已取消收藏");
        // 如果在收藏过滤模式下，从列表移除
        if (filterFavorite) {
          setQuestions((prev) => prev.filter((q) => String(q.id) !== questionId));
        }
      } else {
        await addFavorite(questionId);
        setFavoriteStatus((prev) => ({ ...prev, [questionId]: true }));
        message.success("已收藏");
      }
    } catch (error) {
      message.error("操作失败");
    }
  };

  const handleView = (question: Question) => {
    setViewDrawer({ visible: true, question });
  };

  const handleEdit = (question: Question) => {
    setEditModal({
      visible: true,
      question,
      editText: question.questionText,
      editAnswer: question.questionAnswer || "",
      editMastery: question.masteryLevel,
    });
  };

  const handleSaveEdit = async () => {
    if (!editModal.question) return;
    try {
      await updateQuestion(String(editModal.question.id), {
        questionText: editModal.editText,
        answer: editModal.editAnswer,
        masteryLevel: editModal.editMastery,
      });
      message.success("保存成功");
      setEditModal({ visible: false, question: null, editText: "", editAnswer: "", editMastery: 0 });
      loadQuestions();
    } catch (error) {
      message.error("保存失败");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteQuestion(String(id));
      message.success("删除成功");
      loadQuestions();
    } catch (error) {
      message.error("删除失败");
    }
  };

  const handleRegenerate = async (id: number) => {
    setRegenerating(String(id));
    const hide = message.loading("正在生成新答案...", 0);
    try {
      // preview=true 只生成不保存
      const res = await regenerateAnswer(String(id), true);
      hide();

      // 获取题目文本用于显示
      const question = questions.find(q => q.id === id);
      const questionText = question?.questionText || viewDrawer.question?.questionText || "";

      // 显示预览 Modal
      setPreviewModal({
        visible: true,
        questionId: String(id),
        questionText,
        newAnswer: res.questionAnswer || "",
      });
    } catch (error) {
      hide();
      message.error("生成失败");
    } finally {
      setRegenerating(null);
    }
  };

  // 确认保存新答案
  const handleConfirmAnswer = async () => {
    const { questionId, newAnswer } = previewModal;
    try {
      await updateQuestion(questionId, { answer: newAnswer });
      message.success("答案已保存");

      // 更新当前查看的内容
      if (viewDrawer.question && String(viewDrawer.question.id) === questionId) {
        setViewDrawer({
          visible: true,
          question: { ...viewDrawer.question, questionAnswer: newAnswer },
        });
      }
      // 更新编辑弹窗的内容
      if (editModal.question && String(editModal.question.id) === questionId) {
        setEditModal({
          ...editModal,
          editAnswer: newAnswer,
        });
      }
      setPreviewModal({ visible: false, questionId: "", questionText: "", newAnswer: "" });
      loadQuestions();
    } catch (error) {
      message.error("保存失败");
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
      dataIndex: "company",
      key: "company",
      width: 140,
      ellipsis: {
        showTitle: true,
      },
      render: (text: string) => (
        <Tag color="blue" style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {text}
        </Tag>
      ),
    },
    {
      title: "题目",
      dataIndex: "questionText",
      key: "questionText",
      ellipsis: {
        showTitle: true,
      },
      render: (text: string, record: Question) => (
        <a onClick={() => handleView(record)} style={{ color: "#1890ff" }}>
          {text}
        </a>
      ),
    },
    {
      title: "类型",
      dataIndex: "questionType",
      key: "questionType",
      width: 100,
      ellipsis: {
        showTitle: false,
      },
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: "熟练度",
      dataIndex: "masteryLevel",
      key: "masteryLevel",
      width: 100,
      ellipsis: {
        showTitle: false,
      },
      render: (level: number) => getMasteryTag(level),
    },
    {
      title: "答案",
      dataIndex: "questionAnswer",
      key: "questionAnswer",
      width: 80,
      ellipsis: {
        showTitle: false,
      },
      render: (answer: string) => (
        <Tag color={answer ? "green" : "default"}>{answer ? "已有" : "待生成"}</Tag>
      ),
    },
    {
      title: "收藏",
      key: "favorite",
      width: 60,
      render: (_: unknown, record: Question) => (
        <Button
          type="text"
          icon={favoriteStatus[String(record.id)] ? <StarFilled style={{ color: "#faad14" }} /> : <StarOutlined />}
          onClick={() => handleToggleFavorite(String(record.id))}
        />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 240,
      fixed: "right" as const,
      render: (_: unknown, record: Question) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleView(record)}>
            查看
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <MainLayout>
      <Title level={3}>题目管理</Title>

      {/* 统计卡片 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={6}>
            <Statistic title="聚类总数" value={clusters.length} />
          </Col>
          <Col span={6}>
            <Statistic title="题目总数" value={overviewStats?.totalQuestions ?? 0} suffix="道" />
          </Col>
          <Col span={6}>
            <Statistic
              title="有答案题目"
              value={overviewStats?.hasAnswer ?? 0}
              suffix={`/ ${overviewStats?.totalQuestions ?? 0}`}
            />
          </Col>
          <Col span={6}>
            <Statistic title="当前筛选结果" value={total} suffix="道题目" />
          </Col>
        </Row>
      </Card>

      {/* 过滤器 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Select
            placeholder="聚类过滤"
            allowClear
            showSearch
            style={{ width: 220 }}
            value={filterCluster}
            onChange={setFilterCluster}
            options={clusters.map((c) => ({
              value: c.clusterId,
              label: `${formatClusterName(c.clusterId)} (${c.count})`
            }))}
          />
          <Select
            placeholder="公司过滤"
            allowClear
            showSearch
            style={{ width: 180 }}
            value={filterCompany}
            onChange={setFilterCompany}
            options={companies.map((c) => ({ value: c.company, label: `${c.company} (${c.count})` }))}
          />
          <Select
            placeholder="类型过滤"
            allowClear
            style={{ width: 120 }}
            value={filterType}
            onChange={setFilterType}
            options={[
              { value: "knowledge", label: "知识题" },
              { value: "project", label: "项目题" },
              { value: "behavioral", label: "行为题" },
              { value: "scenario", label: "场景题" },
            ]}
          />
          <Select
            placeholder="熟练度过滤"
            allowClear
            style={{ width: 120 }}
            value={filterMastery}
            onChange={setFilterMastery}
            options={[
              { value: 0, label: "未掌握" },
              { value: 1, label: "熟悉" },
              { value: 2, label: "已掌握" },
            ]}
          />
          <Button
            type={filterFavorite ? "primary" : "default"}
            icon={filterFavorite ? <StarFilled /> : <StarOutlined />}
            onClick={() => setFilterFavorite(filterFavorite ? undefined : true)}
          >
            仅看收藏
          </Button>
          <Input.Search
            placeholder="搜索题目关键词"
            allowClear
            style={{ width: 240 }}
            defaultValue={searchKeyword}
            onSearch={(value) => setSearchKeyword(value || undefined)}
          />
        </Space>
      </Card>

      <Table
        dataSource={questions}
        columns={columns}
        rowKey="id"
        loading={loading}
        scroll={{ x: 780 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

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
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="公司">{viewDrawer.question.company}</Descriptions.Item>
              <Descriptions.Item label="岗位">{viewDrawer.question.position}</Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag>{viewDrawer.question.questionType}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="熟练度">
                {getMasteryTag(viewDrawer.question.masteryLevel)}
              </Descriptions.Item>
            </Descriptions>

            {viewDrawer.question.coreEntities && viewDrawer.question.coreEntities.length > 0 && (
              <div style={{ marginTop: 16 }}>
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

            <div style={{ marginTop: 16 }}>
              <Title level={5}>题目内容</Title>
              <Paragraph style={{ background: "#f5f5f5", padding: 12, borderRadius: 4 }}>
                {viewDrawer.question.questionText}
              </Paragraph>
            </div>

            <div style={{ marginTop: 16 }}>
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

            <div style={{ marginTop: 24, textAlign: "right" }}>
              <Space>
                <Button
                    type={viewDrawer.question.questionAnswer ? "default" : "primary"}
                    icon={<ReloadOutlined />}
                    loading={regenerating === String(viewDrawer.question?.id)}
                    onClick={() => handleRegenerate(viewDrawer.question!.id)}
                  >
                    {viewDrawer.question.questionAnswer ? "重新生成" : "生成答案"}
                  </Button>
                <Button icon={<EditOutlined />} onClick={() => handleEdit(viewDrawer.question!)}>
                  编辑
                </Button>
                <Popconfirm
                  title="确定删除这道题目？"
                  onConfirm={() => {
                    handleDelete(viewDrawer.question!.id);
                    setViewDrawer({ visible: false, question: null });
                  }}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            </div>
          </div>
        )}
      </Drawer>

      {/* 编辑 Modal */}
      <Modal
        title="编辑题目"
        open={editModal.visible}
        onOk={handleSaveEdit}
        onCancel={() => setEditModal({ visible: false, question: null, editText: "", editAnswer: "", editMastery: 0 })}
        width={700}
        okText="保存"
      >
        {editModal.question && (
          <div>
            <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="公司">{editModal.question.company}</Descriptions.Item>
              <Descriptions.Item label="岗位">{editModal.question.position}</Descriptions.Item>
            </Descriptions>

            <div style={{ marginBottom: 16 }}>
              <Title level={5}>题目内容</Title>
              <TextArea
                value={editModal.editText}
                onChange={(e) => setEditModal({ ...editModal, editText: e.target.value })}
                rows={4}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <Title level={5}>熟练度</Title>
              <Select
                value={editModal.editMastery}
                onChange={(v) => setEditModal({ ...editModal, editMastery: v })}
                options={[
                  { value: 0, label: "未掌握" },
                  { value: 1, label: "熟悉" },
                  { value: 2, label: "已掌握" },
                ]}
                style={{ width: 120 }}
              />
            </div>

            <div>
              <Title level={5}>答案</Title>
              <TextArea
                value={editModal.editAnswer}
                onChange={(e) => setEditModal({ ...editModal, editAnswer: e.target.value })}
                rows={8}
              />
            </div>
          </div>
        )}
      </Modal>

      {/* 答案预览确认 Modal */}
      <Modal
        title="预览新答案"
        open={previewModal.visible}
        onOk={handleConfirmAnswer}
        onCancel={() => setPreviewModal({ visible: false, questionId: "", questionText: "", newAnswer: "" })}
        width={700}
        okText="确认保存"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <Title level={5}>题目</Title>
          <Paragraph style={{ background: "#f5f5f5", padding: 12, borderRadius: 4 }}>
            {previewModal.questionText}
          </Paragraph>
        </div>
        <div>
          <Title level={5}>新答案</Title>
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
              {previewModal.newAnswer}
            </ReactMarkdown>
          </div>
        </div>
      </Modal>
    </MainLayout>
  );
}