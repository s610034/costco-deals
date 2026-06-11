#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_html.py
將折扣商品資料產生手機優先的響應式 HTML 報告
輸出到 docs/ 資料夾（GitHub Pages）
"""

import json
import os
import datetime
import re
from typing import List, Dict

# ── 商品分類關鍵字對照表（參考好市多官方分類）──────────────
CATEGORY_RULES = [
    ("🍱 食品飲料", [
        "咖啡", "茶", "飲料", "果汁", "零食", "餅乾", "糖果", "巧克力",
        "堅果", "麵包", "蛋糕", "米", "麵", "泡麵", "醬", "油", "鹽",
        "糖", "米粉", "牛奶", "優格", "起司", "雞蛋", "肉", "魚", "海鮮",
        "蔬菜", "水果", "冷凍", "罐頭", "即食", "披薩", "烘焙", "食品",
        "飲食", "料理", "湯", "粥", "燕麥", "穀物", "蜂蜜", "果醬",
        "Barista", "Coffee", "Tea", "Snack", "Food",
    ]),
    ("📺 家電 3C", [
        "電視", "冰箱", "洗衣機", "冷氣", "空調", "除濕", "空氣清淨",
        "吸塵器", "掃地機器人", "烤箱", "微波爐", "電鍋", "咖啡機",
        "果汁機", "電磁爐", "電熱水瓶", "手機", "平板", "筆電", "電腦",
        "耳機", "喇叭", "相機", "印表機", "路由器", "充電", "電池",
        "Samsung", "Panasonic", "LG", "Sony", "Philips", "Honeywell",
        "Dyson", "Roomba", "iPhone", "iPad", "Apple", "Daikin", "大金",
        "國際牌", "象印", "Zojirushi", "Oster", "Breville", "Nespresso",
        "TV", "Washer", "Fridge", "Purifier", "Vacuum", "Inverter",
    ]),
    ("🧴 保健美妝", [
        "維他命", "魚油", "保健", "益生菌", "葉黃素", "膠原蛋白",
        "乳清蛋白", "營養", "藥", "保養", "面膜", "乳液", "精華",
        "洗面", "防曬", "眼霜", "沐浴乳", "洗髮", "護髮", "牙膏",
        "牙刷", "化妝", "美妝", "香水", "刮鬍", "除臭",
        "Blackmores", "Webber", "Nature", "Vitamin", "Omega",
        "Fish Oil", "Protein", "Probiotic", "Collagen",
    ]),
    ("🏠 生活用品", [
        "衛生紙", "紙巾", "廚房紙", "濕紙巾", "垃圾袋", "保鮮膜",
        "鋁箔", "清潔劑", "洗碗", "洗衣精", "柔軟精", "漂白",
        "除菌", "消毒", "掃除", "拖把", "抹布", "收納", "整理箱",
        "衣架", "曬衣", "燈泡", "電池", "蠟燭", "香薰", "濾水",
        "廚具", "鍋具", "餐具", "保溫瓶", "保溫杯", "水壺",
        "Kirkland", "科克蘭", "Glad", "Hefty",
        "Tissue", "Paper", "Detergent", "Cleaner",
    ]),
    ("👕 服飾寢具", [
        "衣服", "褲子", "上衣", "外套", "羽絨", "襪子", "內衣",
        "運動服", "泳衣", "鞋", "包包", "皮帶", "帽子", "圍巾",
        "棉被", "枕頭", "床墊", "床單", "毛毯", "毛巾", "浴巾",
        "睡袋", "寢具", "Jacket", "Shirt", "Pants", "Shoes",
        "Bedding", "Pillow", "Blanket", "Towel",
    ]),
    ("🐾 寵物用品", [
        "貓", "狗", "寵物", "貓糧", "狗糧", "貓砂", "寵物零食",
        "寵物保健", "Cat", "Dog", "Pet", "Litter",
    ]),
    ("🧸 玩具育兒", [
        "玩具", "積木", "樂高", "嬰兒", "尿布", "奶粉", "奶瓶",
        "推車", "兒童", "童裝", "玩具車", "桌遊", "拼圖",
        "Toy", "Baby", "Diaper", "Kids", "LEGO",
    ]),
    ("🏋️ 運動戶外", [
        "運動", "健身", "瑜珈", "自行車", "登山", "露營", "帳篷",
        "球", "球拍", "游泳", "跑步", "舉重", "按摩",
        "Sport", "Fitness", "Outdoor", "Camping", "Gym",
    ]),
]

OTHER_CATEGORY = "📦 其他"


def classify_product(name: str) -> str:
    """根據商品名稱關鍵字判斷分類"""
    for cat_name, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in name.lower():
                return cat_name
    return OTHER_CATEGORY


def generate_html(products: List[Dict], output_path: str) -> str:
    today = datetime.datetime.now()
    date_str = today.strftime("%Y/%m/%d")
    week_range = _get_week_range()

    # 為每個商品加上細分類
    for p in products:
        p["細分類"] = classify_product(p.get("商品名稱", ""))

    # 依細分類分組，排序
    categories: Dict[str, List] = {}
    for p in products:
        cat = p["細分類"]
        categories.setdefault(cat, []).append(p)

    # 依折扣金額排序
    for cat in categories:
        categories[cat].sort(key=lambda x: x.get("折扣金額") or 0, reverse=True)

    # 分類排序：照 CATEGORY_RULES 順序，其他放最後
    ordered_cats = [r[0] for r in CATEGORY_RULES if r[0] in categories]
    if OTHER_CATEGORY in categories:
        ordered_cats.append(OTHER_CATEGORY)

    # ── 產生分類 Tab HTML ────────────────────────────────
    tabs_html = '<button class="tab active" onclick="filterCat(\'all\')">🏠 全部 <span class="tab-count">' + str(len(products)) + '</span></button>\n'
    for cat in ordered_cats:
        cat_id = re.sub(r'[^\w]', '_', cat)
        tabs_html += f'<button class="tab" onclick="filterCat(\'{cat_id}\')">{cat} <span class="tab-count">{len(categories[cat])}</span></button>\n'

    # ── 產生商品卡片 HTML ────────────────────────────────
    all_cards_html = ""
    for cat in ordered_cats:
        cat_id = re.sub(r'[^\w]', '_', cat)
        for p in categories[cat]:
            name = p.get("商品名稱", "")
            orig = p.get("原價")
            amt  = p.get("折扣金額")
            sale = p.get("折扣後售價")
            pct  = p.get("折扣幅度", "")
            period = p.get("優惠期間", "")
            img  = p.get("圖片URL", "")
            link = p.get("商品連結", "#")
            deal_cat = p.get("分類", "")  # 限時優惠 / 精選優惠

            orig_str = f"${orig:,}" if orig else ""
            sale_str = f"${sale:,}" if sale else ""
            amt_str  = f"省 ${amt:,}" if amt else ""

            img_html = f'<img src="{img}" alt="{name}" loading="lazy" onerror="this.style.display=\'none\'">' if img else '<div class="no-img">📦</div>'
            badge_html = f'<div class="badge">-{pct}</div>' if pct else ""
            deal_tag_html = f'<div class="deal-tag">{deal_cat}</div>' if deal_cat else ""
            period_html = f'<p class="period">⏰ {period}</p>' if period else ""

            all_cards_html += f'''<a class="card" href="{link}" target="_blank" rel="noopener" data-cat="{cat_id}">
  <div class="card-img">{img_html}{badge_html}{deal_tag_html}</div>
  <div class="card-body">
    <p class="card-name">{name}</p>
    <div class="card-price">
      <span class="orig">{orig_str}</span>
      {"<span class='arrow'>→</span>" if orig_str else ""}
      <span class="sale">{sale_str}</span>
    </div>
    <p class="card-save">{amt_str}</p>
    {period_html}
  </div>
</a>
'''

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>好市多折扣週報 {date_str}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --red:#E3001B;--blue:#005DAA;--bg:#f4f4f4;
  --text:#1a1a1a;--sub:#666;--border:#e0e0e0;
  --radius:12px;--shadow:0 2px 12px rgba(0,0,0,0.08);
}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif;background:var(--bg);color:var(--text)}}

/* Header */
header{{background:var(--red);color:#fff;padding:16px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
header h1{{font-size:1.15rem;font-weight:700}}
header .meta{{font-size:.75rem;opacity:.85;margin-top:3px}}
.stats{{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}}
.stat{{background:rgba(255,255,255,.2);border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:600}}

/* Tabs */
.tabs-wrap{{background:#fff;border-bottom:2px solid var(--border);overflow-x:auto;white-space:nowrap;scrollbar-width:none;-webkit-overflow-scrolling:touch}}
.tabs-wrap::-webkit-scrollbar{{display:none}}
.tab{{display:inline-block;padding:10px 14px;font-size:.8rem;font-weight:600;color:var(--sub);border:none;background:none;border-bottom:3px solid transparent;cursor:pointer;transition:all .2s;white-space:nowrap}}
.tab:hover,.tab.active{{color:var(--red);border-bottom-color:var(--red)}}
.tab-count{{background:var(--border);border-radius:20px;padding:1px 6px;font-size:.68rem;margin-left:3px}}
.tab.active .tab-count{{background:var(--red);color:#fff}}

/* Search */
.search-wrap{{padding:12px 16px;background:#fff;border-bottom:1px solid var(--border)}}
.search-wrap input{{width:100%;padding:9px 14px;border:1.5px solid var(--border);border-radius:24px;font-size:.88rem;outline:none;transition:border .2s}}
.search-wrap input:focus{{border-color:var(--red)}}

/* Grid */
main{{padding:14px;max-width:960px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:11px}}
.empty{{text-align:center;padding:48px 16px;color:var(--sub);font-size:.9rem;display:none}}

/* Card */
.card{{background:#fff;border-radius:var(--radius);box-shadow:var(--shadow);text-decoration:none;color:var(--text);overflow:hidden;display:flex;flex-direction:column;border:1px solid var(--border);transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,.12)}}
.card:active{{transform:scale(.97)}}
.card[style*="display:none"]{{display:none!important}}

.card-img{{position:relative;width:100%;aspect-ratio:1;background:#f9f9f9;overflow:hidden}}
.card-img img{{width:100%;height:100%;object-fit:contain;padding:8px}}
.no-img{{display:flex;align-items:center;justify-content:center;height:100%;font-size:2.5rem;opacity:.25}}
.badge{{position:absolute;top:6px;right:6px;background:var(--red);color:#fff;font-size:.68rem;font-weight:700;padding:2px 7px;border-radius:20px}}
.deal-tag{{position:absolute;bottom:5px;left:5px;background:rgba(0,93,170,.85);color:#fff;font-size:.62rem;padding:2px 6px;border-radius:8px}}

.card-body{{padding:9px;flex:1;display:flex;flex-direction:column;gap:3px}}
.card-name{{font-size:.8rem;font-weight:600;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.card-price{{display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-top:auto;padding-top:5px}}
.orig{{font-size:.72rem;color:var(--sub);text-decoration:line-through}}
.arrow{{font-size:.65rem;color:var(--sub)}}
.sale{{font-size:.92rem;font-weight:700;color:var(--red)}}
.card-save{{font-size:.72rem;color:#d97706;font-weight:600}}
.period{{font-size:.65rem;color:var(--sub);margin-top:2px}}

/* Footer */
footer{{text-align:center;padding:20px;font-size:.72rem;color:var(--sub)}}

/* RWD */
@media(max-width:380px){{.grid{{grid-template-columns:repeat(2,1fr);gap:9px}}}}
@media(min-width:600px){{.grid{{grid-template-columns:repeat(auto-fill,minmax(175px,1fr))}}}}
</style>
</head>
<body>

<header>
  <h1>🛒 好市多折扣週報</h1>
  <div class="meta">📅 {date_str}（{week_range}）</div>
  <div class="stats">
    <span class="stat">共 {len(products)} 項折扣</span>
    {''.join(f'<span class="stat">{c} {len(categories[c])}項</span>' for c in ordered_cats)}
  </div>
</header>

<div class="tabs-wrap">
{tabs_html}</div>

<div class="search-wrap">
  <input type="search" id="searchInput" placeholder="🔍 搜尋商品名稱..." oninput="doSearch(this.value)">
</div>

<main>
  <div class="grid" id="grid">
{all_cards_html}  </div>
  <div class="empty" id="empty">😢 找不到符合的商品</div>
</main>

<footer>
  🤖 Hermes Agent 自動整理｜資料來源：costco.com.tw｜更新：{today.strftime("%Y-%m-%d %H:%M")}
</footer>

<script>
let currentCat = 'all';
let currentSearch = '';

function filterCat(cat) {{
  currentCat = cat;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  applyFilter();
}}

function doSearch(val) {{
  currentSearch = val.trim().toLowerCase();
  applyFilter();
}}

function applyFilter() {{
  const cards = document.querySelectorAll('.card');
  let visible = 0;
  cards.forEach(card => {{
    const matchCat = currentCat === 'all' || card.dataset.cat === currentCat;
    const matchSearch = !currentSearch || card.querySelector('.card-name').textContent.toLowerCase().includes(currentSearch);
    const show = matchCat && matchSearch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('empty').style.display = visible === 0 ? 'block' : 'none';
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🌐 HTML 報告已產生：{output_path}")
    return output_path


def _get_week_range() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%m/%d')}～{sunday.strftime('%m/%d')}"


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".json")])
    if not files:
        print("找不到資料，請先執行 scraper.py")
        exit(1)
    with open(os.path.join(DATA_DIR, files[-1]), encoding="utf-8") as f:
        products = json.load(f)
    today = datetime.datetime.now().strftime("%Y%m%d")
    out = os.path.join(BASE_DIR, "docs", f"costco_{today}.html")
    generate_html(products, out)
    import subprocess
    subprocess.run(["open", out])
