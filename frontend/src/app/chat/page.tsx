"use client";

import { useState, useRef, useEffect } from "react";
import {
  Input,
  Button,
  Card,
  List,
  Typography,
  Spin,
  message,
  Upload,
  Image,
} from "antd";
import {
  SendOutlined,
  PlusOutlined,
  ClearOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { chatStreamFetch } from "@/lib/api";
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

  useEffect(() => {
    // 滚动到底部
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, streamingContent]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStreamingContent("");

    try {
      await chatStreamFetch(
        {
          message: input,
          session_id: sessionId,
          history: messages,
        },
        (chunk) => {
          setStreamingContent((prev) => prev + chunk);
        },
        () => {
          setStreamingContent((prev) => {
            const aiMessage: Message = { role: "assistant", content: prev };
            setMessages((msgs) => [...msgs, aiMessage]);
            return "";
          });
          setLoading(false);
        },
        (error) => {
          message.error(`错误: ${error}`);
          setLoading(false);
        }
      );
    } catch (error) {
      message.error("发送失败");
      setLoading(false);
    }
  };

  const handleClear = () => {
    setMessages([]);
    setStreamingContent("");
  };

  return (
    <MainLayout activeKey="/chat" onMenuClick={() => {}}>
      <div style={{ height: "calc(100vh - 160px)", display: "flex", flexDirection: "column" }}>
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
          <List
            dataSource={messages}
            renderItem={(msg) => (
              <div
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
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    <Paragraph style={{ margin: 0 }}>{msg.content}</Paragraph>
                  )}
                </Card>
              </div>
            )}
          />
          {streamingContent && (
            <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
              <Card size="small" style={{ maxWidth: "80%", background: "#fff" }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamingContent}
                </ReactMarkdown>
              </Card>
            </div>
          )}
          {loading && !streamingContent && (
            <div style={{ textAlign: "center" }}>
              <Spin />
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息..."
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}>
            发送
          </Button>
          <Button icon={<ClearOutlined />} onClick={handleClear}>
            清空
          </Button>
        </div>
      </div>
    </MainLayout>
  );
}