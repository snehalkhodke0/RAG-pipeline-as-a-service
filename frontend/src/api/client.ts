import type {
  ApiErrorBody,
  ApiKeySummary,
  Collection,
  CreateKeyResponse,
  DocumentItem,
  JobStatus,
  QueryLogEntry,
  QueryResponse,
  SearchResult,
  TokenResponse,
  UploadAccepted,
  UsageTotals,
  User,
} from "./types";

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_STORAGE_KEY = "rag_dashboard_token";

let inMemoryToken: string | null = localStorage.getItem(TOKEN_STORAGE_KEY);

export function getToken(): string | null {
  return inMemoryToken;
}

export function setToken(token: string | null): void {
  inMemoryToken = token;
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error?.message ?? "Request failed");
    this.code = body.error?.code ?? "unknown_error";
    this.status = status;
    this.requestId = body.error?.request_id ?? "";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isForm?: boolean;
  query?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, API_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (options.body !== undefined && !options.isForm) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  } else if (options.isForm) {
    body = options.body as FormData;
  }

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ApiError(response.status, data as ApiErrorBody);
  }

  return data as T;
}

// ---------- Auth ----------

export function signup(email: string, password: string): Promise<TokenResponse> {
  return request("/auth/signup", { method: "POST", body: { email, password } });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request("/auth/login", { method: "POST", body: { email, password } });
}

export function me(): Promise<User> {
  return request("/auth/me");
}

// ---------- API Keys ----------

export function createKey(name: string): Promise<CreateKeyResponse> {
  return request("/keys", { method: "POST", body: { name } });
}

export function listKeys(): Promise<ApiKeySummary[]> {
  return request("/keys");
}

export function revokeKey(id: string): Promise<void> {
  return request(`/keys/${id}`, { method: "DELETE" });
}

// ---------- Collections ----------

export function listCollections(): Promise<Collection[]> {
  return request("/collections");
}

export function createCollection(
  name: string,
  description?: string,
  chunk_size?: number,
  chunk_overlap?: number
): Promise<Collection> {
  return request("/collections", { method: "POST", body: { name, description, chunk_size, chunk_overlap } });
}

export function getCollection(id: string): Promise<Collection> {
  return request(`/collections/${id}`);
}

export function updateCollection(id: string, patch: { name?: string; description?: string }): Promise<Collection> {
  return request(`/collections/${id}`, { method: "PATCH", body: patch });
}

export function deleteCollection(id: string): Promise<void> {
  return request(`/collections/${id}`, { method: "DELETE" });
}

// ---------- Documents ----------

export function uploadDocument(collectionId: string, file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  return request(`/collections/${collectionId}/documents`, { method: "POST", body: form, isForm: true });
}

export function uploadDocumentUrl(collectionId: string, url: string): Promise<UploadAccepted> {
  return request(`/collections/${collectionId}/documents/url`, { method: "POST", body: { url } });
}

export function listDocuments(collectionId: string): Promise<DocumentItem[]> {
  return request(`/collections/${collectionId}/documents`);
}

export function deleteDocument(id: string): Promise<void> {
  return request(`/documents/${id}`, { method: "DELETE" });
}

export function getJob(id: string): Promise<JobStatus> {
  return request(`/jobs/${id}`);
}

// ---------- Search / Query ----------

export function searchCollection(collectionId: string, q: string, topK = 5): Promise<{ query: string; results: SearchResult[] }> {
  return request(`/collections/${collectionId}/search`, { query: { q, top_k: topK } });
}

export interface QueryPayload {
  query: string;
  top_k?: number;
  document_id?: string;
  conversation_id?: string;
}

export function queryCollection(collectionId: string, payload: QueryPayload): Promise<QueryResponse> {
  return request(`/collections/${collectionId}/query`, { method: "POST", body: payload });
}

// ---------- Usage / Logs ----------

export function getUsage(): Promise<UsageTotals> {
  return request("/usage");
}

export function getLogs(limit = 50): Promise<QueryLogEntry[]> {
  return request("/logs", { query: { limit } });
}

// ---------- Streaming query (fetch + ReadableStream, not EventSource) ----------

export interface StreamHandlers {
  onToken: (text: string) => void;
  onCitations: (citations: unknown[]) => void;
  onDone: (payload: { timings: unknown; usage: unknown; conversation_id: string | null }) => void;
  onError: (message: string) => void;
}

/**
 * EventSource cannot send an Authorization header, so streaming uses fetch() with a
 * ReadableStream reader and hand-rolled SSE frame parsing instead.
 */
export async function streamQuery(
  collectionId: string,
  payload: QueryPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const response = await fetch(buildUrl(`/collections/${collectionId}/query/stream`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, data as ApiErrorBody);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      dispatchSseFrame(rawEvent, handlers);
    }
  }
}

function dispatchSseFrame(rawEvent: string, handlers: StreamHandlers): void {
  let eventName = "message";
  let dataLine = "";
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
  }
  if (!dataLine) return;

  let parsed: any;
  try {
    parsed = JSON.parse(dataLine);
  } catch {
    return;
  }

  switch (eventName) {
    case "token":
      handlers.onToken(parsed.text ?? "");
      break;
    case "citations":
      handlers.onCitations(parsed.citations ?? []);
      break;
    case "done":
      handlers.onDone(parsed);
      break;
    case "error":
      handlers.onError(parsed.message ?? "Unknown streaming error");
      break;
    default:
      break;
  }
}
