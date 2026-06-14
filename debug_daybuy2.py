#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import time, re

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0")
    page.goto("https://www.daybuy.tw/costco/254139/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)

    content = page.query_selector(".entry-content, .post-content")
    if content:
        html = content.inner_html()
        # 找圖片
        imgs = re.findall(r'src=[\'"](https?://[^\'"]+\.(?:jpg|png|webp)[^\'"]*)[\'"]', html)
        print(f"圖片數量: {len(imgs)}")
        for img in imgs[:5]:
            print(f"  {img[:100]}")
        # 找所有文字節點
        texts = re.findall(r">([^<]{5,})<", html)
        print(f"\n文字節點:")
        for t in texts[:20]:
            t = t.strip()
            if t:
                print(f"  {t[:80]}")
    browser.close()
