/**
 * 知辨 (Zhibian) 首页
 *
 * Stage 1 工程脚手架占位页：三栏布局
 * （左栏回答列表 / 中栏搜索与图谱 / 右栏 AI 面板）。
 * 搜索功能在 Stage 2 启用，图谱（Sigma.js）在 Stage 6 启用，
 * AI 问答在 Stage 8 启用。
 */

const FIXED_SCOPE_NOTICE = "观点基于知乎搜索返回内容生成，可能不包含原回答全部信息";

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
            Stage 1 · 工程脚手架
          </span>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6 sm:px-6 lg:px-8">
        {/* 固定范围提示（MVP 契约，始终可见） */}
        <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          {FIXED_SCOPE_NOTICE}
        </p>

        {/* 三栏占位布局：移动端仅显示中栏 */}
        <div className="grid flex-1 grid-cols-1 gap-6 md:grid-cols-[240px_minmax(0,1fr)_300px]">
          {/* 左栏：回答列表 */}
          <aside className="hidden md:block">
            <div className="flex h-full flex-col rounded-xl border border-dashed border-slate-300 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">
                回答列表
              </h2>
              <p className="text-xs leading-relaxed text-slate-400">
                此处将展示最多 10 条知乎回答，按赞同数降序排列。
                搜索功能将在 Stage 2 启用。
              </p>
            </div>
          </aside>

          {/* 中栏：搜索与图谱 */}
          <section className="flex flex-col rounded-xl border border-dashed border-slate-300 bg-white p-6">
            <div className="mb-4 flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" aria-hidden="true" />
              <h2 className="text-base font-semibold text-slate-800">
                搜索功能将在 Stage 2 启用
              </h2>
            </div>
            <p className="text-sm leading-relaxed text-slate-500">
              输入自然语言问题后，系统将调用知乎搜索，保留返回结果中的最多 10
              条回答，并生成 QUERY → ANSWER → CLAIM → CONCEPT 知识图谱。
            </p>
            {/* 图谱占位区域 */}
            <div className="mt-6 flex flex-1 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-8">
              <span className="text-xs text-slate-400">
                图谱区域（Sigma.js）将在 Stage 6 启用
              </span>
            </div>
          </section>

          {/* 右栏：AI 面板骨架 */}
          <aside className="hidden md:block">
            <div className="flex h-full flex-col rounded-xl border border-dashed border-slate-300 bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-700">
                AI 问答
              </h2>
              <p className="text-xs leading-relaxed text-slate-400">
                AI 问答将在 Stage 8 启用。当前仅显示选中节点的上下文预览。
              </p>
              <div className="mt-4 flex flex-1 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs text-slate-400">尚未选择节点</p>
              </div>
            </div>
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
