#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    page.goto("https://www.daybuy.tw/costco/160705/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(2)
    content = page.query_selector(".entry-content, .post-content")
    if content:
        print(content.inner_text()[:2000])
    browser.close()
