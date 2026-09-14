import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// 非 globals 模式下 RTL 不自动清理 DOM，这里显式注册，
// 避免多个 render 的节点累积导致 getByText/getByRole 多匹配。
afterEach(() => {
  cleanup();
});
