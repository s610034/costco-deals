#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        locale="zh-TW"
    )
    page = ctx.new_page()

    # 接受 cookie
    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    btn = page.query_selector("button:has-text('同意')")
    if btn:
        btn.click()
        time.sleep(1)
        print("cookie OK")

    # networkidle
    print("載入清單頁...")
    try:
        page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="networkidle", timeout=40000)
        print("networkidle 完成")
    except Exception as e:
        print(f"networkidle 超時，繼續: {e}")
    time.sleep(2)

    count = page.evaluate("document.querySelectorAll('.product-list-item').length")
    print(f"商品數量: {count}")

    items = page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-list-item');
        return Array.from(cards).slice(0,3).map(c => {
            const n = c.querySelector('.lister-name .notranslate, .lister-name');
            const l = c.querySelector('a.lister-name, a.thumb');
            return {name: n ? n.innerText.trim() : '', href: l ? l.getAttribute('href') : ''};
        });
    }""")
    for item in items:
        print(f"  {item['name'][:35]:35s} => {item['href'][:60]}")

    browser.close()
    print("完成")
