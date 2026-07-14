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
    """薄包裝：轉呼叫 database.get_products_last_n_days（單一資料來源）"""
    from database import get_products_last_n_days
    return get_products_last_n_days(30)


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
