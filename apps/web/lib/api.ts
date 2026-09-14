/**
 * 知辨 (Zhibian) 前端 API 客户端
 *
 * 面向 apps/api（FastAPI）服务。默认基础地址为 http://localhost:8000，
 * 可通过 NEXT_PUBLIC_API_URL 环境变量覆盖（见 .env.example）。
 * 响应类型与 docs/IMPLEMENTATION_PLAN.md 第 6.1 节的外部搜索 DTO 对齐。
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000";

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
  return "请求失败，请稍后重试";
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
    const code =
      typeof body.error_code === "string" && body.error_code.length > 0
        ? body.error_code
        : `HTTP_${response.status}`;
    throw new ApiError(messageFromErrorBody(body), response.status, code);
  }

  return (await response.json()) as T;
}

export const api = {
  /** GET /api/health — API 与数据库健康检查。 */
  health: (): Promise<HealthResponse> =>
    request<HealthResponse>("/api/health"),

  // 以下接口在后续 Stage 启用：
  // POST /api/queries/analyze     （Stage 3）
  // GET  /api/jobs/{id}           （Stage 3）
  // GET  /api/queries/{id}/answers（Stage 3）
  // GET  /api/queries/{id}/graph  （Stage 5）
  // POST /api/chat                （Stage 8）
};
