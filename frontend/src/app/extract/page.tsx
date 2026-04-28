"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Tabs,
  Input,
  Button,
  Upload,
  App,
  Tag,
  Typography,
  Spin,
  Image,
  Space,
  Table,
  Modal,
  Drawer,
  List,
  Popconfirm,
  Badge,
  Tooltip,
  Row,
  Col,
  Statistic,
  Select,
} from "antd";
import {
  UploadOutlined,
  InboxOutlined,
  CheckOutlined,
  FileImageOutlined,
  EyeOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { XMarkdown } from "@ant-design/x-markdown";
import MainLayout from "@/components/MainLayout";
import {
  submitExtractTask,
  getExtractTasks,
  getExtractTask,
  updateExtractTask,
  confirmExtractTask,
  deleteExtractTask,
  getBatchAnswers,
} from "@/lib/api";
import type { Question, ExtractTaskListItem, ExtractTask } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

// 状态颜色和文字
const statusConfig: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending: { color: "default", text: "待处理", icon: <ClockCircleOutlined /> },
  processing: { color: "processing", text: "处理中", icon: <SyncOutlined spin /> },
  completed: { color: "success", text: "已完成", icon: <CheckCircleOutlined /> },
  failed: { color: "error", text: "失败", icon: <CloseCircleOutlined /> },
  confirmed: { color: "purple", text: "已入库", icon: <CheckCircleOutlined /> },
};

export default function ExtractPage() {
  const { message } = App.useApp();

  // 任务列表状态
  const [tasks, setTasks] = useState<ExtractTaskListItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksTotal, setTasksTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  // 新建任务
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // 任务详情
  const [detailDrawer, setDetailDrawer] = useState<{ visible: boolean; task: ExtractTask | null }>({
    visible: false,
    task: null,
  });
  const [detailLoading, setDetailLoading] = useState(false);
  const [answersMap, setAnswersMap] = useState<Record<string, string | null>>({});

  // 编辑题目
  const [editModal, setEditModal] = useState<{
    visible: boolean;
    questionIndex: number;
    questionText: string;
  }>({ visible: false, questionIndex: -1, questionText: "" });

  // 展开答案的状态
  const [answerModal, setAnswerModal] = useState<{
    visible: boolean;
    questionText: string;
    answer: string | null;
  }>({ visible: false, questionText: "", answer: null });

  // 加载任务列表
  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const res = await getExtractTasks({
        status: statusFilter,
        page,
        pageSize,
      });
      setTasks(res.items);
      setTasksTotal(res.total);
    } catch (error) {
      message.error("加载任务列表失败");
    } finally {
      setTasksLoading(false);
    }
  }, [statusFilter, page, pageSize, message]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // 自动刷新进行中的任务
  useEffect(() => {
    const hasProcessing = tasks.some((t) => t.status === "pending" || t.status === "processing");
    if (!hasProcessing) return;

    const timer = setInterval(loadTasks, 3000);
    return () => clearInterval(timer);
  }, [tasks, loadTasks]);

  // 提交文本任务
  const handleTextSubmit = async () => {
    if (!text.trim()) {
      message.warning("请输入文本");
      return;
    }
    setSubmitting(true);
    try {
      const res = await submitExtractTask({
        sourceType: "text",
        sourceContent: text,
      });
      message.success(res.message);
      setText("");
      loadTasks();
    } catch (error) {
      message.error("提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  // 提交图片任务
  const handleImageSubmit = async () => {
    if (files.length === 0) {
      message.warning("请上传图片");
      return;
    }

    setSubmitting(true);
    try {
      // 将图片转为 base64
      const base64Images = await Promise.all(
        files.map((file) => {
          return new Promise<string>((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.readAsDataURL(file);
          });
        })
      );

      const res = await submitExtractTask({
        sourceType: "image",
        sourceImages: base64Images,
      });
      message.success(res.message);
      setFiles([]);
      setPreviewUrls([]);
      loadTasks();
    } catch (error) {
      message.error("提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  // 查看任务详情
  const handleViewTask = async (taskId: number) => {
    setDetailLoading(true);
    setAnswersMap({});
    try {
      const task = await getExtractTask(taskId);
      setDetailDrawer({ visible: true, task });

      // 如果任务已入库，批量获取答案
      if (task.status === "confirmed" && task.result) {
        const questions = task.result.questions as Array<{ questionId?: string; question_id?: string }> | undefined;
        if (questions && questions.length > 0) {
          const questionIds = questions.map((q) => q.questionId || q.question_id || "");
          try {
            const { answers } = await getBatchAnswers(questionIds);
            setAnswersMap(answers);
          } catch (error) {
            console.error("Failed to fetch answers:", error);
          }
        }
      }
    } catch (error) {
      message.error("加载任务详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  // 确认入库
  const handleConfirm = async (taskId: number) => {
    try {
      const res = await confirmExtractTask(taskId);
      message.success(`入库成功：处理 ${res.processed} 条题目`);
      setDetailDrawer({ visible: false, task: null });
      loadTasks();
    } catch (error) {
      message.error("入库失败");
    }
  };

  // 删除任务
  const handleDelete = async (taskId: number) => {
    try {
      await deleteExtractTask(taskId);
      message.success("删除成功");
      loadTasks();
    } catch (error) {
      message.error("删除失败");
    }
  };

  // 编辑题目
  const handleEditQuestion = (index: number) => {
    const task = detailDrawer.task;
    const questions = task?.result?.questions as Array<{ question_text?: string; questionText?: string }> | undefined;
    if (!questions || !questions[index]) return;
    setEditModal({
      visible: true,
      questionIndex: index,
      questionText: questions[index].question_text || questions[index].questionText || "",
    });
  };

  // 保存编辑的题目
  const handleSaveQuestion = async () => {
    const task = detailDrawer.task;
    if (!task?.result) return;

    const questions = task.result.questions as Array<Record<string, unknown>>;
    const newQuestions = [...questions];
    newQuestions[editModal.questionIndex] = {
      ...newQuestions[editModal.questionIndex],
      questionText: editModal.questionText,
    };

    try {
      const updated = await updateExtractTask(task.taskId, {
        questions: newQuestions,
      });
      setDetailDrawer({ visible: true, task: updated });
      message.success("保存成功");
    } catch (error) {
      message.error("保存失败");
    } finally {
      setEditModal({ visible: false, questionIndex: -1, questionText: "" });
    }
  };

  // 删除题目
  const handleDeleteQuestion = async (index: number) => {
    const task = detailDrawer.task;
    if (!task?.result) return;

    const questions = task.result.questions as Array<Record<string, unknown>>;
    const newQuestions = questions.filter((_, i) => i !== index);

    try {
      const updated = await updateExtractTask(task.taskId, {
        questions: newQuestions,
      });
      setDetailDrawer({ visible: true, task: updated });
      message.success("删除成功");
    } catch (error) {
      message.error("删除失败");
    }
  };

  // 文件上传处理
  const uploadProps = {
    multiple: true,
    accept: "image/*",
    beforeUpload: (file: File) => {
      if (!file.type.startsWith("image/")) {
        message.error("只能上传图片文件");
        return false;
      }
      if (file.size > 10 * 1024 * 1024) {
        message.error("图片大小不能超过 10MB");
        return false;
      }
      setFiles((prev) => [...prev, file]);
      return false;
    },
    onRemove: (file: { name: string }) => {
      const index = files.findIndex((f) => f.name === file.name);
      setFiles((prev) => prev.filter((f) => f.name !== file.name));
      if (index !== -1 && previewUrls[index]) {
        URL.revokeObjectURL(previewUrls[index]);
        setPreviewUrls((prev) => prev.filter((_, i) => i !== index));
      }
    },
    fileList: files.map((f, i) => ({ uid: String(i), name: f.name, status: "done" as const })),
  };

  const questionTypeColor: Record<string, string> = {
    knowledge: "blue",
    project: "green",
    behavioral: "orange",
    scenario: "purple",
    algorithm: "cyan",
  };

  // 任务列表表格列
  const columns = [
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: string) => {
        const config = statusConfig[status] || statusConfig.pending;
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
    },
    {
      title: "来源",
      dataIndex: "sourceType",
      key: "sourceType",
      width: 80,
      render: (type: string) => (
        <Tag icon={type === "text" ? <FileTextOutlined /> : <FileImageOutlined />}>
          {type === "text" ? "文本" : "图片"}
        </Tag>
      ),
    },
    {
      title: "公司",
      dataIndex: "company",
      key: "company",
      ellipsis: true,
      render: (text: string, record: ExtractTaskListItem) => {
        if (text) return text;
        if (record.status === "pending") return <Text type="secondary">等待解析...</Text>;
        if (record.status === "processing") return <Text type="secondary">正在解析...</Text>;
        return "-";
      },
    },
    {
      title: "岗位",
      dataIndex: "position",
      key: "position",
      ellipsis: true,
      render: (text: string, record: ExtractTaskListItem) => {
        if (text) return text;
        if (record.status === "pending") return <Text type="secondary">等待解析...</Text>;
        if (record.status === "processing") return <Text type="secondary">正在解析...</Text>;
        return "-";
      },
    },
    {
      title: "题目数",
      dataIndex: "questionCount",
      key: "questionCount",
      width: 80,
      render: (count: number, record: ExtractTaskListItem) => {
        if (count > 0) return count;
        if (record.status === "pending" || record.status === "processing") {
          return <Text type="secondary">-</Text>;
        }
        return "-";
      },
    },
    {
      title: "时间",
      dataIndex: "createdAt",
      key: "createdAt",
      width: 150,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: "操作",
      key: "actions",
      width: 180,
      render: (_: unknown, record: ExtractTaskListItem) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewTask(record.taskId)}>
            查看
          </Button>
          {record.status !== "pending" && record.status !== "processing" && (
            <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.taskId)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <MainLayout>
      <Title level={3}>录入面经</Title>
      <Paragraph type="secondary">
        上传面经图片或输入文本，系统将异步解析并入库
      </Paragraph>

      {/* 新建任务 */}
      <Card style={{ marginBottom: 16 }}>
        <Tabs
          items={[
            {
              key: "text",
              label: "文本输入",
              children: (
                <div>
                  <TextArea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={`粘贴面经文本...\n\n示例：\n字节跳动 Agent开发面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目\n3. 如何优化LLM的推理速度？`}
                    rows={6}
                  />
                  <Button
                    type="primary"
                    style={{ marginTop: 16 }}
                    onClick={handleTextSubmit}
                    loading={submitting}
                    disabled={!text.trim()}
                  >
                    提交解析
                  </Button>
                </div>
              ),
            },
            {
              key: "image",
              label: (
                <span>
                  <FileImageOutlined style={{ marginRight: 4 }} />
                  图片上传
                </span>
              ),
              children: (
                <div
                  onPaste={(e) => {
                    const items = e.clipboardData?.items;
                    if (!items) return;

                    const newFiles: File[] = [];
                    const newUrls: string[] = [];

                    for (const item of items) {
                      if (item.type.startsWith("image/")) {
                        const file = item.getAsFile();
                        if (file) {
                          if (file.size > 10 * 1024 * 1024) {
                            message.error("图片大小不能超过 10MB");
                            continue;
                          }
                          newFiles.push(file);
                          newUrls.push(URL.createObjectURL(file));
                        }
                      }
                    }

                    if (newFiles.length > 0) {
                      setFiles((prev) => [...prev, ...newFiles]);
                      setPreviewUrls((prev) => [...prev, ...newUrls]);
                      message.success(`已粘贴 ${newFiles.length} 张图片`);
                    }
                  }}
                  tabIndex={0}
                  style={{ outline: "none" }}
                >
                  <Dragger {...uploadProps}>
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">点击或拖拽图片到此区域</p>
                    <p className="ant-upload-hint">支持多张图片，系统将异步 OCR 识别</p>
                    <p className="ant-upload-hint">也可直接粘贴剪贴板中的图片 (Ctrl+V)</p>
                  </Dragger>

                  {previewUrls.length > 0 && (
                    <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {previewUrls.map((url, index) => (
                        <Image
                          key={index}
                          src={url}
                          width={80}
                          height={80}
                          style={{ objectFit: "cover", borderRadius: 4 }}
                          alt={`预览 ${index + 1}`}
                        />
                      ))}
                    </div>
                  )}

                  <Button
                    type="primary"
                    style={{ marginTop: 16 }}
                    onClick={handleImageSubmit}
                    loading={submitting}
                    disabled={files.length === 0}
                  >
                    提交解析
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* 任务列表 */}
      <Card
        title="解析任务"
        extra={
          <Space>
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                setPage(1);
              }}
              options={Object.entries(statusConfig).map(([key, val]) => ({
                value: key,
                label: val.text,
              }))}
            />
            <Button icon={<ReloadOutlined />} onClick={loadTasks}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={tasks}
          columns={columns}
          rowKey="taskId"
          loading={tasksLoading}
          pagination={{
            current: page,
            pageSize,
            total: tasksTotal,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      {/* 任务详情抽屉 */}
      <Drawer
        title="任务详情"
        placement="right"
        size="large"
        open={detailDrawer.visible}
        onClose={() => setDetailDrawer({ visible: false, task: null })}
        loading={detailLoading}
      >
        {detailDrawer.task && (
          <div>
            {/* 任务状态 */}
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic
                    title="状态"
                    value={statusConfig[detailDrawer.task.status]?.text || detailDrawer.task.status}
                    prefix={statusConfig[detailDrawer.task.status]?.icon}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="来源"
                    value={detailDrawer.task.sourceType === "text" ? "文本" : "图片"}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="题目数"
                    value={(detailDrawer.task.result?.questions as Array<unknown> | undefined)?.length || 0}
                  />
                </Col>
              </Row>
            </Card>

            {/* 解析结果 */}
            {detailDrawer.task.result && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <Title level={5}>公司 / 岗位</Title>
                  <Text>
                    {(detailDrawer.task.result as Record<string, unknown>)?.company as string || "未识别"} /{" "}
                    {(detailDrawer.task.result as Record<string, unknown>)?.position as string || "未识别"}
                  </Text>
                </div>

                <Title level={5}>题目列表</Title>
                <List
                  dataSource={(detailDrawer.task.result?.questions as Question[]) || []}
                  renderItem={(q: Question, index: number) => {
                    const answer = answersMap[q.id];
                    return (
                      <List.Item
                        actions={
                          detailDrawer.task?.status === "completed"
                            ? [
                                <Button
                                  key="edit"
                                  size="small"
                                  icon={<EditOutlined />}
                                  onClick={() => handleEditQuestion(index)}
                                >
                                  编辑
                                </Button>,
                                <Popconfirm
                                  key="delete"
                                  title="删除这道题目？"
                                  onConfirm={() => handleDeleteQuestion(index)}
                                >
                                  <Button size="small" danger icon={<DeleteOutlined />} />
                                </Popconfirm>,
                              ]
                            : answer
                              ? [
                                  <Button
                                    key="view-answer"
                                    size="small"
                                    icon={<EyeOutlined />}
                                    onClick={() =>
                                      setAnswerModal({
                                        visible: true,
                                        questionText: q.questionText,
                                        answer: answer,
                                      })
                                    }
                                  >
                                    查看答案
                                  </Button>,
                                ]
                              : undefined
                        }
                      >
                        <List.Item.Meta
                          avatar={
                            <Tag color={questionTypeColor[q.questionType] || "default"}>
                              {q.questionType}
                            </Tag>
                          }
                          title={`${index + 1}. ${q.questionText}`}
                          description={
                            <div>
                              {q.coreEntities?.length > 0 && (
                                <Space size={[4, 8]} wrap style={{ marginBottom: 4 }}>
                                  {q.coreEntities.map((e) => (
                                    <Tag key={e} color="geekblue" style={{ fontSize: 12 }}>
                                      {e}
                                    </Tag>
                                  ))}
                                </Space>
                              )}
                              {/* 显示答案状态（已入库时） */}
                              {detailDrawer.task?.status === "confirmed" && (
                                <div style={{ marginTop: 8 }}>
                                  {answer ? (
                                    <Text type="secondary" style={{ fontSize: 13 }}>
                                      答案：{answer.slice(0, 80)}...
                                    </Text>
                                  ) : (
                                    <Tag color="orange" style={{ fontSize: 12 }}>
                                      答案生成中...
                                    </Tag>
                                  )}
                                </div>
                              )}
                            </div>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />

                {/* 操作按钮 */}
                {detailDrawer.task.status === "completed" && (
                  <div style={{ marginTop: 24, textAlign: "right" }}>
                    <Popconfirm
                      title="确认入库到题库？"
                      onConfirm={() => handleConfirm(detailDrawer.task!.taskId)}
                    >
                      <Button type="primary" icon={<CheckOutlined />}>
                        确认入库
                      </Button>
                    </Popconfirm>
                  </div>
                )}
              </>
            )}

            {/* 错误信息 */}
            {detailDrawer.task.status === "failed" && (
              <Card size="small" style={{ marginTop: 16, borderColor: "#ff4d4f" }}>
                <Text type="danger">错误: 任务处理失败</Text>
              </Card>
            )}

            {/* 处理中提示 */}
            {(detailDrawer.task.status === "pending" ||
              detailDrawer.task.status === "processing") && (
              <div style={{ textAlign: "center", padding: 24 }}>
                <Spin size="large" />
                <Paragraph type="secondary" style={{ marginTop: 16 }}>
                  正在解析中，请稍后刷新...
                </Paragraph>
              </div>
            )}
          </div>
        )}
      </Drawer>

      {/* 编辑题目弹窗 */}
      <Modal
        title="编辑题目"
        open={editModal.visible}
        onOk={handleSaveQuestion}
        onCancel={() => setEditModal({ visible: false, questionIndex: -1, questionText: "" })}
      >
        <TextArea
          value={editModal.questionText}
          onChange={(e) => setEditModal({ ...editModal, questionText: e.target.value })}
          rows={4}
        />
      </Modal>

      {/* 查看答案弹窗 */}
      <Modal
        title="查看答案"
        open={answerModal.visible}
        onCancel={() => setAnswerModal({ visible: false, questionText: "", answer: null })}
        footer={null}
        width="70%"
        style={{ top: 20 }}
      >
        <div style={{ marginBottom: 16 }}>
          <Text strong>题目：</Text>
          <Paragraph>{answerModal.questionText}</Paragraph>
        </div>
        <div>
          <Text strong>答案：</Text>
          <div
            style={{
              marginTop: 8,
              padding: 16,
              backgroundColor: "#fafafa",
              borderRadius: 8,
              fontSize: 14,
              lineHeight: 1.8,
            }}
          >
            <XMarkdown>{answerModal.answer || "暂无答案"}</XMarkdown>
          </div>
        </div>
      </Modal>
    </MainLayout>
  );
}