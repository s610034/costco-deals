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

try:
    from scraper        import scrape_all, save_json
    from formatter      import format_summary
    from generate_html  import generate_html
    from deploy         import deploy
    from notify         import tg_send, line_send
    from database       import init_db, upsert_products, enrich_with_history, get_summary_stats, update_product_category
except Exception as _import_err:
    import traceback
    err_text = traceback.format_exc()
    print(f"❌ 模組載入失敗，腳本無法啟動：{_import_err}")
    print(err_text)
    try:
        _tg_token = os.environ.get("COSTCO_TG_TOKEN", "")
        _tg_chat  = os.environ.get("COSTCO_TG_CHAT_ID", "")
        if _tg_token and _tg_chat:
            _payload = json.dumps({
                "chat_id": _tg_chat,
                "text": f"⚠️ 好市多排程啟動失敗（模組載入錯誤）\n{_import_err}",
            }).encode("utf-8")
            _req = urllib.request.Request(
                f"https://api.telegram.org/bot{_tg_token}/sendMessage",
                data=_payload, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(_req, timeout=10)
    except Exception:
        pass
    sys.exit(1)

DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
PAGE_URL = "https://s610034.github.io/costco-deals/"
TOKEN    = os.environ.get("GITHUB_TOKEN", "")


def sync_overrides_to_github():
    """把本機 DB 的分類覆蓋推送到 GitHub overrides.json"""
    if not TOKEN:
        return 0
    try:
        import sqlite3 as _sq
        conn = _sq.connect(os.path.join(DATA_DIR, "costco_history.db"))
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
    """薄包裝：轉呼叫 database.get_products_last_n_days（單一資料來源）"""
    from database import get_products_last_n_days
    return get_products_last_n_days(30)


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

        if ptt_products:
            # 用官網搜尋補商品編號，再驗證是否有折扣
            from costco_search import enrich_ptt_products
            from playwright.sync_api import sync_playwright as _spw2
            import time as _t2

            with _spw2() as _pw2:
                _browser2 = _pw2.chromium.launch(headless=True)
                _ctx2 = _browser2.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    locale="zh-TW"
                )
                _page2 = _ctx2.new_page()
                _page2.goto("https://www.costco.com.tw/", wait_until="domcontentloaded", timeout=20000)
                _t2.sleep(1)
                try:
                    _btn2 = _page2.query_selector("button:has-text('同意')")
                    if _btn2: _btn2.click(); _t2.sleep(1)
                except Exception:
                    pass
                ptt_products = enrich_ptt_products(ptt_products, _page2)
                _browser2.close()

        new_products = merge_ptt_with_existing(new_products, ptt_products)
    except Exception as e:
        import traceback
        print(f"  ⚠️  PTT 失敗（繼續）：{e}")
        traceback.print_exc()

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

                # daybuy/PTT 來源：官網無折扣的排除
                before = len(new_products)
                new_products = [
                    p for p in new_products
                    if p.get("來源") not in ("daybuy_tg", "ptt_hypermall", "daybuy_sighting")
                    or p.get("折扣金額")  # 官網驗證有折扣才保留
                    or p.get("分類") in ("限時優惠", "精選優惠")  # 官網直接爬的保留
                ]
                removed = before - len(new_products)
                if removed:
                    print(f"  🗑️  移除社群來源無折扣商品：{removed} 筆")

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

        # 方案二：價格只在照片裡的現場特價 → 存成 JSON 供 HTML 的
        # 「📸 現場特價目擊」收合區塊使用（不進主商品列表）
        try:
            from sighting_monitor import fetch_sighting_photo_deals
            from photo_ocr import enrich_photo_deals_with_ocr
            photo_deals = fetch_sighting_photo_deals(days_back=7)
            photo_deals = enrich_photo_deals_with_ocr(photo_deals, max_new=200)
            photo_payload = {
                "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "deals": photo_deals,
            }
            _photo_path = os.path.join(BASE_DIR, "data", "sighting_photos.json")
            with open(_photo_path, "w", encoding="utf-8") as _pf:
                json.dump(photo_payload, _pf, ensure_ascii=False, indent=1)
            print(f"  💾 現場特價照片：{len(photo_deals)} 筆 → data/sighting_photos.json")
        except Exception as _pe:
            print(f"  ⚠️  現場特價照片解析失敗（略過）：{_pe}")

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

    # Step 3：只顯示今天爬到的有效折扣（不再用30天合併）
    print(f"\n【Step 3】整理 30 天有效折扣...")
    # 單一資料來源：database.get_products_last_n_days（30天有效折扣合併）
    # 舊版此處有一份內嵌 SQL 只撈「當天」，造成排程部署與 rebuild 部署內容不一致
    from database import get_products_last_n_days
    products_30d = get_products_last_n_days(30)

    # 補充討論連結和官網連結（統一從 database 模組處理）
    from database import enrich_discussion_links
    products_30d = enrich_discussion_links(products_30d)
    print(f"  📦 30 天有效折扣：{len(products_30d)} 筆（去重後）")

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
    if not deployed:
        print("  ❌ 部署失敗！網站不會更新（詳見上方 git 錯誤）")
    sync_overrides_to_github()  # DB overrides → GitHub

    # Step 6：推播 Telegram + Line
    print(f"\n【Step 6】推播通知...")
    summary = format_summary(new_products)
    msg = summary + f"\n\n📱 完整折扣清單：\n{PAGE_URL}"
    if not deployed:
        msg += "\n\n⚠️ 部署失敗，連結稍後更新"
    _tg_ok = tg_send(msg)
    print("  ✅ Telegram 已發送" if _tg_ok else "  ❌ Telegram 發送失敗")
    _line_ok = line_send(msg)
    print("  ✅ Line 已發送" if _line_ok else "  ❌ Line 發送失敗")
    if not deployed:
        # 部署失敗是嚴重問題（網站停更），額外發警報確保被看到
        tg_send("🚨 好市多週報部署失敗！資料已入DB但網站未更新，請手動檢查 git push")

    elapsed = (datetime.datetime.now() - start).seconds
    print(f"\n{'='*52}")
    print(f"✅ 完成！顯示 {len(products_30d)} 項（30天合併），本次新抓 {len(new_products)} 項，耗時 {elapsed} 秒")
    print(f"🌐 {PAGE_URL}")
    print(f"{'='*52}\n")
    return True


if __name__ == "__main__":
    from database import acquire_pipeline_lock
    _lock = acquire_pipeline_lock(wait_seconds=900)  # 最多等 15 分鐘
    if not _lock:
        print("❌ 等待排程鎖逾時（可能有卡死的排程），本次放棄執行")
        try:
            tg_send("⚠️ 好市多週報：排程鎖等待逾時，本次未執行（請檢查是否有卡死的程序）")
        except Exception:
            pass
        sys.exit(1)
    try:
        sys.exit(0 if run() else 1)
    except Exception as _fatal_err:
        import traceback
        print(f"❌ 主流程未預期崩潰：{_fatal_err}")
        traceback.print_exc()
        try:
            tg_send(f"⚠️ 好市多折扣週報主流程崩潰\n{_fatal_err}")
        except Exception:
            pass
        sys.exit(1)
