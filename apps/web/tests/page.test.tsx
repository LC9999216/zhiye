import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "@/app/page";

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

  it("shows the Stage 2 search placeholder", () => {
    render(<HomePage />);
    const placeholders = screen.getAllByText("搜索功能将在 Stage 2 启用");
    expect(placeholders.length).toBeGreaterThanOrEqual(1);
  });
});
