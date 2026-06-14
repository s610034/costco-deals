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

    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    btn = page.query_selector("button:has-text('同意'), button:has-text('Accept')")
    if btn:
        btn.click(); time.sleep(1)

    page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # 安全滾動
    for _ in range(5):
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            time.sleep(1)
        except Exception:
            break

    cards = page.query_selector_all(".product-list-item")
    print(f"商品卡片數量: {len(cards)}")

    for i, card in enumerate(cards[:5]):
        print(f"\n--- 卡片 {i+1} ---")
        # 直接看 inner_text 和 inner_html
        txt = card.inner_text().strip()[:100].replace("\n", " | ")
        print(f"  text: {txt}")

        # 試 selector
        for sel in [".lister-name .notranslate", ".lister-name", "a.lister-name", "h3", ".product-name"]:
            el = card.query_selector(sel)
            if el:
                print(f"  name [{sel}]: {el.inner_text().strip()[:50]}")
                break

        link_el = card.query_selector("a.lister-name, a.thumb, a[href*='/p/']")
        if link_el:
            print(f"  link: {link_el.get_attribute('href')[:70]}")

    browser.close()
