"use client";

import { useState, useEffect } from "react";
import {
  Table,
  Card,
  Select,
  Button,
  Tag,
  Modal,
  Input,
  message,
  Popconfirm,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import MainLayout from "@/components/MainLayout";
import { getQuestions, updateQuestion, deleteQuestion, regenerateAnswer } from "@/lib/api";
import type { Question } from "@/types";

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

export default function QuestionsPage() {
  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 过滤器
  const [filterCompany, setFilterCompany] = useState<string | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterMastery, setFilterMastery] = useState<number | undefined>();

  // 编辑弹窗
  const [editModal, setEditModal] = useState<{
    visible: boolean;
    question: Question | null;
    editText: string;
    editAnswer: string;
  }>({ visible: false, question: null, editText: "", editAnswer: "" });

  useEffect(() => {
    loadQuestions();
  }, [page, pageSize, filterCompany, filterType, filterMastery]);

  const loadQuestions = async () => {
    setLoading(true);
    try {
      const res = await getQuestions({
        company: filterCompany,
        question_type: filterType,
        mastery_level: filterMastery,
        page,
        page_size: pageSize,
      });
      setQuestions(res.items);
      setTotal(res.total);
    } catch (error) {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (question: Question) => {
    setEditModal({
      visible: true,
      question,
      editText: question.question_text,
      editAnswer: question.question_answer || "",
    });
  };

  const handleSaveEdit = async () => {
    if (!editModal.question) return;
    try {
      await updateQuestion(editModal.question.question_id, {
        question_text: editModal.editText,
        question_answer: editModal.editAnswer,
      });
      message.success("保存成功");
      setEditModal({ visible: false, question: null, editText: "", editAnswer: "" });
      loadQuestions();
    } catch (error) {
      message.error("保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteQuestion(id);
      message.success("删除成功");
      loadQuestions();
    } catch (error) {
      message.error("删除失败");
    }
  };

  const handleRegenerate = async (id: string) => {
    message.loading("正在重新生成答案...");
    try {
      await regenerateAnswer(id);
      message.success("生成成功");
      loadQuestions();
    } catch (error) {
      message.error("生成失败");
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
      width: 120,
    },
    {
      title: "题目",
      dataIndex: "question_text",
      key: "question_text",
      ellipsis: true,
      render: (text: string) => (
        <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
          {text}
        </Paragraph>
      ),
    },
    {
      title: "类型",
      dataIndex: "question_type",
      key: "question_type",
      width: 100,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: "熟练度",
      dataIndex: "mastery_level",
      key: "mastery_level",
      width: 80,
      render: (level: number) => getMasteryTag(level),
    },
    {
      title: "答案",
      dataIndex: "question_answer",
      key: "question_answer",
      width: 80,
      render: (answer: string) => (
        <Tag color={answer ? "green" : "default"}>{answer ? "已有" : "待生成"}</Tag>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 150,
      render: (_: unknown, record: Question) => (
        <div style={{ display: "flex", gap: 8 }}>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          {!record.question_answer && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRegenerate(record.question_id)}>
              生成
            </Button>
          )}
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.question_id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <MainLayout activeKey="/questions" onMenuClick={() => {}}>
      <Title level={3}>题目管理</Title>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <Select
            placeholder="公司过滤"
            allowClear
            style={{ width: 150 }}
            value={filterCompany}
            onChange={setFilterCompany}
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
        </div>
      </Card>

      <Table
        dataSource={questions}
        columns={columns}
        rowKey="question_id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title="编辑题目"
        open={editModal.visible}
        onOk={handleSaveEdit}
        onCancel={() => setEditModal({ visible: false, question: null, editText: "", editAnswer: "" })}
        width={600}
      >
        <div style={{ marginBottom: 16 }}>
          <Title level={5}>题目内容</Title>
          <TextArea
            value={editModal.editText}
            onChange={(e) => setEditModal({ ...editModal, editText: e.target.value })}
            rows={3}
          />
        </div>
        <div>
          <Title level={5}>答案</Title>
          <TextArea
            value={editModal.editAnswer}
            onChange={(e) => setEditModal({ ...editModal, editAnswer: e.target.value })}
            rows={6}
          />
        </div>
      </Modal>
    </MainLayout>
  );
}