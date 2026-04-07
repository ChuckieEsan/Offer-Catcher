"use client";

import { useState, useEffect } from "react";
import {
  Card,
  Select,
  Button,
  Input,
  message,
  Typography,
  Tag,
  Statistic,
  List,
  Spin,
  Drawer,
  Space,
  Tabs,
} from "antd";
import {
  SendOutlined,
  ReloadOutlined,
  SearchOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MainLayout from "@/components/MainLayout";
import { search, scoreAnswer, getCompanyStats, getEntityStats } from "@/lib/api";
import type { SearchResult, ScoreResult, CompanyStats, EntityStats } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph } = Typography;

export default function PracticePage() {
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<SearchResult[]>([]);
  const [selectedQuestion, setSelectedQuestion] = useState<SearchResult | null>(null);
  const [userAnswer, setUserAnswer] = useState("");
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null);
  const [scoring, setScoring] = useState(false);

  // 抽题模式
  const [mode, setMode] = useState<string>("random");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCompany, setSelectedCompany] = useState<string | undefined>();
  const [selectedEntity, setSelectedEntity] = useState<string | undefined>();
  const [selectedMastery, setSelectedMastery] = useState<number | undefined>();

  // 过滤选项
  const [companies, setCompanies] = useState<CompanyStats[]>([]);
  const [entities, setEntities] = useState<EntityStats[]>([]);

  // 查看答案 Drawer
  const [answerDrawer, setAnswerDrawer] = useState<{ visible: boolean; question: SearchResult | null }>({
    visible: false,
    question: null,
  });

  useEffect(() => {
    loadFilterOptions();
    loadRandomQuestions();
  }, []);

  const loadFilterOptions = async () => {
    try {
      const [companyData, entityData] = await Promise.all([getCompanyStats(), getEntityStats(undefined, 50)]);
      setCompanies(companyData);
      setEntities(entityData);
    } catch (error) {
      console.error("加载过滤选项失败");
    }
  };

  const loadRandomQuestions = async () => {
    setLoading(true);
    try {
      const res = await search({ query: "", k: 200 });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
    } catch (error) {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    try {
      const res = await search({
        query: searchQuery,
        k: 50,
      });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
      if (withAnswer.length > 0) {
        message.success(`找到 ${withAnswer.length} 道带答案的题目`);
      } else {
        message.warning("未找到带答案的题目");
      }
    } catch (error) {
      message.error("搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleFilterByCompany = async () => {
    if (!selectedCompany) {
      loadRandomQuestions();
      return;
    }
    setLoading(true);
    try {
      const res = await search({ query: "", company: selectedCompany, k: 50 });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
      message.success(`找到 ${withAnswer.length} 道题目`);
    } catch (error) {
      message.error("搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleFilterByEntity = async () => {
    if (!selectedEntity) {
      loadRandomQuestions();
      return;
    }
    setLoading(true);
    try {
      const res = await search({ query: "", core_entities: [selectedEntity], k: 50 });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
      message.success(`找到 ${withAnswer.length} 道题目`);
    } catch (error) {
      message.error("搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleFilterByMastery = async () => {
    setLoading(true);
    try {
      const res = await search({ query: "", mastery_level: selectedMastery ?? 0, k: 50 });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
      message.success(`找到 ${withAnswer.length} 道题目`);
    } catch (error) {
      message.error("搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRandomPick = () => {
    if (questions.length === 0) {
      message.warning("没有可选题目，请先加载");
      return;
    }
    const randomIndex = Math.floor(Math.random() * questions.length);
    setSelectedQuestion(questions[randomIndex]);
    setUserAnswer("");
    setScoreResult(null);
  };

  const handleSubmit = async () => {
    if (!selectedQuestion || !userAnswer.trim()) {
      message.warning("请选择题目并输入答案");
      return;
    }
    setScoring(true);
    try {
      const result = await scoreAnswer({
        question_id: selectedQuestion.question_id,
        user_answer: userAnswer,
      });
      setScoreResult(result);
      message.success("评分完成");
    } catch (error) {
      message.error("评分失败");
    } finally {
      setScoring(false);
    }
  };

  const handleSelectQuestion = (q: SearchResult) => {
    setSelectedQuestion(q);
    setUserAnswer("");
    setScoreResult(null);
  };

  const getMasteryText = (level: number) => {
    const texts = ["未掌握", "熟悉", "已掌握"];
    return texts[level] || level;
  };

  const modeItems = [
    {
      key: "random",
      label: "随机抽题",
      children: (
        <Card>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={handleRandomPick} type="primary">
                随机抽题
              </Button>
              <Button onClick={loadRandomQuestions}>刷新题库</Button>
            </Space>
            <span style={{ color: "#666" }}>共 {questions.length} 道带答案的题目可选</span>
          </Space>
        </Card>
      ),
    },
    {
      key: "search",
      label: "语义搜索",
      children: (
        <Card>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              placeholder="输入关键词搜索题目"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={handleSearch}
              style={{ width: "calc(100% - 80px)" }}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              搜索
            </Button>
          </Space.Compact>
        </Card>
      ),
    },
    {
      key: "company",
      label: "按公司",
      children: (
        <Card>
          <Space>
            <Select
              placeholder="选择公司"
              showSearch
              allowClear
              style={{ width: 200 }}
              value={selectedCompany}
              onChange={(v) => setSelectedCompany(v)}
              options={companies.map((c) => ({ value: c.company, label: `${c.company} (${c.count})` }))}
            />
            <Button type="primary" onClick={handleFilterByCompany}>
              查找题目
            </Button>
          </Space>
        </Card>
      ),
    },
    {
      key: "entity",
      label: "按知识点",
      children: (
        <Card>
          <Space>
            <Select
              placeholder="选择知识点"
              showSearch
              allowClear
              style={{ width: 200 }}
              value={selectedEntity}
              onChange={(v) => setSelectedEntity(v)}
              options={entities.map((e) => ({ value: e.entity, label: `${e.entity} (${e.count})` }))}
            />
            <Button type="primary" onClick={handleFilterByEntity}>
              查找题目
            </Button>
          </Space>
        </Card>
      ),
    },
    {
      key: "mastery",
      label: "按熟练度",
      children: (
        <Card>
          <Space>
            <Select
              placeholder="选择熟练度"
              style={{ width: 150 }}
              value={selectedMastery}
              onChange={(v) => setSelectedMastery(v)}
              options={[
                { value: 0, label: "未掌握" },
                { value: 1, label: "熟悉" },
                { value: 2, label: "已掌握" },
              ]}
            />
            <Button type="primary" onClick={handleFilterByMastery}>
              查找题目
            </Button>
          </Space>
        </Card>
      ),
    },
    {
      key: "quick",
      label: "快速搜索",
      children: (
        <Card>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              placeholder="快速搜索查看答案"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={async () => {
                if (!searchQuery.trim()) return;
                setLoading(true);
                try {
                  const res = await search({ query: searchQuery, k: 20 });
                  setQuestions(res.results);
                } catch (error) {
                  message.error("搜索失败");
                } finally {
                  setLoading(false);
                }
              }}
              style={{ width: "calc(100% - 80px)" }}
            />
            <Button
              type="primary"
              onClick={async () => {
                if (!searchQuery.trim()) return;
                setLoading(true);
                try {
                  const res = await search({ query: searchQuery, k: 20 });
                  setQuestions(res.results);
                } catch (error) {
                  message.error("搜索失败");
                } finally {
                  setLoading(false);
                }
              }}
            >
              搜索
            </Button>
          </Space.Compact>
          {questions.length > 0 && (
            <List
              style={{ marginTop: 16 }}
              dataSource={questions}
              renderItem={(q) => (
                <List.Item
                  actions={[
                    <Button
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => setAnswerDrawer({ visible: true, question: q })}
                    >
                      查看答案
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <span>
                        <Tag color="blue">{q.company}</Tag>
                        {q.question_text.slice(0, 50)}...
                      </span>
                    }
                    description={
                      <Space>
                        <Tag>{q.question_type}</Tag>
                        <span style={{ color: q.question_answer ? "#52c41a" : "#999" }}>
                          {q.question_answer ? "有答案" : "待生成"}
                        </span>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      ),
    },
  ];

  return (
    <MainLayout>
      <Title level={3}>练习答题</Title>

      <Tabs items={modeItems} activeKey={mode} onChange={setMode} />

      {loading && (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin size="large" />
        </div>
      )}

      {!loading && mode !== "quick" && selectedQuestion ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* 左侧：题目和答案输入 */}
          <Card title="题目">
            <div style={{ marginBottom: 16 }}>
              <Tag color="blue">{selectedQuestion.company}</Tag>
              <Tag>{selectedQuestion.question_type}</Tag>
              <span style={{ marginLeft: 8, color: "#666" }}>{selectedQuestion.position}</span>
            </div>
            <Paragraph style={{ fontSize: 16, fontWeight: 500 }}>{selectedQuestion.question_text}</Paragraph>
            {selectedQuestion.core_entities && selectedQuestion.core_entities.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <span style={{ marginRight: 8, color: "#666" }}>知识点：</span>
                {selectedQuestion.core_entities.map((e) => (
                  <Tag key={e} color="geekblue">
                    {e}
                  </Tag>
                ))}
              </div>
            )}

            <Title level={5} style={{ marginTop: 24 }}>
              你的答案
            </Title>
            <TextArea
              value={userAnswer}
              onChange={(e) => setUserAnswer(e.target.value)}
              placeholder="请输入你的答案..."
              rows={6}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              style={{ marginTop: 16 }}
              onClick={handleSubmit}
              loading={scoring}
              disabled={!userAnswer.trim()}
            >
              提交评分
            </Button>
          </Card>

          {/* 右侧：评分结果 */}
          <Card title="评分结果">
            {scoreResult ? (
              <div>
                <div style={{ display: "flex", gap: 32, marginBottom: 24 }}>
                  <Statistic
                    title="得分"
                    value={scoreResult.score}
                    suffix="/ 100"
                    valueStyle={{ color: scoreResult.score >= 60 ? "#3f8600" : "#cf1322" }}
                  />
                  <Statistic title="熟练度" value={getMasteryText(scoreResult.mastery_level)} />
                </div>

                {scoreResult.strengths.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <Title level={5}>优点</Title>
                    <List
                      size="small"
                      dataSource={scoreResult.strengths}
                      renderItem={(item) => <List.Item style={{ color: "#3f8600" }}>✓ {item}</List.Item>}
                    />
                  </div>
                )}

                {scoreResult.improvements.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <Title level={5}>改进建议</Title>
                    <List
                      size="small"
                      dataSource={scoreResult.improvements}
                      renderItem={(item) => <List.Item style={{ color: "#fa8c16" }}>→ {item}</List.Item>}
                    />
                  </div>
                )}

                {scoreResult.feedback && (
                  <div style={{ marginBottom: 16 }}>
                    <Title level={5}>综合反馈</Title>
                    <Paragraph>{scoreResult.feedback}</Paragraph>
                  </div>
                )}

                {scoreResult.standard_answer && (
                  <div style={{ marginTop: 16 }}>
                    <Title level={5}>标准答案</Title>
                    <div
                      style={{
                        background: "#f5f5f5",
                        padding: 12,
                        borderRadius: 4,
                        maxHeight: 300,
                        overflow: "auto",
                      }}
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{scoreResult.standard_answer}</ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <Paragraph type="secondary">提交答案后将显示评分结果</Paragraph>
            )}
          </Card>
        </div>
      ) : !loading && mode !== "quick" && questions.length > 0 ? (
        <Card title={`可选题目 (${questions.length})`}>
          <List
            dataSource={questions.slice(0, 20)}
            renderItem={(q) => (
              <List.Item
                actions={[
                  <Button size="small" onClick={() => handleSelectQuestion(q)}>
                    选择
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      <Tag color="blue">{q.company}</Tag>
                      {q.question_text.slice(0, 40)}...
                    </span>
                  }
                  description={
                    <Space>
                      <Tag>{q.question_type}</Tag>
                      {q.core_entities?.slice(0, 3).map((e) => <Tag key={e} color="geekblue">{e}</Tag>)}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
      ) : null}

      {/* 快速搜索查看答案 Drawer */}
      <Drawer
        title="题目详情"
        placement="right"
        width={500}
        open={answerDrawer.visible}
        onClose={() => setAnswerDrawer({ visible: false, question: null })}
      >
        {answerDrawer.question && (
          <div>
            <Paragraph style={{ fontWeight: 500 }}>{answerDrawer.question.question_text}</Paragraph>
            <Space style={{ marginBottom: 16 }}>
              <Tag color="blue">{answerDrawer.question.company}</Tag>
              <Tag>{answerDrawer.question.question_type}</Tag>
            </Space>
            {answerDrawer.question.question_answer ? (
              <div>
                <Title level={5}>答案</Title>
                <div style={{ background: "#f5f5f5", padding: 12, borderRadius: 4 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {answerDrawer.question.question_answer}
                  </ReactMarkdown>
                </div>
              </div>
            ) : (
              <Paragraph type="secondary">暂无答案</Paragraph>
            )}
          </div>
        )}
      </Drawer>
    </MainLayout>
  );
}