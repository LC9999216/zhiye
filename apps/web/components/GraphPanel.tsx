"use client";

import { useEffect, useRef } from "react";
import type { GraphEdge, GraphNode, GraphNodeType } from "@/lib/api";
import { useSearchStore } from "@/stores/search";

/** 节点类型 → 颜色。 */
export const NODE_COLORS: Record<GraphNodeType, string> = {
  QUERY: "#334155", // slate-700
  ANSWER: "#2563eb", // blue-600
  CLAIM: "#059669", // emerald-600
  CONCEPT: "#d97706", // amber-600
};

/** 节点类型 → 中文标签（图例用）。 */
export const NODE_TYPE_LABELS: Record<GraphNodeType, string> = {
  QUERY: "问题",
  ANSWER: "回答",
  CLAIM: "观点",
  CONCEPT: "概念",
};

/** 基础节点尺寸（Sigma size）。 */
const BASE_SIZES: Record<GraphNodeType, number> = {
  QUERY: 12,
  ANSWER: 10,
  CLAIM: 6,
  CONCEPT: 7,
};

/** 根据节点构建 graphology 图；确定性环形布局（无外部布局依赖）。 */
export function buildGraphology(
  GraphCtor: new () => import("graphology").default,
  nodes: GraphNode[],
  edges: GraphEdge[],
): import("graphology").default {
  const graph = new GraphCtor();

  const n = Math.max(nodes.length, 1);
  const radius = 140;
  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2;
    let size = BASE_SIZES[node.type] ?? 6;
    if (node.type === "ANSWER") {
      const votes = Number(node.extra?.voteup_count ?? 0);
      // 赞同数越多节点越大（8 ~ 18）。
      size = Math.min(18, Math.max(8, 8 + Math.log2(votes + 1) * 2));
    }
    graph.addNode(node.id, {
      label: node.label,
      size,
      color: NODE_COLORS[node.type] ?? "#94a3b8",
      type: node.type,
      url: node.url ?? null,
      x: radius * Math.cos(angle),
      y: radius * Math.sin(angle),
    });
  });

  edges.forEach((edge) => {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      graph.addEdge(edge.source, edge.target, {
        type: edge.type,
        color: edge.type === "SIMILAR_TO" ? "#94a3b8" : "#cbd5e1",
        size: 1,
      });
    }
  });

  return graph;
}

interface GraphPanelProps {
  /** 外部传入的图数据（测试用）；默认从 store 读取。 */
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}

/**
 * 中栏：Sigma.js 知识图谱。
 * - zoom / drag / hover / click 由 Sigma 内置交互提供
 * - 点击 ANSWER/CLAIM → 打开原文（新标签，noopener,noreferrer）
 * - 点击 CONCEPT → 过滤左栏回答列表
 * - 空数据时显示空态占位
 */
export function GraphPanel({ nodes, edges }: GraphPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const storeNodes = useSearchStore((s) => s.graphNodes);
  const storeEdges = useSearchStore((s) => s.graphEdges);
  const setActiveConcept = useSearchStore((s) => s.setActiveConcept);
  const selectNode = useSearchStore((s) => s.selectNode);
  const selectedNodeId = useSearchStore((s) => s.selectedNodeId);

  const sourceNodes = nodes ?? storeNodes;
  const sourceEdges = edges ?? storeEdges;

  // 渲染图谱（仅浏览器环境，动态加载避免 SSR/jest 报错）。
  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof window === "undefined") return;
    if (sourceNodes.length === 0) return;

    let cancelled = false;
    let sigmaInstance: import("sigma").default | null = null;

    void Promise.all([
      import("graphology"),
      import("sigma"),
    ]).then(([{ default: Graph }, { default: Sigma }]) => {
      if (cancelled || !container) return;
      const graph = buildGraphology(Graph, sourceNodes, sourceEdges);
      sigmaInstance = new Sigma(graph, container, {
        minCameraRatio: 0.1,
        maxCameraRatio: 8,
        renderLabels: true,
      });

      sigmaInstance.on("clickNode", ({ node }) => {
        const nodeData = graph.getNodeAttributes(node) as {
          type: GraphNodeType;
          url: string | null;
        };
        selectNode(node);
        if (nodeData.type === "CONCEPT") {
          const label = graph.getNodeAttribute(node, "label") as string;
          setActiveConcept(label);
        } else if (nodeData.url) {
          // ANSWER/CLAIM → 安全打开原文。
          window.open(nodeData.url, "_blank", "noopener,noreferrer");
        }
      });

      sigmaInstance.on("clickStage", () => {
        selectNode(null);
      });
    });

    return () => {
      cancelled = true;
      if (sigmaInstance) sigmaInstance.kill();
    };
  }, [sourceNodes, sourceEdges, selectNode, setActiveConcept]);

  if (sourceNodes.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">知识图谱</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {(Object.keys(NODE_TYPE_LABELS) as GraphNodeType[]).map((t) => (
              <span key={t} className="flex items-center gap-1">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: NODE_COLORS[t] }}
                  aria-hidden="true"
                />
                {NODE_TYPE_LABELS[t]}
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-8">
          <p className="text-xs text-slate-400">图谱将在分析完成后显示</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">知识图谱</h2>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          {(Object.keys(NODE_TYPE_LABELS) as GraphNodeType[]).map((t) => (
            <span key={t} className="flex items-center gap-1">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: NODE_COLORS[t] }}
                aria-hidden="true"
              />
              {NODE_TYPE_LABELS[t]}
            </span>
          ))}
        </div>
      </div>
      <div
        ref={containerRef}
        role="img"
        aria-label="知识图谱：问题、回答、观点与概念"
        className="relative min-h-[420px] flex-1 overflow-hidden rounded-lg border border-slate-200 bg-white"
      />
      <p className="mt-2 text-xs text-slate-400">
        {selectedNodeId
          ? "已选中节点（右栏查看详情）。点击空白处取消。"
          : "拖拽平移、滚轮缩放、点击节点查看详情。"}
      </p>
    </div>
  );
}
