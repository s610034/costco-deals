#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crawl_all_products.py
完整爬取好市多官網所有商品，存入 products_master 表。
使用子分類 URL (/c/數字)，每個子分類能抓到 50-200 個商品。

執行方式：
  python3 crawl_all_products.py           # 完整爬取所有分類
  python3 crawl_all_products.py --test     # 只爬前3個子分類（測試用）
  python3 crawl_all_products.py --resume   # 跳過 DB 已有的分類
"""

import sys, os, time, re, datetime, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://www.costco.com.tw"
UA   = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

LOG_FILE    = "/tmp/costco_crawl_all.log"
STATE_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crawl_state.json")

# 主分類對照（用於分類標記）
MAIN_CAT_MAP = {
    "8": "食品飲料", "901": "食品飲料", "907": "食品飲料", "908": "食品飲料",
    "90201": "食品飲料", "90101": "食品飲料", "90206": "食品飲料",
    "90207": "食品飲料", "90301": "食品飲料", "90304": "食品飲料",
    "90208": "食品飲料", "902": "食品飲料",
    "1": "家電3C", "101": "家電3C", "102": "家電3C", "104": "家電3C",
    "10100": "家電3C", "10101": "家電3C", "20201": "家電3C",
    "3": "影音家電", "301": "影音家電", "305": "影音家電", "306": "影音家電",
    "7": "健康美妝", "701": "健康美妝", "801": "健康美妝", "802": "健康美妝",
    "12": "生活用品", "915": "生活用品", "916": "寵物用品", "1305": "母嬰用品",
    "1308": "玩具", "9": "服飾時尚", "1001": "服飾時尚", "1002": "服飾時尚",
    "5": "家具餐廚", "502": "家具餐廚", "601": "家具餐廚", "602": "家具餐廚",
    "10": "珠寶黃金", "11": "運動戶外", "1201": "運動戶外", "1209": "運動戶外",
    "17": "辦公文具", "1503": "辦公文具",
}


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_number(text: str):
    if not text:
        return None
    d = re.sub(r"[^\d]", "", str(text))
    return int(d) if d else None


def get_all_category_urls(page) -> list:
    """從首頁導覽列取得所有子分類 URL"""
    page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)
    try:
        btn = page.query_selector("button:has-text('同意')")
        if btn: btn.click(); time.sleep(1)
    except Exception:
        pass

    links = page.evaluate("""() => {
        const result = new Map();
        for (const a of document.querySelectorAll('a[href*="/c/"]')) {
            const href = a.getAttribute('href') || '';
            const text = a.innerText?.trim() || '';
            // 只要 /c/數字 格式（真正的商品分類頁）
            const m = href.match(/\\/c\\/(\\d+)$/);
            if (m && text && text.length < 25 && !text.includes('指南') && !text.includes('more')) {
                const full = href.startsWith('http') ? href : 'https://www.costco.com.tw' + href;
                result.set(full, text);
            }
        }
        return Array.from(result.entries()).map(([url, name]) => ({url, name}));
    }""")

    # 過濾掉重複的大分類（只保留子分類）
    # 原則：有商品的子分類 id 通常 >= 5 位數
    filtered = []
    seen = set()
    for item in links:
        url = item['url']
        cat_id = url.split('/c/')[-1]
        if url not in seen:
            seen.add(url)
            filtered.append({
                "url": url,
                "name": item['name'],
                "cat_id": cat_id,
                "main_cat": MAIN_CAT_MAP.get(cat_id, "其他")
            })

    log(f"找到 {len(filtered)} 個分類 URL")
    return filtered


def scrape_category(page, cat_url: str, cat_name: str, main_cat: str) -> list:
    """爬取一個分類頁面的所有商品"""
    try:
        page.goto(cat_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except PWTimeout:
        return []

    # 捲動觸發懶載入
    page.evaluate("window.scrollTo(0, 300)")
    time.sleep(1)

    products = page.evaluate("""() => {
        const seen = new Set();
        const results = [];

        for (const a of document.querySelectorAll('a[href*="/p/"]')) {
            const href = a.getAttribute('href') || '';
            const m = href.match(/\\/p\\/(\\d+)/);
            if (!m) continue;
            const code = m[1];
            if (seen.has(code)) continue;
            seen.add(code);

            // 找商品卡片（往上找，但不超過含多個商品的容器）
            let card = a;
            for (let i = 0; i < 7; i++) {
                const par = card.parentElement;
                if (!par || par.querySelectorAll('a[href*="/p/"]').length > 2) break;
                card = par;
            }

            // 商品名稱：優先從 a[title]，其次找 [class*=name], [class*=title]
            let name = a.getAttribute('title') || '';
            if (!name || name.length < 2) {
                for (const sel of ['[class*=product-name]', '[class*=lister-name]',
                                    '[class*=name]', '[class*=title]']) {
                    const el = card.querySelector(sel);
                    if (el) {
                        const t = el.innerText?.trim() || '';
                        if (t.length > 2 && !t.includes('$') && !t.includes('速配')) {
                            name = t;
                            break;
                        }
                    }
                }
            }
            if (!name) continue;

            // 圖片
            const imgEl = card.querySelector('img');
            let img = '';
            if (imgEl) {
                img = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || imgEl.src || '';
                if (img && !img.startsWith('http')) img = 'https://www.costco.com.tw' + img;
            }

            let fullHref = href.startsWith('http') ? href : 'https://www.costco.com.tw' + href;

            results.push({code, name, img: img.slice(0, 200), href: fullHref});
        }
        return results;
    }""")

    return products


def crawl_all(categories: list, test_mode: bool = False, resume: bool = False) -> dict:
    """主爬蟲流程"""
    from database import init_db, upsert_master, get_master_count

    init_db()
    start_master = get_master_count()
    log(f"開始爬取，目前 master 商品數：{start_master}")

    # 載入已完成的分類（resume 模式）
    done_cats = set()
    if resume and os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
        done_cats = set(state.get("done", []))
        log(f"Resume 模式：已完成 {len(done_cats)} 個分類，跳過")

    stats = {"total_products": 0, "total_new_master": 0, "cats_done": 0, "cats_skip": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            locale="zh-TW"
        )
        page = ctx.new_page()

        # 取得所有分類 URL
        all_cats = get_all_category_urls(page)

        if test_mode:
            all_cats = all_cats[:5]
            log(f"測試模式：只爬前 5 個分類")

        for i, cat in enumerate(all_cats):
            cat_url  = cat["url"]
            cat_name = cat["name"]
            main_cat = cat["main_cat"]
            cat_id   = cat["cat_id"]

            if cat_url in done_cats:
                stats["cats_skip"] += 1
                continue

            log(f"\n[{i+1}/{len(all_cats)}] 📂 {cat_name}（{main_cat}）{cat_url}")

            products = scrape_category(page, cat_url, cat_name, main_cat)
            log(f"  → {len(products)} 個商品")

            if products:
                # 轉換格式
                db_products = [{
                    "商品編號":  p["code"],
                    "商品名稱":  p["name"],
                    "分類":     main_cat,
                    "細分類":   cat_name,
                    "原價":     None,     # 清單頁抓不到原價，之後進詳情頁補
                    "折扣金額": None,
                    "折扣後售價": None,
                    "圖片URL":  p["img"],
                    "商品連結": p["href"],
                } for p in products]

                cnt = upsert_master(db_products, source=f"crawl/{cat_name}")
                log(f"  ✅ 寫入 master：{cnt} 筆，total master：{get_master_count()}")
                stats["total_products"] += len(products)
                stats["total_new_master"] += cnt

            stats["cats_done"] += 1
            done_cats.add(cat_url)

            # 每50個分類存一次進度
            if stats["cats_done"] % 50 == 0:
                os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
                with open(STATE_FILE, "w") as f:
                    json.dump({"done": list(done_cats), "updated": str(datetime.datetime.now())}, f)
                log(f"  💾 進度已存（{stats['cats_done']} 個分類完成）")

            time.sleep(0.3)

        browser.close()

    # 儲存最終進度
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"done": list(done_cats), "updated": str(datetime.datetime.now())}, f)

    end_master = get_master_count()
    log(f"\n{'='*55}")
    log(f"✅ 爬取完成！")
    log(f"   處理分類：{stats['cats_done']} 個（跳過：{stats['cats_skip']}）")
    log(f"   商品總計：{stats['total_products']} 筆")
    log(f"   master 增加：{end_master - start_master} 個（共 {end_master} 個）")

    return stats


def _notify_failure(err_msg: str):
    """崩潰時直接用urllib發送，不依賴可能也崩潰的其他模組"""
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        token, chat_id = "", ""
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("COSTCO_TG_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                elif line.startswith("COSTCO_TG_CHAT_ID="):
                    chat_id = line.split("=", 1)[1].strip()
        if token and chat_id:
            import urllib.request
            payload = json.dumps({"chat_id": chat_id, "text": f"⚠️ 好市多全量爬蟲失敗\n{err_msg}"}).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="全量爬取好市多官網商品")
        parser.add_argument("--test",   action="store_true", help="測試模式：只爬前5個分類")
        parser.add_argument("--resume", action="store_true", help="繼續上次中斷的爬取")
        args = parser.parse_args()

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== 好市多全量商品爬蟲 {datetime.datetime.now()} ===\n")

        crawl_all([], test_mode=args.test, resume=args.resume)
    except Exception as _fatal_err:
        import traceback
        print(f"❌ 全量爬蟲未預期崩潰：{_fatal_err}")
        traceback.print_exc()
        _notify_failure(str(_fatal_err))
        sys.exit(1)
