#!/usr/bin/env python3
import sys, time, re
sys.path.insert(0, '/Users/ericchen/Documents/testthing/costco-deals')
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, locale="zh-TW")
    page = ctx.new_page()
    page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    try:
        btn = page.query_selector("button:has-text('同意')")
        if btn: btn.click(); time.sleep(1)
    except Exception:
        pass

    page.goto("https://www.costco.com.tw/search?q=COLEMAN", wait_until="domcontentloaded", timeout=20000)
    time.sleep(4)

    result = page.evaluate("""() => {
        const card = document.querySelector('.product-list-item');
        if (!card) return {error: 'no card'};

        const nameEl = card.querySelector('.lister-name .notranslate, a[title]');
        const name = nameEl ? (nameEl.innerText || nameEl.getAttribute('title') || '') : '';

        const origEl = card.querySelector('.original-price .product-price-amount, .product-price-amount');
        const orig = origEl ? origEl.innerText : 'NOT FOUND';

        const discEl = card.querySelector('.discount-value, .lister-savings, [class*="saving"]');
        const disc = discEl ? discEl.innerText : 'NOT FOUND';

        // 也找其他可能的 selector
        const allAmounts = Array.from(card.querySelectorAll('[class*=amount], [class*=price]'))
            .map(el => ({cls: el.className.slice(0,50), text: el.innerText?.trim().slice(0,20)}))
            .filter(x => x.text && /[0-9]/.test(x.text));

        return {name: name.slice(0,40), orig, disc, allAmounts};
    }""")

    print("名稱:", result.get('name',''))
    print("orig repr:", repr(result.get('orig','')))
    print("disc repr:", repr(result.get('disc','')))
    print("所有含數字的 price/amount 元素:")
    for x in result.get('allAmounts', []):
        print(f"  [{x['cls']}] -> {repr(x['text'])}")

    browser.close()
