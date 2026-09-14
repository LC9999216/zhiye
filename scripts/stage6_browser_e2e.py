"""Repeatable Stage 6 browser smoke test.

Run with a local or deployed Web/API pair:

    $env:STAGE6_WEB_URL = "http://localhost:3000"
    $env:STAGE6_INVITE_CODE = "<local invite code>"  # production only
    $env:STAGE6_EXPECT_AUTH_ERROR = "1"                # optional auth smoke
    python scripts/stage6_browser_e2e.py

The script uses the repository's Python Playwright installation and never
handles provider keys. It only submits a natural-language question through
the visible page and checks the user-visible three-column result.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


WEB_URL = os.environ.get("STAGE6_WEB_URL", "http://localhost:3000")
QUERY = os.environ.get("STAGE6_QUERY", "计算机专业考研还是就业")
INVITE_CODE = os.environ.get("STAGE6_INVITE_CODE", "")
EXPECT_AUTH_ERROR = os.environ.get("STAGE6_EXPECT_AUTH_ERROR", "0") == "1"
HEADLESS = os.environ.get("STAGE6_HEADLESS", "1") != "0"


def run(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(WEB_URL, wait_until="domcontentloaded")
    page.get_by_text("观点基于知乎搜索返回内容生成，可能不包含原回答全部信息").first.wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.get_by_label("输入体验码").is_visible()
    if EXPECT_AUTH_ERROR and not INVITE_CODE:
        page.get_by_label("输入要分析的问题").fill(QUERY)
        page.get_by_role("button", name="开始分析").click()
        page.get_by_role("alert").wait_for(timeout=10_000)
        page.reload(wait_until="domcontentloaded")
    if INVITE_CODE:
        page.get_by_label("输入体验码").fill(INVITE_CODE)
    page.get_by_label("输入要分析的问题").fill(QUERY)
    page.get_by_role("button", name="开始分析").click()

    try:
        page.get_by_text(
            re.compile(r"(?:分析完成：已生成回答列表与知识图谱|部分完成：")
        ).wait_for(timeout=900_000)
    except PlaywrightTimeoutError as exc:
        error = page.get_by_role("alert")
        detail = error.inner_text() if error.count() else "任务仍在执行或页面不可用"
        raise RuntimeError(detail) from exc

    assert page.get_by_role("heading", name="回答列表").is_visible()
    graph = page.get_by_role("img", name="知识图谱：问题、回答、观点与概念")
    assert graph.is_visible()
    graph.hover()
    page.mouse.wheel(0, 240)
    page.mouse.move(720, 450)
    assert page.get_by_text("AI 问答将在 Stage 8 启用").first.is_visible()

    links = page.get_by_role("link", name=re.compile("查看原文"))
    if links.count():
        first_link = links.first
        assert first_link.get_attribute("target") == "_blank"
        assert "noopener" in (first_link.get_attribute("rel") or "")
        assert "noreferrer" in (first_link.get_attribute("rel") or "")
        href = first_link.get_attribute("href") or ""
        assert re.match(r"https://(?:www\.)?zhihu\.com/answer/", href)


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=HEADLESS)
        try:
            page = browser.new_page()
            run(page)
            screenshot = Path(".local") / "stage6-browser-e2e.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            print(f"Stage 6 browser smoke passed: {WEB_URL}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
