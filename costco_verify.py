#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
costco_verify.py
用商品編號直接訪問官網詳情頁，驗證並補充正確的價格、優惠期間、圖片。
取代原本用搜尋的 costco_search.py。

流程：
  有商品編號 → 直接訪問 /p/{編號} → 抓正確原價/折扣/.Wallet期間
  無商品編號 → 從連結取 /p/數字 → 同上
  都沒有 → 跳過（不搜尋，避免搜到錯誤商品）
"""

import re, time
from typing import Optional, Dict, List

BASE_URL = "https://www.costco.com.tw"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

DATE_RANGE_RE = re.compile(r"(\d{1,2}/\d{1,2}[^~\d]*[~～\-]+[^~\d]*\d{1,2}/\d{1,2}|\d{4}/\d{2}/\d{2}[^\d]+\d{4}/\d{2}/\d{2})")


def _parse_num(text: str) -> Optional[int]:
    if not text: return None
    d = re.sub(r"[^\d]", "", str(text))
    return int(d) if d else None


def get_item_code(product: Dict) -> str:
    """從商品編號欄位或連結中取商品編號"""
    # 直接有商品編號
    code = product.get("商品編號", "")
    if code:
        return str(code)
    # 從官網連結取 /p/數字
    link = product.get("商品連結", "")
    m = re.search(r"/p/(\d+)", link)
    if m:
        return m.group(1)
    return ""


def fetch_product_detail(item_code: str, page) -> Optional[Dict]:
    """
    直接訪問 /p/{item_code} 抓取正確的商品資料。
    回傳 dict 或 None（找不到）。
    """
    url = f"{BASE_URL}/p/{item_code}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except Exception:
        return None

    result = page.evaluate("""() => {
        // 確認頁面是商品詳情頁
        if (!document.querySelector('.pdp-main, .product-name, [class*=pdp]')) {
            return null;
        }

        // 商品名稱
        const nameEl = document.querySelector('h1.product-name, h1[itemprop=name], h1');
        const name = nameEl ? nameEl.innerText.trim() : '';

        // 原價
        let orig = '';
        const origSelectors = [
            '.your-price .product-price-amount',
            '.original-price .product-price-amount',
            '[itemprop=price]',
        ];
        for (const sel of origSelectors) {
            const el = document.querySelector(sel);
            if (el && el.innerText.trim()) { orig = el.innerText.trim(); break; }
        }

        // 折扣金額
        let disc = '';
        const discSelectors = ['.discount-value', '[class*=saving]', '[class*=discount-amount]'];
        for (const sel of discSelectors) {
            const el = document.querySelector(sel);
            if (el && el.innerText.trim()) { disc = el.innerText.trim(); break; }
        }

        // .Wallet 優惠期間
        const wallet = document.querySelector('.Wallet');
        const walletText = wallet ? wallet.innerText.trim() : '';

        // 圖片
        const imgEl = document.querySelector('.pdp-main img, .product-image img, img[itemprop=image]');
        let img = imgEl ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '') : '';
        if (img && !img.startsWith('http')) img = 'https://www.costco.com.tw' + img;

        // 商品連結（正式的）
        const canonical = document.querySelector('link[rel=canonical]');
        const canonicalHref = canonical ? canonical.getAttribute('href') : window.location.href;

        return {name, orig, disc, walletText, img, canonicalHref};
    }""")

    if not result:
        return None

    orig_price = _parse_num(result.get("orig", ""))
    disc_amt   = _parse_num(result.get("disc", ""))
    sale_price = None
    if orig_price and disc_amt:
        sale_price = orig_price - disc_amt

    period = ""
    wallet_text = result.get("walletText", "")
    if wallet_text:
        m = DATE_RANGE_RE.search(wallet_text)
        if m:
            period = m.group(1).strip()
        elif "優惠期間" in wallet_text:
            period = re.sub(r"[*\s]*(優惠期間|更多|»|>)\s*", " ", wallet_text).strip()
            period = re.sub(r"更多.*$", "", period).strip()

    return {
        "商品名稱_官網":   result.get("name", ""),
        "原價":           orig_price,
        "折扣金額":       disc_amt,
        "折扣後售價":     sale_price,
        "折扣幅度":       (str(round(disc_amt/orig_price*100,1))+"%") if orig_price and disc_amt else None,
        "優惠期間_官網":  period,
        "圖片URL":        result.get("img", ""),
        "商品連結_官網":  result.get("canonicalHref", ""),
    }


def verify_products(products: List[Dict], page) -> List[Dict]:
    """
    對每個商品用商品編號去官網詳情頁驗證。
    只處理：
      1. daybuy/PTT 來源（需要補充圖片和確認價格）
      2. 沒有圖片的官網商品（補充圖片）
    有商品編號才處理，沒有編號的跳過（避免搜到錯誤商品）。
    """
    verified = 0
    skipped  = 0

    for p in products:
        source = p.get("來源", "")
        needs_verify = (
            source in ("daybuy_tg", "ptt_hypermall") or
            not p.get("圖片URL")
        )
        if not needs_verify:
            continue

        item_code = get_item_code(p)
        if not item_code:
            skipped += 1
            continue

        print(f"  🔍 驗證 #{item_code} {p.get('商品名稱','')[:25]}")
        detail = fetch_product_detail(item_code, page)

        if not detail:
            print(f"    ⚠️  官網找不到此商品")
            skipped += 1
            continue

        # 補充圖片（優先）
        if not p.get("圖片URL") and detail.get("圖片URL"):
            p["圖片URL"] = detail["圖片URL"]

        # 補充官網連結（PTT 來源）
        if source == "ptt_hypermall" and detail.get("商品連結_官網"):
            p["商品連結"] = detail["商品連結_官網"]

        # daybuy 原價：daybuy.tw 已有就不覆蓋，但若 daybuy.tw 沒有就補官網的
        if not p.get("原價") and detail.get("原價"):
            p["原價"] = detail["原價"]

        # 折扣金額：社群來源的折扣優先，官網沒折扣才補
        if not p.get("折扣金額") and detail.get("折扣金額"):
            p["折扣金額"] = detail["折扣金額"]

        # 重算
        if p.get("原價") and p.get("折扣金額"):
            p["折扣後售價"] = p["原價"] - p["折扣金額"]
            p["折扣幅度"]   = str(round(p["折扣金額"]/p["原價"]*100,1)) + "%"

        # 優惠期間：官網 .Wallet 最準確
        if detail.get("優惠期間_官網") and not p.get("優惠期間"):
            p["優惠期間"] = detail["優惠期間_官網"]

        # 商品編號確保有存
        if not p.get("商品編號"):
            p["商品編號"] = item_code

        verified += 1
        print(f"    ✅ 原價={p.get('原價')} 折={p.get('折扣金額')} 特={p.get('折扣後售價')} 期間={p.get('優惠期間','')[:20]}")
        time.sleep(0.5)

    print(f"  共驗證 {verified} 筆，跳過（無商品編號）{skipped} 筆")
    return products


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/Users/ericchen/Documents/testthing/costco-deals')
    from playwright.sync_api import sync_playwright

    test_products = [
        {"商品名稱": "CASTROL EDGE 嘉實多極緻5W-30全合成機油", "來源": "daybuy_tg",
         "商品編號": "125482", "原價": 1369, "折扣金額": 300, "圖片URL": "",
         "商品連結": "https://www.daybuy.tw/costco/213783/"},
        {"商品名稱": "Panasonic Eneloop 充電電池", "來源": "ptt_hypermall",
         "商品編號": "", "原價": None, "折扣金額": 200, "圖片URL": "",
         "商品連結": "https://www.pttweb.cc/bbs/hypermall/M.1779184003"},
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="zh-TW")
        page = ctx.new_page()
        page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1)
        try:
            btn = page.query_selector("button:has-text('同意')")
            if btn: btn.click(); time.sleep(1)
        except Exception: pass

        result = verify_products(test_products, page)
        browser.close()

    print("\n=== 驗證結果 ===")
    for p in result:
        print(f"  {p['商品名稱'][:35]}")
        print(f"    原價={p.get('原價')} 折={p.get('折扣金額')} 特={p.get('折扣後售價')}")
        print(f"    期間={p.get('優惠期間')}")
        print(f"    圖片={'✅' if p.get('圖片URL') else '❌'}")
