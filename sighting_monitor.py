#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sighting_monitor.py
爬取 daybuy.tw「賣場優惠目擊情報」和「隱藏優惠目擊情報」
解析商品列表（商品名 #商品編號 格式）
"""

import re
import time
import datetime
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

BASE_URL    = "https://www.daybuy.tw"
SALE_URL    = BASE_URL + "/costco/hypermarket-news/hypermarket-sale/"
SIGHTING_URL = BASE_URL + "/costco/hypermarket-news/"
DAYS_LIMIT  = 7  # 只處理最近 N 天的文章

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# 商品列表格式：「商品名稱 #數字」
ITEM_RE   = re.compile(r"^(.+?)\s+#(\d{5,8})\s*$")
# 折扣資訊格式：「現省 $N」「單盒現省 $N」「現折 $N」
DISCOUNT_RE = re.compile(r"現省\s*\$?([\d,]+)|現折\s*\$?([\d,]+)|省\$?([\d,]+)|折價\s*\$?([\d,]+)")
# 特價格式：「特價 $N」「只要 $N」
SALE_RE     = re.compile(r"(?:特價|只要|限時)\s*\$?([\d,]+)")
# 優惠期間格式
PERIOD_RE   = re.compile(r"(\d{1,2}/\d{1,2}[^~\-]*?[~\-]+\s*\d{1,2}/\d{1,2}|\d{4}[./]\d{2}[./]\d{2}[^~\-]*?[~\-]+\s*\d{4}[./]\d{2}[./]\d{2})")
# 縣市關鍵字
LOCATION_RE = re.compile(r"(台北|新北|桃園|台中|台南|高雄|新竹|宜蘭|花蓮|台東|南港|內湖|中和|板橋|中壢|忠孝|敦化|大直)")


def parse_num(text: str) -> Optional[int]:
    if not text:
        return None
    d = re.sub(r"[^\d]", "", str(text))
    return int(d) if d else None


def get_article_urls(page_url: str, days_limit: int = DAYS_LIMIT) -> List[Dict]:
    """從列表頁取得近期文章的 URL 和標題"""
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = []
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days_limit)

    for a in soup.select("a[href*='/costco/']"):
        href  = a.get("href", "")
        title = a.get_text(strip=True)
        if not title or len(title) < 5 or len(title) > 80:
            continue
        if not any(kw in title for kw in ["目擊", "隱藏", "優惠", "特價", "現場"]):
            continue
        if not re.search(r"/costco/\d+/", href):
            continue

        # 從 URL timestamp 判斷文章時間
        m = re.search(r"/costco/(\d+)/", href)
        if m:
            # daybuy 的文章編號不是時間戳，用旁邊的日期元素
            pass

        articles.append({"title": title, "url": href})

    # 去重
    seen = set()
    result = []
    for art in articles:
        if art["url"] not in seen:
            seen.add(art["url"])
            result.append(art)

    return result[:10]  # 最多取10篇


def parse_article_with_playwright(url: str, title: str) -> List[Dict]:
    """用 Playwright 載入文章，解析商品列表"""
    from playwright.sync_api import sync_playwright

    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    products = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(user_agent=UA)
        page    = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_selector(".entry-content img, table tr", timeout=10000)
            except Exception:
                pass
            time.sleep(2)

            body_text = page.evaluate("() => document.body.innerText")
            products  = parse_body_text(body_text, url, title)
        except Exception as e:
            print(f"  ⚠️  Playwright 載入失敗：{e}")
        finally:
            browser.close()

    return products


def parse_body_text(body_text: str, url: str, article_title: str) -> List[Dict]:
    """從頁面文字解析商品列表"""
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]

    products = []
    current_discount = None
    current_sale     = None
    current_period   = None
    current_location = None

    # 先從文章標題抓日期
    date_m = re.search(r"(\d{4})/(\d{2})/(\d{2})", article_title)
    article_date = ""
    if date_m:
        article_date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"

    for i, line in enumerate(lines):
        # 過濾廣告/導航行
        if any(kw in line for kw in ["LINE", "daybuy", "http", "@", "FB粉", "粉絲", "追蹤", "加入", "訂閱"]):
            continue
        if len(line) < 3 or len(line) > 200:
            continue

        # 抓折扣資訊（在商品名之前或之後出現）
        disc_m = DISCOUNT_RE.search(line)
        if disc_m:
            vals = [v for v in disc_m.groups() if v]
            if vals:
                current_discount = parse_num(vals[0])

        sale_m = SALE_RE.search(line)
        if sale_m:
            current_sale = parse_num(sale_m.group(1))

        period_m = PERIOD_RE.search(line)
        if period_m:
            current_period = period_m.group(1)

        loc_m = LOCATION_RE.search(line)
        if loc_m:
            current_location = loc_m.group(1)

        # 解析商品行（商品名 #商品編號）
        item_m = ITEM_RE.match(line)
        if item_m:
            name = item_m.group(1).strip()
            code = item_m.group(2).strip()

            if len(name) < 2:
                continue

            # 向前後幾行找折扣資訊
            context_lines = lines[max(0, i-3):i+4]
            for ctx_line in context_lines:
                d = DISCOUNT_RE.search(ctx_line)
                if d:
                    vals = [v for v in d.groups() if v]
                    if vals:
                        current_discount = parse_num(vals[0])
                s = SALE_RE.search(ctx_line)
                if s:
                    current_sale = parse_num(s.group(1))

            products.append({
                "商品名稱":    name,
                "商品編號":    code,
                "折扣金額":    current_discount,
                "折扣後售價":  current_sale,
                "原價":       None,   # 後續從 DB 補
                "折扣幅度":    None,
                "優惠期間":    current_period or "",
                "實體賣場":    True,
                "限定門市":    current_location or "",
                "分類":       "精選優惠",
                "圖片URL":    "",
                "商品連結":    f"https://www.costco.com.tw/p/{code}",
                "討論連結":    url,
                "來源":       "daybuy_sighting",
                "抓取時間":    datetime.datetime.now().isoformat(timespec="seconds"),
                "ptt_標題":   article_title,
            })

            # 每篇商品解析後重置折扣（避免跨商品污染）
            current_discount = None
            current_sale     = None

    # 去重（同商品編號只保留一筆）
    seen_codes: Dict[str, Dict] = {}
    for p in products:
        code = p["商品編號"]
        if code not in seen_codes:
            seen_codes[code] = p
        elif p.get("折扣金額") and not seen_codes[code].get("折扣金額"):
            seen_codes[code] = p

    return list(seen_codes.values())


def fetch_sighting_products(days_back: int = 7) -> List[Dict]:
    """
    爬取最近 N 天的賣場目擊情報和隱藏優惠
    回傳商品列表（含商品編號，後續可去官網比對）
    """
    print("🏪 爬取 daybuy 賣場目擊情報...")

    all_articles = []

    # 1. 賣場優惠目擊
    arts1 = get_article_urls(SALE_URL, days_back)
    print(f"  賣場優惠目擊：{len(arts1)} 篇")
    all_articles.extend(arts1)

    # 2. 完整賣場情報（含隱藏優惠）
    arts2 = get_article_urls(SIGHTING_URL, days_back)
    print(f"  完整賣場情報：{len(arts2)} 篇")
    all_articles.extend(arts2)

    # 去重文章
    seen_urls = set()
    unique_articles = []
    for art in all_articles:
        if art["url"] not in seen_urls:
            seen_urls.add(art["url"])
            unique_articles.append(art)

    print(f"  共 {len(unique_articles)} 篇不重複文章，開始解析...")

    all_products = []
    for art in unique_articles[:2]:  # 最多處理2篇（最新的）
        print(f"  📄 {art['title'][:40]}")
        products = parse_article_with_playwright(art["url"], art["title"])
        print(f"     → 解析出 {len(products)} 個商品")
        for p in products[:5]:
            print(f"       #{p['商品編號']} {p['商品名稱'][:30]} 折={p['折扣金額']} 門市={p['限定門市'] or '全國'}")
        all_products.extend(products)
        time.sleep(1)

    # 最終去重
    seen = {}
    for p in all_products:
        code = p["商品編號"]
        if code not in seen:
            seen[code] = p
        elif p.get("折扣金額") and not seen[code].get("折扣金額"):
            seen[code] = p

    result = list(seen.values())
    print(f"\n  ✅ 賣場目擊情報：共 {len(result)} 個不重複商品（含商品編號）")
    return result


if __name__ == "__main__":
    products = fetch_sighting_products(days_back=7)
    print(f"\n=== 最終結果 {len(products)} 筆 ===")
    for p in products:
        loc = f"【{p['限定門市']}限定】" if p['限定門市'] else ""
        print(f"  #{p['商品編號']} {p['商品名稱'][:35]} {loc} 折={p['折扣金額']}")
