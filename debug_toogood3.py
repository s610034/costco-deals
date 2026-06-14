#!/usr/bin/env python3
# 快速測試把握優惠頁完整抓取（只抓前3個商品）
import sys, os
sys.path.insert(0, '/Users/ericchen/Documents/testthing/costco-deals')
os.chdir('/Users/ericchen/Documents/testthing/costco-deals')

# 載入 .env
with open('.env') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if k and v: os.environ[k] = v

import time, json, re
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
URL = "https://www.costco.com.tw/While-Supplies-Last/c/Toogood"

def parse_num(text):
    if not text: return None
    d = re.sub(r"[^\d]", "", text)
    return int(d) if d else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="zh-TW")
    list_page   = ctx.new_page()
    detail_page = ctx.new_page()

    for pg in [list_page, detail_page]:
        pg.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1)
        btn = pg.query_selector("button:has-text('同意')")
        if btn: btn.click(); time.sleep(1)

    print("Loading Toogood list page...")
    try:
        list_page.goto(URL, wait_until="networkidle", timeout=40000)
        time.sleep(3)
    except Exception as e:
        print("Timeout:", e)
        list_page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

    # 新版 JS（支援 a[title] fallback）
    raw = list_page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-list-item');
        const results = [];
        cards.forEach(card => {
            const nameEl = card.querySelector('.lister-name .notranslate, .lister-name');
            let name = nameEl ? nameEl.innerText.trim() : '';
            if (!name) {
                const titleEl = card.querySelector('a[title]');
                if (titleEl) name = titleEl.getAttribute('title') || titleEl.innerText.trim();
            }
            if (!name) {
                const nc = card.querySelector('.product-name-container');
                if (nc) name = nc.innerText.trim();
            }
            if (!name) return;
            const linkEl = card.querySelector('a.lister-name, a.thumb, a[href*="/p/"]');
            let href = linkEl ? linkEl.getAttribute('href') : '';
            if (href && !href.startsWith('http')) href = 'https://www.costco.com.tw' + href;
            const imgEl = card.querySelector('img');
            let imgSrc = imgEl ? (imgEl.getAttribute('src') || '') : '';
            if (imgSrc && !imgSrc.startsWith('http')) imgSrc = 'https://www.costco.com.tw' + imgSrc;
            results.push({name, href, imgSrc});
        });
        return results;
    }""")
    print(f"Found {len(raw)} products on Toogood page")

    # 測試前3個商品的詳情頁
    for item in raw[:3]:
        print(f"\n商品: {item['name'][:40]}")
        print(f"  URL: {item['href'][:60]}")
        try:
            detail_page.goto(item['href'], wait_until="networkidle", timeout=30000)
            time.sleep(1)
        except Exception:
            detail_page.goto(item['href'], wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)

        # 試各種價格 selector
        for sel in [".price-value", ".discount-value", ".price-after-discount"]:
            el = detail_page.query_selector(sel)
            if el: print(f"  {sel}: {el.inner_text().strip()[:20]}")

        # 詳情文字
        detail = detail_page.query_selector(".pdp-messages-wrapper, .product-information-text")
        if detail:
            txt = detail.inner_text()[:200]
            print(f"  Detail text: {txt[:100]}")

    browser.close()
