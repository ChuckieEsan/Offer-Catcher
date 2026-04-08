"use client";

import { useState } from "react";
import {
  Card,
  Tabs,
  Input,
  Button,
  Upload,
  App,
  List,
  Tag,
  Typography,
  Spin,
  Image,
  Space,
} from "antd";
import { UploadOutlined, InboxOutlined, CheckOutlined, FileImageOutlined } from "@ant-design/icons";
import MainLayout from "@/components/MainLayout";
import { extractText, extractImage, confirmIngest } from "@/lib/api";
import type { Question } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

export default function ExtractPage() {
  const { message } = App.useApp();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("正在提取...");
  const [result, setResult] = useState<{
    company: string;
    position: string;
    questions: Question[];
  } | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);

  const handleTextExtract = async () => {
    if (!text.trim()) {
      message.warning("请输入文本");
      return;
    }
    setLoading(true);
    setLoadingText("正在提取面经...");
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
    setLoadingText("正在 OCR 识别图片...");
    try {
      const fileList = files as unknown as FileList;
      // 启用 OCR 预处理：先 OCR 识别文字，再提取面经
      const res = await extractImage(fileList, true);
      setResult(res);
      message.success("提取成功");
    } catch (error) {
      message.error("提取失败，请检查图片是否清晰");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!result) return;
    setLoading(true);
    setLoadingText("正在入库...");
    try {
      const res = await confirmIngest(result);
      message.success(`入库成功：处理 ${res.processed} 条，触发 ${res.async_tasks} 个异步答案生成任务`);
      setResult(null);
      setText("");
      setFiles([]);
      setPreviewUrls([]);
    } catch (error) {
      message.error("入库失败");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (newFiles: File[]) => {
    setFiles(newFiles);

    // 生成预览 URL
    const urls = newFiles.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
  };

  const uploadProps = {
    multiple: true,
    accept: "image/*",
    beforeUpload: (file: File) => {
      // 检查文件类型
      if (!file.type.startsWith("image/")) {
        message.error("只能上传图片文件");
        return false;
      }
      // 检查文件大小（限制 10MB）
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

  return (
    <MainLayout>
      <Title level={3}>录入面经</Title>
      <Paragraph type="secondary">
        上传面经图片或输入文本，系统将自动提取题目并入库
      </Paragraph>

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
                  placeholder={`粘贴面经文本...\n\n示例：\n字节跳动 Agent开发面经：\n1. 什么是RAG？\n2. 讲讲你的Agent项目\n3. 如何优化LLM的推理速度？`}
                  rows={8}
                />
                <Button
                  type="primary"
                  style={{ marginTop: 16 }}
                  onClick={handleTextExtract}
                  loading={loading}
                  disabled={!text.trim()}
                >
                  提取
                </Button>
              </Card>
            ),
          },
          {
            key: "image",
            label: (
              <span>
                <FileImageOutlined style={{ marginRight: 4 }} />
                图片上传（OCR）
              </span>
            ),
            children: (
              <Card>
                <Dragger {...uploadProps}>
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽图片到此区域</p>
                  <p className="ant-upload-hint">
                    支持多张图片上传，系统将自动 OCR 识别文字并提取面经
                  </p>
                </Dragger>

                {/* 图片预览 */}
                {previewUrls.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Text type="secondary">已上传 {files.length} 张图片：</Text>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                      {previewUrls.map((url, index) => (
                        <Image
                          key={index}
                          src={url}
                          width={100}
                          height={100}
                          style={{ objectFit: "cover", borderRadius: 4 }}
                          alt={`预览 ${index + 1}`}
                        />
                      ))}
                    </div>
                  </div>
                )}

                <Button
                  type="primary"
                  style={{ marginTop: 16 }}
                  onClick={handleImageExtract}
                  loading={loading}
                  disabled={files.length === 0}
                >
                  OCR 识别并提取
                </Button>
              </Card>
            ),
          },
        ]}
      />

      {/* 加载状态 */}
      {loading && (
        <Card style={{ marginTop: 16, textAlign: "center" }}>
          <Spin size="large" />
          <Paragraph style={{ marginTop: 16, marginBottom: 0 }} type="secondary">
            {loadingText}
          </Paragraph>
        </Card>
      )}

      {/* 提取结果 */}
      {result && !loading && (
        <Card style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <Title level={4} style={{ marginBottom: 4 }}>
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
                    <Tag color={questionTypeColor[q.question_type] || "default"}>
                      {q.question_type}
                    </Tag>
                    <span style={{ marginLeft: 8, fontWeight: 500 }}>
                      {i + 1}. {q.question_text}
                    </span>
                  </div>
                  {q.core_entities && q.core_entities.length > 0 && (
                    <Space size={[4, 8]} wrap>
                      {q.core_entities.map((e) => (
                        <Tag key={e} color="geekblue" style={{ fontSize: 12 }}>
                          {e}
                        </Tag>
                      ))}
                    </Space>
                  )}
                </div>
              </List.Item>
            )}
          />

          <div style={{ marginTop: 16, textAlign: "right" }}>
            <Button onClick={() => {
              setResult(null);
              setFiles([]);
              setPreviewUrls([]);
            }} style={{ marginRight: 8 }}>
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