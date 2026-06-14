#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
costco_search.py
用官網搜尋補充社群來源商品的圖片、原價、折扣金額、正確連結

流程：
  1. 輸入商品名稱（來自 daybuy / PTT）
  2. 去 https://www.costco.com.tw/search?q=商品名稱 搜尋
  3. 取第一筆結果的圖片、原價、折扣、連結
  4. 回傳補充資料
"""

import re, time
from typing import Optional, Dict, List

BASE_URL = "https://www.costco.com.tw"
SEARCH_URL = BASE_URL + "/search?q={}"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def _parse_price(text: str) -> Optional[int]:
    """從價格文字萃取數字"""
    if not text:
        return None
    d = re.sub(r"[^\d]", "", text)
    return int(d) if d else None


def search_costco_product(query: str, page, base_url: str = BASE_URL) -> Optional[Dict]:
    """
    在已開啟的 Playwright page 上搜尋商品
    回傳第一筆結果的補充資料，或 None（找不到）
    """
    search_url = SEARCH_URL.format(query.replace(" ", "+"))

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)  # 等 Angular SPA 渲染
    except Exception:
        return None

    result = page.evaluate("""() => {
        const cards = document.querySelectorAll('.product-list-item');
        if (!cards.length) return null;

        const card = cards[0];

        // 商品名
        let name = '';
        const nameEl = card.querySelector('.lister-name .notranslate, .lister-name');
        if (nameEl) {
            name = nameEl.innerText?.trim() || '';
        }
        if (!name) {
            const titleEl = card.querySelector('a[title]');
            if (titleEl) name = titleEl.getAttribute('title') || '';
        }

        // 連結
        const linkEl = card.querySelector('a.lister-name, a.thumb, a[href*="/p/"]');
        let href = linkEl ? linkEl.getAttribute('href') : '';
        if (href && !href.startsWith('http')) href = 'https://www.costco.com.tw' + href;

        // 圖片
        const imgEl = card.querySelector('img');
        let img = '';
        if (imgEl) {
            img = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
            if (img && !img.startsWith('http')) img = 'https://www.costco.com.tw' + img;
        }

        // 原價（與 scraper.py 相同的 selector）
        const origEl = card.querySelector('.original-price .product-price-amount, .product-price-amount');
        const orig = origEl ? origEl.innerText?.trim() : '';

        // 折扣金額
        const discEl = card.querySelector('.discount-value, .lister-savings, [class*="saving"]');
        const disc = discEl ? discEl.innerText?.trim() : '';

        return {name, href, img, orig, disc};
    }""")

    if not result or not result.get("href"):
        return None

    # 驗證搜尋結果是否與查詢相關（避免搜到不相關商品）
    result_name = result.get("name", "").lower()
    query_words = [w for w in query.lower().split() if len(w) >= 2]
    if query_words:
        match_count = sum(1 for w in query_words if w in result_name)
        if match_count == 0:
            # 完全沒有關鍵字重疊，嘗試第二筆
            result2 = page.evaluate("""() => {
                const cards = document.querySelectorAll('.product-list-item');
                if (cards.length < 2) return null;
                const card = cards[1];
                const nameEl = card.querySelector('.lister-name .notranslate, a[title]');
                const name = nameEl ? (nameEl.innerText || nameEl.getAttribute('title') || '') : '';
                const linkEl = card.querySelector('a.lister-name, a.thumb, a[href*="/p/"]');
                let href = linkEl ? linkEl.getAttribute('href') : '';
                if (href && !href.startsWith('http')) href = 'https://www.costco.com.tw' + href;
                const imgEl = card.querySelector('img');
                let img = imgEl ? (imgEl.getAttribute('src') || '') : '';
                if (img && !img.startsWith('http')) img = 'https://www.costco.com.tw' + img;
                return {name, href, img, orig: '', disc: ''};
            }""")
            if result2 and result2.get("href"):
                result = result2

    orig_price = _parse_price(result.get("orig", ""))
    disc_amt   = _parse_price(result.get("disc", ""))
    sale_price = None
    if orig_price and disc_amt:
        sale_price = orig_price - disc_amt

    return {
        "商品名稱_官網": result.get("name", ""),
        "圖片URL":      result.get("img", ""),
        "商品連結":     result.get("href", ""),
        "原價":         orig_price,
        "折扣金額":     disc_amt,
        "折扣後售價":   sale_price,
        "折扣幅度":     (str(round(disc_amt / orig_price * 100, 1)) + "%"
                        if orig_price and disc_amt else None),
    }


def enrich_from_costco(products: List[Dict], page,
                        sources: tuple = ("daybuy_tg", "ptt_hypermall")) -> List[Dict]:
    """
    針對社群來源商品，去官網搜尋補充資料
    sources: 要補充的來源，預設 daybuy 和 PTT
    """
    enriched = 0
    for p in products:
        # 只處理指定來源，且沒有圖片或沒有折扣金額的
        if p.get("來源") not in sources:
            continue
        needs_img   = not p.get("圖片URL")
        needs_disc  = not p.get("折扣金額")
        # 官網搜尋作為最終驗證來源：
        # - 圖片：沒有才補
        # - 原價：官網結果優先（覆蓋 daybuy.tw 的原價，官網更準確）
        # - 只有圖片和折扣都已有，且不是 daybuy/PTT 來源，才跳過
        source = p.get("來源", "")
        is_social = source in ("daybuy_tg", "ptt_hypermall")
        # daybuy 已有圖片就完全跳過（原價和折扣由 daybuy.tw 提供）
        if source == "daybuy_tg" and not needs_img:
            continue
        # PTT 或官網商品：沒有圖片和原價才補
        if source != "daybuy_tg" and not needs_img and not p.get("原價"):
            continue
            continue

        name = p.get("商品名稱", "")
        if not name:
            continue

        # 優先用商品編號搜尋（最精準），否則用商品名稱
        import re as _re
        item_code = p.get("商品編號", "")
        if item_code:
            query = item_code
        else:
            clean = _re.sub(r"[^\w\s\u4e00-\u9fff&+\-]", " ", name)
            clean = _re.sub(r"\s+", " ", clean).strip()
            for noise in ["入", "公克", "毫升", "公升", "片", "顆", "粒", "份", "大牌"]:
                clean = clean.replace(noise, "")
            query = clean[:25].strip()
        print(f"  🔍 搜尋補充：{query[:30]}")

        result = search_costco_product(query, page)

        if result and result.get("商品連結"):
            # 補充圖片
            if needs_img and result.get("圖片URL"):
                p["圖片URL"] = result["圖片URL"]

            # 原價：daybuy.tw 已有就不覆蓋，沒有才補官網的
            if result.get("原價") and not p.get("原價"):
                p["原價"] = result["原價"]
            # 折扣：官網有的話補上，社群來源自己的折扣保留
            if result.get("折扣金額") and not p.get("折扣金額"):
                p["折扣金額"] = result["折扣金額"]
            # 重算折扣後售價和幅度
            if p.get("原價") and p.get("折扣金額"):
                pct = round(p["折扣金額"] / p["原價"] * 100, 1)
                p["折扣幅度"] = str(pct) + "%"
                p["折扣後售價"] = p["原價"] - p["折扣金額"]

            # PTT 商品用官網連結取代（PTT 連結點進去是討論文）
            # daybuy 商品保留 daybuy.tw 連結（daybuy 頁面有完整商品資訊）
            if result.get("商品連結") and "/p/" in result["商品連結"]:
                p["商品連結_官網"] = result["商品連結"]
                if "pttweb" in p.get("商品連結", ""):
                    p["商品連結"] = result["商品連結"]
                # daybuy 連結保留不覆蓋

            enriched += 1
            print(f"    ✅ 補充完成：原價(結果)={p.get('原價')} 折={p.get('折扣金額')} 特={p.get('折扣後售價')} 圖片={'有' if p.get('圖片URL') else '無'}")
        else:
            print(f"    ⚠️  找不到對應商品")

        time.sleep(0.5)

    print(f"  共補充 {enriched} 筆社群商品的官網資料")
    return products


if __name__ == "__main__":
    # 獨立測試
    import sys
    sys.path.insert(0, "/Users/ericchen/Documents/testthing/costco-deals")
    from playwright.sync_api import sync_playwright

    test_products = [
        {"商品名稱": "Panasonic Eneloop 3、4號充電電池 10入", "來源": "ptt_hypermall",
         "圖片URL": "", "原價": None, "折扣金額": 200, "商品連結": "https://pttweb.cc/xxx"},
        {"商品名稱": "鐵鎚牌 多功能小蘇打粉", "來源": "daybuy_tg",
         "圖片URL": "", "原價": None, "折扣金額": 64, "商品連結": "https://daybuy.tw/xxx"},
        {"商品名稱": "COLEMAN 摺疊露營椅", "來源": "daybuy_tg",
         "圖片URL": "", "原價": None, "折扣金額": 400, "商品連結": "https://daybuy.tw/xxx"},
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="zh-TW")
        page = ctx.new_page()

        # 先接受 cookie
        page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1)
        try:
            btn = page.query_selector("button:has-text('同意')")
            if btn:
                btn.click()
                time.sleep(1)
        except Exception:
            pass

        result = enrich_from_costco(test_products, page)
        browser.close()

    print("\n=== 補充結果 ===")
    for p in result:
        print(f"  {p['商品名稱'][:35]}")
        print(f"    圖片: {'✅' if p.get('圖片URL') else '❌'} {p.get('圖片URL','')[:50]}")
        print(f"    原價: {p.get('原價')}  折扣: {p.get('折扣金額')}  連結: {p.get('商品連結','')[:50]}")
