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
} from "@ant-design/icons";
import { MemoizedMarkdown, StreamingMarkdown } from "@/components/MemoizedMarkdown";
import MainLayout from "@/components/MainLayout";
import {
  getConversations,
  createConversation,
  getConversation,
  deleteConversation,
  chatStream,
} from "@/lib/api";
import type { Conversation, Message } from "@/types";

const { Sider, Content } = Layout;
const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

// AI 消息组件 - 使用 MemoizedMarkdown
function AIMessage({ content, id }: { content: string; id: string }) {
  return <MemoizedMarkdown content={content} id={id} className="markdown-body" />;
}

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
  const [streamingContent, setStreamingContent] = useState("");
  const [thinking, setThinking] = useState(false);
  const [streamComplete, setStreamComplete] = useState(false);

  // Refs
  const listRef = useRef<HTMLDivElement>(null);

  // 加载会话列表
  useEffect(() => {
    loadConversations();
  }, []);

  // 自动滚动
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, streamingContent, thinking]);

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
    setStreamingContent("");
    setThinking(false);

    try {
      const res = await getConversation(id);
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
      setStreamingContent("");
      setThinking(false);
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

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming || !activeConversation) return;

    const userMessage: Message = {
      id: `temp_${Date.now()}`,
      role: "user",
      content: input,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const currentInput = input;
    setInput("");
    setStreaming(true);  // 开始流式输出
    setThinking(true);  // 开始思考
    setStreamingContent("");
    setStreamComplete(false);  // 重置完成状态

    let responseText = "";

    await chatStream(
      {
        message: currentInput,
        conversation_id: activeConversation,
      },
      {
        onChunk: (chunk) => {
          // 收到第一个 chunk，停止思考状态
          if (!responseText) {
            setThinking(false);
          }
          responseText += chunk;
          setStreamingContent(responseText);
        },
        onDone: () => {
          setThinking(false);
          setStreamComplete(true);  // 标记流式完成
          // 延迟一点添加消息，让 Markdown 有时间渲染
          setTimeout(() => {
            if (responseText) {
              const aiMessage: Message = {
                id: `ai_${Date.now()}`,
                role: "assistant",
                content: responseText,
                created_at: new Date().toISOString(),
              };
              setMessages((prev) => [...prev, aiMessage]);
            }
            setStreamingContent("");
            setStreaming(false);
            setStreamComplete(false);
          }, 100);
        },
        onError: (error) => {
          setThinking(false);
          message.error(`错误: ${error}`);
          setStreaming(false);
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
                  <div style={{ flex: 1, overflow: "hidden" }}>
                    <div
                      style={{
                        fontWeight: activeConversation === conv.id ? 600 : 400,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {conv.title}
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatDate(conv.updated_at)}
                    </Text>
                  </div>
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
                ) : messages.length === 0 && !streamingContent && !thinking ? (
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
                    {messages.map((msg) => (
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
                            <AIMessage content={msg.content} id={msg.id} />
                          ) : (
                            <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                              {msg.content}
                            </Paragraph>
                          )}
                        </Card>
                      </div>
                    ))}

                    {/* 思考中提示 */}
                    {thinking && (
                      <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
                        <Card size="small" style={{ maxWidth: "80%", background: "#fff" }}>
                          <ThinkingIndicator />
                        </Card>
                      </div>
                    )}

                    {/* 流式输出内容 */}
                    {streamingContent && (
                      <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
                        <Card size="small" style={{ maxWidth: "80%", background: "#fff" }}>
                          <StreamingMarkdown
                            content={streamingContent}
                            isComplete={streamComplete}
                            id="streaming"
                          />
                        </Card>
                      </div>
                    )}
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
                    disabled={streaming || thinking}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    loading={streaming || thinking}
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
        .typing-cursor {
          display: inline-block;
          animation: blink 1s infinite;
          color: #1890ff;
          margin-left: 2px;
        }
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </MainLayout>
  );
}