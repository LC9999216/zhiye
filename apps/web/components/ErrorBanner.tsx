"use client";

import { useSearchStore } from "@/stores/search";

/** 已知错误码 → 可行动的中文提示。 */
const ERROR_HINTS: Record<string, string> = {
  QUERY_NOT_FOUND: "查询不存在，请重新提交问题。",
  JOB_FAILED: "分析任务失败，请稍后重试。",
  SERVER_RESTART: "服务刚重启，之前的任务已中断，请重新提交。",
  NETWORK_ERROR: "无法连接后端服务，请确认 API 已启动。",
  INVALID_INVITE_CODE: "体验码无效，请检查后重新输入。",
  INVITE_CODE_NOT_CONFIGURED: "服务端尚未配置体验码，请联系管理员。",
  ANALYSIS_BUSY: "当前已有真实分析任务，请稍后再试。",
  BUDGET_EXHAUSTED: "体验预算已用尽，请等待管理员补充预算。",
  BUDGET_PRICING_NOT_CONFIGURED: "服务端尚未配置模型计价，暂不能启动真实分析。",
  BUDGET_UPPER_BOUND_EXCEEDS_RESERVE: "本次结果规模超过单次预算上限，请换一个更短的问题重试。",
  BUDGET_UPPER_BOUND_UNAVAILABLE: "无法可靠估算本次调用费用，任务未启动。",
  ZHIHU_AUTH_FAILED: "知乎服务鉴权失败，请联系管理员检查配置。",
  ZHIHU_RATE_LIMITED: "知乎额度或频率受限，请稍后再试。",
  PROVIDER_AUTH_FAILED: "模型服务鉴权失败，请联系管理员检查配置。",
  PROVIDER_RATE_LIMITED: "模型服务额度或频率受限，请稍后再试。",
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
