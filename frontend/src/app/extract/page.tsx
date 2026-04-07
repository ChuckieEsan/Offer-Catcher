"use client";

import { useState } from "react";
import {
  Card,
  Tabs,
  Input,
  Button,
  Upload,
  message,
  List,
  Tag,
  Typography,
  Spin,
} from "antd";
import { UploadOutlined, InboxOutlined, CheckOutlined } from "@ant-design/icons";
import MainLayout from "@/components/MainLayout";
import { extractText, extractImage, confirmIngest } from "@/lib/api";
import type { Question } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph } = Typography;
const { Dragger } = Upload;

export default function ExtractPage() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    company: string;
    position: string;
    questions: Question[];
  } | null>(null);
  const [files, setFiles] = useState<File[]>([]);

  const handleTextExtract = async () => {
    if (!text.trim()) {
      message.warning("请输入文本");
      return;
    }
    setLoading(true);
    try {
      const res = await extractText(text);
      setResult(res);
      message.success("提取成功");
    } catch (error) {
      message.error("提取失败");
    } finally {
      setLoading(false);
    }
  };

  const handleImageExtract = async () => {
    if (files.length === 0) {
      message.warning("请上传图片");
      return;
    }
    setLoading(true);
    try {
      const fileList = files as unknown as FileList;
      const res = await extractImage(fileList, false);
      setResult(res);
      message.success("提取成功");
    } catch (error) {
      message.error("提取失败");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!result) return;
    setLoading(true);
    try {
      const res = await confirmIngest(result);
      message.success(`入库成功：处理 ${res.processed} 条，触发 ${res.async_tasks} 个异步任务`);
      setResult(null);
      setText("");
      setFiles([]);
    } catch (error) {
      message.error("入库失败");
    } finally {
      setLoading(false);
    }
  };

  const uploadProps = {
    multiple: true,
    accept: "image/*",
    beforeUpload: (file: File) => {
      setFiles((prev) => [...prev, file]);
      return false;
    },
    onRemove: (file: { name: string }) => {
      setFiles((prev) => prev.filter((f) => f.name !== file.name));
    },
    fileList: files.map((f, i) => ({ uid: String(i), name: f.name, status: "done" as const })),
  };

  return (
    <MainLayout>
      <Title level={3}>录入面经</Title>

      <Tabs
        items={[
          {
            key: "text",
            label: "文本输入",
            children: (
              <Card>
                <TextArea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="粘贴面经文本..."
                  rows={6}
                />
                <Button
                  type="primary"
                  style={{ marginTop: 16 }}
                  onClick={handleTextExtract}
                  loading={loading}
                >
                  提取
                </Button>
              </Card>
            ),
          },
          {
            key: "image",
            label: "图片上传",
            children: (
              <Card>
                <Dragger {...uploadProps}>
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽图片到此区域</p>
                  <p className="ant-upload-hint">支持多张图片上传</p>
                </Dragger>
                <Button
                  type="primary"
                  style={{ marginTop: 16 }}
                  onClick={handleImageExtract}
                  loading={loading}
                  disabled={files.length === 0}
                >
                  提取
                </Button>
              </Card>
            ),
          },
        ]}
      />

      {loading && (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin size="large" />
        </div>
      )}

      {result && !loading && (
        <Card style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <Title level={4}>
              {result.company} - {result.position}
            </Title>
            <Paragraph type="secondary">
              提取到 {result.questions.length} 道题目
            </Paragraph>
          </div>

          <List
            dataSource={result.questions}
            renderItem={(q, i) => (
              <List.Item>
                <div style={{ width: "100%" }}>
                  <div style={{ marginBottom: 8 }}>
                    <Tag color="blue">{q.question_type}</Tag>
                    <span style={{ marginLeft: 8 }}>{i + 1}. {q.question_text}</span>
                  </div>
                  {q.core_entities && q.core_entities.length > 0 && (
                    <div>
                      {q.core_entities.map((e) => (
                        <Tag key={e} color="geekblue">{e}</Tag>
                      ))}
                    </div>
                  )}
                </div>
              </List.Item>
            )}
          />

          <div style={{ marginTop: 16, textAlign: "right" }}>
            <Button onClick={() => setResult(null)} style={{ marginRight: 8 }}>
              取消
            </Button>
            <Button type="primary" icon={<CheckOutlined />} onClick={handleConfirm} loading={loading}>
              确认入库
            </Button>
          </div>
        </Card>
      )}
    </MainLayout>
  );
}