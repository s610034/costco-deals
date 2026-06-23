#!/usr/bin/env python3
"""
verify_prices.py
用商品編號去官網詳情頁驗證原價，同時補充 .Wallet 優惠期間
只處理有商品編號的商品（官網/daybuy 都有）
"""

import re
import time
import datetime
from typing import Dict, List, Optional

BASE_URL = "https://www.costco.com.tw"


def verify_product_price(item_code: str, page) -> Optional[Dict]:
    """
    去官網 /p/{item_code} 抓取正確的原價、折扣、優惠期間
    """
    url = f"{BASE_URL}/p/{item_code}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except Exception:
        return None

    result = page.evaluate("""() => {
        // 從 product-price-detail 區塊抓（這是詳情頁的標準一般會員價格區塊）
        const detailBlock = document.querySelector('.product-price-detail, .price-with-discount');
        let origPrice = '', disc = '', sale = '';

        if (detailBlock) {
            const origEl = detailBlock.querySelector('.price-original .product-price-amount, .price-value');
            const discEl = detailBlock.querySelector('.discount-value, .discount .product-price-amount');
            const saleEl = detailBlock.querySelector('.price-after-discount .product-price-amount');
            origPrice = origEl ? origEl.innerText.trim() : '';
            disc      = discEl ? discEl.innerText.trim() : '';
            sale      = saleEl ? saleEl.innerText.trim() : '';
        }

        // fallback：直接抓 .price-value（第一個）
        if (!origPrice) {
            const pvEl = document.querySelector('.price-value');
            if (pvEl) origPrice = pvEl.innerText.trim();
        }
        // fallback：.discount-value（第一個）
        if (!disc) {
            const dvEl = document.querySelector('.discount-value');
            if (dvEl) disc = dvEl.innerText.trim();
        }

        // .Wallet 優惠期間
        const w = document.querySelector('.Wallet');
        const walletText = w ? w.innerText.trim() : '';
        const actualUrl = window.location.href;

        // 商品圖片：找第一個夠大的 medias 圖
        let imgUrl = '';
        for (const img of document.querySelectorAll('img')) {
            if (img.src && img.src.includes('medias') && img.naturalWidth > 200) {
                imgUrl = img.src;
                break;
            }
        }

        return {origPrice, disc, sale, walletText, actualUrl, imgUrl};
    }""")

    if not result or result.get("actualUrl", "").endswith("/404"):
        return None

    # 解析數字
    def parse_num(text):
        if not text:
            return None
        d = re.sub(r"[^\d]", "", str(text))
        return int(d) if d else None

    orig = parse_num(result.get("origPrice", ""))
    disc = parse_num(result.get("disc", ""))
    sale = parse_num(result.get("sale", ""))

    if orig and disc and not sale:
        sale = orig - disc
    if orig and sale and not disc:
        disc = orig - sale

    # 優惠期間
    wallet_text = result.get("walletText", "")
    period = ""
    if wallet_text and "優惠期間" in wallet_text:
        m = re.search(r"(\d{4}/\d{2}/\d{2}[^\d]+\d{4}/\d{2}/\d{2})", wallet_text)
        if m:
            period = m.group(1)
        else:
            period = re.sub(r"[*\s]*(優惠期間|更多|»|>)\s*", " ", wallet_text).strip()
            period = re.sub(r"更多.*$", "", period).strip()

    return {
        "原價":     orig,
        "折扣金額": disc,
        "折扣後售價": sale,
        "折扣幅度": f"{round(disc/orig*100, 1)}%" if orig and disc else None,
        "優惠期間_官網": period,
        "官網連結": f"{BASE_URL}/p/{item_code}",
        "圖片URL":  result.get("imgUrl", ""),
    }


def verify_all_products(products: List[Dict], page, max_verify: int = 30) -> List[Dict]:
    """
    對商品去官網詳情頁驗證價格。
    已在 DB 有正確原價的直接套用，不重複進詳情頁（節省時間）。
    只對沒有原價、或 DB 沒有記錄的才去詳情頁驗證。
    """
    import sqlite3, os
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "costco_history.db")

    # 從 DB 讀已驗證過的原價
    verified_codes = {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT 商品編號, MAX(原價) as orig FROM products WHERE 商品編號 != '' AND 原價 IS NOT NULL GROUP BY 商品編號"
        ).fetchall()
        verified_codes = {r[0]: r[1] for r in rows}
        conn.close()
    except Exception:
        pass

    verified = 0
    skipped = 0

    for p in products:
        code = p.get("商品編號", "")
        if not code:
            skipped += 1
            continue

        # 社群來源（daybuy/PTT）：一定要去官網確認折扣，不能只用 DB 快取
        source = p.get("來源", "")
        is_social = source in ("daybuy_tg", "ptt_hypermall", "daybuy_sighting")

        # 官網直接爬的商品：DB 有原價就套用，不重複進官網
        if code in verified_codes and not is_social:
            db_orig = verified_codes[code]
            if db_orig and db_orig != p.get("原價"):
                p["原價"] = db_orig
                disc = p.get("折扣金額")
                if disc and db_orig:
                    p["折扣後售價"] = db_orig - disc
                    p["折扣幅度"] = str(round(disc/db_orig*100, 1)) + "%"
            skipped += 1
            continue

        # DB 沒有，去詳情頁驗證
        if verified >= max_verify:
            skipped += 1
            continue

        result = verify_product_price(code, page)
        if not result:
            skipped += 1
            continue

        # 更新原價（以官網詳情頁為準）
        if result.get("原價"):
            p["原價"] = result["原價"]
        if result.get("折扣金額"):
            p["折扣金額"] = result["折扣金額"]
        if result.get("折扣後售價"):
            p["折扣後售價"] = result["折扣後售價"]
        if result.get("折扣幅度"):
            p["折扣幅度"] = result["折扣幅度"]

        # 優惠期間（詳情頁有就用，沒有保留原本的）
        if result.get("優惠期間_官網") and not p.get("優惠期間"):
            p["優惠期間"] = result["優惠期間_官網"]

        # 保留官網連結（和 daybuy 連結並存）
        official_url = result.get("官網連結", "")
        current_link = p.get("商品連結", "")
        if official_url and official_url != current_link:
            p["官網連結"] = official_url
            # 如果原本是 daybuy/PTT，保留原連結，官網另存
            if "daybuy.tw" in current_link or "pttweb" in current_link:
                p["討論連結"] = current_link  # daybuy 連結
                p["商品連結"] = official_url   # 主連結改成官網
            # 如果原本已是官網但路徑較短，更新為正確路徑不變（/p/編號 就夠了）

        verified += 1
        print(f"  ✅ #{code} {p['商品名稱'][:30].ljust(30)} 原={result['原價']} 折={result['折扣金額']}")
        time.sleep(0.5)

    print(f"  驗證 {verified} 筆，跳過 {skipped} 筆")
    return products


if __name__ == "__main__":
    # 測試單一商品
    import sys
    sys.path.insert(0, '/Users/ericchen/Documents/testthing/costco-deals')
    from playwright.sync_api import sync_playwright

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="zh-TW")
        page = ctx.new_page()
        page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1)
        try:
            btn = page.query_selector("button:has-text('同意')")
            if btn: btn.click(); time.sleep(1)
        except Exception: pass

        test_codes = ["247284", "125482", "488431", "158560"]
        for code in test_codes:
            print(f"\n=== #{code} ===")
            r = verify_product_price(code, page)
            if r:
                print(f"  原價: {r['原價']}  折扣: {r['折扣金額']}  特價: {r['折扣後售價']}")
                print(f"  期間: {r['優惠期間_官網']}")
                print(f"  URL: {r['官網連結']}")
            else:
                print("  找不到")

        browser.close()
