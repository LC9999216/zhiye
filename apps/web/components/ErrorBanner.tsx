"use client";

import { useSearchStore } from "@/stores/search";

/** 已知错误码 → 可行动的中文提示。 */
const ERROR_HINTS: Record<string, string> = {
  QUERY_NOT_FOUND: "查询不存在，请重新提交问题。",
  JOB_FAILED: "分析任务失败，请稍后重试。",
  SERVER_RESTART: "服务刚重启，之前的任务已中断，请重新提交。",
  NETWORK_ERROR: "无法连接后端服务，请确认 API 已启动。",
};

function extractCode(error: string): string {
  // ApiError.message 可能形如 “请求失败（错误码 XXX）”，
  // 或后端 message 直接含错误码。
  const match = error.match(/错误码\s*([A-Z0-9_]+)/);
  return match ? match[1] : "";
}

/**
 * 错误提示条。识别常见错误码并给出可行动提示；
 * 通用错误显示原始消息（不泄露敏感信息）。
 */
export function ErrorBanner() {
  const error = useSearchStore((s) => s.error);
  const reset = useSearchStore((s) => s.reset);
  if (!error) return null;

  const code = extractCode(error);
  const hint = code ? ERROR_HINTS[code] : null;

  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
    >
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-red-800">
          {hint ?? "请求失败，请稍后重试"}
        </span>
        <span className="text-xs text-red-500">{error}</span>
      </div>
      <button
        type="button"
        onClick={reset}
        className="shrink-0 rounded-md border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
      >
        重试
      </button>
    </div>
  );
}
