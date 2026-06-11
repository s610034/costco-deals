#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper.py
爬取台灣好市多 costco.com.tw 三個折扣頁面的特價商品
只保留實體門市有折扣的商品（過濾掉無折扣 / 線上限定）
"""

import json
import time
import datetime
import os
import re
from typing import Optional, List, Dict

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DEAL_PAGES = [
    {
        "name": "限時優惠 (Hot Buys)",
        "url": "https://www.costco.com.tw/c/hot-buys",
        "category_tag": "限時優惠",
    },
    {
        "name": "精選優惠 (Coupon)",
        "url": "https://www.costco.com.tw/Deals/c/Coupon",
        "category_tag": "精選優惠",
    },
    {
        "name": "把握優惠 (While Supplies Last)",
        "url": "https://www.costco.com.tw/While-Supplies-Last/c/Toogood",
        "category_tag": "把握優惠",
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# 線上限定關鍵字（出現在商品名稱或摘要時跳過）
ONLINE_ONLY_KEYWORDS = ["線上限定", "線上專屬", "網路限定", "online only", "online exclusive"]


def parse_number(text: str) -> Optional[int]:
    """從字串取出第一個整數，'$7,099' → 7099"""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def extract_chinese_name(text: str) -> str:
    """
    從「中文名稱\n英文名稱」格式中只取中文行
    例如 'Honeywell 淨味空氣清淨機 HPA5350WTWV1\nHoneywell Air Purifier HPA5350WTWV1'
    → 'Honeywell 淨味空氣清淨機 HPA5350WTWV1'
    """
    if not text:
        return ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return text.strip()
    # 優先取含中文字的行
    for line in lines:
        if re.search(r'[\u4e00-\u9fff]', line):
            return line
    # 沒有中文就回傳第一行
    return lines[0]


def scrape_page(page, url: str, category_tag: str) -> List[Dict]:
    products = []

    print(f"  📡 載入頁面：{url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("li.item, .product-list-item", timeout=15000)
    except PlaywrightTimeout:
        print(f"  ⚠️  頁面逾時，繼續嘗試解析...")

    # 緩慢滾動觸發 lazy-load
    for _ in range(5):
        page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
        time.sleep(1.2)

    cards = page.query_selector_all("li.item, .product-list-item")
    if not cards:
        cards = page.query_selector_all("[data-product-code]")

    print(f"  📦 找到 {len(cards)} 個商品卡片")
    scraped_at = datetime.datetime.now().isoformat(timespec="seconds")
    skipped_no_discount = 0
    skipped_online_only = 0

    for card in cards:
        try:
            # ── 商品名稱（只取中文）──
            name_el = card.query_selector(".lister-name .notranslate, .lister-name")
            raw_name = name_el.inner_text().strip() if name_el else ""
            name = extract_chinese_name(raw_name)
            if not name:
                continue

            # ── 摘要文字（用於判斷線上限定 / 優惠期間）──
            summary_el = card.query_selector(".product-summary-container, .product-information-text")
            summary_text = summary_el.inner_text() if summary_el else ""

            # ── 過濾線上限定 ──
            combined_check = (name + summary_text).lower()
            if any(kw in combined_check for kw in ONLINE_ONLY_KEYWORDS):
                skipped_online_only += 1
                continue

            # ── 商品連結 ──
            link_el = card.query_selector("a.lister-name, a.thumb")
            href = link_el.get_attribute("href") if link_el else ""
            if href and not href.startswith("http"):
                href = "https://www.costco.com.tw" + href

            # ── 圖片 ──
            img_el = card.query_selector("img")
            img_url = ""
            if img_el:
                src = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""
                if src and not src.startswith("http"):
                    src = "https://www.costco.com.tw" + src
                img_url = src

            # ── 原價 ──
            orig_el = card.query_selector(".original-price .product-price-amount, .product-price-amount")
            original_price = parse_number(orig_el.inner_text() if orig_el else "")

            # ── 折扣金額（從 .savings 或 price-panel 全文搜尋「折價」）──
            saving_el = card.query_selector(".savings, [class*='saving'], [class*='discount-amount']")
            saving_text = saving_el.inner_text() if saving_el else ""

            if not saving_text:
                panel_el = card.query_selector(".price-panel, .product-price")
                if panel_el:
                    panel_text = panel_el.inner_text()
                    m = re.search(r"折價[\s\$]*[\d,]+", panel_text)
                    if m:
                        saving_text = m.group()

            discount_amt = parse_number(saving_text) if saving_text else None

            # ── 只保留有折扣金額的商品 ──
            if not discount_amt:
                skipped_no_discount += 1
                continue

            # ── 折扣後售價 & 折扣幅度 ──
            if original_price and discount_amt < original_price:
                sale_price = original_price - discount_amt
                pct = round((discount_amt / original_price) * 100, 1)
                discount_pct = f"{pct}%"
            else:
                sale_price = None
                discount_pct = None

            # ── 優惠期間 ──
            period = ""
            if summary_text:
                m = re.search(r"優惠期間[^\n]*", summary_text)
                if m:
                    period = m.group().replace("*", "").replace("優惠期間", "").strip()

            products.append({
                "商品名稱": name,
                "分類": category_tag,
                "原價": original_price,
                "折扣金額": discount_amt,
                "折扣幅度": discount_pct,
                "折扣後售價": sale_price,
                "優惠期間": period,
                "圖片URL": img_url,
                "商品連結": href,
                "抓取時間": scraped_at,
            })

        except Exception as e:
            print(f"  ⚠️  解析商品失敗：{e}")
            continue

    print(f"  ✅ 有效折扣商品：{len(products)} 筆（跳過無折扣 {skipped_no_discount}、線上限定 {skipped_online_only}）")
    return products


def scrape_all() -> List[Dict]:
    all_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="zh-TW",
        )
        page = context.new_page()

        try:
            page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
            accept_btn = page.query_selector("button:has-text('同意'), button:has-text('Accept')")
            if accept_btn:
                accept_btn.click()
                time.sleep(1)
        except Exception:
            pass

        for deal_page in DEAL_PAGES:
            print(f"\n🔍 爬取：{deal_page['name']}")
            items = scrape_page(page, deal_page["url"], deal_page["category_tag"])
            all_products.extend(items)
            time.sleep(2)

        browser.close()

    print(f"\n✅ 最終共 {len(all_products)} 項有效折扣商品")
    return all_products


def save_json(products: List[Dict], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    path = os.path.join(output_dir, f"costco_deals_{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"💾 已儲存：{path}")
    return path


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    products = scrape_all()
    save_json(products, DATA_DIR)
