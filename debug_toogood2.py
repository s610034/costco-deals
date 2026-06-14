#!/usr/bin/env python3
# 快速測試把握優惠頁一個商品的詳情結構
from playwright.sync_api import sync_playwright
import time, re

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# 從 debug 結果取的真實商品 URL
TEST_URL = "https://www.costco.com.tw/Clothing-Accessories/Womens-Clothing/Womens-Pajamas/Polo-Ralph-Lauren-Ladies-Long-Sleeve-Pajama-Set/p/1846321"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, locale="zh-TW")
    page = ctx.new_page()

    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1)
    btn = page.query_selector("button:has-text('同意')")
    if btn: btn.click(); time.sleep(1)

    print("Loading product page...")
    try:
        page.goto(TEST_URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)
    except Exception as e:
        print("Timeout:", e)
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

    # 試各種價格 selector
    for sel in [".price-value", ".discount-value", ".price-after-discount",
                ".product-price-amount", ".product-price", "[class*=price]",
                ".product-summary-price"]:
        els = page.query_selector_all(sel)
        if els:
            texts = [e.inner_text().strip()[:30] for e in els[:3]]
            print(f"  {sel}: {texts}")

    # JS 抓所有可見文字含數字的區塊
    result = page.evaluate("""() => {
        const priceEls = document.querySelectorAll('[class*=price], [class*=discount]');
        return Array.from(priceEls).slice(0, 15).map(el => ({
            cls: el.className.slice(0, 60),
            text: el.innerText.trim().slice(0, 40)
        })).filter(x => x.text);
    }""")
    print("\nAll price-related elements:")
    for r in result:
        print(f"  [{r['cls'][:50]}]: {r['text']}")

    browser.close()
