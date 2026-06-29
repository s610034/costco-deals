#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_verify_prices.py
對 products_master 沒有原價的商品，分批去官網詳情頁補充原價
每次執行補充 BATCH_SIZE 個，避免一次跑太久

執行方式：
  python3 batch_verify_prices.py          # 補充 50 個
  python3 batch_verify_prices.py --size 100  # 補充 100 個
  python3 batch_verify_prices.py --stats     # 只看統計不執行
"""

import sys, os, time, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_conn, init_db

def get_stats():
    conn = get_conn()
    total     = conn.execute("SELECT COUNT(*) FROM products_master").fetchone()[0]
    has_price = conn.execute("SELECT COUNT(*) FROM products_master WHERE 原價 IS NOT NULL AND 原價 > 0").fetchone()[0]
    no_price  = total - has_price
    print(f"products_master 統計：")
    print(f"  總商品：{total}")
    print(f"  有原價：{has_price} ({round(has_price/total*100, 1)}%)")
    print(f"  缺原價：{no_price} ({round(no_price/total*100, 1)}%)")
    conn.close()
    return total, has_price, no_price

def batch_verify(batch_size: int = 50):
    from playwright.sync_api import sync_playwright
    from verify_prices import verify_product_price

    init_db()
    total, has_price, no_price = get_stats()
    if no_price == 0:
        print("✅ 所有商品都已有原價！")
        return

    conn = get_conn()
    # 取沒有原價的商品（優先取有圖片的，代表資料較完整）
    rows = conn.execute("""
        SELECT 商品編號, 商品名稱, 商品連結
        FROM products_master
        WHERE (原價 IS NULL OR 原價 = 0)
          AND 商品編號 != ''
        ORDER BY CASE WHEN 圖片URL != '' THEN 0 ELSE 1 END, 商品編號
        LIMIT ?
    """, (batch_size,)).fetchall()
    conn.close()

    print(f"\n開始補充原價（{len(rows)} 個）...")

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    updated = 0
    not_found = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="zh-TW")
        page = ctx.new_page()
        page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1)
        try:
            btn = page.query_selector("button:has-text('同意')")
            if btn: btn.click(); time.sleep(1)
        except Exception:
            pass

        conn = get_conn()
        for i, (code, name, link) in enumerate(rows):
            result = verify_product_price(code, page)
            if result and result.get("原價"):
                conn.execute("""
                    UPDATE products_master SET
                        原價 = ?, 折扣金額 = ?, 折扣後售價 = ?, 最後更新 = datetime('now')
                    WHERE 商品編號 = ?
                """, (result["原價"], result["折扣金額"], result["折扣後售價"], code))
                if (i + 1) % 10 == 0:
                    conn.commit()
                updated += 1
                disc_str = f" 折={result['折扣金額']}" if result.get("折扣金額") else ""
                print(f"  [{i+1}/{len(rows)}] #{code} ${result['原價']}{disc_str} {name[:30]}")
            else:
                not_found += 1
                if (i + 1) % 10 == 0:
                    print(f"  [{i+1}/{len(rows)}] （進行中，{updated}個成功）")
            time.sleep(0.3)

        conn.commit()
        conn.close()
        browser.close()

    print(f"\n✅ 完成：補充 {updated} 個，找不到 {not_found} 個")
    get_stats()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size",  type=int, default=50, help="每次補充幾個（預設 50）")
    parser.add_argument("--stats", action="store_true", help="只看統計")
    args = parser.parse_args()

    try:
        if args.stats:
            get_stats()
        else:
            batch_verify(args.size)
    except Exception as _fatal_err:
        import traceback
        print(f"❌ 補原價未預期崩潰：{_fatal_err}")
        traceback.print_exc()
        sys.exit(1)
