#!/usr/bin/env python3
import os, sys, json, datetime, urllib.request, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, '.env')) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        if k.strip() and v.strip():
            os.environ[k.strip()] = v.strip()

from database import init_db, enrich_with_history, get_summary_stats, update_product_category
from generate_html import generate_html
from deploy import deploy
from notify import tg_send
from formatter import format_summary

init_db()

TOKEN = os.environ.get('GITHUB_TOKEN', '')

def sync_overrides_from_github():
    if not TOKEN:
        print("  ⚠️  GITHUB_TOKEN 未設定，跳過 overrides 同步")
        return 0
    url = "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        content = json.loads(base64.b64decode(data["content"].replace("\n", "")).decode())
        count = 0
        for card_id, info in content.items():
            if isinstance(info, dict):
                cat  = info.get("cat", "")
                name = info.get("name", "")
                link = info.get("link", "")
            else:
                cat, name, link = str(info), "", ""
            if cat:
                update_product_category(card_id, cat, name, link)
                count += 1
        print(f"  ✅ 從 GitHub 同步 {count} 筆分類覆蓋到 DB")
        return count
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("  ℹ️  overrides.json 尚未建立")
        else:
            print(f"  ⚠️  GitHub API 錯誤：{e.code}")
        return 0
    except Exception as e:
        print(f"  ⚠️  overrides 同步失敗：{e}")
        return 0

def get_products_last_30_days():
    """
    從 DB 撈最近30天內出現過的所有商品。
    同一商品（依商品連結判斷）只保留最新一次的資料，
    但 crawl_date 紀錄為最新出現日期。
    """
    import sqlite3
    db_path = os.path.join(BASE_DIR, 'data', 'costco_history.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y%m%d')

    # 取得最近30天內出現過的商品連結（取最新那筆，只保留有折扣的）
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
        ORDER BY p.折扣金額 DESC NULLS LAST
    """, (cutoff,)).fetchall()
    conn.close()

    products = []
    for row in rows:
        p = dict(row)
        products.append({
            '商品名稱':    p.get('商品名稱', ''),
            '分類':       p.get('分類', ''),
            '細分類':     p.get('細分類', ''),
            '原價':       p.get('原價'),
            '折扣金額':   p.get('折扣金額'),
            '折扣幅度':   p.get('折扣幅度', ''),
            '折扣後售價': p.get('折扣後售價'),
            '優惠期間':   p.get('優惠期間', ''),
            '實體賣場':   bool(p.get('實體賣場', 0)),
            '圖片URL':    p.get('圖片URL', ''),
            '商品連結':   p.get('商品連結', ''),
            '抓取時間':   p.get('抓取時間', ''),
            '討論連結':   '',
            '來源':       '',
        })

    # 商品ID去重（同一商品可能有完整URL和短URL兩條）
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


print("\n【Step 0】同步前端分類覆蓋...")
sync_overrides_from_github()

print("\n【Step 1】從 DB 撈取最近30天商品...")
products = get_products_last_30_days()

if not products:
    # fallback：讀最新 JSON
    print("  DB 無資料，改讀最新 JSON...")
    files = sorted([f for f in os.listdir(os.path.join(BASE_DIR, 'data'))
                    if f.startswith('costco_deals_') and f.endswith('.json')])
    if not files:
        print("❌ 找不到任何資料"); sys.exit(1)
    with open(os.path.join(BASE_DIR, 'data', files[-1])) as f:
        products = json.load(f)

today = datetime.datetime.now().strftime('%Y%m%d')
print(f"\n【Step 2】附加歷史資訊...")
products = enrich_with_history(products, today)
stats = get_summary_stats(today)

print(f"\n【Step 3】產生 HTML...")
html_path = os.path.join(BASE_DIR, 'docs', 'index.html')
generate_html(products, html_path)

print(f"\n【Step 4】部署到 GitHub Pages...")
deploy()

report_url = 'https://s610034.github.io/costco-deals/'
summary = format_summary(products, stats)
msg = summary + f"\n\n📱 完整折扣清單：\n{report_url}"
tg_send(msg)
print("  ✅ Telegram 已發送")

print('\n✅ 完成！')
