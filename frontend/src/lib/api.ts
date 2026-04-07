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

export function chatStream(
  message: string,
  sessionId: string,
  history: Array<{ role: string; content: string }>,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  onError: (error: string) => void
): EventSource {
  // 使用 POST 需要用 fetch + ReadableStream，这里简化为 GET（需要后端支持）
  // 或者使用 fetch-event-source 库
  // 这里提供一个简化版本
  const es = new EventSource(
    `${API_BASE}/chat/stream?message=${encodeURIComponent(message)}&session_id=${sessionId}`
  );

  es.onmessage = (event) => {
    const data = event.data;
    if (data === "[DONE]") {
      es.close();
      onDone();
    } else if (data.startsWith("[ERROR]")) {
      es.close();
      onError(data.replace("[ERROR] ", ""));
    } else {
      onChunk(data);
    }
  };

  es.onerror = (err) => {
    es.close();
    onError("Connection error");
  };

  return es;
}

// 使用 fetch 的流式聊天（推荐）
export async function chatStreamFetch(
  request: ChatRequest,
  onChunk: (chunk: string) => void,
  onDone: () => void,
  onError: (error: string) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No reader available");
    }

    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") {
            onDone();
          } else if (data.startsWith("[ERROR]")) {
            onError(data.replace("[ERROR] ", ""));
          } else {
            onChunk(data);
          }
        }
      }
    }

    onDone();
  } catch (error) {
    onError(error instanceof Error ? error.message : "Unknown error");
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