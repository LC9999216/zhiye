import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ── mocks：避免 jsdom 加载 sigma/graphology（无 WebGL） ──────────────
vi.mock("sigma", () => ({
  default: class {
    on() {}
    kill() {}
  },
}));
vi.mock("graphology", () => ({
  default: class {
    addNode() {}
    addEdge() {}
    hasNode() {
      return false;
    }
  },
}));

import { AnswerList, sortByVoteupDesc } from "@/components/AnswerList";
import { ContextPanel, nodeDetailRows } from "@/components/ContextPanel";
import { ErrorBanner } from "@/components/ErrorBanner";
import { SearchForm, STATUS_LABELS } from "@/components/SearchForm";
import { GraphPanel, NODE_COLORS, NODE_TYPE_LABELS } from "@/components/GraphPanel";
import type { AnswerItem, GraphNode } from "@/lib/api";
import { useSearchStore } from "@/stores/search";

// ── 合成 fixture（与后端 DTO 对齐） ──────────────────────────────────

function makeAnswer(over: Partial<AnswerItem>): AnswerItem {
  return {
    id: "answer-1",
    content_id: "cid-1",
    title: "考研还是就业？",
    author_name: "作者甲",
    content_text: "考研能提升学历竞争力",
    voteup_count: 100,
    url: "https://www.zhihu.com/answer/1",
    original_index: 0,
    summary: null,
    stance: null,
    claim_count: 0,
    ...over,
  };
}

function makeNode(over: Partial<GraphNode>): GraphNode {
  return {
    id: "query:q1",
    type: "QUERY",
    label: "考研还是就业",
    url: null,
    extra: {},
    ...over,
  };
}

beforeEach(() => {
  useSearchStore.setState({
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
  });
});

// ── 排序与数量 ────────────────────────────────────────────────────────

describe("sortByVoteupDesc", () => {
  it("sorts answers by voteup descending (stable)", () => {
    const a = makeAnswer({ id: "a", voteup_count: 5, original_index: 0 });
    const b = makeAnswer({ id: "b", voteup_count: 20, original_index: 1 });
    const c = makeAnswer({ id: "c", voteup_count: 20, original_index: 2 });
    const sorted = sortByVoteupDesc([a, b, c]);
    expect(sorted.map((x) => x.id)).toEqual(["b", "c", "a"]);
  });
});

describe("AnswerList", () => {
  it("shows at most 10 answers", () => {
    const answers = Array.from({ length: 12 }, (_, i) =>
      makeAnswer({ id: `a-${i}`, title: `回答 ${i}`, voteup_count: i })
    );
    render(<AnswerList answers={answers} />);
    const items = screen.getAllByRole("listitem");
    expect(items.length).toBe(10);
  });

  it("opens original answer with noopener,noreferrer", () => {
    const answers = [makeAnswer({ url: "https://www.zhihu.com/answer/42" })];
    render(<AnswerList answers={answers} />);
    const link = screen.getByRole("link", { name: /查看原文/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("href", "https://www.zhihu.com/answer/42");
  });

  it("filters by active concept", () => {
    const answers = [
      makeAnswer({ id: "a1", title: "考研分析", content_text: "考研提升学历" }),
      makeAnswer({ id: "a2", title: "就业分析", content_text: "就业看经验" }),
    ];
    useSearchStore.setState({ activeConcept: "考研" });
    render(<AnswerList answers={answers} />);
    expect(screen.getByText("考研分析")).toBeInTheDocument();
    expect(screen.queryByText("就业分析")).not.toBeInTheDocument();
  });

  it("shows empty state without answers", () => {
    render(<AnswerList answers={[]} />);
    expect(screen.getByText(/暂无回答/)).toBeInTheDocument();
  });

  it("is keyboard accessible (answer button focusable)", () => {
    const answers = [makeAnswer({})];
    render(<AnswerList answers={answers} />);
    const button = screen.getByRole("button", { name: /考研还是就业/ });
    button.focus();
    expect(document.activeElement).toBe(button);
  });
});

// ── 固定提示 ──────────────────────────────────────────────────────────

describe("fixed scope notice", () => {
  it("HomePage always shows the notice", async () => {
    // 通过 SearchForm 页面级断言在 page.test.tsx 覆盖；此处断言组件级渲染。
    const { default: HomePage } = await import("@/app/page");
    render(<HomePage />);
    const notices = screen.getAllByText(
      "观点基于知乎搜索返回内容生成，可能不包含原回答全部信息"
    );
    expect(notices.length).toBeGreaterThanOrEqual(1);
  });
});

// ── 错误态 ────────────────────────────────────────────────────────────

describe("ErrorBanner", () => {
  it("renders nothing when no error", () => {
    render(<ErrorBanner />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows actionable hint for known codes", () => {
    useSearchStore.setState({ error: "请求失败（错误码 NETWORK_ERROR）" });
    render(<ErrorBanner />);
    expect(screen.getByText(/无法连接后端服务/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("shows generic error fallback", () => {
    useSearchStore.setState({ error: "something unexpected" });
    render(<ErrorBanner />);
    expect(screen.getByText("请求失败，请稍后重试")).toBeInTheDocument();
  });
});

// ── Job 进度 / 表单 ──────────────────────────────────────────────────

describe("SearchForm", () => {
  it("shows progress label for fetching status", () => {
    useSearchStore.setState({ status: "fetching" });
    render(<SearchForm />);
    expect(screen.getByRole("status")).toHaveTextContent(
      STATUS_LABELS.fetching
    );
  });

  it("shows a warning instead of the green success copy for partial completion", () => {
    useSearchStore.setState({ status: "completed_partial" });
    render(<SearchForm />);
    expect(screen.getByText(/已保存搜索结果和可用图谱/)).toBeInTheDocument();
    expect(screen.queryByText(/已生成回答列表与知识图谱/)).not.toBeInTheDocument();
  });

  it("submits the trimmed query", async () => {
    const submitMock = vi.fn(async () => {});
    useSearchStore.setState({
      query: "考研还是就业",
      submit: submitMock,
    });
    render(<SearchForm />);
    const input = screen.getByLabelText("输入要分析的问题");
    expect(input).toHaveValue("考研还是就业");
    const button = screen.getByRole("button", { name: "开始分析" });
    fireEvent.click(button);
    // async handler；等待微任务。
    await Promise.resolve();
    await Promise.resolve();
    expect(submitMock).toHaveBeenCalledWith("考研还是就业");
  });
});

// ── 图谱组件（纯逻辑部分） ────────────────────────────────────────────

describe("GraphPanel / graph constants", () => {
  it("defines colors and labels for all four node types", () => {
    expect(Object.keys(NODE_COLORS).sort()).toEqual([
      "ANSWER",
      "CLAIM",
      "CONCEPT",
      "QUERY",
    ]);
    expect(NODE_TYPE_LABELS.ANSWER).toBe("回答");
  });

  it("shows empty placeholder without nodes", () => {
    render(<GraphPanel nodes={[]} edges={[]} />);
    expect(screen.getByText(/图谱将在分析完成后显示/)).toBeInTheDocument();
  });
});

// ── 右栏上下文预览 ───────────────────────────────────────────────────

describe("ContextPanel", () => {
  it("shows disabled AI panel with Stage 8 notice", () => {
    render(<ContextPanel />);
    // 提示出现在说明文字与禁用按钮两处。
    const notices = screen.getAllByText(/AI 问答将在 Stage 8 启用/);
    expect(notices.length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByRole("button", { name: /AI 问答将在 Stage 8 启用/ })
    ).toBeDisabled();
  });

  it("shows selected node details", () => {
    const node: GraphNode = makeNode({
      id: "concept:c1",
      type: "CONCEPT",
      label: "考研",
      extra: { frequency: 3 },
    });
    useSearchStore.setState({
      graphNodes: [node],
      selectedNodeId: "concept:c1",
    });
    render(<ContextPanel />);
    expect(screen.getByText("考研")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows placeholder without selection", () => {
    render(<ContextPanel />);
    expect(screen.getByText(/尚未选择节点/)).toBeInTheDocument();
  });
});

describe("nodeDetailRows", () => {
  it("extracts answer rows", () => {
    const node: GraphNode = makeNode({
      type: "ANSWER",
      label: "回答标题",
      extra: { voteup_count: 88, author_name: "作者", stance: "support" },
    });
    const rows = nodeDetailRows(node);
    expect(rows).toEqual(
      expect.arrayContaining([
        ["类型", "回答"],
        ["赞同数", "88"],
        ["作者", "作者"],
        ["立场", "support"],
      ])
    );
  });
});
