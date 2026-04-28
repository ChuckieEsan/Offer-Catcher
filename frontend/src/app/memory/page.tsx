"use client";

import { useState, useEffect } from "react";
import { Card, Tabs, Spin, Empty, Typography, Button, Space, App } from "antd";
import { BookOutlined, SettingOutlined, UserOutlined, EditOutlined, SaveOutlined, CloseOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { getMemoryContent, getPreferences, getBehaviors, updatePreferences, updateBehaviors } from "@/lib/api";

const { Title } = Typography;

export default function MemoryPage() {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [memoryContent, setMemoryContent] = useState<string>("");
  const [preferences, setPreferences] = useState<string>("");
  const [behaviors, setBehaviors] = useState<string>("");

  // 编辑状态
  const [editingTab, setEditingTab] = useState<string | null>(null);
  const [editContent, setEditContent] = useState<string>("");

  useEffect(() => {
    fetchMemoryData();
  }, []);

  const fetchMemoryData = async () => {
    setLoading(true);
    try {
      const [memoryRes, prefsRes, behaviorsRes] = await Promise.all([
        getMemoryContent(),
        getPreferences(),
        getBehaviors(),
      ]);

      // API 直接返回字符串
      setMemoryContent(memoryRes);
      setPreferences(prefsRes);
      setBehaviors(behaviorsRes);
    } catch (error) {
      message.error("加载记忆数据失败");
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (tabKey: string) => {
    const content = tabKey === "preferences" ? preferences : behaviors;
    setEditContent(content);
    setEditingTab(tabKey);
  };

  const handleCancelEdit = () => {
    setEditingTab(null);
    setEditContent("");
  };

  const handleSave = async () => {
    if (!editingTab) return;

    setSaving(true);
    try {
      if (editingTab === "preferences") {
        await updatePreferences(editContent);
        setPreferences(editContent);
        message.success("偏好设置已保存");
      } else if (editingTab === "behaviors") {
        await updateBehaviors(editContent);
        setBehaviors(editContent);
        message.success("行为模式已保存");
      }
      setEditingTab(null);
      setEditContent("");
    } catch (error) {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const renderTabContent = (
    tabKey: string,
    content: string,
    editable: boolean = false
  ) => {
    if (loading) {
      return <Spin />;
    }

    if (editingTab === tabKey) {
      return (
        <div style={{ padding: 16 }}>
          <Space style={{ marginBottom: 16 }}>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={saving}
            >
              保存
            </Button>
            <Button
              icon={<CloseOutlined />}
              onClick={handleCancelEdit}
              disabled={saving}
            >
              取消
            </Button>
          </Space>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            style={{
              width: "100%",
              minHeight: 400,
              padding: 12,
              border: "1px solid #d9d9d9",
              borderRadius: 6,
              fontFamily: "monospace",
              fontSize: 14,
              lineHeight: 1.6,
              resize: "vertical",
            }}
          />
        </div>
      );
    }

    if (!content) {
      return <Empty description="暂无内容" />;
    }

    return (
      <div style={{ padding: 16 }}>
        {editable && (
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => handleEdit(tabKey)}
            style={{ marginBottom: 16 }}
          >
            编辑
          </Button>
        )}
        <div className="markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {content}
          </ReactMarkdown>
        </div>
      </div>
    );
  };

  const tabItems = [
    {
      key: "overview",
      label: "概要",
      icon: <BookOutlined />,
      children: renderTabContent("overview", memoryContent, false),
    },
    {
      key: "preferences",
      label: "偏好设置",
      icon: <SettingOutlined />,
      children: renderTabContent("preferences", preferences, true),
    },
    {
      key: "behaviors",
      label: "行为模式",
      icon: <UserOutlined />,
      children: renderTabContent("behaviors", behaviors, true),
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