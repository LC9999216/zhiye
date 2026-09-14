/**
 * 知辨 (Zhibian) 前端 API 客户端
 *
 * 面向 apps/api（FastAPI）服务。默认基础地址为 http://localhost:8000，
 * 可通过 NEXT_PUBLIC_API_URL 环境变量覆盖（见 .env.example）。
 * 响应类型与 docs/IMPLEMENTATION_PLAN.md 第 6.1 节的外部搜索 DTO 对齐。
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000";

// Module memory only: refreshing the page clears the invite code.
let inviteCode = "";

export function setInviteCode(value: string): void {
  inviteCode = value.trim();
}

/** 返回 API 基础地址，去除尾部斜杠，保证 URL 拼接一致。 */
export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured && configured.trim().length > 0) {
    return configured.trim().replace(/\/+$/, "");
  }
  return DEFAULT_API_BASE_URL;
}

// ---------------------------------------------------------------------------
// 响应类型（与后端 DTO 对齐）
// ---------------------------------------------------------------------------

/** 知乎搜索结果中的单条 Answer（已过滤、去重、排序后的内部 DTO）。 */
export interface SearchAnswer {
  original_index: number;
  title: string;
  content_type: string;
  content_id: string;
  content_text: string;
  url: string;
  voteup_count: number;
  author_name: string;
  edit_time: number;
  ranking_score: number;
}

/** POST /api/queries/analyze 相关搜索结果响应。 */
export interface SearchResponse {
  search_hash_id: string;
  items: SearchAnswer[];
}

/** GET /api/health 健康检查响应。 */
export interface HealthResponse {
  status: string;
  version?: string;
  database?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Stage 6: query/job/answers/graph 类型（与后端 DTO 对齐）
// ---------------------------------------------------------------------------

/** POST /api/queries/analyze 的 202 响应。 */
export interface AnalyzeResponse {
  job_id: string;
  query_id: string;
  job_url: string;
}

/** GET /api/jobs/{id} 的 Job 状态。 */
export interface JobResponse {
  id: string;
  query_id: string;
  status: JobStatus;
  current_step: string;
  error_code: string | null;
  error_message: string | null;
  warnings: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  query_url: string | null;
  answers_url: string | null;
  graph_url: string | null;
}

/** 后端 Job 状态机（与 stores/search.ts 的 SearchStatus 对齐）。 */
export type JobStatus =
  | "pending"
  | "fetching"
  | "analyzing"
  | "building"
  | "completed"
  | "completed_partial"
  | "failed";

/** GET /api/queries/{id}/answers 的单条 Answer。 */
export interface AnswerItem {
  id: string;
  content_id: string;
  title: string;
  author_name: string;
  content_text: string;
  voteup_count: number;
  url: string;
  original_index: number;
  summary: string | null;
  stance: string | null;
  claim_count: number;
  analysis_status?: "pending" | "completed" | "failed";
  analysis_error_code?: string | null;
}

/** GET /api/queries/{id}/answers 的响应。 */
export interface AnswersResponse {
  query_id: string;
  query_text: string;
  answers: AnswerItem[];
  total: number;
}

/** GET /api/queries/{id}/graph 的节点类型。 */
export type GraphNodeType = "QUERY" | "ANSWER" | "CLAIM" | "CONCEPT";

/** GET /api/queries/{id}/graph 的节点。 */
export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  url?: string | null;
  extra: Record<string, unknown>;
}

/** GET /api/queries/{id}/graph 的边类型。 */
export type GraphEdgeType =
  | "RETURNS_ANSWER"
  | "MAKES_CLAIM"
  | "REFERS_TO"
  | "SIMILAR_TO";

/** GET /api/queries/{id}/graph 的边。 */
export interface GraphEdge {
  source: string;
  target: string;
  type: GraphEdgeType;
}

/** GET /api/queries/{id}/graph 的响应。 */
export interface GraphResponse {
  query_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// 错误处理
// ---------------------------------------------------------------------------

/** 后端错误响应体（字段以后端实际错误 Schema 为准）。 */
export interface ApiErrorBody {
  detail?: unknown;
  error_code?: string;
  message?: string;
}

/** 统一的 API 请求错误。status 为 0 表示网络层失败。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = "API_ERROR") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null) {
      return body as ApiErrorBody;
    }
  } catch {
    // 响应体不是 JSON 时忽略，使用默认错误信息。
  }
  return {};
}

function messageFromErrorBody(body: ApiErrorBody): string {
  if (typeof body.message === "string" && body.message.length > 0) {
    return body.message;
  }
  if (typeof body.error_code === "string" && body.error_code.length > 0) {
    return `请求失败（错误码 ${body.error_code}）`;
  }
  if (typeof body.detail === "object" && body.detail !== null) {
    const detail = body.detail as { message?: unknown };
    if (typeof detail.message === "string" && detail.message.length > 0) {
      return detail.message;
    }
  }
  return "请求失败，请稍后重试";
}

function errorCodeFromBody(body: ApiErrorBody, fallback: string): string {
  if (typeof body.error_code === "string" && body.error_code.length > 0) {
    return body.error_code;
  }
  if (typeof body.detail === "object" && body.detail !== null) {
    const detail = body.detail as { error_code?: unknown };
    if (typeof detail.error_code === "string" && detail.error_code.length > 0) {
      return detail.error_code;
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(inviteCode ? { "X-Invite-Code": inviteCode } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `无法连接到后端服务（${baseUrl}），请确认 API 已启动`,
      0,
      "NETWORK_ERROR"
    );
  }

  if (!response.ok) {
    const body = await parseErrorBody(response);
    const code = errorCodeFromBody(body, `HTTP_${response.status}`);
    throw new ApiError(
      `${messageFromErrorBody(body)}（错误码 ${code}）`,
      response.status,
      code,
    );
  }

  return (await response.json()) as T;
}

export const api = {
  /** GET /api/health — API 与数据库健康检查。 */
  health: (): Promise<HealthResponse> =>
    request<HealthResponse>("/api/health"),

  /** POST /api/queries/analyze — 提交问题，创建分析 Job。 */
  analyze: (queryText: string): Promise<AnalyzeResponse> =>
    request<AnalyzeResponse>("/api/queries/analyze", {
      method: "POST",
      body: JSON.stringify({ query_text: queryText }),
    }),

  /** GET /api/jobs/{id} — 轮询 Job 状态。 */
  getJob: (jobId: string): Promise<JobResponse> =>
    request<JobResponse>(`/api/jobs/${jobId}`),

  /** GET /api/queries/{id}/answers — 已排序的回答列表。 */
  getAnswers: (queryId: string): Promise<AnswersResponse> =>
    request<AnswersResponse>(`/api/queries/${queryId}/answers`),

  /** GET /api/queries/{id}/graph — 知识图谱节点与边。 */
  getGraph: (queryId: string): Promise<GraphResponse> =>
    request<GraphResponse>(`/api/queries/${queryId}/graph`),
};
