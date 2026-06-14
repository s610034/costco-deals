#!/usr/bin/env python3
# 測試清單頁抓到的連結，以及進去後的 selector 結果
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", locale="zh-TW")
    list_page   = ctx.new_page()
    detail_page = ctx.new_page()

    # Step1: 清單頁抓前3個連結
    print("=== 清單頁抓連結 ===")
    list_page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    for _ in range(3):
        list_page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    cards = list_page.query_selector_all("li.item, .product-list-item")
    print(f"找到 {len(cards)} 個卡片")

    links = []
    for card in cards[:5]:
        link_el = card.query_selector("a.lister-name, a.thumb")
        href = link_el.get_attribute("href") if link_el else ""
        if href and not href.startswith("http"):
            href = "https://www.costco.com.tw" + href
        name_el = card.query_selector(".lister-name .notranslate, .lister-name")
        name = name_el.inner_text().strip()[:30] if name_el else ""
        print(f"  {name} => {href[:80]}")
        links.append((name, href))

    # Step2: 逐一進商品頁測試 selector
    print("\n=== 商品頁 Selector 測試 ===")
    for name, href in links:
        if not href:
            continue
        print(f"\n商品: {name}")
        print(f"URL: {href[:80]}")
        detail_page.goto(href, wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)

        pv = detail_page.query_selector(".price-value")
        dv = detail_page.query_selector(".discount-value")
        pa = detail_page.query_selector(".price-after-discount")

        print(f"  .price-value:        {'OK: '+repr(pv.inner_text().strip()[:30]) if pv else 'NOT FOUND'}")
        print(f"  .discount-value:     {'OK: '+repr(dv.inner_text().strip()[:30]) if dv else 'NOT FOUND'}")
        print(f"  .price-after-discount: {'OK: '+repr(pa.inner_text().strip()[:30]) if pa else 'NOT FOUND'}")

    browser.close()
    print("\n完成")
