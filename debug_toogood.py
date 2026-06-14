#!/usr/bin/env python3
# debug_toogood.py - 診斷把握優惠頁結構
from playwright.sync_api import sync_playwright
import time, json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
URL = "https://www.costco.com.tw/While-Supplies-Last/c/Toogood"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="zh-TW")
    page = ctx.new_page()

    # 先去首頁接受 cookie
    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    btn = page.query_selector("button:has-text('同意'), button:has-text('Accept')")
    if btn: btn.click(); time.sleep(1)

    print("Loading Toogood page...")
    try:
        page.goto(URL, wait_until="networkidle", timeout=40000)
        time.sleep(3)
    except Exception as e:
        print("networkidle timeout:", e)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)
        except Exception as e2:
            print("domcontentloaded also failed:", e2)

    print("Current URL:", page.url)
    print("Title:", page.title())

    # 試各種 selector
    selectors = [
        ".product-list-item",
        ".lister-item",
        ".product-tile",
        ".product-card",
        "[class*=product]",
        ".cx-product-container",
        "product-list-item",
        ".item-product",
    ]
    for sel in selectors:
        els = page.query_selector_all(sel)
        if els:
            print(f"  {sel}: {len(els)} items")

    # 看 HTML 結構
    html = page.content()
    print("\nHTML length:", len(html))

    # 找商品相關的 class
    import re
    classes = re.findall(r'class="([^"]*product[^"]*)"', html[:10000], re.I)
    unique_classes = list(set(classes))[:20]
    print("\nProduct-related classes (first 10000 chars):")
    for c in unique_classes[:15]:
        print(" ", c[:80])

    # 存 HTML 供檢查
    with open("/Users/ericchen/Documents/testthing/costco-deals/data/toogood_debug.html", "w") as f:
        f.write(html)
    print("\nSaved HTML to data/toogood_debug.html")

    # 看 JS 能抓到什麼
    result = page.evaluate("""() => {
        const info = {
            productListItems: document.querySelectorAll('.product-list-item').length,
            listerItems: document.querySelectorAll('.lister-item').length,
            allLinks: document.querySelectorAll('a[href*="/p/"]').length,
            bodyText: document.body.innerText.slice(0, 500),
        };
        // 找有商品名稱的元素
        const nameEls = document.querySelectorAll('.lister-name, .product-name, [class*=name]');
        info.nameEls = nameEls.length;
        info.firstNames = Array.from(nameEls).slice(0,5).map(el => el.innerText.trim().slice(0,40));
        return info;
    }""")
    print("\nJS result:", json.dumps(result, ensure_ascii=False, indent=2))

    browser.close()
