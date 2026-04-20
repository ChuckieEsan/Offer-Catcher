"use client";

import { useState, useEffect } from "react";
import { Card, Tabs, Spin, Empty, Typography } from "antd";
import { BookOutlined, SettingOutlined, UserOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";

const { Title } = Typography;

interface MemoryContent {
  content: string;
  reference_name?: string;
}

export default function MemoryPage() {
  const [loading, setLoading] = useState(true);
  const [memoryContent, setMemoryContent] = useState<string>("");
  const [preferences, setPreferences] = useState<string>("");
  const [behaviors, setBehaviors] = useState<string>("");

  const userId = "default_user";

  useEffect(() => {
    fetchMemoryData();
  }, []);

  const fetchMemoryData = async () => {
    setLoading(true);
    try {
      // Fetch all memory content in parallel
      const [memoryRes, prefsRes, behaviorsRes] = await Promise.all([
        fetch(`http://localhost:8000/api/v1/memory/${userId}/content`),
        fetch(`http://localhost:8000/api/v1/memory/${userId}/preferences`),
        fetch(`http://localhost:8000/api/v1/memory/${userId}/behaviors`),
      ]);

      if (memoryRes.ok) {
        const data = await memoryRes.json();
        setMemoryContent(data.content);
      }
      if (prefsRes.ok) {
        const data = await prefsRes.json();
        setPreferences(data.content);
      }
      if (behaviorsRes.ok) {
        const data = await behaviorsRes.json();
        setBehaviors(data.content);
      }
    } catch (error) {
      console.error("Failed to fetch memory:", error);
    } finally {
      setLoading(false);
    }
  };

  const tabItems = [
    {
      key: "overview",
      label: "概要",
      icon: <BookOutlined />,
      children: (
        <div style={{ padding: 16 }}>
          {loading ? (
            <Spin />
          ) : memoryContent ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {memoryContent}
              </ReactMarkdown>
            </div>
          ) : (
            <Empty description="暂无记忆内容" />
          )}
        </div>
      ),
    },
    {
      key: "preferences",
      label: "偏好设置",
      icon: <SettingOutlined />,
      children: (
        <div style={{ padding: 16 }}>
          {loading ? (
            <Spin />
          ) : preferences ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {preferences}
              </ReactMarkdown>
            </div>
          ) : (
            <Empty description="暂无偏好设置" />
          )}
        </div>
      ),
    },
    {
      key: "behaviors",
      label: "行为模式",
      icon: <UserOutlined />,
      children: (
        <div style={{ padding: 16 }}>
          {loading ? (
            <Spin />
          ) : behaviors ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {behaviors}
              </ReactMarkdown>
            </div>
          ) : (
            <Empty description="暂无行为模式" />
          )}
        </div>
      ),
    },
  ];

  return (
    <MainLayout>
      <Title level={3}>我的记忆</Title>
      <Card>
        <Tabs items={tabItems} />
      </Card>
      <style jsx global>{`
        .markdown-content {
          font-size: 14px;
          line-height: 1.8;
        }
        .markdown-content h1 {
          font-size: 20px;
          margin-bottom: 16px;
        }
        .markdown-content h2 {
          font-size: 16px;
          margin-top: 24px;
          margin-bottom: 12px;
        }
        .markdown-content h3 {
          font-size: 14px;
          margin-top: 16px;
          margin-bottom: 8px;
        }
        .markdown-content p {
          margin-bottom: 12px;
        }
        .markdown-content ul,
        .markdown-content ol {
          margin-left: 20px;
          margin-bottom: 12px;
        }
        .markdown-content li {
          margin-bottom: 4px;
        }
        .markdown-content table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 16px;
        }
        .markdown-content th,
        .markdown-content td {
          border: 1px solid #f0f0f0;
          padding: 8px 12px;
        }
        .markdown-content th {
          background: #fafafa;
        }
        .markdown-content code {
          background: #f5f5f5;
          padding: 2px 6px;
          border-radius: 3px;
          font-family: monospace;
        }
        .markdown-content pre {
          background: #f5f5f5;
          padding: 12px;
          border-radius: 6px;
          overflow-x: auto;
        }
      `}</style>
    </MainLayout>
  );
}