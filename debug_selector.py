#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        locale="zh-TW", viewport={"width": 1280, "height": 900}
    )
    page = ctx.new_page()

    # 接受 cookie
    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    btn = page.query_selector("button:has-text('同意'), button:has-text('Accept')")
    if btn:
        btn.click(); time.sleep(1); print("cookie 已接受")

    page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    for _ in range(3):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # 試所有可能的 selector
    selectors = [
        ".product-list-item",
        "sip-product-list-item",
        "li.item",
        "[class*='product-list']",
        "[class*='lister']",
        ".lister-name",
        "[data-product-code]",
    ]
    print("\n=== Selector 測試 ===")
    for sel in selectors:
        els = page.query_selector_all(sel)
        print(f"  {len(els):3d}  {sel}")

    # 看頁面 HTML 片段找線索
    print("\n=== 商品區塊 HTML 前段 ===")
    content = page.query_selector("main, #main, .main, [class*='product-list'], [class*='lister']")
    if content:
        print(content.inner_html()[:800])

    browser.close()
