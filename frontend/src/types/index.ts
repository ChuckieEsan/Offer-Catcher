// API 类型定义

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoning_content?: string;  // DeepSeek thinking mode 思考过程
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
}

export interface ChatRequest {
  message: string;
  conversation_id: string;
  user_id: string;  // 用户 ID，用于长期记忆
}

export interface ChatResponse {
  response: string;
}

export interface Question {
  question_id: string;
  question_text: string;
  company: string;
  position: string;
  question_type: string;
  mastery_level: number;
  core_entities: string[];
  question_answer?: string;
  cluster_ids?: string[];
  metadata?: Record<string, unknown>;
}

export interface QuestionListResponse {
  items: Question[];
  total: number;
  page: number;
  page_size: number;
}

export interface SearchRequest {
  query: string;
  company?: string;
  position?: string;
  mastery_level?: number;
  question_type?: string;
  core_entities?: string[];
  cluster_ids?: string[];
  k?: number;
  score_threshold?: number;
}

export interface SearchResult {
  question_id: string;
  question_text: string;
  company: string;
  position: string;
  mastery_level: number;
  question_type: string;
  core_entities: string[];
  question_answer?: string;
  cluster_ids?: string[];
  metadata?: Record<string, unknown>;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface ExtractResponse {
  company: string;
  position: string;
  questions: Question[];
}

export interface ScoreRequest {
  question_id: string;
  user_answer: string;
}

export interface ScoreResult {
  question_id: string;
  question_text: string;
  standard_answer?: string;
  user_answer: string;
  score: number;
  mastery_level: number;
  strengths: string[];
  improvements: string[];
  feedback: string;
}

export interface OverviewStats {
  total_questions: number;
  total_companies: number;
  total_positions: number;
  by_type: Record<string, number>;
  by_mastery: Record<number, number>;
  has_answer: number;
  no_answer: number;
}

export interface CompanyStats {
  company: string;
  count: number;
  mastered: number;
  has_answer: number;
}

export interface EntityStats {
  entity: string;
  count: number;
}

export interface ClusterStats {
  cluster_id: string;
  count: number;
}

export interface PositionStats {
  position: string;
  count: number;
}

// ========== Extract Task Types ==========

export interface ExtractTask {
  task_id: string;
  user_id: string;
  source_type: "image" | "text";
  status: "pending" | "processing" | "completed" | "failed" | "confirmed";
  error_message?: string;
  created_at: string;
  updated_at: string;
  result?: ExtractedInterview;
}

export interface ExtractedInterview {
  company: string;
  position: string;
  questions: Question[];
}

export interface ExtractTaskListItem {
  task_id: string;
  status: string;
  source_type: string;
  company: string;
  position: string;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExtractTaskListResponse {
  items: ExtractTaskListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExtractTaskSubmitRequest {
  source_type: "image" | "text";
  source_content?: string;
  source_images?: string[];
}

export interface ExtractTaskSubmitResponse {
  task_id: string;
  message: string;
}

export interface ExtractTaskUpdateRequest {
  company?: string;
  position?: string;
  questions?: Question[];
}

// ========== Favorites Types ==========

export interface FavoriteItem {
  id: string;
  question_id: string;
  created_at: string;
}

export interface FavoriteListResponse {
  items: FavoriteItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CheckFavoritesResponse {
  status: Record<string, boolean>;
}