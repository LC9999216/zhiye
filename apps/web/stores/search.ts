import { create } from "zustand";
import type { SearchAnswer } from "@/lib/api";

/**
 * 搜索状态机。status 与后端 Job 状态
 * （docs/IMPLEMENTATION_PLAN.md 第 7 节）对齐。
 *
 * 当前为 Stage 1 占位实现；Stage 6/7 将接入真实搜索提交、
 * Job 轮询与回答/图谱双向联动。
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

export interface SearchState {
  /** 用户输入的自然语言问题。 */
  query: string;
  /** 当前搜索/分析任务状态。 */
  status: SearchStatus;
  /** 已排序的回答列表（最多 10 条，VoteUpCount 降序）。 */
  results: SearchAnswer[];
  /** 用户可见错误信息；status 为 "failed" 时非空。 */
  error: string | null;
  /** 后台 Job id（POST /api/queries/analyze 返回）。 */
  jobId: string | null;
  /** 图谱中当前选中的节点 id。 */
  selectedNodeId: string | null;
  /** 当前选中的回答 id。 */
  selectedAnswerId: string | null;
  /** 当前激活的 Concept（用于过滤回答列表）。 */
  activeConcept: string | null;

  setQuery: (query: string) => void;
  setStatus: (status: SearchStatus) => void;
  setResults: (results: SearchAnswer[]) => void;
  setError: (error: string | null) => void;
  setJobId: (jobId: string | null) => void;
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
  | "error"
  | "jobId"
  | "selectedNodeId"
  | "selectedAnswerId"
  | "activeConcept"
>;

const initialState: SearchDataState = {
  query: "",
  status: "idle",
  results: [],
  error: null,
  jobId: null,
  selectedNodeId: null,
  selectedAnswerId: null,
  activeConcept: null,
};

export const useSearchStore = create<SearchState>()((set) => ({
  ...initialState,
  setQuery: (query) => set({ query }),
  setStatus: (status) => set({ status }),
  setResults: (results) => set({ results }),
  setError: (error) => set({ error }),
  setJobId: (jobId) => set({ jobId }),
  selectNode: (selectedNodeId) => set({ selectedNodeId }),
  selectAnswer: (selectedAnswerId) => set({ selectedAnswerId }),
  setActiveConcept: (activeConcept) => set({ activeConcept }),
  reset: () => set({ ...initialState }),
}));
