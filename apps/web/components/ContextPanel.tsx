"use client";

import { useMemo } from "react";
import type { GraphNode } from "@/lib/api";
import { NODE_TYPE_LABELS } from "@/components/GraphPanel";
import { useSearchStore } from "@/stores/search";

/** 提取节点详情行（key, label）。 */
export function nodeDetailRows(
  node: GraphNode,
): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  rows.push(["类型", NODE_TYPE_LABELS[node.type] ?? node.type]);
  if (node.label) rows.push(["名称", node.label]);
  if (node.type === "ANSWER") {
    const votes = node.extra?.voteup_count;
    if (typeof votes === "number") rows.push(["赞同数", String(votes)]);
    const author = node.extra?.author_name;
    if (typeof author === "string" && author) rows.push(["作者", author]);
    const stance = node.extra?.stance;
    if (typeof stance === "string" && stance) rows.push(["立场", stance]);
    const summary = node.extra?.summary;
    if (typeof summary === "string" && summary) {
      rows.push(["摘要", summary]);
    }
  }
  if (node.type === "CLAIM") {
    const confidence = node.extra?.confidence;
    if (typeof confidence === "number") {
      rows.push(["置信度", `${Math.round(confidence * 100)}%`]);
    }
  }
  if (node.type === "CONCEPT") {
    const frequency = node.extra?.frequency;
    if (typeof frequency === "number") rows.push(["出现次数", String(frequency)]);
  }
  return rows;
}

/**
 * 右栏：禁用的 AI 面板骨架 + 选中节点上下文预览。
 * 本阶段不调用 /api/chat，不展示伪 Citation；
 * 明确显示「AI 问答将在 Stage 8 启用」。
 */
export function ContextPanel() {
  const selectedNodeId = useSearchStore((s) => s.selectedNodeId);
  const graphNodes = useSearchStore((s) => s.graphNodes);

  const selectedNode = useMemo(
    () => graphNodes.find((n) => n.id === selectedNodeId) ?? null,
    [graphNodes, selectedNodeId],
  );

  return (
    <div className="flex h-full flex-col gap-3">
      <h2 className="text-sm font-semibold text-slate-700">AI 问答</h2>

      {/* 禁用的 AI 面板骨架 */}
      <div
        className="rounded-lg border border-slate-200 bg-slate-50 p-3"
        aria-disabled="true"
      >
        <p className="text-xs leading-relaxed text-slate-500">
          AI 问答将在 Stage 8 启用。当前仅显示选中节点的上下文预览。
        </p>
        <button
          type="button"
          disabled
          className="mt-3 w-full cursor-not-allowed rounded-lg bg-slate-200 px-3 py-2 text-xs font-medium text-slate-400"
        >
          AI 问答将在 Stage 8 启用
        </button>
      </div>

      {/* 选中节点上下文预览 */}
      <div className="flex flex-1 flex-col rounded-lg border border-slate-200 bg-white p-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          选中节点
        </h3>
        {selectedNode ? (
          <dl className="flex flex-col gap-2 overflow-y-auto">
            {nodeDetailRows(selectedNode).map(([key, value]) => (
              <div key={key} className="text-xs">
                <dt className="text-slate-400">{key}</dt>
                <dd className="mt-0.5 break-words text-slate-700">{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-xs text-slate-400">
            尚未选择节点。点击图谱中的节点查看详情。
          </p>
        )}
      </div>
    </div>
  );
}
