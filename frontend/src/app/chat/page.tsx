"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Input,
  Button,
  Card,
  Typography,
  message,
} from "antd";
import {
  SendOutlined,
  ClearOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { chatStream } from "@/lib/api";
import type { Message } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph } = Typography;

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<boolean>(false);
  const messageAddedRef = useRef<boolean>(false);

  // 自动滚动到底部
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, streamingContent]);

  // 发送消息
  const handleSend = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStreamingContent("");
    abortRef.current = false;
    messageAddedRef.current = false;

    await chatStream(
      {
        message: input,
        session_id: sessionId,
        history: messages,
      },
      {
        onChunk: (chunk) => {
          if (!abortRef.current) {
            setStreamingContent((prev) => prev + chunk);
          }
        },
        onDone: () => {
          if (!messageAddedRef.current) {
            messageAddedRef.current = true;
            setStreamingContent((prev) => {
              if (prev && !abortRef.current) {
                const aiMessage: Message = { role: "assistant", content: prev };
                setMessages((msgs) => [...msgs, aiMessage]);
              }
              return "";
            });
          }
          setLoading(false);
        },
        onError: (error) => {
          message.error(`错误: ${error}`);
          setLoading(false);
        },
      }
    );
  }, [input, loading, messages, sessionId]);

  // 清空对话
  const handleClear = () => {
    setMessages([]);
    setStreamingContent("");
  };

  return (
    <MainLayout>
      <div style={{ height: "calc(100vh - 160px)", display: "flex", flexDirection: "column" }}>
        {/* 消息列表区域 */}
        <div
          ref={listRef}
          style={{
            flex: 1,
            overflow: "auto",
            padding: 16,
            background: "#fafafa",
            borderRadius: 8,
            marginBottom: 16,
          }}
        >
          {messages.length === 0 && !streamingContent && (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Title level={4} type="secondary">
                开始对话
              </Title>
              <Paragraph type="secondary">
                你可以问我关于面试的问题，或者让我帮你提取面经
              </Paragraph>
            </div>
          )}

          {/* 历史消息 */}
          {messages.map((msg, index) => (
            <div
              key={index}
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
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>{msg.content}</Paragraph>
                )}
              </Card>
            </div>
          ))}

          {/* 流式输出中的消息 */}
          {streamingContent && (
            <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
              <Card size="small" style={{ maxWidth: "80%", background: "#fff" }}>
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {streamingContent}
                  </ReactMarkdown>
                </div>
              </Card>
            </div>
          )}

          {/* 加载指示器 */}
          {loading && !streamingContent && (
            <div style={{ textAlign: "center", padding: 20 }}>
              <span style={{ color: "#999" }}>AI 思考中...</span>
            </div>
          )}
        </div>

        {/* 输入区域 */}
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
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            disabled={!input.trim()}
          >
            发送
          </Button>
          <Button icon={<ClearOutlined />} onClick={handleClear} disabled={loading}>
            清空
          </Button>
        </div>
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