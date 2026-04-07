// API 类型定义

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id: string;
  history: Message[];
}

export interface ChatResponse {
  response: string;
  intent?: string;
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