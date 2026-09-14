"use client";

import { useSearchStore } from "@/stores/search";

/** 可完成但带部分失败/降级的真实任务提示。 */
export function WarningBanner() {
  const warnings = useSearchStore((state) => state.warnings);
  if (warnings.length === 0) return null;
  return (
    <div
      role="status"
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <p className="font-medium">结果已保存，但部分分析未完成</p>
      <ul className="mt-1 list-disc pl-5 text-xs">
        {warnings.map((warning) => <li key={warning}>{warning}</li>)}
      </ul>
    </div>
  );
}
