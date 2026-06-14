#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_costco.py
好市多折扣週報 — 主執行腳本
流程：爬取 → daybuy/PTT 補充 → 存 DB → 30天合併 → 產生 HTML → 部署 → 推播
"""

import os, sys, datetime, json, base64, urllib.request
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and v and k not in os.environ:
                os.environ[k] = v

load_env()

from scraper        import scrape_all, save_json
from formatter      import format_summary
from generate_html  import generate_html
from deploy         import deploy
from notify         import tg_send
from database       import init_db, upsert_products, enrich_with_history, get_summary_stats, update_product_category

DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
PAGE_URL = "https://s610034.github.io/costco-deals/"
TOKEN    = os.environ.get("GITHUB_TOKEN", "")


def sync_overrides_from_github():
    """從 GitHub overrides.json 同步分類覆蓋到本機 DB"""
    if not TOKEN:
        return 0
    url = "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        content = json.loads(base64.b64decode(data["content"].replace("\n", "")).decode("utf-8"))
        count = 0
        for card_id, info in content.items():
            cat  = info.get("cat", "") if isinstance(info, dict) else str(info)
            name = info.get("name", "") if isinstance(info, dict) else ""
            link = info.get("link", "") if isinstance(info, dict) else ""
            if cat:
                update_product_category(card_id, cat, name, link)
                count += 1
        print(f"  ✅ overrides 同步 {count} 筆到 DB")
        return count
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  ⚠️  GitHub API {e.code}")
        return 0
    except Exception as e:
        print(f"  ⚠️  overrides 同步失敗：{e}")
        return 0


def get_products_last_30_days():
    """從 DB 撈最近30天內的商品，同一商品只取最新一筆，去重合併"""
    import sqlite3
    db_path = os.path.join(DATA_DIR, "costco_history.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y%m%d")
    rows = conn.execute("""
        SELECT p.*
        FROM products p
        INNER JOIN (
            SELECT 商品連結, MAX(crawl_date) as max_date
            FROM products
            WHERE crawl_date >= ?
              AND 商品連結 != ''
              AND 商品名稱 != ''
              AND (折扣金額 IS NOT NULL OR 折扣後售價 IS NOT NULL)
            GROUP BY 商品連結
        ) latest ON p.商品連結 = latest.商品連結
                    AND p.crawl_date = latest.max_date
        WHERE p.折扣金額 IS NOT NULL OR p.折扣後售價 IS NOT NULL
        ORDER BY p.折扣金額 DESC
    """, (cutoff,)).fetchall()
    conn.close()

    products = []
    for row in rows:
        p = dict(row)
        products.append({
            "商品名稱":    p.get("商品名稱", ""),
            "分類":       p.get("分類", ""),
            "細分類":     p.get("細分類", ""),
            "原價":       p.get("原價"),
            "折扣金額":   p.get("折扣金額"),
            "折扣幅度":   p.get("折扣幅度", ""),
            "折扣後售價": p.get("折扣後售價"),
            "優惠期間":   p.get("優惠期間", ""),
            "實體賣場":   bool(p.get("實體賣場", 0)),
            "圖片URL":    p.get("圖片URL", ""),
            "商品連結":   p.get("商品連結", ""),
            "抓取時間":   p.get("抓取時間", ""),
            "討論連結":   "",
            "來源":       "",
            "商品編號":   p.get("商品編號", "") or "",
        })
    import re as _re
    seen = {}
    for p in products:
        link = p.get("商品連結", "")
        code = p.get("商品編號", "")
        name = p.get("商品名稱", "")
        # 去重鍵優先順序：商品編號 > URL的/p/數字 > 完整連結末段 > 名稱前12字
        if code:
            pid = "code_" + code
        else:
            m = _re.search(r"/p/(\d+)", link)
            if m:
                pid = "p_" + m.group(1)
            elif "costco.com.tw" in link:
                parts = [x for x in link.rstrip("/").split("/") if x]
                pid = "url_" + parts[-1] if parts else link
            else:
                pid = "name_" + name[:12]

        if pid not in seen:
            seen[pid] = p
        else:
            old_p = seen[pid]
            # 保留資料較完整的：有官網連結 > 有原價 > 有折扣幅度
            new_score = sum([
                bool(p.get("原價")),
                bool(p.get("折扣幅度")),
                "costco.com.tw" in link and "/p/" in link,
                bool(code),
            ])
            old_score = sum([
                bool(old_p.get("原價")),
                bool(old_p.get("折扣幅度")),
                "costco.com.tw" in old_p.get("商品連結","") and "/p/" in old_p.get("商品連結",""),
                bool(old_p.get("商品編號")),
            ])
            if new_score > old_score:
                seen[pid] = p
    products = list(seen.values())
    print(f"  📦 DB 30天合併：{len(products)} 筆（去重後）")
    return products


def run():
    start = datetime.datetime.now()
    today = start.strftime("%Y%m%d")
    print(f"\n{'='*52}")
    print(f"🛒 好市多折扣週報啟動  {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*52}\n")

    # Step 0：初始化 DB + 同步 overrides
    print("【Step 0】初始化...")
    init_db()
    print("  同步前端分類覆蓋...")
    sync_overrides_from_github()

    # Step 1：爬取官網
    print("\n【Step 1】爬取好市多折扣頁面...")
    try:
        new_products = scrape_all()
    except Exception as e:
        print(f"❌ 爬取失敗：{e}")
        tg_send(f"⚠️ 好市多折扣週報失敗\n爬取錯誤：{e}")
        return False

    if not new_products:
        tg_send("⚠️ 好市多折扣週報：本週未抓到折扣商品")
        return False

    print(f"  ✅ 官網抓到 {len(new_products)} 筆")

    # Step 1.5：daybuy 補充
    print("\n【Step 1.5】daybuy 補充...")
    try:
        from daybuy_monitor import fetch_daybuy_channel, merge_with_official
        daybuy_products = fetch_daybuy_channel(days_back=7)
        new_products = merge_with_official(new_products, daybuy_products)
    except Exception as e:
        print(f"  ⚠️  daybuy 失敗（繼續）：{e}")

    # Step 1.6：PTT 補充
    print("\n【Step 1.6】PTT 補充...")
    try:
        from ptt_monitor import fetch_ptt_costco, merge_ptt_with_existing
        ptt_products = fetch_ptt_costco(pages=3, fetch_content=True)
        new_products = merge_ptt_with_existing(new_products, ptt_products)
    except Exception as e:
        print(f"  ⚠️  PTT 失敗（繼續）：{e}")

    # Step 1.7：用商品編號去官網詳情頁驗證正確價格
    print(f"\n【Step 1.7】官網詳情頁驗證價格...")
    try:
        from verify_prices import verify_all_products
        from playwright.sync_api import sync_playwright as _spw
        import time as _time

        # 找有商品編號的商品
        need_verify = [p for p in new_products if p.get("商品編號")]
        if need_verify:
            print(f"  需要驗證：{len(need_verify)} 筆（有商品編號）")
            with _spw() as _pw:
                _browser = _pw.chromium.launch(headless=True)
                _ctx = _browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    locale="zh-TW"
                )
                _page = _ctx.new_page()
                _page.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
                _time.sleep(1)
                try:
                    _btn = _page.query_selector("button:has-text('同意')")
                    if _btn: _btn.click(); _time.sleep(1)
                except Exception:
                    pass
                new_products = verify_all_products(new_products, _page)
                _browser.close()
        else:
            print("  無商品編號可驗證，跳過")
    except Exception as e:
        print(f"  ⚠️  價格驗證失敗（繼續）：{e}")

    # Step 1.8：daybuy 賣場目擊情報
    # 用途：補充現有商品的「限定門市」標記，並找出有折扣的賣場限定商品
    print(f"\n【Step 1.8】daybuy 賣場目擊情報...")
    try:
        from sighting_monitor import fetch_sighting_products
        sighting_products = fetch_sighting_products(days_back=7)

        # 建立商品編號 → 目擊資料的對照表
        sighting_map = {sp["商品編號"]: sp for sp in sighting_products if sp.get("商品編號")}

        added = 0
        enriched = 0
        for p in new_products:
            code = p.get("商品編號", "")
            if not code or code not in sighting_map:
                continue
            sp = sighting_map[code]
            # 補充限定門市標記
            if sp.get("限定門市") and not p.get("限定門市"):
                p["限定門市"] = sp["限定門市"]
                enriched += 1
            # 補充折扣（如果目擊情報有更即時的折扣）
            if sp.get("折扣金額") and not p.get("折扣金額"):
                p["折扣金額"] = sp["折扣金額"]

        # 找出目擊情報裡有折扣但主清單沒有的商品（賣場獨家折扣）
        existing_codes = {p.get("商品編號", "") for p in new_products}
        for sp in sighting_products:
            code = sp.get("商品編號", "")
            if not code or code in existing_codes:
                continue
            if sp.get("折扣金額") or sp.get("限定門市"):
                # 賣場有折扣或限定門市的，加進來
                new_products.append(sp)
                existing_codes.add(code)
                added += 1

        print(f"  ✅ 補充限定門市：{enriched} 筆，新增賣場折扣：{added} 筆")
    except Exception as e:
        print(f"  ⚠️  賣場目擊情報失敗（繼續）：{e}")

    # Step 2：存 DB + JSON
    print(f"\n【Step 2】儲存資料...")
    try:
        save_json(new_products, DATA_DIR)
    except Exception as e:
        print(f"  ⚠️  JSON 儲存失敗：{e}")
    inserted = upsert_products(new_products, today)
    stats = get_summary_stats(today)
    print(f"  📊 本次 {stats['total']} 筆（新品 {stats['new']} / 重複 {stats['repeat']}）")

    # 同步寫入 products_master（永久商品資料庫）
    from database import upsert_master, get_master_count
    master_cnt = upsert_master(new_products, source="scraper")
    print(f"  📦 商品主資料庫：共 {get_master_count()} 個商品")

    # Step 3：30天合併 + 附加歷史
    print(f"\n【Step 3】30天合併...")
    products_30d = get_products_last_30_days()
    if not products_30d:
        products_30d = new_products  # fallback
    products_30d = enrich_with_history(products_30d, today)

    # Step 4：產生 HTML
    print(f"\n【Step 4】產生 HTML 報告...")
    html_path = os.path.join(DOCS_DIR, "index.html")
    try:
        generate_html(products_30d, html_path)
    except Exception as e:
        print(f"❌ HTML 產生失敗：{e}")
        tg_send(f"⚠️ 好市多折扣週報 HTML 產生失敗：{e}")
        return False

    # Step 5：部署
    print(f"\n【Step 5】部署到 GitHub Pages...")
    deployed = deploy()

    # Step 6：Telegram 推播
    print(f"\n【Step 6】推播 Telegram...")
    summary = format_summary(new_products)
    msg = summary + f"\n\n📱 完整折扣清單：\n{PAGE_URL}"
    if not deployed:
        msg += "\n\n⚠️ 部署失敗，連結稍後更新"
    tg_send(msg)
    print("  ✅ Telegram 已發送")

    elapsed = (datetime.datetime.now() - start).seconds
    print(f"\n{'='*52}")
    print(f"✅ 完成！顯示 {len(products_30d)} 項（30天合併），本次新抓 {len(new_products)} 項，耗時 {elapsed} 秒")
    print(f"🌐 {PAGE_URL}")
    print(f"{'='*52}\n")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
