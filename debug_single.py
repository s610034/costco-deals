#!/usr/bin/env python3
# 用單一 page 直接進商品頁測試
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
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
        btn.click(); time.sleep(1); print("cookie OK")

    # 直接進 Honeywell 商品頁
    url = "https://www.costco.com.tw/Televisions-Appliances/Cooling-Heating-Air-Treatment/Air-Purifiers-Filters-Accessories/Honeywell-Air-Purifier-HPA5350WTWV1/p/157137"
    print(f"\n進商品頁: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # 看頁面標題確認有載入
    title = page.title()
    print(f"頁面標題: {title}")

    # 試 selector
    for sel in [".price-value", ".discount-value", ".price-after-discount",
                ".product-price-amount", "[class*=price]", "sip-price"]:
        el = page.query_selector(sel)
        if el:
            print(f"  ✅ [{sel}]: {el.inner_text().strip()[:50]}")
        else:
            print(f"  ❌ [{sel}]")

    # 截圖確認頁面狀態
    page.screenshot(path="/tmp/product_page.png")
    print("\n截圖已存到 /tmp/product_page.png")

    browser.close()
