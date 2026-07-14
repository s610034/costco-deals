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
from notify import tg_send, line_send
from formatter import format_summary

init_db()

TOKEN = os.environ.get('GITHUB_TOKEN', '')

def sync_overrides_to_github():
    """把本機 DB 的分類覆蓋推送到 GitHub overrides.json"""
    if not TOKEN:
        return 0
    try:
        import sqlite3 as _sq
        conn = _sq.connect(os.path.join(BASE_DIR, "data", "costco_history.db"))
        rows = conn.execute("SELECT card_id, 商品名稱, 商品連結, 細分類, updated_at FROM category_overrides").fetchall()
        conn.close()
        overrides = {r[0]: {"name": r[1], "link": r[2], "cat": r[3], "updated": r[4]} for r in rows}

        content_b64 = base64.b64encode(json.dumps(overrides, ensure_ascii=False, indent=2).encode()).decode()
        url = "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json"

        # 取得現有 sha
        sha = None
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                sha = json.loads(r.read()).get("sha")
        except Exception:
            pass

        body = {"message": f"sync: overrides {len(overrides)} 筆", "content": content_b64}
        if sha:
            body["sha"] = sha
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
            headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json", "Accept": "application/vnd.github.v3+json"},
            method="PUT")
        with urllib.request.urlopen(req, timeout=15) as r:
            json.loads(r.read())
        print(f"  ✅ overrides 推送 GitHub：{len(overrides)} 筆")
        return len(overrides)
    except Exception as e:
        print(f"  ⚠️  overrides 推送失敗：{e}")
        return 0

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
        content = json.loads(base64.b64decode(data["content"].replace("\n", "")).decode("utf-8"))
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

    # 取得最新一次爬取的所有有折扣商品
    # 找最新的 crawl_date
    latest_date = conn.execute(
        "SELECT MAX(crawl_date) FROM products WHERE 折扣金額 IS NOT NULL OR 折扣後售價 IS NOT NULL"
    ).fetchone()[0]

    rows = conn.execute("""
        SELECT p.*
        FROM products p
        INNER JOIN (
            SELECT
                CASE WHEN 商品編號 != '' AND 商品編號 IS NOT NULL
                     THEN 商品編號
                     ELSE 商品連結 END as group_key,
                MAX(CASE WHEN 商品連結 LIKE '%costco.com.tw%/p/%' THEN 1 ELSE 0 END) as has_official
            FROM products
            WHERE crawl_date = ?
              AND 商品連結 != ''
              AND 商品名稱 != ''
              AND (折扣金額 IS NOT NULL OR 折扣後售價 IS NOT NULL)
            GROUP BY group_key
        ) latest ON (
            CASE WHEN p.商品編號 != '' AND p.商品編號 IS NOT NULL
                 THEN p.商品編號
                 ELSE p.商品連結 END = latest.group_key
        ) AND p.crawl_date = ?
          AND (latest.has_official = 0
               OR p.商品連結 LIKE '%costco.com.tw%/p/%')
        WHERE (p.折扣金額 IS NOT NULL OR p.折扣後售價 IS NOT NULL)

        UNION ALL

        -- 賣場隱藏優惠：人工confirm的暫時性資料，不受「當天」限制，
        -- 只要還在優惠期間內就持續顯示（每個商品編號取最新一筆）
        SELECT p.*
        FROM products p
        WHERE p.資料來源 = 'hidden_sighting'
          AND p.id IN (
              SELECT MAX(id) FROM products
              WHERE 資料來源 = 'hidden_sighting'
              GROUP BY 商品編號
          )
          AND (
              -- 優惠期間結束日期還沒過（嘗試解析 ~MM/DD 結尾），解析失敗則保留7天
              CAST(strftime('%Y%m%d', 'now', 'localtime') AS INTEGER) <=
              CAST(crawl_date AS INTEGER) + 14
          )

        ORDER BY 折扣金額 DESC NULLS LAST
    """, (latest_date, latest_date)).fetchall()

    # 去重：如果 UNION 後同一商品編號重複（今日資料+隱藏優惠都有），保留今日版本
    seen_codes = set()
    deduped = []
    for r in rows:
        code = r["商品編號"] if r["商品編號"] else r["商品連結"]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        deduped.append(r)
    rows = deduped
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
            '討論連結':   p.get('討論連結', '') or '',
            '官網連結':   p.get('官網連結', '') or '',
            '期間來源':   p.get('期間來源', '') or '',
            '商品編號':   p.get('商品編號', '') or '',
            '資料來源':   p.get('資料來源', '') or '',
            'crawl_date': p.get('crawl_date', '') or '',
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
                # 切換到新的，但繼承舊的 討論連結（如果新的沒有）
                if not p.get("討論連結") and old_p.get("討論連結"):
                    p["討論連結"] = old_p["討論連結"]
                seen[pid] = p
            else:
                # 保留舊的，但繼承新的 討論連結（如果舊的沒有）
                if not old_p.get("討論連結") and p.get("討論連結"):
                    old_p["討論連結"] = p["討論連結"]
    products = list(seen.values())

    from database import enrich_discussion_links
    products = enrich_discussion_links(products)
    print(f"  📦 今日有效折扣：{len(products)} 筆（去重後）")
    from database import canonicalize_products
    return canonicalize_products(products)


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
_deployed = deploy()
if not _deployed:
    print("❌ 部署失敗！網站不會更新")
sync_overrides_to_github()  # DB overrides → GitHub

report_url = 'https://s610034.github.io/costco-deals/'
summary = format_summary(products)
msg = summary + f"\n\n📱 完整折扣清單：\n{report_url}"
_tg_ok = tg_send(msg)
print("Telegram:", "✅" if _tg_ok else "❌ 發送失敗")
if not _deployed:
    tg_send("🚨 rebuild 部署失敗！網站未更新，請手動檢查 git push")
print("  ✅ Telegram 已發送")
line_send(msg)
print("  ✅ Line 已發送")

print('\n✅ 完成！')
