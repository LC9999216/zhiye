"use client";

import { useSearchStore, type SearchStatus } from "@/stores/search";

/** 每个 Job 状态对应的用户可见文案。 */
export const STATUS_LABELS: Record<SearchStatus, string> = {
  idle: "等待输入",
  submitting: "正在提交…",
  pending: "排队中…",
  fetching: "正在搜索知乎…",
  analyzing: "正在提取观点…",
  building: "正在构建知识图谱…",
  completed: "分析完成",
  failed: "分析失败",
};

/** 需要显示进度的状态（提交后到完成/失败前）。 */
const PROGRESS_STATUSES: ReadonlySet<SearchStatus> = new Set([
  "submitting",
  "pending",
  "fetching",
  "analyzing",
  "building",
]);

interface SearchFormProps {
  onSubmit?: (text: string) => void;
}

/**
 * 左栏顶部：自然语言问题输入 + 提交按钮 + Job 进度提示。
 * 键盘可达：Enter 提交、按钮可聚焦。
 */
export function SearchForm({ onSubmit }: SearchFormProps) {
  const query = useSearchStore((s) => s.query);
  const setQuery = useSearchStore((s) => s.setQuery);
  const status = useSearchStore((s) => s.status);
  const isSubmitting = useSearchStore((s) => s.isSubmitting);
  const submit = useSearchStore((s) => s.submit);

  const busy = isSubmitting || PROGRESS_STATUSES.has(status);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    await submit(query);
    onSubmit?.(query);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
      <label htmlFor="query-input" className="text-sm font-semibold text-slate-700">
        输入问题
      </label>
      <input
        id="query-input"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="例如：计算机专业考研还是就业？"
        maxLength={200}
        disabled={busy}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100"
        aria-label="输入要分析的问题"
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {busy ? "分析中…" : "开始分析"}
      </button>

      {PROGRESS_STATUSES.has(status) && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800"
        >
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" aria-hidden="true" />
          {STATUS_LABELS[status]}
        </p>
      )}
      {status === "completed" && (
        <p role="status" className="rounded-lg border border-green-100 bg-green-50 px-3 py-2 text-xs text-green-800">
          {STATUS_LABELS.completed}：已生成回答列表与知识图谱
        </p>
      )}
    </form>
  );
}
