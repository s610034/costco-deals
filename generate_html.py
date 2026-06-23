#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_html.py - 產生手機優先的響應式 HTML 報告"""

import json, os, datetime, re, hashlib
from typing import List, Dict


def fetch_sighting_articles(days: int = 7) -> list:
    """從 daybuy 抓最近 N 天內的賣場目擊情報文章（兩個來源）"""
    try:
        import requests
        from bs4 import BeautifulSoup
        import datetime

        headers = {"User-Agent": "Mozilla/5.0"}
        # 三個來源：賣場優惠目擊 + 隱藏優惠懶人包 + 品牌特展目擊（哈根達斯等現場特展）
        sources = [
            "https://www.daybuy.tw/costco/hypermarket-news/",
            "https://www.daybuy.tw/costco/hypermarket-news/hypermarket-sale/",
            "https://www.daybuy.tw/costco/hypermarket-news/brand-event/",
        ]
        combined_html = ""
        for src_url in sources:
            try:
                r = requests.get(src_url, headers=headers, timeout=8)
                combined_html += r.text
            except Exception:
                pass
        soup = BeautifulSoup(combined_html, "html.parser")

        today = datetime.date.today()
        cutoff = today - datetime.timedelta(days=days)

        articles, seen = [], set()
        for a in soup.select('a[href*="/costco/"]'):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or len(title) < 8 or href in seen:
                continue
            if not (re.search(r"/costco/\d+/", href) and any(
                kw in title for kw in ["賣場", "隱藏", "情報", "目擊", "現場", "穿搭", "週報", "特展"]
            )):
                continue

            # 從標題解析日期，取所有日期中最晚的（週報用結束日期）
            # 支援 2026/06/09、2026.06.09、06.09(二) 等格式
            year = today.year
            parsed = []
            # 完整日期 yyyy/mm/dd 或 yyyy.mm.dd
            for y, m, d in re.findall(r"(\d{4})[/\.](\d{1,2})[/\.](\d{1,2})", title):
                try: parsed.append(datetime.date(int(y), int(m), int(d)))
                except ValueError: pass
            # 短日期 mm.dd 或 mm/dd（補當年）
            for m, d in re.findall(r"(?<!\d)(\d{1,2})[./](\d{2})(?![\d/.])", title):
                try:
                    dt = datetime.date(year, int(m), int(d))
                    # 如果超過今天很多，可能是去年
                    if dt > today + datetime.timedelta(days=30):
                        dt = datetime.date(year - 1, int(m), int(d))
                    parsed.append(dt)
                except ValueError: pass
            if parsed:
                art_date = max(parsed)
                if art_date < cutoff:
                    continue

            seen.add(href)
            articles.append({"title": title, "url": href})

        # 列表頁若暫時故障(如 daybuy 500 錯誤)，文章抓不到時用已知清單 fallback
        # 這份清單會隨時間過期，daybuy 恢復正常後上面的爬取邏輯會自動取代它
        if not articles:
            fallback = [
                {"title": "COSTCO好市多 本週限時隱藏優惠懶人包 2026 06.22(一)~06.28(日)",
                 "url": "https://www.daybuy.tw/costco/256120/"},
                {"title": "COSTCO好市多 2026/06/23 週二賣場隱藏優惠目擊情報",
                 "url": "https://www.daybuy.tw/costco/256283/"},
                {"title": "HAAGEN DAZS 哈根達斯冰淇淋特展 2026.06.08~2026.07.05",
                 "url": "https://www.daybuy.tw/costco/256402/"},
            ]
            return fallback

        return articles
    except Exception as e:
        print(f"  ⚠️  抓取目擊情報失敗：{e}")
        return []

CATEGORY_RULES = [
    ("🐾 寵物用品", ["貓","狗","寵物","貓糧","狗糧","貓砂","Mon Petit","貓倍麗","愛貓","愛犬","Cat","Dog","Pet","Litter"]),
    ("🍱 食品飲料", ["咖啡","茶","飲料","果汁","零食","餅乾","糖果","巧克力","冰淇淋","哈根達斯","HAAGEN","Dazs","堅果","麵包","蛋糕","米","麵","泡麵","醬","油","鹽","糖","牛奶","優格","起司","雞蛋","肉","魚","海鮮","蔬菜","水果","冷凍","罐頭","即食","披薩","烘焙","食品","料理","湯","粥","燕麥","穀物","蜂蜜","果醬","汽水","氣泡水","卡迪那","野村","椰子汁","乾酪","豆腐","蛋捲","果乾","洋芋片","果凍","奶酪","拿鐵","威化","乳酸菌","高麗蔘","Barista","Coffee","Tea","Snack","Food","A&W","KOH","Tree Top","Laughing Cow","啤酒","麒麟","一番搾","Kirin","拉麵","炸物","RODEO"]),
    ("🧴 保健美妝", ["維他命","魚油","保健","益生菌","葉黃素","膠原蛋白","乳清蛋白","營養","保養","面膜","乳液","精華","洗面","防曬","沐浴乳","洗髮","護髮","牙膏","牙刷","護齦","電動牙刷","音波","美妝","香水","刮鬍","除毛","蔘","威德","補給","Blackmores","Webber","Vitamin","Omega","Fish Oil","Protein","Probiotic","Collagen","sum37","su:m","漱口水","LISTERINE","李施德霖","牙周","潔牙","舒酸定","PRONAMEL","口腔","Sonicare"]),
    ("📺 家電 3C",  ["電視","冰箱","洗衣機","冷氣","空調","除濕","空氣清淨","吸塵器","掃地機","烤箱","微波爐","電鍋","咖啡機","果汁機","電磁爐","電熱水瓶","手機","平板","筆電","電腦","耳機","喇叭","相機","印表機","路由器","充電","電池","吹風機","升降桌","Samsung","Panasonic","LG","Sony","Philips","Honeywell","Dyson","Roomba","Tescom","Flexispot","iPhone","iPad","Apple","Daikin","大金","國際牌","象印","Zojirushi","Oster","Breville","Nespresso","Duracell","金頂","TV","Washer","Fridge","Purifier","Vacuum"]),
    ("🏠 生活用品", ["衛生紙","紙巾","廚房紙","濕紙巾","垃圾袋","保鮮膜","清潔劑","洗碗","洗衣精","柔軟精","除菌","消毒","收納","整理箱","燈泡","蠟燈","濾水","廚具","鍋具","餐具","保溫瓶","保溫杯","水壺","小蘇打","除臭","滅蟑","花灑","保鮮盒","折疊椅","Kirkland","科克蘭","ARM","HAMMER","Neoflam","Stakmore","Tissue","Paper","Detergent","Cleaner"]),
    ("👕 服飾寢具", ["衣服","褲子","上衣","外套","羽絨","襪子","內衣","運動服","泳衣","鞋","包包","帽子","棉被","枕頭","床墊","床單","毛毯","毛巾","浴巾","寢具","Polo衫","Jacket","Shirt","Pants","Shoes","Bedding","Pillow","Blanket","Towel","Timberland","Advent","Well Worn"]),
    ("🧸 玩具育兒", ["玩具","積木","嬰兒","尿布","拉拉褲","紙尿褲","奶粉","奶瓶","推車","兒童","童裝","桌遊","拼圖","幫寶適","好奇","Toy","Baby","Diaper","Kids","LEGO","Pampers","Huggies"]),
    ("🏋️ 運動戶外", ["運動","健身","瑜珈","自行車","登山","露營","帳篷","球","球拍","游泳","跑步","舉重","按摩","Coleman","Sport","Fitness","Outdoor","Camping","Gym"]),
]
OTHER_CATEGORY = "📦 其他"
ALL_CATS = [r[0] for r in CATEGORY_RULES] + [OTHER_CATEGORY]

LIMITED_TIME_KEYWORDS = ["優惠週","限時","特展","期間限定","只到","限量","快閃"]


def classify_product(name: str) -> str:
    for cat_name, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in name.lower():
                return cat_name
    return OTHER_CATEGORY


def normalize_deal_category(product: Dict) -> Dict:
    deal_cat = product.get("分類", "")
    if "限時" in deal_cat:
        return product
    combined = " ".join([
        deal_cat,
        product.get("ptt_標題", "") or "",
        product.get("優惠期間", "") or "",
        product.get("商品名稱", "") or "",
    ])
    for kw in LIMITED_TIME_KEYWORDS:
        if kw in combined:
            product["分類"] = "限時優惠"
            return product
    return product


def generate_html(products: List[Dict], output_path: str) -> str:
    # 讀取 DB 分類覆蓋
    try:
        from database import get_all_category_overrides
        db_overrides = get_all_category_overrides()
    except Exception:
        db_overrides = {}

    # 讀取密碼 hash
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_pw = "costco2024"
    try:
        with open(os.path.join(base_dir, ".env")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("EDITOR_PASSWORD="):
                    env_pw = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
    pw_hash = hashlib.sha256(env_pw.encode()).hexdigest()

    today      = datetime.datetime.now()
    date_str   = today.strftime("%Y/%m/%d")
    week_range = _get_week_range()

    # 套用分類和限時歸類
    for p in products:
        normalize_deal_category(p)
        p["細分類"] = classify_product(p.get("商品名稱", ""))

    # DB 覆蓋：用商品連結的 card_id 對應
    link_overrides: Dict[str, str] = {}
    for card_id, cat in db_overrides.items():
        link_overrides[card_id] = cat

    # 分組
    categories: Dict[str, List] = {}
    for p in products:
        categories.setdefault(p["細分類"], []).append(p)
    for cat in categories:
        categories[cat].sort(key=lambda x: x.get("折扣金額") or 0, reverse=True)

    ordered_cats = [r[0] for r in CATEGORY_RULES if r[0] in categories]
    if OTHER_CATEGORY in categories:
        ordered_cats.append(OTHER_CATEGORY)

    total       = len(products)
    hotbuys_cnt = sum(1 for p in products if "限時" in p.get("分類",""))
    # 抓取最新目擊情報（隱藏優惠區塊用）
    sighting_articles = fetch_sighting_articles(days=7)
    coupon_cnt  = sum(1 for p in products if "精選" in p.get("分類","") and "限時" not in p.get("分類",""))
    both_cnt    = sum(1 for p in products if "限時" in p.get("分類","") and "精選" in p.get("分類",""))
    all_cats_js = json.dumps(ALL_CATS, ensure_ascii=False)
    db_overrides_js = json.dumps(db_overrides, ensure_ascii=False)

    # 產生卡片
    all_cards_html = ""
    for cat in ordered_cats:
        for p in categories[cat]:
            name      = p.get("商品名稱", "")
            orig      = p.get("原價")
            amt       = p.get("折扣金額")
            sale      = p.get("折扣後售價")
            pct       = p.get("折扣幅度", "")
            period    = p.get("優惠期間", "").strip()
            img       = p.get("圖片URL", "")
            link      = p.get("商品連結", "#")
            deal_cat  = p.get("分類", "")
            disc_url  = p.get("討論連結", "")
            days      = p.get("距上次折扣天數")
            price_chg = p.get("價格變化", "")
            cat_id    = re.sub(r"[^\w]", "_", p["細分類"])
            card_id   = "c_" + re.sub(r"[^\w]", "_", link[-35:])

            # 套用 DB 覆蓋分類
            actual_cat_id = link_overrides.get(card_id, cat_id)

            if "限時" in deal_cat and "精選" in deal_cat: deal_val = "both"
            elif "限時" in deal_cat:  deal_val = "hotbuys"
            elif "精選" in deal_cat:  deal_val = "coupon"
            else:                     deal_val = "other"

            # 優惠類型小標籤
            if deal_val == "hotbuys":
                deal_badge_html = '<span class="deal-type-badge badge-hot">⏰ 限時優惠</span>'
            elif deal_val == "coupon":
                deal_badge_html = '<span class="deal-type-badge badge-coup">🏷️ 精選優惠</span>'
            elif deal_val == "both":
                deal_badge_html = '<span class="deal-type-badge badge-hot">⏰ 限時優惠</span>'
            else:
                deal_badge_html = ''

            # 資料來源標籤（動態判斷，反映折扣資料時效性，不寫死 DB）
            disc_url = p.get("討論連結", "") or ""
            data_src = p.get("資料來源", "") or ""
            is_hidden = data_src == "hidden_sighting" or ("daybuy.tw" in disc_url and p.get("實體賣場"))
            if is_hidden:
                deal_badge_html += '<span class="deal-type-badge badge-hidden" title="人工confirm的賣場隱藏優惠，折扣可能隨時異動">🏪 賣場隱藏</span>'
            elif "daybuy.tw" in disc_url and not p.get("分類","") in ("限時優惠","精選優惠"):
                deal_badge_html += '<span class="deal-type-badge badge-daybuy" title="daybuy情報來源，建議以官網現場為準">📰 daybuy</span>'

            orig_str = f"${orig:,}" if orig else ""
            sale_str = f"${sale:,}" if sale else ""
            amt_str  = f"省 ${amt:,}" if amt else ""

            img_html    = f'<img src="{img}" alt="{name}" loading="lazy" onerror="this.style.display=\'none\'">' if img else '<div class="no-img">📦</div>'
            badge_html  = f'<div class="badge">-{pct}</div>' if pct else ""
            # 限定門市標籤
            location = p.get("限定門市", "")
            location_html = f'<span class="location-badge">📍 {location}限定</span>' if location else ""

            # 優惠期間標籤：有日期就顯示日期，沒有則依分類顯示標籤
            # 解析結束日，計算倒數
            countdown_html = ""
            if period and deal_val in ("hotbuys", "both"):
                import re as _re
                end_m = _re.search(r"(\d{1,2})/(\d{1,2})(?:\(.*?\))?\s*$", period.replace("~","-").split("-")[-1].strip())
                if end_m:
                    import datetime as _dt
                    _td = _dt.date.today()
                    end_month, end_day = int(end_m.group(1)), int(end_m.group(2))
                    if 1 <= end_month <= 12 and 1 <= end_day <= 31:
                        try:
                            end_year = _td.year if end_month >= _td.month else _td.year + 1
                            end_date = _dt.date(end_year, end_month, end_day)
                            days_left = (end_date - _td).days
                            if days_left >= 0:
                                if days_left == 0:
                                    countdown_html = '<span class="countdown urgent">⏰ 今天到期！</span>'
                                elif days_left <= 3:
                                    countdown_html = f'<span class="countdown urgent">⏰ 倒數 {days_left} 天</span>'
                                else:
                                    countdown_html = f'<span class="countdown">⏰ 剩 {days_left} 天</span>'
                        except ValueError:
                            pass

            # 賣場隱藏優惠：顯示「最後確認日」暫時性標籤（折扣可能已變動，提醒使用者）
            confirm_date_html = ""
            if is_hidden:
                cdate = p.get("crawl_date", "")
                if cdate and len(cdate) == 8:
                    cdate_fmt = f"{cdate[4:6]}/{cdate[6:8]}"
                    confirm_date_html = f'<span class="confirm-date-hint" title="此折扣為人工confirm的暫時性資料，僅代表{cdate_fmt}當時確認狀態，可能已變動">🕐 {cdate_fmt}確認</span>'

            if period:
                # daybuy 來源的期間可能是從文章頁面推測的，加上標記
                period_src = p.get("期間來源", "")
                if period_src in ("daybuy_article", "daybuy_tg") and deal_val not in ("hotbuys",):
                    period_html = f'<p class="deal-period">📅 {period} <span class="period-hint">（daybuy）</span>{confirm_date_html}</p>'
                else:
                    period_html = f'<p class="deal-period">📅 {period}{confirm_date_html}</p>'
            elif "把握" in deal_cat:
                period_html = '<p class="deal-period">🔥 把握優惠（數量有限）</p>'
            else:
                period_html = ""

            src_icon = ""
            daybuy_link_html = ""
            disc_url = p.get("討論連結", "") or p.get("商品連結_官網", "")

            # 判斷是否有 daybuy 連結
            orig_link = p.get("商品連結", "")
            has_daybuy = "daybuy.tw" in orig_link or ("daybuy.tw" in disc_url)

            code = p.get("商品編號", "")

            if has_daybuy:
                daybuy_url = orig_link if "daybuy.tw" in orig_link else disc_url
                # 官網連結
                official_url = p.get("官網連結", "") or (f"https://www.costco.com.tw/p/{code}" if code else "")
                # 如果主連結是官網，官網連結就是主連結本身
                if not official_url and "costco.com.tw" in orig_link:
                    official_url = orig_link
                src_icon = f'<a class="src-icon" href="{daybuy_url}" target="_blank" onclick="event.stopPropagation()" title="daybuy 情報">📰</a>'
                if official_url and official_url != daybuy_url:
                    daybuy_link_html = (
                        f'<a class="daybuy-link official-link" href="{official_url}" target="_blank" onclick="event.stopPropagation()">🛒 好市多官網</a>'
                        f'<a class="daybuy-link" href="{daybuy_url}" target="_blank" onclick="event.stopPropagation()">📰 daybuy 情報頁</a>'
                    )
                else:
                    daybuy_link_html = f'<a class="daybuy-link" href="{daybuy_url}" target="_blank" onclick="event.stopPropagation()">📰 daybuy 情報頁</a>'
            elif disc_url and "daybuy.tw" in disc_url:
                # 主連結是官網但有 daybuy 討論連結
                official_url = orig_link if "costco.com.tw" in orig_link else (f"https://www.costco.com.tw/p/{code}" if code else "")
                src_icon = f'<a class="src-icon" href="{disc_url}" target="_blank" onclick="event.stopPropagation()" title="daybuy 情報">📰</a>'
                if official_url:
                    daybuy_link_html = (
                        f'<a class="daybuy-link official-link" href="{official_url}" target="_blank" onclick="event.stopPropagation()">🛒 好市多官網</a>'
                        f'<a class="daybuy-link" href="{disc_url}" target="_blank" onclick="event.stopPropagation()">📰 daybuy 情報頁</a>'
                    )
                else:
                    daybuy_link_html = f'<a class="daybuy-link" href="{disc_url}" target="_blank" onclick="event.stopPropagation()">📰 daybuy 情報頁</a>'
            elif p.get("實體賣場"):
                src_icon = '<span class="src-icon" title="線上售價與賣場相同">🏪</span>'

            history_html = ""
            if days is not None:
                history_html = f'<p class="history">🕐 距上次折扣 {days} 天</p>'
            elif price_chg == "首次出現":
                history_html = '<p class="history">🆕 首次出現</p>'

            name_esc = name.replace("'", "\\'")
            link_esc = link.replace("'", "\\'")

            all_cards_html += f'''<div class="card" id="{card_id}" data-cat="{actual_cat_id}" data-deal="{deal_val}">
  <a href="{link}" target="_blank" rel="noopener" class="card-link">
    <div class="card-img">{img_html}{badge_html}{src_icon}</div>
    <div class="card-body">
      <p class="card-name">{name}</p>
      {deal_badge_html}{countdown_html}
      {location_html}
      {period_html}
      <div class="card-price">
        <span class="orig">{orig_str}</span>{"<span class='arrow'>→</span>" if orig_str else ""}
        <span class="sale">{sale_str}</span>
      </div>
      <p class="card-save">{amt_str}</p>
      {history_html}
    </div>
  </a>
  <button class="change-cat-btn" onclick="openCatModal('{card_id}','{actual_cat_id}','{name_esc}','{link_esc}')" title="修改分類（需登入）">✏️</button>
  {daybuy_link_html}
</div>
'''

    # Header 篩選
    both_btn = f'<button class="hf-btn hf-both" onclick="dealFilter(\'both\',this)">🔥 兩者皆有 <span>{both_cnt}</span></button>' if both_cnt else ""
    # 隱藏優惠區塊 HTML
    if sighting_articles:
        sighting_cards = ""
        for art in sighting_articles:
            title = art['title']
            url = art['url']
            # 判斷類型 emoji
            if "懶人包" in title:
                icon = "📋"
            elif "隱藏" in title:
                icon = "🕵️"
            elif "穿搭" in title:
                icon = "👗"
            elif "新商品" in title or "週報" in title:
                icon = "🆕"
            elif "試吃" in title:
                icon = "🍽️"
            else:
                icon = "🏪"
            sighting_cards += f'''<a class="sighting-card" href="{url}" target="_blank" rel="noopener">
  <span class="sighting-icon">{icon}</span>
  <span class="sighting-title">{title}</span>
  <span class="sighting-arrow">→</span>
</a>
'''
        sighting_section = f'''<div class="sighting-section" id="sightingSection">
  <div class="sighting-header">🕵️ 賣場隱藏優惠情報 <span class="sighting-sub">（資料來源：daybuy，點擊查看圖片）</span></div>
  {sighting_cards}
</div>'''
    else:
        sighting_section = ""

    header_filters = f'''<div class="header-filters">
  <button class="hf-btn hf-all active" onclick="dealFilter(\'all\',this)">全部 <span>{total}</span></button>
  <button class="hf-btn hf-hot" onclick="dealFilter(\'hotbuys\',this)">⏰ 限時優惠 <span>{hotbuys_cnt}</span></button>
  <button class="hf-btn hf-coup" onclick="dealFilter(\'coupon\',this)">🏷️ 精選優惠 <span>{coupon_cnt}</span></button>
  {both_btn}
</div>'''

    # Tabs
    tabs_html = '<button class="tab active" data-catid="all" onclick="catFilter(\'all\',this)">🏠 全部 <span class="tab-count">' + str(total) + '</span></button>\n'
    for cat in ordered_cats:
        cid = re.sub(r"[^\w]", "_", cat)
        tabs_html += f'<button class="tab" data-catid="{cid}" onclick="catFilter(\'{cid}\',this)">{cat} <span class="tab-count">{len(categories[cat])}</span></button>\n'

    # Modal 選項
    modal_options = "\n".join(
        f'<button class="modal-cat-btn" data-cat="{re.sub(chr(92) + "W", "_", c)}" onclick="selectCat(\'{re.sub(chr(92) + "W", "_", c)}\')">{c}</button>'
        for c in ALL_CATS
    )

    build_time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>好市多折扣週報 {date_str}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--red:#E3001B;--orange:#d97706;--bg:#f4f4f4;--text:#1a1a1a;--sub:#666;--border:#e0e0e0;--radius:12px;--shadow:0 2px 12px rgba(0,0,0,.08)}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif;background:var(--bg);color:var(--text)}}
header{{background:var(--red);color:#fff;padding:14px 16px 0;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.header-row{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
header h1{{font-size:1.1rem;font-weight:700}}
header .meta{{font-size:.72rem;opacity:.85}}
header .total{{background:rgba(255,255,255,.2);border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:600;margin-left:auto}}
.login-wrap{{position:relative;margin-left:8px}}
.login-btn{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.4);color:#fff;border-radius:20px;padding:3px 10px;font-size:.7rem;cursor:pointer}}
.login-btn.logged-in{{background:rgba(255,255,255,.3)}}
.editor-menu{{position:absolute;top:calc(100% + 6px);right:0;background:#fff;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.15);overflow:hidden;min-width:130px;display:none;z-index:300}}
.editor-menu button{{display:block;width:100%;padding:10px 16px;border:none;background:none;font-size:.82rem;cursor:pointer;text-align:left}}
.editor-menu button:hover{{background:#f5f5f5}}
.editor-menu .logout-btn{{color:#dc2626;border-top:1px solid #eee}}
.header-filters{{display:flex;gap:6px;margin-top:10px;overflow-x:auto;padding-bottom:10px;scrollbar-width:none}}
.header-filters::-webkit-scrollbar{{display:none}}
.hf-btn{{flex-shrink:0;border:none;border-radius:20px;padding:5px 13px;font-size:.75rem;font-weight:700;cursor:pointer;white-space:nowrap}}
.sighting-section{{display:none;padding:12px 12px 4px;border-bottom:1px solid var(--color-border-tertiary)}}
.sighting-section.visible{{display:block}}
.sighting-header{{font-size:.78rem;font-weight:700;color:var(--color-text-secondary);margin-bottom:8px}}
.sighting-sub{{font-weight:400;font-size:.72rem;opacity:.75}}
.sighting-card{{display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:6px;background:var(--color-background-secondary);border-radius:8px;text-decoration:none;color:var(--color-text-primary);border:1px solid var(--color-border-tertiary);transition:.15s}}
.sighting-card:hover{{background:var(--color-background-tertiary);border-color:var(--color-border-secondary)}}
.sighting-icon{{font-size:1.1rem;flex-shrink:0}}
.sighting-title{{flex:1;font-size:.78rem;line-height:1.3}}
.sighting-arrow{{color:var(--color-text-secondary);font-size:.8rem;flex-shrink:0}}
.hf-btn span{{background:rgba(0,0,0,.15);border-radius:20px;padding:1px 7px;margin-left:4px;font-size:.68rem}}
.hf-all{{background:rgba(255,255,255,.2);color:#fff}}.hf-all.active{{background:#fff;color:var(--red)}}
.hf-hot{{background:rgba(255,200,0,.3);color:#fff}}.hf-hot.active{{background:#fef9c3;color:#854d0e}}
.hf-coup{{background:rgba(99,102,241,.3);color:#fff}}.hf-coup.active{{background:#e0e7ff;color:#4338ca}}
.hf-both{{background:rgba(239,68,68,.3);color:#fff}}.hf-both.active{{background:#fee2e2;color:#b91c1c}}
.tabs-wrap{{background:#fff;border-bottom:2px solid var(--border);overflow-x:auto;white-space:nowrap;scrollbar-width:thin;-webkit-overflow-scrolling:touch;padding:0 4px;position:sticky;top:var(--header-h,0px);z-index:90;box-shadow:0 2px 4px rgba(0,0,0,.06)}}
.tab{{display:inline-block;padding:10px 12px;font-size:.78rem;font-weight:600;color:var(--sub);border:none;background:none;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap}}
.tab:hover,.tab.active{{color:var(--red);border-bottom-color:var(--red)}}
.tab-count{{background:var(--border);border-radius:20px;padding:1px 5px;font-size:.65rem;margin-left:2px}}.tab.active .tab-count{{background:var(--red);color:#fff}}
.search-wrap{{padding:10px 16px;background:#fff;border-bottom:1px solid var(--border)}}
.search-wrap input{{width:100%;padding:8px 14px;border:1.5px solid var(--border);border-radius:24px;font-size:.88rem;outline:none}}
.search-wrap input:focus{{border-color:var(--red)}}
main{{padding:12px;max-width:960px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:10px}}
.empty{{text-align:center;padding:48px 16px;color:var(--sub);font-size:.9rem;display:none}}
.card{{background:#fff;border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden;display:flex;flex-direction:column;border:1px solid var(--border);position:relative}}
.card:hover{{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,.12)}}
.card-link{{text-decoration:none;color:var(--text);display:flex;flex-direction:column;flex:1}}
.card-img{{position:relative;width:100%;aspect-ratio:1;background:#f9f9f9;overflow:hidden}}
.card-img img{{width:100%;height:100%;object-fit:contain;padding:8px}}
.no-img{{display:flex;align-items:center;justify-content:center;height:100%;font-size:2.5rem;opacity:.25}}
.badge{{position:absolute;top:6px;right:6px;background:var(--red);color:#fff;font-size:.66rem;font-weight:700;padding:2px 7px;border-radius:20px}}
.src-icon{{position:absolute;bottom:5px;left:6px;font-size:.85rem;text-decoration:none;opacity:.8}}
.deal-period{{font-size:.68rem;font-weight:600;color:#9a3412;background:#fff7ed;border-radius:4px;padding:2px 7px;margin-top:2px;margin-bottom:2px;display:inline-block}}
.card-body{{padding:9px;flex:1;display:flex;flex-direction:column;gap:3px}}
.card-name{{font-size:.8rem;font-weight:600;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.card-price{{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-top:auto;padding-top:5px}}
.orig{{font-size:.72rem;color:var(--sub);text-decoration:line-through}}
.arrow{{font-size:.65rem;color:var(--sub)}}
.sale{{font-size:.92rem;font-weight:700;color:var(--red)}}
.card-save{{font-size:.72rem;color:var(--orange);font-weight:600}}
.history{{font-size:.65rem;color:var(--sub);margin-top:2px}}
.cat-badge{{display:inline-block;font-size:.6rem;background:#e0f2fe;color:#0369a1;padding:1px 6px;border-radius:10px;margin-top:2px}}
.location-badge{{display:inline-block;font-size:.62rem;font-weight:700;color:#fff;background:#dc2626;padding:1px 7px;border-radius:10px;margin-top:2px}}
.deal-type-badge{{display:inline-block;font-size:.6rem;font-weight:600;padding:1px 6px;border-radius:8px;margin-top:2px}}
.countdown{{display:inline-block;font-size:.6rem;font-weight:700;padding:1px 6px;border-radius:8px;margin-top:2px;margin-left:3px;background:#fef9c3;color:#854d0e}}
.badge-hidden{{background:#fce7f3;color:#9d174d}}
.badge-daybuy{{background:#e0f2fe;color:#075985}}
.countdown.urgent{{background:#fee2e2;color:#991b1b;animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}
.badge-hot{{background:#fef3c7;color:#92400e}}
.badge-coup{{background:#ede9fe;color:#5b21b6}}
.change-cat-btn{{position:absolute;bottom:6px;right:6px;border:none;background:transparent;font-size:.75rem;cursor:pointer;opacity:0;pointer-events:none;padding:2px;transition:opacity .2s}}
.daybuy-link{{display:block;font-size:.65rem;color:#0369a1;text-align:center;padding:4px 8px;border-top:1px solid var(--border);background:#f0f9ff;text-decoration:none}}
.daybuy-link:hover{{background:#dbeafe}}
.official-link{{background:#f0fdf4;color:#166534}}
.official-link:hover{{background:#dcfce7}}
.period-hint{{font-size:.6rem;color:#92400e;opacity:.75}}
.confirm-date-hint{{font-size:.6rem;color:#9d174d;opacity:.8;margin-left:4px;background:#fce7f3;padding:1px 5px;border-radius:8px}}
.confirm-date-hint{{font-size:.6rem;color:#9d174d;opacity:.85;margin-left:4px;background:#fce7f3;padding:1px 5px;border-radius:8px}}
body.editor-mode .change-cat-btn{{opacity:.35;pointer-events:auto}}
body.editor-mode .change-cat-btn:hover{{opacity:1}}
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;align-items:flex-end;justify-content:center}}
.modal-overlay.open{{display:flex}}
.modal{{background:#fff;border-radius:20px 20px 0 0;width:100%;max-width:480px;padding:20px;max-height:80vh;overflow-y:auto}}
.modal-box{{background:var(--color-background-primary);border-radius:12px;width:90%;max-width:360px;padding:20px;margin:auto}}
.modal-title{{font-size:.95rem;font-weight:700;margin-bottom:4px}}
.modal-subtitle{{font-size:.75rem;color:var(--sub);margin-bottom:16px}}
.modal-cats{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}}
.modal-cat-btn{{border:2px solid var(--border);background:#fff;border-radius:10px;padding:10px 8px;font-size:.82rem;cursor:pointer;text-align:center}}
.modal-cat-btn:hover,.modal-cat-btn.selected{{border-color:var(--red);color:var(--red);background:#fff0f0;font-weight:700}}
.modal-cancel{{width:100%;padding:12px;border:none;background:var(--bg);border-radius:10px;font-size:.9rem;cursor:pointer;font-weight:600;color:var(--sub)}}
.login-modal{{background:#fff;border-radius:20px;width:90%;max-width:320px;padding:24px;margin:auto}}
.login-modal h3{{font-size:1rem;font-weight:700;margin-bottom:16px;text-align:center}}
.login-modal input{{width:100%;padding:10px 14px;border:1.5px solid var(--border);border-radius:10px;font-size:.9rem;outline:none;margin-bottom:12px}}
.login-modal input:focus{{border-color:var(--red)}}
.login-submit{{width:100%;padding:12px;background:var(--red);color:#fff;border:none;border-radius:10px;font-size:.9rem;font-weight:700;cursor:pointer}}
.login-error{{color:#dc2626;font-size:.78rem;text-align:center;margin-top:8px;display:none}}
.login-cancel{{width:100%;padding:10px;border:none;background:var(--bg);border-radius:10px;font-size:.9rem;cursor:pointer;font-weight:600;color:var(--sub);margin-top:8px}}
footer{{text-align:center;padding:20px;font-size:.72rem;color:var(--sub)}}
@media(min-width:600px){{.grid{{grid-template-columns:repeat(auto-fill,minmax(175px,1fr))}}.modal{{border-radius:20px;margin-bottom:20px}}}}
</style>
<script>
  // 版本控制：每次部署時更新，強制瀏覽器重新載入
  const BUILD_TIME = '{build_time}';
  const stored = localStorage.getItem('costco_build');
  if (stored && stored !== BUILD_TIME) {{
    localStorage.setItem('costco_build', BUILD_TIME);
    window.location.reload(true);
  }} else {{
    localStorage.setItem('costco_build', BUILD_TIME);
  }}
</script>
</head>
<body>
<header>
  <div class="header-row">
    <h1>🛒 好市多折扣週報</h1>
    <span class="meta">📅 {date_str}（{week_range}）</span>
    <span class="total">共 {total} 項</span>
    <div class="login-wrap">
      <button class="login-btn" id="loginToggleBtn" onclick="toggleLogin()">🔐 登入</button>
      <div class="editor-menu" id="editorMenu">
        <button onclick="syncNow()">☁️ 同步到雲端</button>
        <button onclick="openSetToken()">🔑 設定 GitHub Token</button>
        <button onclick="openChangePw()">🔒 修改密碼</button>
        <button class="logout-btn" onclick="logout()">🚪 登出</button>
      </div>
    </div>
  </div>
  {header_filters}
</header>

{sighting_section}

<div class="tabs-wrap">
{tabs_html}</div>

<div class="search-wrap">
  <input type="search" id="searchInput" placeholder="🔍 搜尋商品名稱..." oninput="applyFilter()">
</div>

<main>
  <div class="grid" id="grid">{all_cards_html}</div>
  <div class="empty" id="empty">😢 找不到符合的商品</div>
</main>

<div class="modal-overlay" id="tokenModal" onclick="if(event.target===this)closeTokenModal()">
  <div class="modal-box">
    <h3>🔑 GitHub Token 設定</h3>
    <div id="tokenCurrentStatus" style="font-size:.8rem;padding:8px;border-radius:6px;margin:.5rem 0;background:var(--color-background-secondary)">
      載入中...
    </div>
    <p style="font-size:.75rem;color:var(--color-text-secondary);margin:.25rem 0 .5rem">Token 僅存於本裝置，不會上傳至任何地方。<br>取得方式：github.com/settings/tokens → Generate new token (classic) → 勾選 repo + workflow</p>
    <input type="password" id="ghTokenInput" placeholder="ghp_xxxx 或 github_pat_xxxx" style="width:100%;padding:8px;border:1px solid var(--color-border-tertiary);border-radius:6px;font-size:.82rem;margin:.25rem 0;background:var(--color-background-secondary);color:var(--color-text-primary);box-sizing:border-box">
    <div style="display:flex;gap:8px;margin-top:.5rem">
      <button onclick="testToken()" style="flex:1;padding:8px;background:var(--color-background-tertiary);border:1px solid var(--color-border-secondary);border-radius:6px;cursor:pointer;font-size:.82rem">🧪 測試</button>
      <button onclick="saveToken()" style="flex:1;padding:8px;background:#1d4ed8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:.82rem">💾 儲存</button>
      <button onclick="clearToken()" style="padding:8px 12px;background:var(--color-background-tertiary);border:1px solid var(--color-border-secondary);border-radius:6px;cursor:pointer;font-size:.82rem">🗑️</button>
    </div>
    <p id="tokenStatus" style="font-size:.75rem;margin-top:.5rem;min-height:1.2em;color:var(--color-text-secondary)"></p>
  </div>
</div>

<footer>🤖 Hermes Agent 自動整理｜資料來源：costco.com.tw｜更新：{today.strftime("%Y-%m-%d %H:%M")}<br>🏪=賣場同售 📰=daybuy情報 ✏️=登入後可修改分類</footer>

<!-- 分類 Modal -->
<div class="modal-overlay" id="catModal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-title">修改商品分類</div>
    <div class="modal-subtitle" id="modalProductName"></div>
    <div class="modal-cats">{modal_options}</div>
    <button class="modal-cancel" onclick="closeModal()">取消</button>
  </div>
</div>

<!-- 登入 Modal -->
<div class="modal-overlay" id="loginModal" onclick="if(event.target===this)closeLoginModal()">
  <div class="login-modal">
    <div id="loginView">
      <h3>🔐 編輯者登入</h3>
      <input type="password" id="loginPwInput" placeholder="請輸入密碼" onkeydown="if(event.key==='Enter')doLogin()">
      <button class="login-submit" onclick="doLogin()">登入</button>
      <div class="login-error" id="loginError">密碼錯誤，請再試一次</div>
    </div>
    <div id="changePwView" style="display:none">
      <h3>🔑 修改密碼</h3>
      <input type="password" id="oldPwInput" placeholder="目前密碼">
      <input type="password" id="newPwInput" placeholder="新密碼（至少6字）">
      <input type="password" id="newPwInput2" placeholder="確認新密碼">
      <button class="login-submit" onclick="doChangePw()">確認修改</button>
      <div class="login-error" id="changePwError"></div>
      <button class="login-cancel" onclick="closeLoginModal()">取消</button>
    </div>
  </div>
</div>

<script>
const ALL_CATS = {all_cats_js};
const DB_OVERRIDES = {db_overrides_js};
const PW_HASH_DEFAULT = "{pw_hash}";
const CONFIG_URL = "https://raw.githubusercontent.com/s610034/costco-deals/main/data/config.json";
const CONFIG_API = "https://api.github.com/repos/s610034/costco-deals/contents/data/config.json";
const STORAGE_KEY = "costco_cat_overrides";
const SESSION_KEY = "costco_editor_session";
let currentDeal = "all", currentCat = "all";
let modalCardId = null, modalProductLink = "";
let isLoggedIn = false;
let _pwHash = PW_HASH_DEFAULT;

// 動態計算 header 高度，讓 tabs sticky 緊貼在 header 下
function updateHeaderHeight() {{
  const h = document.querySelector('header');
  if (h) document.documentElement.style.setProperty('--header-h', h.offsetHeight + 'px');
}}
window.addEventListener('DOMContentLoaded', updateHeaderHeight);
window.addEventListener('resize', updateHeaderHeight);

// 從 GitHub 載入最新密碼 hash
async function loadConfig() {{
  try {{
    const r = await fetch(CONFIG_URL + "?t=" + Date.now());
    if (r.ok) {{
      const cfg = await r.json();
      if (cfg.editor_pw_hash) _pwHash = cfg.editor_pw_hash;
    }}
  }} catch(e) {{}}
}}
loadConfig();

// SHA-256
async function sha256(msg) {{
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,"0")).join("");
}}

// 登入
async function doLogin() {{
  const pw = document.getElementById("loginPwInput").value;
  const hash = await sha256(pw);
  if (hash === _pwHash) {{
    isLoggedIn = true;
    sessionStorage.setItem(SESSION_KEY, "1");
    document.body.classList.add("editor-mode");
    document.getElementById("loginToggleBtn").textContent = "✏️ 編輯中 ▾";
    document.getElementById("loginToggleBtn").classList.add("logged-in");
    document.getElementById("loginError").style.display = "none";
    closeLoginModal();
  }} else {{
    document.getElementById("loginError").style.display = "block";
    document.getElementById("loginPwInput").value = "";
  }}
}}

function toggleLogin() {{
  if (isLoggedIn) {{
    const menu = document.getElementById("editorMenu");
    menu.style.display = menu.style.display === "block" ? "none" : "block";
    return;
  }}
  document.getElementById("loginView").style.display = "block";
  document.getElementById("changePwView").style.display = "none";
  document.getElementById("loginModal").classList.add("open");
  setTimeout(() => document.getElementById("loginPwInput").focus(), 100);
}}

function logout() {{
  isLoggedIn = false;
  sessionStorage.removeItem(SESSION_KEY);
  document.body.classList.remove("editor-mode");
  document.getElementById("loginToggleBtn").textContent = "🔐 登入";
  document.getElementById("loginToggleBtn").classList.remove("logged-in");
  document.getElementById("editorMenu").style.display = "none";
}}

function openChangePw() {{
  document.getElementById("editorMenu").style.display = "none";
  document.getElementById("loginView").style.display = "none";
  document.getElementById("changePwView").style.display = "block";
  document.getElementById("changePwError").style.display = "none";
  document.getElementById("oldPwInput").value = "";
  document.getElementById("newPwInput").value = "";
  document.getElementById("newPwInput2").value = "";
  document.getElementById("loginModal").classList.add("open");
  setTimeout(() => document.getElementById("oldPwInput").focus(), 100);
}}

async function doChangePw() {{
  const oldPw  = document.getElementById("oldPwInput").value;
  const newPw  = document.getElementById("newPwInput").value;
  const newPw2 = document.getElementById("newPwInput2").value;
  const errEl  = document.getElementById("changePwError");
  errEl.style.display = "none";
  if (newPw.length < 6) {{ errEl.textContent = "新密碼至少 6 字元"; errEl.style.display = "block"; return; }}
  if (newPw !== newPw2) {{ errEl.textContent = "兩次輸入不一致"; errEl.style.display = "block"; return; }}
  const oldHash = await sha256(oldPw);
  if (oldHash !== _pwHash) {{ errEl.textContent = "目前密碼錯誤"; errEl.style.display = "block"; return; }}
  const newHash = await sha256(newPw);
  _pwHash = newHash;
  const token = localStorage.getItem("costco_gh_token") || "";
  if (token) {{
    try {{
      const getR = await fetch(CONFIG_API, {{headers: {{"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"}}}});
      const data = await getR.json();
      const sha  = data.sha || "";
      const content = btoa(unescape(encodeURIComponent(JSON.stringify({{"editor_pw_hash": newHash, "version": 1}}, null, 2))));
      await fetch(CONFIG_API, {{method: "PUT", headers: {{"Authorization": "token " + token, "Content-Type": "application/json"}}, body: JSON.stringify({{"message": "update password hash", "content": content, "sha": sha}})}});
      closeLoginModal();
      alert("密碼已更新並同步到所有設備");
      return;
    }} catch(e) {{}}
  }}
  closeLoginModal();
  alert("密碼本次已更新（僅此分頁）");
}}

function closeLoginModal() {{
  document.getElementById("loginModal").classList.remove("open");
  document.getElementById("loginPwInput").value = "";
}}

// 恢復 session
if (sessionStorage.getItem(SESSION_KEY)) {{
  isLoggedIn = true;
  document.body.classList.add("editor-mode");
  document.getElementById("loginToggleBtn").textContent = "✏️ 編輯中 ▾";
  document.getElementById("loginToggleBtn").classList.add("logged-in");
}}

// 點其他地方關閉 editorMenu
document.addEventListener("click", e => {{
  const menu = document.getElementById("editorMenu");
  const btn  = document.getElementById("loginToggleBtn");
  if (!menu.contains(e.target) && e.target !== btn) menu.style.display = "none";
}});

// 分類 overrides（localStorage）
function getOverrides() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{{}}"); }} catch {{ return {{}}; }}
}}
function saveOverride(id, cat) {{
  const o = getOverrides(); o[id] = cat;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(o));
}}

// 手動觸發同步
async function syncNow() {{
  document.getElementById("editorMenu").style.display = "none";
  const token = localStorage.getItem("costco_gh_token") || "";
  if (!token) {{
    openSetToken();
    return;
  }}
  const btn = document.querySelector('#editorMenu button');
  const apiUrl = "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json";
  try {{
    // 讀取現有 overrides
    const getR = await fetch(apiUrl, {{headers: {{"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"}}}});
    let sha = "", existing = {{}};
    if (getR.ok) {{
      const d = await getR.json();
      sha = d.sha;
      const _b64 = d.content.replaceAll(String.fromCharCode(10), "");
      const _bytes = Uint8Array.from(atob(_b64), c => c.charCodeAt(0));
      existing = JSON.parse(new TextDecoder("utf-8").decode(_bytes));
    }}
    // 合併本地 overrides
    const local = getOverrides();
    Object.assign(existing, local);
    const encoded = new TextEncoder().encode(JSON.stringify(existing, null, 2));
    const encoded2 = btoa(String.fromCharCode(...encoded));
    const putR = await fetch(apiUrl, {{
      method: "PUT",
      headers: {{"Authorization": "token " + token, "Content-Type": "application/json"}},
      body: JSON.stringify({{"message": "sync: overrides " + Object.keys(existing).length + " 筆", "content": encoded2, "sha": sha}})
    }});
    if (putR.ok) {{
      alert("✅ 同步成功！所有設備將在重整後看到最新分類");
    }} else {{
      const err = await putR.json();
      alert("❌ 同步失敗：" + (err.message || putR.status));
    }}
  }} catch(e) {{
    alert("❌ 同步失敗：" + e.message);
  }}
}}

// Token 設定
function openSetToken() {{
  const existing = localStorage.getItem("costco_gh_token") || "";
  document.getElementById("ghTokenInput").value = existing ? "●".repeat(20) : "";
  document.getElementById("ghTokenInput").dataset.hasToken = existing ? "1" : "";
  document.getElementById("tokenStatus").textContent = "";
  // 顯示目前狀態
  const statusEl = document.getElementById("tokenCurrentStatus");
  if (existing) {{
    const masked = existing.slice(0,8) + "..." + existing.slice(-4);
    statusEl.innerHTML = "✅ 已設定 Token：<code style='background:var(--color-background-tertiary);padding:1px 4px;border-radius:3px'>" + masked + "</code>";
    statusEl.style.color = "var(--color-text-success)";
  }} else {{
    statusEl.textContent = "❌ 尚未設定 Token，同步功能無法使用";
    statusEl.style.color = "var(--color-text-danger)";
  }}
  document.getElementById("tokenModal").classList.add("open");
  setTimeout(() => document.getElementById("ghTokenInput").focus(), 100);
}}
function closeTokenModal() {{
  document.getElementById("tokenModal").classList.remove("open");
}}
async function testToken() {{
  const inputVal = document.getElementById("ghTokenInput").value.trim();
  const hasExisting = document.getElementById("ghTokenInput").dataset.hasToken;
  const token = (inputVal === "●".repeat(20) && hasExisting)
    ? localStorage.getItem("costco_gh_token")
    : inputVal;
  if (!token) {{ document.getElementById("tokenStatus").textContent = "⚠️ 請先輸入 Token"; return; }}
  document.getElementById("tokenStatus").textContent = "測試中...";
  try {{
    const r = await fetch("https://api.github.com/repos/s610034/costco-deals", {{
      headers: {{"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"}}
    }});
    if (r.ok) {{
      document.getElementById("tokenStatus").textContent = "✅ Token 有效！可以正常同步";
    }} else if (r.status === 401) {{
      document.getElementById("tokenStatus").textContent = "❌ Token 無效或已過期";
    }} else {{
      document.getElementById("tokenStatus").textContent = "⚠️ 狀態碼 " + r.status;
    }}
  }} catch(e) {{
    document.getElementById("tokenStatus").textContent = "❌ 測試失敗：" + e.message;
  }}
}}
function saveToken() {{
  const inputVal = document.getElementById("ghTokenInput").value.trim();
  const hasExisting = document.getElementById("ghTokenInput").dataset.hasToken;
  const token = (inputVal === "●".repeat(20) && hasExisting)
    ? localStorage.getItem("costco_gh_token")
    : inputVal;
  if (token && token !== "●".repeat(20)) {{
    localStorage.setItem("costco_gh_token", token);
    document.getElementById("tokenStatus").textContent = "✅ 已儲存";
    setTimeout(closeTokenModal, 800);
  }} else if (!token) {{
    clearToken();
  }}
}}
function clearToken() {{
  localStorage.removeItem("costco_gh_token");
  document.getElementById("ghTokenInput").value = "";
  document.getElementById("ghTokenInput").dataset.hasToken = "";
  document.getElementById("tokenCurrentStatus").textContent = "❌ 尚未設定 Token";
  document.getElementById("tokenStatus").textContent = "🗑️ Token 已清除";
  setTimeout(closeTokenModal, 800);
}}

// GitHub overrides.json 同步
async function syncToGitHub(cardId, catId, productName, productLink) {{
  const token = localStorage.getItem("costco_gh_token") || "";
  if (!token) return;
  const apiUrl = "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json";
  try {{
    const getR = await fetch(apiUrl, {{headers: {{"Authorization": "token " + token, "Accept": "application/vnd.github.v3+json"}}}});
    let sha = "", existing = {{}};
    if (getR.ok) {{
      const d = await getR.json();
      sha = d.sha;
      const _b64 = d.content.replaceAll(String.fromCharCode(10), "");
      const _bytes = Uint8Array.from(atob(_b64), c => c.charCodeAt(0));
      existing = JSON.parse(new TextDecoder("utf-8").decode(_bytes));
    }}
    existing[cardId] = {{cat: catId, name: productName, link: productLink}};
    const encoded = new TextEncoder().encode(JSON.stringify(existing, null, 2)); const content = btoa(String.fromCharCode(...encoded));
    await fetch(apiUrl, {{method: "PUT", headers: {{"Authorization": "token " + token, "Content-Type": "application/json"}}, body: JSON.stringify({{"message": "update category: " + cardId, "content": content, "sha": sha}})}});
  }} catch(e) {{}}
}}

// 套用分類覆蓋
function _applyCatToCard(card, catId, showBadge) {{
  card.dataset.cat = catId;
  const body = card.querySelector(".card-body");
  const ex = body.querySelector(".cat-badge");
  if (ex) ex.remove();
  // 不顯示手動改分類的標籤（保持和自動分類一樣的樣式）
}}

// Tab 數字更新
function updateTabCounts() {{
  // 根據目前的 deal 篩選計算各分類數量
  const counts = {{}};
  let total = 0;
  document.querySelectorAll(".card").forEach(card => {{
    const mDeal = currentDeal === "all" || card.dataset.deal === currentDeal;
    if (!mDeal) return;
    const cat = card.dataset.cat || "__其他";
    counts[cat] = (counts[cat] || 0) + 1;
    total++;
  }});
  document.querySelectorAll(".tab[data-catid]").forEach(tab => {{
    const catid = tab.dataset.catid;
    const span = tab.querySelector(".tab-count");
    if (!span) return;
    if (catid === "all") span.textContent = total;
    else span.textContent = counts[catid] || 0;
  }});
}}

// 初始化
const OVERRIDES_URL = "https://raw.githubusercontent.com/s610034/costco-deals/main/data/overrides.json";

// 從 GitHub 即時拉最新 overrides 並套用（每台設備都能拿到最新分類）
async function applyGitHubOverrides() {{
  try {{
    const r = await fetch(OVERRIDES_URL + "?t=" + Date.now());
    if (!r.ok) return;
    const overrides = await r.json();
    Object.entries(overrides).forEach(([id, data]) => {{
      const catId = typeof data === "object" ? data.cat : data;
      const card = document.getElementById(id);
      if (card && catId) _applyCatToCard(card, catId, false);
    }});
    updateTabCounts();
    applyFilter();
  }} catch(e) {{}}
}}

window.addEventListener("DOMContentLoaded", () => {{
  // 套用 DB 覆蓋（後端分好的）
  Object.entries(DB_OVERRIDES).forEach(([id, catId]) => {{
    const card = document.getElementById(id);
    if (card) _applyCatToCard(card, catId, false);
  }});
  // 套用 localStorage 覆蓋（離線備用）
  Object.entries(getOverrides()).forEach(([id, catId]) => {{
    const card = document.getElementById(id);
    if (card) _applyCatToCard(card, catId, true);
  }});
  updateTabCounts();
  applyFilter();
  // 從 GitHub 即時拉最新 overrides（覆蓋上面的，確保所有設備同步）
  applyGitHubOverrides();
}});

// 篩選
function dealFilter(val, el) {{
  // 再點一次同一個按鈕 → 取消篩選
  currentDeal = (currentDeal === val) ? "all" : val;
  // 隱藏優惠區塊：全部或限時優惠時顯示
  const sightEl = document.getElementById("sightingSection");
  if (sightEl) {{
    sightEl.classList.toggle("visible", currentDeal === "all" || currentDeal === "hotbuys");
  }}
  // 更新 hf-btn active 狀態
  document.querySelectorAll(".hf-btn").forEach(t => t.classList.remove("active"));
  if (currentDeal === "all") {{
    document.querySelector(".hf-all").classList.add("active");
  }} else {{
    el.classList.add("active");
  }}
  // 不重置 currentCat，讓分類篩選繼續作用
  updateTabCounts();
  applyFilter();
}}
function catFilter(cat, el) {{
  currentCat = cat;
  // 不重置 currentDeal，讓優惠類型篩選繼續作用
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");
  applyFilter();
}}
function applyFilter() {{
  const search = document.getElementById("searchInput").value.trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll(".card").forEach(card => {{
    const mDeal   = currentDeal === "all" || card.dataset.deal === currentDeal;
    const mCat    = currentCat  === "all" || card.dataset.cat  === currentCat;
    const mSearch = !search || card.querySelector(".card-name").textContent.toLowerCase().includes(search);
    const show = mDeal && mCat && mSearch;
    card.style.display = show ? "" : "none";
    if (show) visible++;
  }});
  document.getElementById("empty").style.display = visible === 0 ? "block" : "none";
}}

// 分類 Modal
function openCatModal(cardId, curCat, name, productLink) {{
  if (!isLoggedIn) {{
    document.getElementById("loginView").style.display = "block";
    document.getElementById("changePwView").style.display = "none";
    document.getElementById("loginModal").classList.add("open");
    setTimeout(() => document.getElementById("loginPwInput").focus(), 100);
    return;
  }}
  modalCardId = cardId;
  modalProductLink = productLink || "";
  document.getElementById("modalProductName").textContent = name || "";
  const card = document.getElementById(cardId);
  document.querySelectorAll(".modal-cat-btn").forEach(b =>
    b.classList.toggle("selected", b.dataset.cat === card.dataset.cat)
  );
  document.getElementById("catModal").classList.add("open");
}}
function closeModal() {{ document.getElementById("catModal").classList.remove("open"); modalCardId = null; }}
function selectCat(catId) {{
  if (!modalCardId || !isLoggedIn) return;
  const card = document.getElementById(modalCardId);
  const productName = document.getElementById("modalProductName").textContent;
  card.dataset.cat = catId;
  saveOverride(modalCardId, catId);
  _applyCatToCard(card, catId, true);
  syncToGitHub(modalCardId, catId, productName, modalProductLink);
  closeModal();
  updateTabCounts();
  applyFilter();
}}
</script>
</body>
</html>"""

    # 注入密碼 hash（已在 pw_hash 變數裡）
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🌐 HTML 報告已產生：{output_path}")
    return output_path


def _get_week_range() -> str:
    today  = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%m/%d')}～{sunday.strftime('%m/%d')}"


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    files = sorted([f for f in os.listdir(DATA_DIR) if f.startswith("costco_deals_") and f.endswith(".json")])
    if not files:
        print("找不到資料"); exit(1)
    with open(os.path.join(DATA_DIR, files[-1]), encoding="utf-8") as f:
        products = json.load(f)
    out = os.path.join(BASE_DIR, "docs", "index.html")
    generate_html(products, out)
    import subprocess
    subprocess.run(["open", out])
