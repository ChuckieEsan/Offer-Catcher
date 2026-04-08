"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Layout,
  Button,
  Input,
  Card,
  Typography,
  Empty,
  Spin,
  Popconfirm,
  App,
} from "antd";
import {
  PlusOutlined,
  SendOutlined,
  DeleteOutlined,
  LoadingOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { XMarkdown } from "@ant-design/x-markdown";
import MainLayout from "@/components/MainLayout";
import {
  getConversations,
  createConversation,
  getConversation,
  deleteConversation,
  updateConversation,
  generateTitle,
  chatStream,
  getUserId,
} from "@/lib/api";
import type { Conversation, Message } from "@/types";

const { Sider, Content } = Layout;
const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

// 思考中提示组件
function ThinkingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <LoadingOutlined spin style={{ color: "#1890ff" }} />
      <Text type="secondary">AI 正在思考中...</Text>
    </div>
  );
}

export default function ChatPage() {
  const { message } = App.useApp();

  // 会话列表
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);

  // 当前会话
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);

  // 输入状态
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  // 记录已完成的消息 ID，用于切换渲染模式
  const [completedMessageIds, setCompletedMessageIds] = useState<Set<string>>(new Set());

  // 标题编辑状态
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Refs
  const listRef = useRef<HTMLDivElement>(null);
  const conversationsRef = useRef<Conversation[]>(conversations);
  const messagesRef = useRef<Message[]>(messages);

  // 更新 refs
  useEffect(() => {
    conversationsRef.current = conversations;
    messagesRef.current = messages;
  }, [conversations, messages]);

  // 加载会话列表
  useEffect(() => {
    loadConversations();
  }, []);

  // 自动滚动
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const loadConversations = async () => {
    setLoadingConversations(true);
    try {
      const res = await getConversations();
      setConversations(res.items);

      // 如果有会话，自动选择第一个
      if (res.items.length > 0 && !activeConversation) {
        handleSelectConversation(res.items[0].id);
      }
    } catch (error) {
      message.error("加载会话列表失败");
    } finally {
      setLoadingConversations(false);
    }
  };

  const handleSelectConversation = async (id: string) => {
    if (id === activeConversation) return;

    setActiveConversation(id);
    setLoadingMessages(true);
    setMessages([]);
    setStreamingMessageId(null);
    setCompletedMessageIds(new Set());

    try {
      const res = await getConversation(id);
      // 历史消息全部标记为已完成
      const completedIds = new Set(res.messages.map((m) => m.id));
      setCompletedMessageIds(completedIds);
      setMessages(res.messages);
    } catch (error) {
      message.error("加载消息失败");
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleCreateConversation = async () => {
    try {
      const conv = await createConversation();
      setConversations((prev) => [conv, ...prev]);
      setActiveConversation(conv.id);
      setMessages([]);
      setStreamingMessageId(null);
      setCompletedMessageIds(new Set());
      message.success("创建新对话");
    } catch (error) {
      message.error("创建会话失败");
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));

      if (activeConversation === id) {
        const remaining = conversations.filter((c) => c.id !== id);
        if (remaining.length > 0) {
          handleSelectConversation(remaining[0].id);
        } else {
          setActiveConversation(null);
          setMessages([]);
        }
      }
      message.success("删除成功");
    } catch (error) {
      message.error("删除失败");
    }
  };

  // 标题编辑相关
  const handleStartEditTitle = (conv: Conversation) => {
    setEditingConversationId(conv.id);
    setEditingTitle(conv.title);
  };

  const handleSaveTitle = async (id: string) => {
    if (!editingTitle.trim()) {
      setEditingConversationId(null);
      return;
    }
    try {
      const updated = await updateConversation(id, editingTitle.trim());
      setConversations((prev) =>
        prev.map((c) => c.id === updated.id ? updated : c)
      );
      message.success("标题已更新");
    } catch (error) {
      message.error("更新标题失败");
    }
    setEditingConversationId(null);
  };

  const handleCancelEditTitle = () => {
    setEditingConversationId(null);
    setEditingTitle("");
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming || !activeConversation) return;

    const userMessageId = `temp_${Date.now()}`;
    const userMessage: Message = {
      id: userMessageId,
      role: "user",
      content: input,
      created_at: new Date().toISOString(),
    };

    // 添加 AI 消息（流式输出时持续更新）
    const aiMessageId = `ai_${Date.now()}`;
    const aiMessage: Message = {
      id: aiMessageId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage, aiMessage]);
    const currentInput = input;
    setInput("");
    setStreaming(true);
    setStreamingMessageId(aiMessageId);

    await chatStream(
      {
        message: currentInput,
        conversation_id: activeConversation,
        user_id: getUserId(),
      },
      {
        onChunk: (chunk) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === aiMessageId
                ? { ...msg, content: msg.content + chunk }
                : msg
            )
          );
        },
        onDone: () => {
          setStreaming(false);
          setStreamingMessageId(null);
          // 标记消息已完成，触发从 streaming 模式切换到 complete 模式
          setCompletedMessageIds((prev) => new Set([...prev, aiMessageId]));

          // 自动生成标题（消息数达到 6 条且标题为"新对话"）
          const currentConv = conversationsRef.current.find((c) => c.id === activeConversation);
          if (currentConv && currentConv.title === "新对话") {
            // 计算消息总数（包括刚添加的 2 条消息）
            const totalMessages = messagesRef.current.length + 2;
            if (totalMessages >= 6) {
              generateTitle(activeConversation)
                .then((updated) => {
                  setConversations((prev) =>
                    prev.map((c) => c.id === updated.id ? updated : c)
                  );
                })
                .catch((err) => {
                  console.error("Failed to generate title:", err);
                });
            }
          }
        },
        onError: (error) => {
          setStreaming(false);
          setStreamingMessageId(null);
          setMessages((prev) => prev.filter((msg) => msg.id !== aiMessageId));
          message.error(`错误: ${error}`);
        },
      }
    );
  }, [input, streaming, activeConversation]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } else if (days === 1) {
      return "昨天";
    } else if (days < 7) {
      return `${days}天前`;
    } else {
      return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
    }
  };

  return (
    <MainLayout>
      <Layout style={{ height: "calc(100vh - 160px)", background: "#fff" }}>
        {/* 左侧会话列表 */}
        <Sider width={260} theme="light" style={{ borderRight: "1px solid #f0f0f0" }}>
          <div style={{ padding: 16 }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreateConversation}
              block
            >
              新建对话
            </Button>
          </div>

          {loadingConversations ? (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Spin />
            </div>
          ) : conversations.length === 0 ? (
            <Empty description="暂无对话" style={{ padding: 40 }} />
          ) : (
            <div style={{ overflow: "auto", maxHeight: "calc(100vh - 240px)" }}>
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv.id)}
                  style={{
                    cursor: "pointer",
                    background: activeConversation === conv.id ? "#e6f7ff" : "transparent",
                    padding: "12px 16px",
                    borderBottom: "1px solid #f0f0f0",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div style={{ flex: 1, overflow: "hidden", marginRight: 8 }}>
                    {editingConversationId === conv.id ? (
                      <Input
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onBlur={() => handleSaveTitle(conv.id)}
                        onPressEnter={(e) => {
                          e.preventDefault();
                          handleSaveTitle(conv.id);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            handleCancelEditTitle();
                          }
                        }}
                        size="small"
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                        style={{ width: "100%" }}
                      />
                    ) : (
                      <div
                        style={{
                          fontWeight: activeConversation === conv.id ? 600 : 400,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          handleStartEditTitle(conv);
                        }}
                      >
                        {conv.title}
                      </div>
                    )}
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatDate(conv.updated_at)}
                    </Text>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {editingConversationId !== conv.id && (
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStartEditTitle(conv);
                        }}
                      />
                    )}
                    <Popconfirm
                      title="确定删除此对话？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDeleteConversation(conv.id);
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        danger
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Sider>

        {/* 右侧聊天区域 */}
        <Content style={{ display: "flex", flexDirection: "column" }}>
          {!activeConversation ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Empty description="选择或创建一个对话开始聊天" />
            </div>
          ) : (
            <>
              {/* 消息列表 */}
              <div
                ref={listRef}
                style={{
                  flex: 1,
                  overflow: "auto",
                  padding: 16,
                  background: "#fafafa",
                }}
              >
                {loadingMessages ? (
                  <div style={{ textAlign: "center", padding: 40 }}>
                    <Spin />
                  </div>
                ) : messages.length === 0 ? (
                  <div style={{ textAlign: "center", padding: 40 }}>
                    <Title level={4} type="secondary">
                      开始对话
                    </Title>
                    <Paragraph type="secondary">
                      你可以问我关于面试的问题，或者让我帮你提取面经
                    </Paragraph>
                  </div>
                ) : (
                  <>
                    {messages.map((msg) => {
                      const isStreaming = msg.id === streamingMessageId;
                      const isCompleted = completedMessageIds.has(msg.id);

                      return (
                        <div
                          key={msg.id}
                          style={{
                            display: "flex",
                            justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                            marginBottom: 16,
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
                              // 内容为空时显示思考中
                              msg.content === "" ? (
                                <ThinkingIndicator />
                              ) : isStreaming && !isCompleted ? (
                                // Streaming 中：使用 XMarkdown 流式渲染
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
                                // 已完成：不传 streaming 配置
                                <XMarkdown
                                  content={msg.content}
                                  className="markdown-body"
                                />
                              )
                            ) : (
                              <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                                {msg.content}
                              </Paragraph>
                            )}
                          </Card>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>

              {/* 输入区域 */}
              <div style={{ padding: 16, borderTop: "1px solid #f0f0f0" }}>
                <div style={{ display: "flex", gap: 8 }}>
                  <TextArea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="输入消息... (Shift+Enter 换行，Enter 发送)"
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    onPressEnter={(e) => {
                      if (!e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    disabled={streaming}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    loading={streaming}
                    disabled={!input.trim()}
                  >
                    发送
                  </Button>
                </div>
              </div>
            </>
          )}
        </Content>
      </Layout>

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