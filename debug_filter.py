#!/usr/bin/env python3
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import time, re

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ONLINE_ONLY_KW = ["線上限定", "線上專屬", "網路限定", "線上獨家"]

def parse_num(text):
    if not text: return None
    d = re.sub(r"[^\d]", "", text)
    return int(d) if d else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, locale="zh-TW", viewport={"width":1280,"height":900})
    list_page   = ctx.new_page()
    detail_page = ctx.new_page()

    # 先接受 cookie
    print("接受 cookie...")
    list_page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    btn = list_page.query_selector("button:has-text('同意'), button:has-text('Accept')")
    if btn:
        btn.click()
        print("  cookie 已接受")
        time.sleep(1)
    else:
        print("  找不到 cookie 按鈕")

    # 清單頁
    print("\n載入清單頁...")
    list_page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    for _ in range(3):
        list_page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    # 試不同 selector
    for sel in ["li.item", ".product-list-item", "[data-product-code]", "sip-product-list-item"]:
        els = list_page.query_selector_all(sel)
        print(f"  selector '{sel}': {len(els)} 個")

    cards = list_page.query_selector_all("li.item")
    if not cards:
        cards = list_page.query_selector_all(".product-list-item")
    print(f"\n使用的卡片數量: {len(cards)}")

    for card in cards[:3]:
        name_el = card.query_selector(".lister-name .notranslate, .lister-name")
        name = name_el.inner_text().strip() if name_el else ""
        link_el = card.query_selector("a.lister-name, a.thumb")
        href = link_el.get_attribute("href") if link_el else ""
        if href and not href.startswith("http"):
            href = "https://www.costco.com.tw" + href

        print(f"\n{'='*55}")
        print(f"商品: {name[:40]}")
        print(f"URL:  {href[:80]}")

        detail_page.goto(href, wait_until="domcontentloaded", timeout=25000)
        try:
            detail_page.wait_for_selector(".price-value, .product-price-container", timeout=5000)
        except PWTimeout:
            print("  ⚠️  等待逾時")
        time.sleep(1)

        body_text = detail_page.inner_text("body")
        found_kw = [kw for kw in ONLINE_ONLY_KW if kw in body_text]
        print(f"  線上限定KW: {found_kw or '無'}")

        pv = detail_page.query_selector(".price-value")
        dv = detail_page.query_selector(".discount-value")
        disc = parse_num(dv.inner_text() if dv else "")

        print(f"  price-value:    {repr(pv.inner_text()[:25]) if pv else 'NOT FOUND'}")
        print(f"  discount-value: {repr(dv.inner_text()[:25]) if dv else 'NOT FOUND'}")
        print(f"  最終判斷: {'✅ 通過' if disc and not found_kw else '❌ 被過濾'}")

    browser.close()
    print("\n完成")
