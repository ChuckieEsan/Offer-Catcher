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
} from "antd";
import { SendOutlined, ReloadOutlined } from "@ant-design/icons";
import MainLayout from "@/components/MainLayout";
import { search, scoreAnswer } from "@/lib/api";
import type { Question, SearchResult, ScoreResult } from "@/types";

const { TextArea } = Input;
const { Title, Paragraph } = Typography;

export default function PracticePage() {
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<SearchResult[]>([]);
  const [selectedQuestion, setSelectedQuestion] = useState<SearchResult | null>(null);
  const [userAnswer, setUserAnswer] = useState("");
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null);
  const [scoring, setScoring] = useState(false);

  const [mode, setMode] = useState<"random" | "search">("random");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    loadRandomQuestions();
  }, []);

  const loadRandomQuestions = async () => {
    setLoading(true);
    try {
      const res = await search({ query: "", k: 50 });
      // 只保留有答案的题目
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
    } catch (error) {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadRandomQuestions();
      return;
    }
    setLoading(true);
    try {
      const res = await search({ query: searchQuery, k: 20 });
      const withAnswer = res.results.filter((r) => r.question_answer);
      setQuestions(withAnswer);
    } catch (error) {
      message.error("搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRandomPick = () => {
    if (questions.length === 0) return;
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

  const getMasteryText = (level: number) => {
    const texts = ["未掌握", "熟悉", "已掌握"];
    return texts[level] || level;
  };

  return (
    <MainLayout activeKey="/practice" onMenuClick={() => {}}>
      <Title level={3}>练习答题</Title>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <Select
            value={mode}
            onChange={setMode}
            style={{ width: 120 }}
            options={[
              { value: "random", label: "随机抽题" },
              { value: "search", label: "搜索抽题" },
            ]}
          />
          {mode === "search" && (
            <>
              <Input
                placeholder="搜索关键词"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ width: 200 }}
                onPressEnter={handleSearch}
              />
              <Button onClick={handleSearch}>搜索</Button>
            </>
          )}
          {mode === "random" && (
            <Button icon={<ReloadOutlined />} onClick={handleRandomPick}>
              随机抽题
            </Button>
          )}
          <span>共 {questions.length} 道可选题目</span>
        </div>
      </Card>

      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin size="large" />
        </div>
      ) : selectedQuestion ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* 左侧：题目和答案输入 */}
          <Card title="题目">
            <div style={{ marginBottom: 16 }}>
              <Tag color="blue">{selectedQuestion.company}</Tag>
              <Tag>{selectedQuestion.question_type}</Tag>
            </div>
            <Paragraph style={{ fontSize: 16, fontWeight: 500 }}>
              {selectedQuestion.question_text}
            </Paragraph>
            {selectedQuestion.core_entities && selectedQuestion.core_entities.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <span style={{ marginRight: 8 }}>知识点：</span>
                {selectedQuestion.core_entities.map((e) => (
                  <Tag key={e} color="geekblue">{e}</Tag>
                ))}
              </div>
            )}

            <Title level={5} style={{ marginTop: 24 }}>你的答案</Title>
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
                  <Statistic
                    title="熟练度"
                    value={getMasteryText(scoreResult.mastery_level)}
                  />
                </div>

                {scoreResult.strengths.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <Title level={5}>优点</Title>
                    <List
                      size="small"
                      dataSource={scoreResult.strengths}
                      renderItem={(item) => (
                        <List.Item style={{ color: "#3f8600" }}>✓ {item}</List.Item>
                      )}
                    />
                  </div>
                )}

                {scoreResult.improvements.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <Title level={5}>改进建议</Title>
                    <List
                      size="small"
                      dataSource={scoreResult.improvements}
                      renderItem={(item) => (
                        <List.Item style={{ color: "#fa8c16" }}>→ {item}</List.Item>
                      )}
                    />
                  </div>
                )}

                {scoreResult.feedback && (
                  <div>
                    <Title level={5}>综合反馈</Title>
                    <Paragraph>{scoreResult.feedback}</Paragraph>
                  </div>
                )}

                {scoreResult.standard_answer && (
                  <div style={{ marginTop: 16 }}>
                    <Title level={5}>标准答案</Title>
                    <Paragraph type="secondary">{scoreResult.standard_answer}</Paragraph>
                  </div>
                )}
              </div>
            ) : (
              <Paragraph type="secondary">
                提交答案后将显示评分结果
              </Paragraph>
            )}
          </Card>
        </div>
      ) : (
        <Card>
          <Paragraph type="secondary">
            请选择抽题模式，然后点击抽题按钮开始练习
          </Paragraph>
        </Card>
      )}
    </MainLayout>
  );
}