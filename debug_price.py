#!/usr/bin/env python3
# 快速測試：進商品頁看 discount-value 是否存在
from playwright.sync_api import sync_playwright
import time

TEST_URL = "https://www.costco.com.tw/Televisions-Appliances/Cooling-Heating-Air-Treatment/Air-Purifiers-Filters-Accessories/Honeywell-Air-Purifier-HPA5350WTWV1/p/157137"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    print(f"載入：{TEST_URL}")
    page.goto(TEST_URL, wait_until="domcontentloaded", timeout=25000)
    time.sleep(2)

    # 直接測試 scraper 裡用的 selector
    selectors = [
        ".price-value",
        ".discount-value",
        ".price-after-discount",
        ".price-original",
        ".price-with-discount",
        ".discount",
    ]
    print("\n=== Selector 測試 ===")
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            print(f"  OK [{sel}]: {repr(el.inner_text().strip()[:80])}")
        else:
            print(f"  NO [{sel}]")

    # 再看所有 class 含 price/discount 的元素
    print("\n=== 目前所有價格元素 ===")
    result = page.evaluate("""() => {
        let out = [];
        document.querySelectorAll('[class*=price],[class*=Price],[class*=discount],[class*=Discount]').forEach(el => {
            const txt = el.innerText.trim();
            if (txt && /[0-9]/.test(txt) && txt.length < 200)
                out.push(el.className.substring(0,70) + ' => ' + txt.substring(0,80).replace(/\\n/g,' | '));
        });
        return [...new Set(out)].slice(0,20);
    }""")
    for r in result:
        print(f"  {r}")

    browser.close()
    print("\n完成")
