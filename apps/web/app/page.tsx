"use client";

import { AnswerList } from "@/components/AnswerList";
import { ContextPanel } from "@/components/ContextPanel";
import { ErrorBanner } from "@/components/ErrorBanner";
import { GraphPanel } from "@/components/GraphPanel";
import { SearchForm } from "@/components/SearchForm";
import { WarningBanner } from "@/components/WarningBanner";

const FIXED_SCOPE_NOTICE =
  "观点基于知乎搜索返回内容生成，可能不包含原回答全部信息";

/**
 * 知辨 (Zhibian) 首页 — Stage 6 三栏界面。
 *
 * 左栏：问题输入 + Job 进度 + 回答列表（最多 10 条，赞同数降序）。
 * 中栏：Sigma.js 知识图谱（QUERY → ANSWER → CLAIM → CONCEPT）。
 * 右栏：禁用的 AI 面板骨架 + 选中节点上下文预览（AI 问答 Stage 8 启用）。
 *
 * 固定范围提示始终可见（MVP 契约）。
 */
export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      {/* 顶部栏 */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              知辨
            </h1>
            <span className="hidden text-sm text-slate-400 sm:inline">
              知乎观点分析
            </span>
          </div>
          <span className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
            Stage 6 · 三栏界面
          </span>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6 sm:px-6 lg:px-8">
        {/* 固定范围提示（MVP 契约，始终可见，不藏在帮助页） */}
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          {FIXED_SCOPE_NOTICE}
        </p>

        {/* 错误态 */}
        <ErrorBanner />
        <WarningBanner />

        {/* 三栏布局：桌面优先；窄屏仅显示左栏（回答） */}
        <div className="mt-4 grid flex-1 grid-cols-1 gap-6 lg:grid-cols-[280px_minmax(0,1fr)_300px]">
          {/* 左栏：输入 + 回答列表 */}
          <aside className="flex min-h-0 flex-col gap-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <SearchForm />
            </div>
            <div className="min-h-0 flex-1 rounded-xl border border-slate-200 bg-white p-4">
              <AnswerList />
            </div>
          </aside>

          {/* 中栏：图谱 */}
          <section className="min-h-0 rounded-xl border border-slate-200 bg-white p-4">
            <GraphPanel />
          </section>

          {/* 右栏：AI 面板骨架 + 选中节点上下文 */}
          <aside className="min-h-0 rounded-xl border border-slate-200 bg-white p-4">
            <ContextPanel />
          </aside>
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-7xl px-4 py-4 text-center text-xs text-slate-400 sm:px-6 lg:px-8">
          知辨 · {FIXED_SCOPE_NOTICE}
        </div>
      </footer>
    </div>
  );
}
