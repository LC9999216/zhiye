"use client";

import { useMemo } from "react";
import type { AnswerItem } from "@/lib/api";
import { useSearchStore } from "@/stores/search";

/** 按赞同数降序稳定排序（与后端/执行方案一致）。 */
export function sortByVoteupDesc(answers: AnswerItem[]): AnswerItem[] {
  return [...answers].sort((a, b) => b.voteup_count - a.voteup_count);
}

/** 默认最多展示 10 条。 */
const MAX_ANSWERS = 10;

interface AnswerListProps {
  /** 外部传入的回答（测试用）；默认从 store 读取。 */
  answers?: AnswerItem[];
}

/**
 * 左栏：最多 10 条回答，按赞同数降序，显示作者与安全原文链接。
 * 点击 Concept（图谱节点）后可通过 activeConcept 过滤。
 */
export function AnswerList({ answers }: AnswerListProps) {
  const storeAnswers = useSearchStore((s) => s.results);
  const activeConcept = useSearchStore((s) => s.activeConcept);
  const setActiveConcept = useSearchStore((s) => s.setActiveConcept);
  const selectAnswer = useSearchStore((s) => s.selectAnswer);
  const selectedAnswerId = useSearchStore((s) => s.selectedAnswerId);

  const source = answers ?? storeAnswers;

  const filtered = useMemo(() => {
    const sorted = sortByVoteupDesc(source).slice(0, MAX_ANSWERS);
    if (!activeConcept) return sorted;
    // Concept 过滤：仅显示内容文本包含该概念的回答（大小写不敏感）。
    const needle = activeConcept.toLowerCase();
    return sorted.filter((a) =>
      `${a.title} ${a.content_text} ${a.summary ?? ""}`
        .toLowerCase()
        .includes(needle)
    );
  }, [source, activeConcept]);

  if (filtered.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">回答列表</h2>
          {activeConcept && (
            <button
              type="button"
              onClick={() => setActiveConcept(null)}
              className="text-xs text-blue-600 hover:underline"
            >
              清除过滤
            </button>
          )}
        </div>
        <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-400">
          {activeConcept
            ? `没有包含「${activeConcept}」的回答`
            : "暂无回答。输入问题并等待分析完成。"}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">回答列表</h2>
        <span className="text-xs text-slate-400">{filtered.length} 条</span>
      </div>
      {activeConcept && (
        <div className="mb-2 flex items-center gap-2">
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
            过滤：{activeConcept}
          </span>
          <button
            type="button"
            onClick={() => setActiveConcept(null)}
            className="text-xs text-blue-600 hover:underline"
            aria-label="清除概念过滤"
          >
            清除
          </button>
        </div>
      )}
      <ul className="flex flex-1 flex-col gap-2 overflow-y-auto pr-1" aria-label="回答列表">
        {filtered.map((answer) => {
          const selected = answer.id === selectedAnswerId;
          return (
            <li key={answer.id}>
              <button
                type="button"
                onClick={() => selectAnswer(selected ? null : answer.id)}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  selected
                    ? "border-blue-400 bg-blue-50"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                }`}
                aria-pressed={selected}
              >
                <div className="mb-1 flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium text-slate-900">
                    {answer.title || `回答 ${answer.original_index + 1}`}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">
                    👍 {answer.voteup_count}
                  </span>
                </div>
                <div className="mb-1 truncate text-xs text-slate-500">
                  {answer.author_name || "匿名用户"}
                </div>
                <p className="line-clamp-2 text-xs leading-relaxed text-slate-600">
                  {answer.content_text}
                </p>
                {/* 安全原文链接：noopener,noreferrer */}
                <a
                  href={answer.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="mt-1 inline-block text-xs text-blue-600 hover:underline"
                >
                  查看原文 ↗
                </a>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
