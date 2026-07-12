#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daybuy_monitor.py
爬取 @daybuy Telegram 頻道公開頁面，解析賣場特價情報
補充好市多官網抓不到的純賣場折扣商品

資料來源：https://t.me/s/daybuy（不需要 API Key）
"""

import os, re, json, datetime, time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "daybuy_cache.json")

TG_URL    = "https://t.me/s/daybuy"
HEADERS   = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

SKIP_PREFIXES = ("優惠情報連結", "優惠完整情報", "特展完整情報", "限時優惠", "精選優惠", "今日優惠", "新品情報", "情報看這裡", "優惠看這裡", "完整情報", "優惠情報看", "新品情報看", "情報看這邊", "優惠情報", "特展情報")

DISC_PATTERNS = [
    r"現省\s*\$?([\d,]+)",
    r"現折\s*\$?([\d,]+)",
    r"折價\s*\$?([\d,]+)",
    r"省\s*\$?([\d,]+)\s*元",
    r"直接現折([\d,]+)元",
    r"折\s*([\d,]+)\s*元",
    r"折扣\s*\$?([\d,]+)",
]

ORIG_PATTERNS = [
    r"原價\s*\$?([\d,]+)",
    r"原\s*\$?([\d,]+)",
]

SALE_PATTERNS = [
    r"特價\s*\$?([\d,]+)",
    r"限時特價\s*\$?([\d,]+)",
    r"現在只要\s*\$?([\d,]+)",
    r"只要\s*\$?([\d,]+)",
    r"不到\s*\$?([\d,]+)元",
]

NAME_TAIL_STRIP = re.compile(r"\s*(特價了?|偷偷特價|正在特價|限時特價|已特價|開始特價|現在特價|超人氣)$")
NAME_HEAD_STRIP = re.compile(r"^(家裡必備的|廣受好評的|超人氣的|今天的|這次的|大家熟悉的|很受歡迎的|超好用的|超夯的|超熱賣的)")
# 動詞：找到後截斷，商品名在動詞之前
VERB_CUT = re.compile(r"正在|已經|已在|開始|限時|特價了?|偷偷|折扣|超人氣")


def parse_num(text: str) -> Optional[int]:
    if not text: return None
    d = re.sub(r"[^\d]", "", text)
    return int(d) if d else None


def _is_per_unit_price(val: int, text: str, match_start: int) -> bool:
    if val >= 50:
        return False
    before = text[max(0, match_start - 15):match_start]
    return bool(re.search(r"一[顆粒片包杯碗份入]", before))


def extract_discount_info(text: str) -> Dict:
    result = {"折扣金額": None, "原價": None, "折扣後售價": None}

    for pat in DISC_PATTERNS:
        m = re.search(pat, text)
        if m:
            result["折扣金額"] = parse_num(m.group(1))
            break

    for pat in ORIG_PATTERNS:
        m = re.search(pat, text)
        if m:
            result["原價"] = parse_num(m.group(1))
            break

    for pat in SALE_PATTERNS:
        m = re.search(pat, text)
        if m:
            val = parse_num(m.group(1))
            if val and _is_per_unit_price(val, text, m.start()):
                continue
            result["折扣後售價"] = val
            break

    if result["原價"] and result["折扣金額"] and not result["折扣後售價"]:
        result["折扣後售價"] = result["原價"] - result["折扣金額"]
    if result["原價"] and result["折扣後售價"] and not result["折扣金額"]:
        result["折扣金額"] = result["原價"] - result["折扣後售價"]
    if result["原價"] and result["折扣金額"]:
        pct = round(result["折扣金額"] / result["原價"] * 100, 1)
        result["折扣幅度"] = str(pct) + "%"
    else:
        result["折扣幅度"] = None

    return result


def _clean_name(raw: str) -> str:
    name = NAME_HEAD_STRIP.sub("", raw).strip()
    name = NAME_TAIL_STRIP.sub("", name).strip()
    name = re.sub(r"[^\w\s\u4e00-\u9fff\u3000-\u303f]", "", name).strip()
    return name[:40]


def extract_product_name(text: str) -> str:
    """
    截斷優先順序：
      1. VERB_CUT.search：找到動詞，位置在4~30字之間 → 截取動詞前
      2. 中文逗號前（4~30字）
      3. 空格截斷
      4. 前25字
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    content_lines = []
    for line in lines:
        if any(line.startswith(p) for p in SKIP_PREFIXES):
            continue
        if re.match(r"https?://\S+$", line):
            continue
        if re.match(r"^#\S+$", line):
            continue
        if len(line) < 4:
            continue
        content_lines.append(line)

    if not content_lines:
        return ""

    first = content_lines[0]

    # 策略1：動詞截斷（search 找第一個動詞，4~30字之間）
    vm = VERB_CUT.search(first)
    if vm and 4 <= vm.start() <= 30:
        name = _clean_name(first[:vm.start()])
        if len(name) >= 4:
            return name

    # 策略2：中文逗號前（擴大到30字）
    m = re.match(r"^([^，,]{4,30})，", first)
    if m:
        name = _clean_name(m.group(1))
        if len(name) >= 4:
            return name

    # 策略3：空格截斷
    parts = first.split()
    if len(parts) >= 2:
        candidate = parts[0] if len(parts[0]) >= 4 else parts[0] + " " + parts[1]
        name = _clean_name(candidate)
        if len(name) >= 4:
            return name

    # 策略4：前25字
    return _clean_name(first[:25])


def extract_period(text: str) -> str:
    patterns = [
        r"(\d{1,2}/\d{1,2}[^\n]*?[-~～至]\s*\d{1,2}/\d{1,2}[^\n]{0,10})",
        r"(即日起[\s\S]{0,10}?\d{1,2}/\d{1,2})",
        r"優惠期間[：:]\s*([^\n]{5,30})",
        r"只到[^\d]*(\d{1,2}/\d{1,2}[^\n]{0,15})",
        r"(\d{4}/\d{1,2}/\d{1,2}[^\n]*?[-~～至]\s*\d{4}/\d{1,2}/\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:40]
    return ""


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


def fetch_daybuy_article(url: str) -> Dict:
    """
    抓取 daybuy.tw 文章頁，補充：
    - 原價（從商品訊息表格）
    - 更新時間（最後確認日期）
    - 折扣後售價（若有）
    - 優惠期間
    - 商品編號（從 h1 的 #數字）
    - 商品名稱（完整版）
    - 過期判斷
    """
    if not url or "daybuy.tw" not in url:
        return {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return {}
    except Exception:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    result: Dict = {}
    import re as _re
    import datetime as _dt

    # ── 從表格抓所有欄位 ──
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        key = cells[0].get_text(strip=True).replace(":", "").replace("：", "").strip()
        val = cells[1].get_text(strip=True)

        if "原價" in key:
            price_num = parse_num(val)
            if price_num and price_num > 10:
                result["原價"] = price_num

        elif "更新時間" in key:
            result["更新時間"] = val

        elif "折後" in key or "特價" in key or "優惠價" in key:
            sale_num = parse_num(val)
            if sale_num and sale_num > 10:
                result["折扣後售價_daybuy"] = sale_num

    # ── 優惠期間 ──
    text = soup.get_text()
    m = _re.search(r"(\d{1,2}/\d{1,2}[\(（][一二三四五六日][\)）][\s~～至-]+\d{1,2}/\d{1,2}[\(（][一二三四五六日][\)）])", text)
    if m:
        result["優惠期間"] = m.group(1)
    if not result.get("優惠期間"):
        m2 = _re.search(r"(\d{4}[./]\d{2}[./]\d{2}[\s~～-]+\d{4}[./]\d{2}[./]\d{2})", text)
        if m2:
            result["優惠期間"] = m2.group(1)

    # ── h1：商品名稱 + 商品編號 ──
    h1 = soup.select_one("h1.entry-title, h1.post-title, h1")
    if h1:
        h1_text = h1.get_text(strip=True)
        code_m = _re.search(r"#(\d{5,7})", h1_text)
        if code_m:
            result["商品編號"] = code_m.group(1)
        name = _re.sub(r"\s*#\d+\s*$", "", h1_text).strip()
        if len(name) >= 3:
            result["商品名稱_daybuy"] = name

    # ── 發布時間 ──
    pub = soup.select_one("time.entry-date[datetime]")
    if pub:
        result["發布時間"] = pub.get("datetime", "")

    # ── og:image（商品圖片）──
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get("content"):
        result["圖片URL"] = og_img.get("content")

    # ── 過期判斷：優先用優惠期間，其次用更新時間 ──
    now = _dt.datetime.now()
    if result.get("優惠期間"):
        all_dates = _re.findall(r"(\d{1,2})/(\d{1,2})", result["優惠期間"])
        if all_dates:
            end_month, end_day = int(all_dates[-1][0]), int(all_dates[-1][1])
            # 取離今天最近的年份解讀（修正：舊邏輯會把上個月結束的優惠推成明年）
            _cands = []
            for _yy in (now.year - 1, now.year, now.year + 1):
                try:
                    _cands.append(_dt.datetime(_yy, end_month, end_day))
                except ValueError:
                    pass
            end_year = min(_cands, key=lambda d: abs((d - now).days)).year if _cands else now.year
            try:
                end_date = _dt.datetime(end_year, end_month, end_day)
                result["優惠結束日"] = end_date.strftime("%Y-%m-%d")
                result["已過期"] = end_date < now
            except Exception:
                result["已過期"] = False
        else:
            result["已過期"] = False
    else:
        update = result.get("更新時間", "")
        if update:
            m3 = _re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", update)
            if m3:
                try:
                    upd_dt = _dt.datetime(int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
                    result["已過期"] = (now - upd_dt).days > 14
                except Exception:
                    result["已過期"] = False
            else:
                result["已過期"] = False
        else:
            result["已過期"] = False

    return result


def fetch_daybuy_channel(days_back: int = 7) -> List[Dict]:
    print("📡 爬取 @daybuy 頻道（最近 " + str(days_back) + " 天）...")

    try:
        r = requests.get(TG_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("  ❌ 無法連線：" + str(e))
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    messages = soup.find_all(class_="tgme_widget_message_wrap")
    print("  找到 " + str(len(messages)) + " 則訊息")

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days_back)
    cached_ids = load_cache()
    products = []
    new_ids = set()

    for msg in messages:
        msg_id = msg.get("data-post", "") or ""

        time_el = msg.find("time")
        if not time_el:
            continue
        dt_str = time_el.get("datetime", "")
        try:
            dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
        except Exception:
            continue

        if dt < cutoff:
            continue

        text_el = msg.find(class_="tgme_widget_message_text")
        if not text_el:
            continue
        text = text_el.get_text("\n")

        links = [a.get("href", "") for a in text_el.find_all("a", href=True)]
        daybuy_link = next((l for l in links if "daybuy.tw" in l), "")

        if not re.search(r"省|折|特價|現省|現折|折扣|限時", text):
            continue

        disc_info = extract_discount_info(text)
        if not disc_info["折扣金額"] and not disc_info["折扣後售價"]:
            continue

        name = extract_product_name(text)
        if not name:
            continue
        # 過濾明顯不是商品名的文字（廣告/活動訊息）
        skip_words = ["情報", "看這裡", "連結", "網址", "完整資訊", "更多資訊",
                      "好市多限時", "facebook", "社友", "驚喜", "活動", "抽獎",
                      "號外", "文末", "限時特價"]
        if any(w in name for w in skip_words):
            continue
        # 名稱太短或以【開頭（廣告格式）
        if len(name) < 3 or name.startswith("【"):
            continue
        # 沒有 daybuy.tw 連結 且 名稱是廣告格式
        if not daybuy_link and ("facebook" in text.lower() or "instagram" in text.lower()):
            continue

        period = extract_period(text)

        # 去 daybuy.tw 補充原價、優惠期間、正確商品名
        article_data: Dict = {}
        if daybuy_link:
            article_data = fetch_daybuy_article(daybuy_link)
            # 優先用文章的優惠期間（比 Telegram 訊息更精確）
            if article_data.get("優惠期間"):
                period = article_data["優惠期間"]
            # 優先用文章的商品名稱（更完整）
            if article_data.get("商品名稱_daybuy") and len(article_data["商品名稱_daybuy"]) > len(name):
                name = article_data["商品名稱_daybuy"]
            # 補充原價（Telegram 通常沒有）
            if article_data.get("原價") and not disc_info["原價"]:
                disc_info["原價"] = article_data["原價"]
                if disc_info["折扣金額"] and disc_info["原價"]:
                    disc_info["折扣後售價"] = disc_info["原價"] - disc_info["折扣金額"]
                    # 如果 daybuy.tw 有折扣後售價，用它（更準確）
                    if article_data.get("折扣後售價_daybuy"):
                        disc_info["折扣後售價"] = article_data["折扣後售價_daybuy"]
                    pct = round(disc_info["折扣金額"] / disc_info["原價"] * 100, 1)
                    disc_info["折扣幅度"] = str(pct) + "%"
            # 驗證優惠是否過期
            if article_data.get("已過期", False):
                print("  ⏰ 跳過已過期：" + name[:30])
                continue

        new_ids.add(msg_id)

        product = {
            "商品名稱": name,
            "分類": "精選優惠",
            "原價": disc_info["原價"],
            "折扣金額": disc_info["折扣金額"],
            "折扣幅度": disc_info["折扣幅度"],
            "折扣後售價": disc_info["折扣後售價"],
            "優惠期間": period,
            "優惠結束日": article_data.get("優惠結束日", ""),
            "實體賣場": True,
            "實體狀態": "🏪 賣場確認",
            "網路討論": True,
            "討論來源": "daybuy @daybuy",
            "討論連結": daybuy_link,
            "圖片URL": article_data.get("圖片URL", ""),
            "商品連結": daybuy_link,
            "官網連結": ("https://www.costco.com.tw/p/" + article_data["商品編號"]) if article_data.get("商品編號") else "",
            "抓取時間": datetime.datetime.now().isoformat(timespec="seconds"),
            "來源": "daybuy_tg",
            "訊息時間": dt.strftime("%Y-%m-%d %H:%M"),
            "商品編號": article_data.get("商品編號", ""),
            "期間來源": "daybuy_article" if article_data.get("優惠期間") else ("daybuy_tg" if period else ""),
        }
        products.append(product)

        print("  🏪 [" + dt.strftime('%m/%d') + "] " + name[:30].ljust(30) +
              " 折扣=" + str(disc_info['折扣金額'] or '-') +
              "  特價=" + str(disc_info['折扣後售價'] or '-'))

    save_cache(cached_ids | new_ids)
    print("\n  ✅ 解析出 " + str(len(products)) + " 個有折扣商品")
    return products


def merge_with_official(official: List[Dict], daybuy: List[Dict]) -> List[Dict]:
    if not daybuy:
        return official

    official_names = {p["商品名稱"][:8] for p in official}
    merged = list(official)
    added = 0

    for p in daybuy:
        name_key = p["商品名稱"][:8]
        if name_key not in official_names:
            merged.append(p)
            official_names.add(name_key)
            added += 1

    print("📊 合併結果：官網 " + str(len(official)) + " + daybuy 新增 " + str(added) + " = 共 " + str(len(merged)) + " 筆")
    return merged


if __name__ == "__main__":
    products = fetch_daybuy_channel(days_back=7)
    print("\n共解析 " + str(len(products)) + " 個商品")
    for p in products:
        print("  " + p['商品名稱'][:35].ljust(35) +
              " 原=" + str(p['原價']) +
              " 折=" + str(p['折扣金額']) +
              " 特=" + str(p['折扣後售價']))
