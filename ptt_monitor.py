#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ptt_monitor.py
爬取 PTT hypermall 板，解析好市多折扣/特價討論串
使用 pttweb.cc（非官方 SSR 版），不需要 Playwright
"""

import os, re, json, datetime, time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "ptt_cache.json")

PTTWEB_BASE  = "https://www.pttweb.cc"
PTTWEB_BOARD = "/bbs/hypermall"
PTTWEB_INDEX = PTTWEB_BASE + PTTWEB_BOARD + "/index"
DAYS_LIMIT   = 14  # 只處理 N 天內的文章（PTT 資訊時效短，14天即可）

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

COSTCO_KEYWORDS = re.compile(r"好市多|Costco|COSTCO|costco|好市|科克蘭|Kirkland")
DEAL_KEYWORDS   = re.compile(
    r"特價|折扣|優惠|現折|現省|折價|降價|買一送一|限時|省錢|便宜|打折|週年|活動|促銷|試吃|新品|下殺|破盤|優惠週"
)
TITLE_VERB_CUT = re.compile(r"[，,！!？?。]|特價|折扣|優惠|現折|降價|限時|活動|促銷|開賣|上架")
DATE_RANGE     = re.compile(r"\d{1,2}/\d{1,2}")


def parse_num(text: str) -> Optional[int]:
    if not text: return None
    d = re.sub(r"[^\d]", "", str(text))
    return int(d) if d else None


def load_cache() -> set:
    if not os.path.exists(CACHE_FILE):
        return set()
    try:
        with open(CACHE_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_cache(ids: set):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(list(ids), f)


def _parse_title(a_tag) -> str:
    desktop = a_tag.select_one(".e7-show-if-device-is-not-xs")
    if desktop:
        return desktop.get_text(strip=True)
    raw = a_tag.get_text(strip=True)
    for split in range(4, len(raw) // 2 + 1):
        if raw[split:].startswith(raw[:min(8, split)]):
            return raw[:split]
    return raw[:60]


def _get_post_age_days(url: str) -> int:
    """從 PTT 文章 URL 的 M.timestamp 計算發文幾天前"""
    m = re.search(r"M\.(\d+)\.", url)
    if m:
        ts = int(m.group(1))
        dt = datetime.datetime.fromtimestamp(ts)
        return (datetime.datetime.now() - dt).days
    return 999


def fetch_article_list(page_num: int = 0) -> List[Dict]:
    url = PTTWEB_INDEX if page_num == 0 else PTTWEB_BASE + PTTWEB_BOARD + "/index" + str(page_num)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print("  HTTP " + str(r.status_code))
            return []
    except Exception as e:
        print("  請求失敗：" + str(e))
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = []
    for a in soup.select('a[href*="/bbs/hypermall/M."]'):
        href  = a.get("href", "")
        title = _parse_title(a).strip()
        if not title or len(title) < 3:
            continue
        if not COSTCO_KEYWORDS.search(title):
            continue
        if not DEAL_KEYWORDS.search(title):
            continue
        if title.startswith("[公告]") or title.startswith("[板規]"):
            continue

        full_url = PTTWEB_BASE + href if href.startswith("/") else href

        # 時間過濾：只保留 DAYS_LIMIT 天內的文章
        if _get_post_age_days(full_url) > DAYS_LIMIT:
            continue

        articles.append({
            "title":      title,
            "url":        full_url,
            "is_reply":   title.startswith("Re:"),
            "push_count": 0,
        })
    return articles


def extract_name_from_title(title: str) -> str:
    clean = re.sub(r"^\[[^\]]{1,6}\]\s*", "", title).strip()
    clean = re.sub(r"^(Re:|Fw:)\s*", "", clean).strip()
    clean = re.sub(r"^(好市多|Costco|COSTCO)\s*/\s*(?!\d)\S+\s*", "", clean).strip()
    clean = re.sub(r"^(好市多|Costco|COSTCO)\s+(?!\d)", "", clean).strip()

    m = TITLE_VERB_CUT.search(clean)
    candidate = clean[:m.start()].strip() if m and m.start() >= 3 else clean[:25].strip()

    if DATE_RANGE.search(candidate):
        return clean[:30]

    name = re.sub(r"[^\w\s\u4e00-\u9fff\u3000-\u303f]", "", candidate).strip()
    return name[:40] if len(name) >= 2 else clean[:30]


def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def parse_products_from_article(url: str, article_title: str = "") -> List[Dict]:
    """
    解析 PTT 文章，萃取商品列表。
    支援兩種格式：
    1. 多商品格式：「產品名稱: XXX\n【原價-折扣】」
    2. 單商品格式：從標題 + 內文抓折扣金額
    """
    html = fetch_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # 抓文章主文（去推文）
    full_text = soup.get_text("\n")
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # 找文章主文起始位置（跳過 header）
    content_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^(心得發文|文章無相關|不得使用|賣場名稱|產品名稱)", line):
            content_start = i
            break

    content_lines = lines[content_start:]

    products = []

    # ── 格式一：「產品名稱:」標記的多商品 ──
    current_name = ""
    current_price_text = ""

    for line in content_lines:
        if re.match(r"^產品名稱[:：]", line):
            if current_name:
                p = _build_product(current_name, current_price_text, url, article_title)
                if p:
                    products.append(p)
            current_name = re.sub(r"^產品名稱[:：]\s*", "", line).strip()
            current_price_text = ""
        elif re.match(r"^【[\d,]+-[\d,]+】", line) and current_name:
            current_price_text = line

    if current_name:
        p = _build_product(current_name, current_price_text, url, article_title)
        if p:
            products.append(p)

    if products:
        return products

    # ── 格式二：單商品，從標題 + 內文抓折扣 ──
    name = extract_name_from_title(article_title) if article_title else ""
    if not name:
        return []

    disc_amt = None
    orig_price = None
    sale_price = None

    content_str = "\n".join(content_lines[:30])

    # 折扣金額
    for pat in [r"現省\s*\$?([\d,]+)", r"現折\s*\$?([\d,]+)", r"折價\s*\$?([\d,]+)",
                r"省\s*\$?([\d,]+)\s*元", r"折\s*([\d,]+)\s*元"]:
        m2 = re.search(pat, content_str)
        if m2:
            disc_amt = parse_num(m2.group(1))
            break

    # 原價
    m2 = re.search(r"原價\s*\$?([\d,]+)", content_str)
    if m2:
        orig_price = parse_num(m2.group(1))

    # 特價
    for pat in [r"特價\s*\$?([\d,]+)", r"只要\s*\$?([\d,]+)"]:
        m2 = re.search(pat, content_str)
        if m2:
            val = parse_num(m2.group(1))
            if val and val > 10:
                sale_price = val
                break

    if orig_price and disc_amt and not sale_price:
        sale_price = orig_price - disc_amt
    if orig_price and sale_price and not disc_amt:
        disc_amt = orig_price - sale_price

    p = _build_product(name, "", url, article_title, orig_price, disc_amt, sale_price)
    if p:
        products.append(p)

    return products


def _build_product(name: str, price_text: str, url: str, article_title: str = "",
                   orig_price: Optional[int] = None, disc_amt: Optional[int] = None,
                   sale_price: Optional[int] = None) -> Optional[Dict]:
    if not name or len(name) < 2:
        return None

    # 從 【原價-折扣】 格式解析
    if price_text:
        m = re.match(r"^【([\d,]+)-([\d,]+)】", price_text)
        if m:
            orig_price = parse_num(m.group(1))
            disc_amt   = parse_num(m.group(2))
            if orig_price and disc_amt:
                sale_price = orig_price - disc_amt

    disc_pct = None
    if orig_price and disc_amt:
        disc_pct = str(round(disc_amt / orig_price * 100, 1)) + "%"

    return {
        "商品名稱":    name,
        "分類":       "精選優惠",
        "原價":       orig_price,
        "折扣金額":   disc_amt,
        "折扣幅度":   disc_pct,
        "折扣後售價": sale_price,
        "優惠期間":   "",
        "實體賣場":   True,
        "實體狀態":   "🏪 網友回報",
        "網路討論":   True,
        "討論來源":   "PTT hypermall板",
        "討論連結":   url,
        "圖片URL":    "",
        "商品連結":   url,
        "抓取時間":   datetime.datetime.now().isoformat(timespec="seconds"),
        "來源":       "ptt_hypermall",
        "ptt_推文數": 0,
        "ptt_標題":   article_title or name,
    }


def fetch_ptt_costco(pages: int = 3, fetch_content: bool = True) -> List[Dict]:
    """
    爬取 PTT hypermall 板，解析好市多折扣商品
    - 只處理 DAYS_LIMIT 天內的文章
    - 每篇文章都進去解析（多商品格式或單商品）
    - 結果以商品名稱前8字去重
    """
    print("📋 爬取 PTT hypermall 板（最近 " + str(pages) + " 頁，" + str(DAYS_LIMIT) + "天內）...")

    cached_ids = load_cache()
    new_ids    = set()
    all_arts   = []

    for page_num in range(pages):
        arts = fetch_article_list(page_num)
        print("  第 " + str(page_num + 1) + " 頁：找到 " + str(len(arts)) + " 篇（" + str(DAYS_LIMIT) + "天內）")
        all_arts.extend(arts)
        time.sleep(0.3)

    # 去重文章（同 URL 只處理一次）
    seen_urls = {}
    for art in all_arts:
        if art["url"] not in seen_urls:
            seen_urls[art["url"]] = art
    unique_arts = list(seen_urls.values())
    print("  共 " + str(len(unique_arts)) + " 篇不重複文章，逐篇解析...")

    all_products = []
    for art in unique_arts:
        new_ids.add(art["url"])

        # 每篇都解析（不用 cached_ids 跳過，確保多商品文章被正確展開）
        parsed = parse_products_from_article(art["url"], art["title"])
        time.sleep(0.3)

        if parsed:
            for p in parsed:
                p["ptt_推文數"] = art["push_count"]
                all_products.append(p)
                print("  💬 " + p["商品名稱"][:32].ljust(32) +
                      " 折=" + str(p["折扣金額"] or "-") +
                      " 特=" + str(p["折扣後售價"] or "-"))
        else:
            # 解析失敗，用標題當商品名
            name = extract_name_from_title(art["title"])
            if name:
                p = _build_product(name, "", art["url"], art["title"])
                if p:
                    p["ptt_推文數"] = art["push_count"]
                    all_products.append(p)
                    print("  💬 [標題] " + name[:30].ljust(30) + " 折=- 特=-")

    # 過濾掉沒有任何折扣資訊的商品
    all_products = [
        p for p in all_products
        if p.get("折扣金額") or p.get("折扣後售價") or p.get("原價")
    ]

    # 嘗試從文章內文補充商品編號（用於後續官網驗證）
    import re as _re2
    for p in all_products:
        if not p.get("商品編號"):
            # 從 PTT 文章內文找 #數字 或商品編號
            try:
                _html = fetch_html(p.get("商品連結", "") or p.get("討論連結", ""))
                if _html:
                    _codes = _re2.findall(r"#(\d{5,8})", _html)
                    if _codes:
                        p["商品編號"] = _codes[0]
            except Exception:
                pass

    # 商品名稱去重（前8字相同只留折扣金額最大的）
    seen_names: Dict[str, Dict] = {}
    for p in all_products:
        key = p["商品名稱"][:8]
        if key not in seen_names:
            seen_names[key] = p
        else:
            # 保留有折扣金額的那筆
            if p.get("折扣金額") and not seen_names[key].get("折扣金額"):
                seen_names[key] = p

    products = list(seen_names.values())

    save_cache(cached_ids | new_ids)
    print("\n  ✅ PTT 解析出 " + str(len(products)) + " 個不重複商品")
    return products


def merge_ptt_with_existing(existing: List[Dict], ptt: List[Dict]) -> List[Dict]:
    if not ptt:
        return existing
    name_map = {p["商品名稱"][:8]: i for i, p in enumerate(existing)}
    merged   = list(existing)
    added    = 0
    for p in ptt:
        key = p["商品名稱"][:8]
        if key in name_map:
            idx = name_map[key]
            if not merged[idx].get("網路討論"):
                merged[idx]["網路討論"]  = True
                merged[idx]["討論來源"] = "PTT hypermall板"
                merged[idx]["討論連結"] = p["討論連結"]
        else:
            merged.append(p)
            name_map[key] = len(merged) - 1
            added += 1
    print("📊 PTT 合併：已有 " + str(len(existing)) +
          " + PTT 新增 " + str(added) + " = 共 " + str(len(merged)) + " 筆")
    return merged


if __name__ == "__main__":
    import sys
    pages = 3
    for arg in sys.argv[1:]:
        if arg.isdigit():
            pages = int(arg)

    # 清 cache 確保重新解析
    with open(CACHE_FILE, "w") as f:
        json.dump([], f)

    products = fetch_ptt_costco(pages=pages, fetch_content=True)
    print("\n共 " + str(len(products)) + " 個商品")
    for p in products:
        print("  " + p["商品名稱"][:35].ljust(35) +
              " 折=" + str(p["折扣金額"]) +
              " 特=" + str(p["折扣後售價"]))
