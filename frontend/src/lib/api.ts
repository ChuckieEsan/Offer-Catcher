// API 客户端

import axios from "axios";
import type {
  ChatRequest,
  ChatResponse,
  Question,
  QuestionListResponse,
  SearchRequest,
  SearchResponse,
  ExtractResponse,
  ScoreRequest,
  ScoreResult,
  OverviewStats,
  CompanyStats,
  EntityStats,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
});

// ========== Chat API ==========

export async function chat(request: ChatRequest): Promise<ChatResponse> {
  const res = await api.post("/chat", request);
  return res.data;
}

/**
 * 流式聊天 API
 * 使用 Fetch API 处理 SSE 流式响应
 */
export async function chatStream(
  request: ChatRequest,
  callbacks: {
    onChunk: (chunk: string) => void;
    onDone: () => void;
    onError: (error: string) => void;
  }
): Promise<void> {
  const { onChunk, onDone, onError } = callbacks;
  let doneCalled = false;

  const safeOnDone = () => {
    if (!doneCalled) {
      doneCalled = true;
      onDone();
    }
  };

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("No response body");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        // 处理缓冲区中剩余的数据
        if (buffer.trim()) {
          processSSELine(buffer, onChunk, safeOnDone);
        }
        break;
      }

      // 将新数据追加到缓冲区
      buffer += decoder.decode(value, { stream: true });

      // 按行分割处理
      const lines = buffer.split("\n");
      // 保留最后一个可能不完整的行
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          processSSELine(line, onChunk, safeOnDone);
        }
      }
    }

    safeOnDone();
  } catch (error) {
    onError(error instanceof Error ? error.message : "Unknown error");
  }
}

/**
 * 处理 SSE 格式的单行数据
 */
function processSSELine(
  line: string,
  onChunk: (chunk: string) => void,
  onDone: () => void
): void {
  // SSE 格式: "data: xxx"
  if (line.startsWith("data: ")) {
    const data = line.slice(6);

    if (data === "[DONE]") {
      onDone();
      return;
    }

    if (data.startsWith("[ERROR]")) {
      console.error("Stream error:", data);
      return;
    }

    // 正常内容
    onChunk(data);
  }
}

// ========== Extract API ==========

export async function extractText(text: string): Promise<ExtractResponse> {
  const res = await api.post("/extract/text", { text });
  return res.data;
}

export async function extractImage(
  files: FileList,
  useOcr: boolean = false
): Promise<ExtractResponse> {
  const formData = new FormData();
  Array.from(files).forEach((file) => {
    formData.append("images", file);
  });
  formData.append("use_ocr", String(useOcr));

  const res = await api.post("/extract/image", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return res.data;
}

export async function confirmIngest(
  interview: ExtractResponse
): Promise<{ processed: number; async_tasks: number }> {
  const res = await api.post("/extract/confirm", {
    interview,
    confirmed: true,
  });
  return res.data;
}

// ========== Score API ==========

export async function scoreAnswer(request: ScoreRequest): Promise<ScoreResult> {
  const res = await api.post("/score", request);
  return res.data;
}

// ========== Questions API ==========

export async function getQuestions(params: {
  company?: string;
  question_type?: string;
  mastery_level?: number;
  page?: number;
  page_size?: number;
}): Promise<QuestionListResponse> {
  const res = await api.get("/questions", { params });
  return res.data;
}

export async function getQuestion(id: string): Promise<Question> {
  const res = await api.get(`/questions/${id}`);
  return res.data;
}

export async function updateQuestion(
  id: string,
  data: Partial<Question>
): Promise<Question> {
  const res = await api.put(`/questions/${id}`, data);
  return res.data;
}

export async function deleteQuestion(id: string): Promise<void> {
  await api.delete(`/questions/${id}`);
}

export async function regenerateAnswer(id: string): Promise<{ question_answer: string }> {
  const res = await api.post(`/questions/${id}/regenerate`);
  return res.data;
}

// ========== Search API ==========

export async function search(request: SearchRequest): Promise<SearchResponse> {
  const res = await api.post("/search", request);
  return res.data;
}

// ========== Stats API ==========

export async function getOverviewStats(): Promise<OverviewStats> {
  const res = await api.get("/stats/overview");
  return res.data;
}

export async function getCompanyStats(): Promise<CompanyStats[]> {
  const res = await api.get("/stats/companies");
  return res.data;
}

export async function getEntityStats(
  company?: string,
  limit?: number
): Promise<EntityStats[]> {
  const res = await api.get("/stats/entities", {
    params: { company, limit },
  });
  return res.data;
}