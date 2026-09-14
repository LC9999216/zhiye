import { create } from "zustand";
import {
  api,
  type AnswerItem,
  type GraphEdge,
  type GraphNode,
  type JobStatus,
} from "@/lib/api";

/**
 * 搜索状态机。status 与后端 Job 状态
 * （docs/IMPLEMENTATION_PLAN.md 第 7 节）对齐。
 *
 * Stage 6 实现：
 * - submit()：POST /api/queries/analyze，然后轮询 Job 到终态
 * - 成功后拉取 answers + graph
 * - selectedNodeId / activeConcept 供三栏联动
 */
export type SearchStatus =
  | "idle"
  | "submitting"
  | "pending"
  | "fetching"
  | "analyzing"
  | "building"
  | "completed"
  | "failed";

/** 将后端 Job 状态映射为前端 SearchStatus。 */
function mapJobStatus(status: JobStatus): SearchStatus {
  switch (status) {
    case "pending":
      return "pending";
    case "fetching":
      return "fetching";
    case "analyzing":
      return "analyzing";
    case "building":
      return "building";
    case "completed":
      return "completed";
    case "failed":
      return "failed";
    default:
      return "failed";
  }
}

/** Job 轮询间隔（毫秒）。 */
const POLL_INTERVAL_MS = 1200;

/** Job 轮询总超时（毫秒），避免无限轮询。 */
const POLL_TIMEOUT_MS = 180_000;

export interface SearchState {
  /** 用户输入的自然语言问题。 */
  query: string;
  /** 当前搜索/分析任务状态。 */
  status: SearchStatus;
  /** 已排序的回答列表（最多 10 条，VoteUpCount 降序）。 */
  results: AnswerItem[];
  /** 知识图谱节点。 */
  graphNodes: GraphNode[];
  /** 知识图谱边。 */
  graphEdges: GraphEdge[];
  /** 用户可见错误信息；status 为 "failed" 时非空。 */
  error: string | null;
  /** 后台 Job id（POST /api/queries/analyze 返回）。 */
  jobId: string | null;
  /** 当前 Query id。 */
  queryId: string | null;
  /** 图谱中当前选中的节点 id。 */
  selectedNodeId: string | null;
  /** 当前选中的回答 id。 */
  selectedAnswerId: string | null;
  /** 当前激活的 Concept（用于过滤回答列表）。 */
  activeConcept: string | null;
  /** 是否正在提交（POST analyze 尚未返回）。 */
  isSubmitting: boolean;

  setQuery: (query: string) => void;
  submit: (queryText: string) => Promise<void>;
  selectNode: (nodeId: string | null) => void;
  selectAnswer: (answerId: string | null) => void;
  setActiveConcept: (concept: string | null) => void;
  reset: () => void;
}

type SearchDataState = Pick<
  SearchState,
  | "query"
  | "status"
  | "results"
  | "graphNodes"
  | "graphEdges"
  | "error"
  | "jobId"
  | "queryId"
  | "selectedNodeId"
  | "selectedAnswerId"
  | "activeConcept"
  | "isSubmitting"
>;

const initialState: SearchDataState = {
  query: "",
  status: "idle",
  results: [],
  graphNodes: [],
  graphEdges: [],
  error: null,
  jobId: null,
  queryId: null,
  selectedNodeId: null,
  selectedAnswerId: null,
  activeConcept: null,
  isSubmitting: false,
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 轮询 Job 直到终态；返回最终 Job 状态与 queryId。 */
async function pollJob(
  jobId: string,
  onStatus: (status: SearchStatus) => void,
): Promise<{ status: JobStatus; queryId: string; errorMessage: string | null }> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  for (;;) {
    const job = await api.getJob(jobId);
    onStatus(mapJobStatus(job.status));
    if (job.status === "completed" || job.status === "failed") {
      return {
        status: job.status,
        queryId: job.query_id,
        errorMessage: job.error_message,
      };
    }
    if (Date.now() >= deadline) {
      return {
        status: "failed",
        queryId: job.query_id,
        errorMessage: "分析超时，请稍后重试",
      };
    }
    await sleep(POLL_INTERVAL_MS);
  }
}

export const useSearchStore = create<SearchState>()((set) => ({
  ...initialState,

  setQuery: (query) => set({ query }),

  submit: async (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed) {
      set({ error: "请输入要分析的问题", status: "idle" });
      return;
    }
    set({
      query: trimmed,
      status: "submitting",
      isSubmitting: true,
      error: null,
      results: [],
      graphNodes: [],
      graphEdges: [],
      selectedNodeId: null,
      selectedAnswerId: null,
      activeConcept: null,
    });

    try {
      const created = await api.analyze(trimmed);
      set({ jobId: created.job_id, queryId: created.query_id });

      const final = await pollJob(created.job_id, (status) => {
        set({ status });
      });

      if (final.status === "failed") {
        set({
          status: "failed",
          isSubmitting: false,
          error:
            final.errorMessage ||
            "分析失败，请检查后重试",
        });
        return;
      }

      // completed → 并行拉取 answers + graph。
      const queryId = final.queryId;
      const [answersRes, graphRes] = await Promise.all([
        api.getAnswers(queryId),
        api.getGraph(queryId),
      ]);
      set({
        status: "completed",
        isSubmitting: false,
        queryId,
        results: answersRes.answers,
        graphNodes: graphRes.nodes,
        graphEdges: graphRes.edges,
        error: null,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "请求失败，请稍后重试";
      set({ status: "failed", isSubmitting: false, error: message });
    }
  },

  selectNode: (selectedNodeId) => set({ selectedNodeId }),
  selectAnswer: (selectedAnswerId) => set({ selectedAnswerId }),
  setActiveConcept: (activeConcept) => set({ activeConcept }),

  reset: () => set({ ...initialState }),
}));
