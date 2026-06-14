#!/usr/bin/env python3
"""快速測試把握優惠頁：只抓清單頁，不進詳情頁，確認商品名稱抓得到"""
import sys, os, time
sys.path.insert(0, '/Users/ericchen/Documents/testthing/costco-deals')

with open('/Users/ericchen/Documents/testthing/costco-deals/.env') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, _, v = line.partition('=')
        if k.strip() and v.strip(): os.environ[k.strip()] = v.strip()

from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="zh-TW")
    page = ctx.new_page()

    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1)
    btn = page.query_selector("button:has-text('同意')")
    if btn: btn.click(); time.sleep(1)

    print("Loading Toogood...")
    try:
        page.goto("https://www.costco.com.tw/While-Supplies-Last/c/Toogood",
                  wait_until="networkidle", timeout=40000)
        time.sleep(2)
    except Exception as e:
        print("Timeout:", e)
        time.sleep(3)

    raw = page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-list-item');
        const results = [];
        cards.forEach(card => {
            let name = '';
            const nameEl = card.querySelector('.lister-name .notranslate, .lister-name');
            if (nameEl) name = nameEl.innerText.trim();
            if (!name) {
                const titleEl = card.querySelector('a[title]');
                if (titleEl) name = titleEl.getAttribute('title') || '';
            }
            if (!name) return;
            const linkEl = card.querySelector('a.thumb, a[href*="/p/"]');
            let href = linkEl ? linkEl.getAttribute('href') : '';
            if (href && !href.startsWith('http')) href = 'https://www.costco.com.tw' + href;
            results.push({name, href});
        });
        return results;
    }""")

    print(f"\n✅ 把握優惠頁共 {len(raw)} 個商品：")
    for i, item in enumerate(raw):
        print(f"  {i+1:2d}. {item['name'][:45]}")
    browser.close()
