export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ApiKeySummary {
  id: string;
  name: string;
  prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface CreateKeyResponse {
  id: string;
  full_key: string;
  prefix: string;
  name: string;
}

export interface Collection {
  id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  source_type: string;
  source_url: string | null;
  file_size: number;
  status: "QUEUED" | "PARSING" | "CHUNKING" | "EMBEDDING" | "READY" | "FAILED";
  page_count: number | null;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
}

export interface UploadAccepted {
  document_id: string;
  job_id: string;
  status: string;
}

export interface JobStatus {
  id: string;
  document_id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  stage: "QUEUED" | "PARSING" | "CHUNKING" | "EMBEDDING" | "READY" | "FAILED";
  progress_pct: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  content: string;
  score: number;
  filename: string;
  page_number: number | null;
  section_title: string | null;
}

export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  snippet: string;
}

export interface Timings {
  retrieval_ms: number;
  llm_ms: number;
  total_ms: number;
}

export interface Usage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  timings: Timings;
  usage: Usage;
  conversation_id: string | null;
  condensed_query: string | null;
}

export interface UsageTotals {
  api_key_id: string;
  queries: number;
  prompt_tokens: number;
  completion_tokens: number;
  documents: number;
  chunks: number;
}

export interface QueryLogEntry {
  id: string;
  collection_id: string;
  query: string;
  retrieval_ms: number | null;
  llm_ms: number | null;
  total_ms: number | null;
  chunks_retrieved: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  created_at: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}
