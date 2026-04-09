// API 客户端
// 通过 Next.js rewrites 代理，使用相对路径避免跨域
// 开发时可通过 NEXT_PUBLIC_API_URL 环境变量覆盖（用于直接连接后端调试）

import axios from "axios";
import type {
  ChatRequest,
  Conversation,
  ConversationDetail,
  ConversationListResponse,
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
  ClusterStats,
  ExtractTask,
  ExtractTaskListResponse,
  ExtractTaskSubmitRequest,
  ExtractTaskSubmitResponse,
  ExtractTaskUpdateRequest,
} from "@/types";

// 默认使用相对路径（通过 Next.js rewrites 代理）
// 如需直接连接后端（绕过代理），设置 NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

const USER_ID_KEY = "offer_catcher_user_id";

/**
 * 获取用户 ID（用于长期记忆和会话管理）
 * 如果不存在则自动生成
 *
 * TODO: 测试完成后，移除下面的 "return 'default_user'" 行，
 * 启用后续的 UUID 生成逻辑以支持多用户
 */
export function getUserId(): string {
  return "default_user";
  // if (typeof window === "undefined") {
  //   return "default_user";
  // }
  //
  // let userId = localStorage.getItem(USER_ID_KEY);
  // if (!userId) {
  //   userId = crypto.randomUUID();
  //   localStorage.setItem(USER_ID_KEY, userId);
  // }
  // return userId;
}

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
});

// ========== Conversation API ==========

export async function getConversations(limit: number = 50): Promise<ConversationListResponse> {
  const res = await api.get("/conversations", {
    params: { limit },
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function createConversation(title: string = "新对话"): Promise<Conversation> {
  const res = await api.post("/conversations", { title }, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await api.get(`/conversations/${id}`, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function updateConversation(id: string, title: string): Promise<Conversation> {
  const res = await api.put(`/conversations/${id}`, { title }, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function deleteConversation(id: string): Promise<void> {
  await api.delete(`/conversations/${id}`, {
    headers: { "X-User-ID": getUserId() },
  });
}

export async function generateTitle(id: string): Promise<Conversation> {
  const res = await api.post(`/conversations/${id}/generate-title`, {}, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

// ========== Chat API ==========

/**
 * 流式聊天 API
 * 使用 Fetch API 处理 SSE 流式响应
 *
 * 注意：直接调用后端，绕过 Next.js rewrites 代理
 * Next.js 代理对 SSE 流式响应支持不完善，会导致流被缓冲
 */
export async function chatStream(
  request: ChatRequest & { user_id?: string },
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

  // 直接调用后端，绕过 Next.js rewrites 代理
  // SSE 流式响应需要直接连接后端
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  try {
    const response = await fetch(`${apiUrl}/chat/stream`, {
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
        if (buffer.trim()) {
          processSSELine(buffer, onChunk, safeOnDone);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
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

function processSSELine(
  line: string,
  onChunk: (chunk: string) => void,
  onDone: () => void
): void {
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

    try {
      // Backend now sends json.dumps(chunk) to preserve newlines
      const parsedChunk = JSON.parse(data);
      onChunk(parsedChunk);
    } catch (e) {
      // Fallback in case backend sends raw strings not json encoded
      onChunk(data);
    }
  }
}

// ========== Extract API ==========

/**
 * 从文本提取面经
 *
 * OCR + LLM 结构化提取耗时较长（可能超过 60 秒）
 * 直接调用后端，绕过 Next.js rewrites 代理
 */
export async function extractText(text: string): Promise<ExtractResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(`${apiUrl}/extract/text`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * 从图片提取面经（OCR + LLM 结构化）
 *
 * OCR 识别 + LLM 结构化提取耗时较长（可能超过 60 秒）
 * 直接调用后端，绕过 Next.js rewrites 代理
 */
export async function extractImage(
  files: FileList,
  useOcr: boolean = false
): Promise<ExtractResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  const formData = new FormData();
  Array.from(files).forEach((file) => {
    formData.append("images", file);
  });
  formData.append("use_ocr", String(useOcr));

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(`${apiUrl}/extract/image`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
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
  cluster_id?: string;
  keyword?: string;
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

/**
 * 重新生成答案
 *
 * TODO: 改用 SSE 流式接口
 *   - 后端改为 StreamingResponse，实时返回生成内容
 *   - 前端使用 EventSource 或 fetch + ReadableStream 接收
 *   - 用户可以看到生成进度，体验更好
 */
export async function regenerateAnswer(
  id: string,
  preview: boolean = true
): Promise<{ question_answer: string }> {
  // LLM + Web Search 耗时较长（可能超过 60 秒）
  // 直接调用后端，绕过 Next.js rewrites 代理的超时限制
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  // 使用 AbortController 实现超时（3 分钟）
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(`${apiUrl}/questions/${id}/regenerate?preview=${preview}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
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

export async function getClusterStats(): Promise<ClusterStats[]> {
  const res = await api.get("/stats/clusters");
  return res.data;
}

// ========== Extract Task API ==========

export async function submitExtractTask(
  request: ExtractTaskSubmitRequest
): Promise<ExtractTaskSubmitResponse> {
  const res = await api.post("/extract/submit", request, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function getExtractTasks(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<ExtractTaskListResponse> {
  const res = await api.get("/extract/tasks", {
    params,
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function getExtractTask(taskId: string): Promise<ExtractTask> {
  const res = await api.get(`/extract/tasks/${taskId}`, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function updateExtractTask(
  taskId: string,
  request: ExtractTaskUpdateRequest
): Promise<ExtractTask> {
  const res = await api.put(`/extract/tasks/${taskId}`, request, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function confirmExtractTask(taskId: string): Promise<{
  processed: number;
  async_tasks: number;
  question_ids: string[];
}> {
  const res = await api.post(`/extract/tasks/${taskId}/confirm`, {}, {
    headers: { "X-User-ID": getUserId() },
  });
  return res.data;
}

export async function deleteExtractTask(taskId: string): Promise<void> {
  await api.delete(`/extract/tasks/${taskId}`, {
    headers: { "X-User-ID": getUserId() },
  });
}