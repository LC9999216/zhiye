import { render, screen } from "@testing-library/react";
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

import HomePage from "@/app/page";
import { useSearchStore } from "@/stores/search";

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

describe("HomePage", () => {
  it("renders the product title 知辨", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: "知辨", level: 1 })
    ).toBeInTheDocument();
  });

  it("always shows the fixed scope notice", () => {
    render(<HomePage />);
    const notices = screen.getAllByText(
      "观点基于知乎搜索返回内容生成，可能不包含原回答全部信息"
    );
    expect(notices.length).toBeGreaterThanOrEqual(1);
  });

  it("shows the three-column layout headings", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "回答列表" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "知识图谱" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI 问答" })).toBeInTheDocument();
  });

  it("shows disabled AI panel with Stage 8 notice", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("button", { name: /AI 问答将在 Stage 8 启用/ })
    ).toBeDisabled();
  });

  it("shows error banner when a known code is present", () => {
    useSearchStore.setState({
      error: "请求失败（错误码 NETWORK_ERROR）",
    });
    render(<HomePage />);
    expect(screen.getByText(/无法连接后端服务/)).toBeInTheDocument();
  });

  it("displays synthetic fixture answers in the left column", () => {
    useSearchStore.setState({
      status: "completed",
      results: [
        {
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
        },
      ],
    });
    render(<HomePage />);
    expect(screen.getByText("考研还是就业？")).toBeInTheDocument();
    expect(screen.getByText("作者甲")).toBeInTheDocument();
    expect(screen.getByText("👍 100")).toBeInTheDocument();
  });
});
