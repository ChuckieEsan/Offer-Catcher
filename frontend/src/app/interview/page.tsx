"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Card,
  Typography,
  Button,
  Input,
  Select,
  Space,
  Spin,
  Progress,
  Tag,
  message,
  Divider,
  Empty,
} from "antd";
import {
  SendOutlined,
  QuestionCircleOutlined,
  ForwardOutlined,
  StopOutlined,
  ReloadOutlined,
  RightOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { XMarkdown } from "@ant-design/x-markdown";
import { useRouter } from "next/navigation";
import MainLayout from "@/components/MainLayout";
import VoiceInput from "@/components/VoiceInput";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// 公司列表
const COMPANIES = [
  "字节跳动",
  "阿里巴巴",
  "腾讯",
  "百度",
  "美团",
  "京东",
  "蚂蚁集团",
  "快手",
  "拼多多",
  "小红书",
];

// 岗位列表
const POSITIONS = [
  "后端开发",
  "前端开发",
  "算法工程师",
  "数据开发",
  "测试开发",
  "运维工程师",
  "AI Agent 开发岗",
  "产品经理",
];

// 难度选项
const DIFFICULTIES = [
  { value: "easy", label: "简单" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "困难" },
];

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  question?: string;
  isStreaming?: boolean;
}

interface SessionInfo {
  session_id: string;
  company: string;
  position: string;
  status: string;
  total_questions: number;
  current_question_idx: number;
  current_question?: string;
}

// 流式数据处理函数
function processSSELine(
  line: string,
  onChunk: (chunk: { type: string; content?: string; [key: string]: any }) => void,
  onDone: () => void
): void {
  if (line.startsWith("data: ")) {
    const data = line.slice(6);

    if (data === "[DONE]") {
      onDone();
      return;
    }

    if (data.startsWith("[ERROR]")) {
      console.error("Stream error:", data);
      return;
    }

    try {
      const parsed = JSON.parse(data);
      onChunk(parsed);
    } catch (e) {
      console.error("Failed to parse SSE data:", data);
    }
  }
}

// 思考中提示组件
function ThinkingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <LoadingOutlined spin style={{ color: "#1890ff" }} />
      <Text type="secondary">AI 面试官正在思考...</Text>
    </div>
  );
}

export default function InterviewPage() {
  const router = useRouter();

  // 面试配置
  const [company, setCompany] = useState<string>("");
  const [position, setPosition] = useState<string>("");
  const [difficulty, setDifficulty] = useState<string>("medium");

  // 会话状态
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  // 下一题按钮状态
  const [showNextButton, setShowNextButton] = useState(false);
  const [nextQuestionText, setNextQuestionText] = useState<string | null>(null);

  // 面试报告
  const [report, setReport] = useState<any>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 开始面试
  const handleStartInterview = async () => {
    if (!company || !position) {
      message.error("请选择公司和岗位");
      return;
    }

    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${apiUrl}/interview/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-ID": "default_user",
        },
        body: JSON.stringify({
          company,
          position,
          difficulty,
          total_questions: 10,
        }),
      });

      if (!response.ok) {
        throw new Error("创建面试失败");
      }

      const data = await response.json();
      setSession(data);

      // 添加 AI 开场白
      setMessages([
        {
          id: `ai_0`,
          role: "assistant",
          content: `你好！我是 ${company} 的面试官。今天我们将进行 ${position} 岗位的面试。\n\n让我们开始第一道题目：`,
          isStreaming: false,
        },
        {
          id: `q_0`,
          role: "assistant",
          content: "",
          question: data.current_question,
          isStreaming: false,
        },
      ]);
    } catch (error) {
      message.error("创建面试失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  // 提交回答（流式）
  const handleSubmitAnswer = useCallback(async () => {
    if (!input.trim() || !session || streaming) return;

    const answer = input.trim();
    setInput("");

    // 添加用户回答
    const userMsgId = `user_${Date.now()}`;
    setMessages((prev) => [...prev, { id: userMsgId, role: "user", content: answer }]);

    // 添加 AI 消息占位
    const aiMsgId = `ai_${Date.now()}`;
    setMessages((prev) => [...prev, { id: aiMsgId, role: "assistant", content: "", isStreaming: true }]);
    setStreaming(true);
    setStreamingMessageId(aiMsgId);
    setShowNextButton(false);
    setNextQuestionText(null);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

    try {
      const response = await fetch(`${apiUrl}/interview/sessions/${session.session_id}/answer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-ID": "default_user",
        },
        body: JSON.stringify({ answer }),
      });

      if (!response.ok) {
        throw new Error("提交回答失败");
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          if (buffer.trim()) {
            processSSELine(buffer, handleChunk, handleDone);
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.trim()) {
            processSSELine(line, handleChunk, handleDone);
          }
        }
      }

      handleDone();

    } catch (error) {
      message.error("提交回答失败");
      setStreaming(false);
      setStreamingMessageId(null);
      // 移除占位消息
      setMessages((prev) => prev.filter((msg) => msg.id !== aiMsgId));
    }
  }, [input, session, streaming]);

  // 处理流式数据块
  const handleChunk = useCallback((chunk: { type: string; content?: string; next_question?: string; [key: string]: any }) => {
    if (chunk.type === "text" && chunk.content) {
      // 更新 AI 消息内容
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamingMessageId
            ? { ...msg, content: msg.content + chunk.content }
            : msg
        )
      );
    } else if (chunk.type === "next_question_ready") {
      // 显示下一题按钮
      setShowNextButton(true);
      setNextQuestionText(chunk.next_question || null);
      // 更新题目索引
      if (chunk.question_idx !== undefined) {
        setSession((prev) =>
          prev ? { ...prev, current_question_idx: chunk.question_idx } : null
        );
      }
    } else if (chunk.type === "follow_up") {
      // 继续追问，更新题目索引
      if (chunk.question_idx !== undefined) {
        setSession((prev) =>
          prev ? { ...prev, current_question_idx: chunk.question_idx } : null
        );
      }
    } else if (chunk.type === "completed") {
      // 面试结束
      setShowNextButton(false);
      setNextQuestionText(null);
      fetchReport(session!.session_id);
    } else if (chunk.type === "error") {
      message.error(chunk.message || "发生错误");
    }
  }, [streamingMessageId, session]);

  // 流式结束
  const handleDone = useCallback(() => {
    setStreaming(false);
    setStreamingMessageId(null);
  }, []);

  // 点击下一题按钮
  const handleNextQuestion = async () => {
    if (!session) return;

    setShowNextButton(false);

    if (nextQuestionText) {
      setMessages((prev) => [
        ...prev,
        {
          id: `q_${Date.now()}`,
          role: "assistant",
          content: "",
          question: nextQuestionText,
          isStreaming: false,
        },
      ]);
      setNextQuestionText(null);
    } else {
      // 没有更多题目，结束面试
      message.info("面试结束");
      fetchReport(session.session_id);
    }
  };

  // 请求提示（流式）
  const handleRequestHint = useCallback(async () => {
    if (!session || streaming) return;

    // 添加 AI 消息占位
    const aiMsgId = `hint_${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: aiMsgId, role: "assistant", content: "", isStreaming: true },
    ]);
    setStreaming(true);
    setStreamingMessageId(aiMsgId);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

    try {
      const response = await fetch(`${apiUrl}/interview/sessions/${session.session_id}/hint`, {
        method: "POST",
        headers: { "X-User-ID": "default_user" },
      });

      if (!response.ok) {
        throw new Error("获取提示失败");
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.trim()) {
            processSSELine(line, (chunk) => {
              if (chunk.type === "text" && chunk.content) {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === aiMsgId
                      ? { ...msg, content: msg.content + chunk.content }
                      : msg
                  )
                );
              }
            }, () => {});
          }
        }
      }

      setStreaming(false);
      setStreamingMessageId(null);

    } catch (error) {
      message.error("获取提示失败");
      setStreaming(false);
      setStreamingMessageId(null);
      setMessages((prev) => prev.filter((msg) => msg.id !== aiMsgId));
    }
  }, [session, streaming]);

  // 跳过题目
  const handleSkipQuestion = async () => {
    if (!session) return;

    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${apiUrl}/interview/sessions/${session.session_id}/skip`, {
        method: "POST",
        headers: { "X-User-ID": "default_user" },
      });

      if (!response.ok) {
        throw new Error("跳过题目失败");
      }

      const data = await response.json();

      if (data.type === "completed") {
        setMessages((prev) => [...prev, { id: `skip_${Date.now()}`, role: "assistant", content: "面试已结束！" }]);
        await fetchReport(session.session_id);
      } else {
        setMessages((prev) => [
          ...prev,
          { id: `skip_${Date.now()}`, role: "assistant", content: "好的，跳过这道题。" },
          { id: `q_${Date.now()}`, role: "assistant", content: "", question: data.question },
        ]);
        setSession((prev) =>
          prev ? { ...prev, current_question_idx: data.question_idx } : null
        );
      }
    } catch (error) {
      message.error("跳过题目失败");
    } finally {
      setLoading(false);
    }
  };

  // 结束面试
  const handleEndInterview = async () => {
    if (!session) return;

    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      await fetch(`${apiUrl}/interview/sessions/${session.session_id}/end`, {
        method: "POST",
        headers: { "X-User-ID": "default_user" },
      });

      await fetchReport(session.session_id);
    } catch (error) {
      message.error("结束面试失败");
    } finally {
      setLoading(false);
    }
  };

  // 获取面试报告
  const fetchReport = async (sessionId: string) => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${apiUrl}/interview/sessions/${sessionId}/report`, {
        headers: { "X-User-ID": "default_user" },
      });

      if (!response.ok) {
        throw new Error("获取报告失败");
      }

      const data = await response.json();
      setReport(data);
    } catch (error) {
      message.error("获取面试报告失败");
    }
  };

  // 重新开始
  const handleRestart = () => {
    setSession(null);
    setMessages([]);
    setReport(null);
    setInput("");
    setShowNextButton(false);
    setNextQuestionText(null);
  };

  // 面试报告展示
  if (report) {
    return (
      <MainLayout>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <Card>
            <Title level={3}>面试报告</Title>
            <Divider />

            <Space direction="vertical" style={{ width: "100%" }} size="large">
              <div>
                <Text strong>公司：</Text>
                <Text>{report.company}</Text>
              </div>
              <div>
                <Text strong>岗位：</Text>
                <Text>{report.position}</Text>
              </div>
              <div>
                <Text strong>面试时长：</Text>
                <Text>{report.duration_minutes?.toFixed(1) || 0} 分钟</Text>
              </div>

              <Divider />

              <div>
                <Title level={4}>总体表现</Title>
                <Space size="large">
                  <div>
                    <Text type="secondary">题目总数</Text>
                    <br />
                    <Text strong style={{ fontSize: 24 }}>
                      {report.total_questions}
                    </Text>
                  </div>
                  <div>
                    <Text type="secondary">回答正确</Text>
                    <br />
                    <Text strong style={{ fontSize: 24, color: "#52c41a" }}>
                      {report.correct_count}
                    </Text>
                  </div>
                  <div>
                    <Text type="secondary">平均得分</Text>
                    <br />
                    <Text strong style={{ fontSize: 24 }}>
                      {report.average_score?.toFixed(1) || 0}
                    </Text>
                  </div>
                </Space>
              </div>

              {report.strengths?.length > 0 && (
                <div>
                  <Title level={5}>优势</Title>
                  {report.strengths.map((s: string, i: number) => (
                    <Tag key={i} color="green">
                      {s}
                    </Tag>
                  ))}
                </div>
              )}

              {report.weaknesses?.length > 0 && (
                <div>
                  <Title level={5}>薄弱点</Title>
                  {report.weaknesses.map((w: string, i: number) => (
                    <Tag key={i} color="red">
                      {w}
                    </Tag>
                  ))}
                </div>
              )}

              {report.recommendations?.length > 0 && (
                <div>
                  <Title level={5}>改进建议</Title>
                  <ul>
                    {report.recommendations.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              <Divider />

              <Button type="primary" icon={<ReloadOutlined />} onClick={handleRestart} block>
                再来一次
              </Button>
            </Space>
          </Card>
        </div>
      </MainLayout>
    );
  }

  // 面试配置页面
  if (!session) {
    return (
      <MainLayout>
        <div style={{ maxWidth: 600, margin: "0 auto" }}>
          <Card>
            <Title level={3}>AI 模拟面试官</Title>
            <Paragraph type="secondary">
              选择目标公司和岗位，开始模拟面试。AI 面试官会根据公司面试风格出题，并对你进行追问。
            </Paragraph>

            <Divider />

            <Space direction="vertical" style={{ width: "100%" }} size="large">
              <div>
                <Text strong>目标公司</Text>
                <Select
                  style={{ width: "100%", marginTop: 8 }}
                  placeholder="选择目标公司"
                  value={company}
                  onChange={setCompany}
                  options={COMPANIES.map((c) => ({ value: c, label: c }))}
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label ?? "").toLowerCase().includes(input.toLowerCase())
                  }
                />
              </div>

              <div>
                <Text strong>目标岗位</Text>
                <Select
                  style={{ width: "100%", marginTop: 8 }}
                  placeholder="选择目标岗位"
                  value={position}
                  onChange={setPosition}
                  options={POSITIONS.map((p) => ({ value: p, label: p }))}
                />
              </div>

              <div>
                <Text strong>难度设置</Text>
                <Select
                  style={{ width: "100%", marginTop: 8 }}
                  value={difficulty}
                  onChange={setDifficulty}
                  options={DIFFICULTIES}
                />
              </div>

              <Divider />

              <Button
                type="primary"
                size="large"
                block
                onClick={handleStartInterview}
                loading={loading}
              >
                开始面试
              </Button>
            </Space>
          </Card>
        </div>
      </MainLayout>
    );
  }

  // 面试进行中页面
  return (
    <MainLayout>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>
        {/* 顶部状态栏 */}
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Space>
              <Text strong>{session.company}</Text>
              <Text type="secondary">|</Text>
              <Text>{session.position}</Text>
            </Space>
            <Space>
              <Progress
                percent={((session.current_question_idx + 1) / session.total_questions) * 100}
                size="small"
                style={{ width: 120 }}
                format={() =>
                  `${session.current_question_idx + 1}/${session.total_questions}`
                }
              />
              <Button danger size="small" onClick={handleEndInterview}>
                结束面试
              </Button>
            </Space>
          </Space>
        </Card>

        {/* 对话区域 */}
        <Card style={{ marginBottom: 16, minHeight: 400, maxHeight: 500, overflow: "auto" }}>
          {messages.length === 0 ? (
            <Empty description="面试即将开始..." />
          ) : (
            <>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    marginBottom: 16,
                    display: "flex",
                    justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                  }}
                >
                  <Card
                    size="small"
                    style={{
                      maxWidth: "80%",
                      background: msg.role === "user" ? "#e6f7ff" : "#fff",
                    }}
                  >
                    {msg.role === "assistant" ? (
                      msg.content === "" && !msg.question ? (
                        <ThinkingIndicator />
                      ) : msg.question ? (
                        // 题目卡片
                        <div>
                          <Text strong style={{ fontSize: 16 }}>
                            {msg.question}
                          </Text>
                        </div>
                      ) : msg.isStreaming ? (
                        // 流式输出
                        <XMarkdown
                          content={msg.content}
                          streaming={{
                            hasNextChunk: true,
                            enableAnimation: true,
                            tail: true,
                          }}
                          className="markdown-body"
                        />
                      ) : (
                        // 已完成
                        <XMarkdown content={msg.content} className="markdown-body" />
                      )
                    ) : (
                      <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                        {msg.content}
                      </Paragraph>
                    )}
                  </Card>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </>
          )}
        </Card>

        {/* 下一题按钮 */}
        {showNextButton && (
          <Card style={{ marginBottom: 16, textAlign: "center" }}>
            <Button
              type="primary"
              icon={<RightOutlined />}
              onClick={handleNextQuestion}
              size="large"
            >
              继续下一题
            </Button>
          </Card>
        )}

        {/* 输入区域 */}
        <Card>
          <Space direction="vertical" style={{ width: "100%" }}>
            <TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入你的回答...（支持语音输入）"
              autoSize={{ minRows: 2, maxRows: 4 }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  handleSubmitAnswer();
                }
              }}
              disabled={loading || streaming || showNextButton}
            />

            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <Space wrap>
                <VoiceInput
                  onTranscriptChange={(text) => setInput(text)}
                  currentText={input}
                  disabled={loading || streaming || showNextButton}
                  language="zh-CN"
                />
                <Button
                  icon={<QuestionCircleOutlined />}
                  onClick={handleRequestHint}
                  loading={streaming}
                  disabled={loading || showNextButton}
                >
                  提示
                </Button>
                <Button
                  icon={<ForwardOutlined />}
                  onClick={handleSkipQuestion}
                  loading={loading}
                  disabled={streaming || showNextButton}
                >
                  跳过
                </Button>
              </Space>

              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSubmitAnswer}
                loading={streaming}
                disabled={!input.trim() || showNextButton}
              >
                发送
              </Button>
            </Space>
          </Space>
        </Card>
      </div>

      {/* Markdown 样式 */}
      <style jsx global>{`
        .markdown-body {
          line-height: 1.6;
        }
        .markdown-body p {
          margin: 0.5em 0;
        }
        .markdown-body ul, .markdown-body ol {
          padding-left: 1.5em;
          margin: 0.5em 0;
        }
        .markdown-body code {
          background: #f5f5f5;
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 0.9em;
        }
        .markdown-body pre {
          background: #f5f5f5;
          padding: 12px;
          border-radius: 6px;
          overflow-x: auto;
          margin: 0.5em 0;
        }
        .markdown-body pre code {
          background: none;
          padding: 0;
        }
        .markdown-body h1, .markdown-body h2, .markdown-body h3 {
          margin: 0.8em 0 0.4em;
          font-weight: 600;
        }
        .markdown-body blockquote {
          border-left: 3px solid #ddd;
          padding-left: 1em;
          margin: 0.5em 0;
          color: #666;
        }
      `}</style>
    </MainLayout>
  );
}