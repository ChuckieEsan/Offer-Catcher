// API 客户端
// 通过 Next.js rewrites 代理，使用相对路径避免跨域
// 开发时可通过 NEXT_PUBLIC_API_URL 环境变量覆盖（用于直接连接后端调试）

import axios from "axios";
import type {
  ChatRequest,
  Conversation,
  ConversationListResponse,
  Question,
  QuestionListResponse,
  QuestionCreateRequest,
  QuestionUpdateRequest,
  SearchRequest,
  SearchResponse,
  ExtractResponse,
  ExtractTask,
  ExtractTaskListResponse,
  ExtractTaskSubmitRequest,
  ExtractTaskSubmitResponse,
  ExtractTaskUpdateRequest,
  ExtractTaskConfirmResponse,
  ScoreRequest,
  ScoreResult,
  OverviewStats,
  CompanyStats,
  EntityStats,
  ClusterStats,
  PositionStats,
  FavoriteItem,
  FavoriteListResponse,
  CheckFavoritesResponse,
  InterviewSession,
  InterviewReport,
  CreateInterviewSessionRequest,
  SubmitAnswerRequest,
  MemoryResponse,
} from "@/types";

// 默认使用相对路径（通过 Next.js rewrites 代理）
// 如需直接连接后端（绕过代理），设置 NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

const USER_ID_KEY = "offer_catcher_user_id";

/**
 * 获取用户 ID（用于多用户数据隔离）
 * 如果不存在则自动生成 UUID
 */
export function getUserId(): string {
  if (typeof window === "undefined") {
    return "default_user";
  }

  let userId = localStorage.getItem(USER_ID_KEY);
  if (!userId) {
    userId = crypto.randomUUID();
    localStorage.setItem(USER_ID_KEY, userId);
  }
  return userId;
}

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
});

// ========== Conversation API ==========

export async function getConversations(limit: number = 50): Promise<ConversationListResponse> {
  const res = await api.get("/conversations", {
    params: { limit },
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function createConversation(title: string = "新对话"): Promise<Conversation> {
  const res = await api.post("/conversations", { title }, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getConversation(id: number): Promise<Conversation> {
  const res = await api.get(`/conversations/${id}`, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function updateConversationTitle(id: number, title: string): Promise<void> {
  await api.put(`/conversations/${id}/title`, { title }, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function generateTitle(id: number): Promise<Conversation> {
  const res = await api.post(`/conversations/${id}/generate-title`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function deleteConversation(id: number): Promise<void> {
  await api.delete(`/conversations/${id}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

// ========== Chat API ==========

/**
 * 流式聊天 API
 * 使用 Fetch API 处理 SSE 流式响应
 */
export async function chatStream(
  request: ChatRequest,
  callbacks: {
    onChunk: (chunk: string) => void;
    onReasoning?: (reasoning: string) => void;
    onDone: () => void;
    onError: (error: string) => void;
  }
): Promise<void> {
  const { onChunk, onReasoning, onDone, onError } = callbacks;
  let doneCalled = false;

  const safeOnDone = () => {
    if (!doneCalled) {
      doneCalled = true;
      onDone();
    }
  };

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  const userId = getUserId();

  try {
    const response = await fetch(`${apiUrl}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-User-Id": userId,
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
          processSSELine(buffer, onChunk, onReasoning, safeOnDone);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          processSSELine(line, onChunk, onReasoning, safeOnDone);
        }
      }
    }

    safeOnDone();
  } catch (error) {
    onError(error instanceof Error ? error.message : "Unknown error");
  }
}

interface StreamEvent {
  type: "token" | "reasoning" | "update" | "final" | "error";
  content: string;
  node?: string;
}

function processSSELine(
  line: string,
  onChunk: (chunk: string) => void,
  onReasoning: ((reasoning: string) => void) | undefined,
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
      const parsedChunk: StreamEvent = JSON.parse(data);

      if (parsedChunk.type === "reasoning" && onReasoning) {
        onReasoning(parsedChunk.content);
      } else if (parsedChunk.type === "token") {
        onChunk(parsedChunk.content);
      }
    } catch (e) {
      onChunk(data);
    }
  }
}

// ========== Extract API ==========

export async function extractText(text: string): Promise<ExtractResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(`${apiUrl}/extract/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

export async function extractImage(files: FileList): Promise<ExtractResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  const formData = new FormData();
  Array.from(files).forEach((file) => {
    formData.append("images", file);
  });

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

// ========== Extract Task API ==========

export async function submitExtractTask(
  request: ExtractTaskSubmitRequest
): Promise<ExtractTaskSubmitResponse> {
  const res = await api.post("/extract/submit", request, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getExtractTasks(params?: {
  status?: string;
  page?: number;
  pageSize?: number;
}): Promise<ExtractTaskListResponse> {
  const res = await api.get("/extract/tasks", {
    params,
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getExtractTask(taskId: number): Promise<ExtractTask> {
  const res = await api.get(`/extract/tasks/${taskId}`, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function updateExtractTask(
  taskId: number,
  request: ExtractTaskUpdateRequest
): Promise<ExtractTask> {
  const res = await api.put(`/extract/tasks/${taskId}`, request, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function confirmExtractTask(taskId: number): Promise<ExtractTaskConfirmResponse> {
  const res = await api.post(`/extract/tasks/${taskId}/confirm`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function cancelExtractTask(taskId: number): Promise<void> {
  await api.post(`/extract/tasks/${taskId}/cancel`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function deleteExtractTask(taskId: number): Promise<void> {
  await api.delete(`/extract/tasks/${taskId}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

// ========== Questions API ==========

export async function getQuestions(params: {
  company?: string;
  questionType?: string;
  masteryLevel?: number;
  clusterId?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
}): Promise<QuestionListResponse> {
  const res = await api.get("/questions", {
    params,
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getQuestion(id: string): Promise<Question> {
  const res = await api.get(`/questions/${id}`);
  return res.data;
}

export async function createQuestion(data: QuestionCreateRequest): Promise<Question> {
  const res = await api.post("/questions", data, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function updateQuestion(id: string, data: QuestionUpdateRequest): Promise<Question> {
  const res = await api.put(`/questions/${id}`, data);
  return res.data;
}

export async function deleteQuestion(id: string): Promise<void> {
  await api.delete(`/questions/${id}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function regenerateAnswer(id: string, preview: boolean = true): Promise<Question> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(`${apiUrl}/questions/${id}/regenerate?preview=${preview}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

export async function publishQuestion(id: string): Promise<Question> {
  const res = await api.post(`/questions/${id}/publish`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getBatchAnswers(
  questionIds: string[]
): Promise<{ answers: Record<string, string | null> }> {
  const res = await api.post("/questions/batch/answers", { questionIds });
  return res.data;
}

// ========== Search API ==========

export async function search(request: SearchRequest): Promise<SearchResponse> {
  const res = await api.post("/search", request, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

// ========== Score API ==========

export async function scoreAnswer(request: ScoreRequest): Promise<ScoreResult> {
  const res = await api.post("/score", request);
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

export async function getPositionStats(): Promise<PositionStats[]> {
  const res = await api.get("/stats/positions");
  return res.data;
}

export async function getEntityStats(company?: string, limit?: number): Promise<EntityStats[]> {
  const res = await api.get("/stats/entities", { params: { company, limit } });
  return res.data;
}

export async function getClusterStats(): Promise<ClusterStats[]> {
  const res = await api.get("/stats/clusters");
  return res.data;
}

// ========== Favorites API ==========

export async function addFavorite(questionId: string): Promise<FavoriteItem> {
  const res = await api.post("/favorites", { questionId }, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function removeFavorite(favoriteId: number): Promise<void> {
  await api.delete(`/favorites/${favoriteId}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function removeFavoriteByQuestionId(questionId: string): Promise<void> {
  await api.delete(`/favorites/by-question/${questionId}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function getFavorites(): Promise<FavoriteListResponse> {
  const res = await api.get("/favorites", {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function checkFavorites(questionIds: string[]): Promise<CheckFavoritesResponse> {
  // 去重，后端期望 String[] (Long 序列化后)
  const uniqueIds = [...new Set(questionIds)];
  const res = await api.post("/favorites/check", { questionIds: uniqueIds }, {
    headers: { "X-User-Id": getUserId() },
  });
  // 后端返回 Map<Long, Boolean>，转换为 Record<string, boolean>
  const favorited: Record<string, boolean> = {};
  for (const [key, value] of Object.entries(res.data.favorited || {})) {
    favorited[key] = Boolean(value);
  }
  return { favorited };
}

// ========== Interview API ==========

export async function createInterviewSession(
  request: CreateInterviewSessionRequest
): Promise<InterviewSession> {
  const res = await api.post("/interview/sessions", request, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getInterviewSessions(params?: {
  limit?: number;
  status?: string;
}): Promise<InterviewSession[]> {
  const res = await api.get("/interview/sessions", {
    params,
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getInterviewSession(sessionId: number): Promise<InterviewSession> {
  const res = await api.get(`/interview/sessions/${sessionId}`, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function submitInterviewAnswer(
  sessionId: number,
  request: SubmitAnswerRequest
): Promise<void> {
  // 流式回答，不等待完整响应
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  await fetch(`${apiUrl}/interview/sessions/${sessionId}/answer`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": getUserId(),
    },
    body: JSON.stringify(request),
  });
}

export async function getInterviewHint(sessionId: number): Promise<void> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  await fetch(`${apiUrl}/interview/sessions/${sessionId}/hint`, {
    method: "POST",
    headers: { "X-User-Id": getUserId() },
  });
}

export async function skipInterviewQuestion(sessionId: number): Promise<InterviewSession> {
  const res = await api.post(`/interview/sessions/${sessionId}/skip`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function pauseInterviewSession(sessionId: number): Promise<InterviewSession> {
  const res = await api.post(`/interview/sessions/${sessionId}/pause`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function resumeInterviewSession(sessionId: number): Promise<InterviewSession> {
  const res = await api.post(`/interview/sessions/${sessionId}/resume`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function endInterviewSession(sessionId: number): Promise<InterviewSession> {
  const res = await api.post(`/interview/sessions/${sessionId}/end`, {}, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getInterviewReport(sessionId: number): Promise<InterviewReport> {
  const res = await api.get(`/interview/sessions/${sessionId}/report`, {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function deleteInterviewSession(sessionId: number): Promise<void> {
  await api.delete(`/interview/sessions/${sessionId}`, {
    headers: { "X-User-Id": getUserId() },
  });
}

// ========== Memory API ==========

export async function getMemory(): Promise<MemoryResponse> {
  const res = await api.get("/memory/me", {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getMemoryContent(): Promise<string> {
  const res = await api.get("/memory/me/content", {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getPreferences(): Promise<string> {
  const res = await api.get("/memory/me/preferences", {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function getBehaviors(): Promise<string> {
  const res = await api.get("/memory/me/behaviors", {
    headers: { "X-User-Id": getUserId() },
  });
  return res.data;
}

export async function updatePreferences(content: string): Promise<void> {
  await api.put("/memory/me/preferences", { content }, {
    headers: { "X-User-Id": getUserId() },
  });
}

export async function updateBehaviors(content: string): Promise<void> {
  await api.put("/memory/me/behaviors", { content }, {
    headers: { "X-User-Id": getUserId() },
  });
}