#!/usr/bin/env python3
# 直接測試完整流程：清單頁抓連結 → 商品頁抓折扣
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import time, re

def parse_num(text):
    if not text: return None
    d = re.sub(r"[^\d]", "", text)
    return int(d) if d else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        locale="zh-TW", viewport={"width": 1280, "height": 900}
    )
    list_page   = ctx.new_page()
    detail_page = ctx.new_page()

    # 接受 cookie
    list_page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    btn = list_page.query_selector("button:has-text('同意'), button:has-text('Accept')")
    if btn:
        btn.click(); time.sleep(1); print("cookie OK")

    # 清單頁
    list_page.goto("https://www.costco.com.tw/c/hot-buys", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    for _ in range(3):
        try:
            list_page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(1)
        except Exception:
            break

    # 用 evaluate 抓連結
    items = list_page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-list-item');
        const results = [];
        cards.forEach(card => {
            const nameEl = card.querySelector('.lister-name .notranslate, .lister-name');
            const name = nameEl ? nameEl.innerText.trim() : '';
            if (!name) return;
            const linkEl = card.querySelector('a.lister-name, a.thumb');
            let href = linkEl ? linkEl.getAttribute('href') : '';
            if (href && !href.startsWith('http')) href = 'https://www.costco.com.tw' + href;
            results.push({name, href});
        });
        return results.slice(0, 3);
    }""")

    print(f"\n清單頁抓到 {len(items)} 筆（只測前3個）")
    for item in items:
        print(f"\n{'='*55}")
        print(f"商品: {item['name'][:40]}")
        print(f"URL:  {item['href'][:70]}")

        # 商品頁
        detail_page.goto(item['href'], wait_until="domcontentloaded", timeout=25000)
        try:
            detail_page.wait_for_selector(".price-value, .product-price-container", timeout=5000)
        except PWTimeout:
            print("  ⚠️  wait_for_selector timeout")
        time.sleep(1)

        pv = detail_page.query_selector(".price-value")
        dv = detail_page.query_selector(".discount-value")
        pa = detail_page.query_selector(".price-after-discount")

        orig = parse_num(pv.inner_text() if pv else "")
        disc = parse_num(dv.inner_text() if dv else "")
        sale = parse_num(re.sub("小計","", pa.inner_text()) if pa else "")

        print(f"  .price-value:    {'OK='+str(orig) if pv else 'NOT FOUND'}")
        print(f"  .discount-value: {'OK='+str(disc) if dv else 'NOT FOUND'}")
        print(f"  .price-after:    {'OK='+str(sale) if pa else 'NOT FOUND'}")

        # 若沒找到折扣，看所有含數字的 price 元素
        if not dv:
            print("  [fallback] 找所有含數字的 price 元素:")
            result = detail_page.evaluate("""() => {
                let out = [];
                document.querySelectorAll('[class*=price],[class*=Price],[class*=discount],[class*=Discount],[class*=saving],[class*=Saving]').forEach(el => {
                    const txt = el.innerText.trim();
                    if (txt && /[0-9]/.test(txt) && txt.length < 100)
                        out.push({cls: el.className.substring(0,60), txt: txt.replace(/\\n/g,' | ').substring(0,80)});
                });
                return out.slice(0,10);
            }""")
            for r in result:
                print(f"    [{r['cls']}]: {r['txt']}")

    browser.close()
    print("\n完成")
