// API 类型定义

// ========== Conversation ==========

export interface Message {
  messageId: number;  // Long
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

export interface Conversation {
  conversationId: number;  // Long
  title: string;
  status: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
  messages?: Message[];
}

export interface ConversationListResponse {
  conversations: Conversation[];
}

export interface ChatRequest {
  message: string;
  conversationId?: number;  // Long, optional for new conversation
}

// ========== Question ==========

export interface Question {
  id: string;  // Long 序列化为 String，避免 JS 精度丢失
  questionHash: string;
  questionText: string;
  company: string;
  position: string;
  questionType: string;
  masteryLevel: number;
  coreEntities: string[];
  questionAnswer?: string;
  clusterIds?: string[];
  metadata?: Record<string, unknown>;
  visibility: string;
  sourceType: string;
  createdAt: string;
  updatedAt: string;
}

export interface QuestionListResponse {
  questions: Question[];
  total: number;
  page: number;
  pageSize: number;
}

export interface QuestionCreateRequest {
  questionText: string;
  company: string;
  position: string;
  questionType: string;
  coreEntities?: string[];
  visibility?: string;
}

export interface QuestionUpdateRequest {
  answer?: string;
  masteryLevel?: number;
  questionText?: string;
  coreEntities?: string[];
}

// ========== Search ==========

export interface SearchRequest {
  query: string;
  company?: string;
  position?: string;
  masteryLevel?: number;
  questionType?: string;
  coreEntities?: string[];
  clusterIds?: string[];
  k?: number;
  scoreThreshold?: number;
}

export interface SearchResult {
  questionId: string;
  questionText: string;
  company: string;
  position: string;
  masteryLevel: string;  // 注意：搜索返回的是 string
  questionType: string;
  coreEntities: string[];
  clusterIds?: string[];
  questionAnswer?: string;
  metadata?: Record<string, unknown>;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
}

// ========== Extract ==========

export interface ExtractResponse {
  company: string;
  position: string;
  questions: ExtractedQuestion[];
}

export interface ExtractedQuestion {
  questionId: string;
  questionText: string;
  questionType: string;
  coreEntities: string[];
  metadata?: Record<string, unknown>;
}

export interface ExtractTask {
  taskId: number;  // Long
  userId: string;
  sourceType: "image" | "text";
  sourceContent?: string;
  sourceImages?: string[];
  status: "pending" | "processing" | "completed" | "failed" | "confirmed" | "cancelled";
  result?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ExtractTaskListItem {
  taskId: number;  // Long
  status: string;
  sourceType: string;
  company: string;
  position: string;
  questionCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ExtractTaskListResponse {
  items: ExtractTaskListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ExtractTaskSubmitRequest {
  sourceType: "image" | "text";
  sourceContent?: string;
  sourceImages?: string[];
}

export interface ExtractTaskSubmitResponse {
  taskId: number;  // Long
  message: string;
}

export interface ExtractTaskUpdateRequest {
  company?: string;
  position?: string;
  questions?: Record<string, unknown>[];  // Map 格式
}

export interface ExtractTaskConfirmResponse {
  processed: number;
  failed: number;
  questionIds: string[];
}

// ========== Favorite ==========

export interface FavoriteItem {
  favoriteId: number;  // Long
  userId: string;
  questionId: string;  // Long 序列化为 String
  createdAt: string;
}

export interface FavoriteListResponse {
  favorites: FavoriteItem[];
}

export interface CheckFavoritesResponse {
  favorited: Record<string, boolean>;  // key 是 string (由 Long 序列化而来)
}

// ========== Interview ==========

export interface InterviewSession {
  sessionId: number;  // Long
  company: string;
  position: string;
  difficulty: string;
  totalQuestions: number;
  status: "created" | "in_progress" | "paused" | "completed" | "abandoned";
  currentQuestionIdx: number;
  correctCount: number;
  totalScore: number;
  createdAt: string;
  updatedAt: string;
  questions: InterviewQuestionItem[];
}

export interface InterviewQuestionItem {
  questionId: string;
  questionText: string;
  questionType: string;
  difficulty: string;
  coreEntities: string[];
  answer?: string;
  score?: number;
  feedback?: string;
  status: "pending" | "answered" | "skipped";
  followUpCount: number;
}

export interface InterviewReport {
  sessionId: number;
  company: string;
  position: string;
  difficulty: string;
  status: string;
  totalQuestions: number;
  answeredCount: number;
  correctCount: number;
  totalScore: number;
  averageScore: number;
  durationMinutes: number;
  questions: InterviewQuestionItem[];
}

export interface CreateInterviewSessionRequest {
  company: string;
  position: string;
  difficulty: string;
  totalQuestions: number;
}

export interface SubmitAnswerRequest {
  answer: string;
}

// ========== Score ==========

export interface ScoreRequest {
  questionId: string;
  userAnswer: string;
}

export interface ScoreResult {
  questionId: string;
  questionText: string;
  standardAnswer?: string;
  userAnswer: string;
  score: number;
  masteryLevel: number;
  strengths: string[];
  improvements: string[];
  feedback: string;
}

// ========== Stats ==========

export interface OverviewStats {
  totalQuestions: number;
  totalCompanies: number;
  totalPositions: number;
  byType: Record<string, number>;
  byMastery: Record<number, number>;
  hasAnswer: number;
  noAnswer: number;
}

export interface CompanyStats {
  company: string;
  count: number;
  mastered: number;
  hasAnswer: number;
}

export interface PositionStats {
  position: string;
  count: number;
}

export interface EntityStats {
  entity: string;
  count: number;
}

export interface ClusterStats {
  clusterId: string;
  count: number;
}

// ========== Memory ==========

export interface MemoryResponse {
  userId: string;
  content: string;
  preferences: string;
  behaviors: string;
}