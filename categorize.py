#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
categorize.py
商品自動分類工具
- 先用關鍵字規則分類（免費、即時）
- 有設定 ANTHROPIC_API_KEY 時，不確定的商品再用 Claude API 補強

執行方式：
  python3 categorize.py           # 分類所有未分類商品
  python3 categorize.py --dry-run # 只看結果不存入 DB
"""

import os, sys, json, time, re, sqlite3, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'costco_history.db')
API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
API_MODEL  = "claude-sonnet-4-6"

# ── 分類定義 ──────────────────────────────────────────────────
CATEGORIES = {
    "__食品飲料": "食品飲料",
    "__家電_3C":  "家電3C",
    "__健康美妝": "健康美妝",
    "__服飾時尚": "服飾時尚",
    "__生活用品": "生活用品",
    "__家具餐廚": "家具餐廚",
    "__運動戶外": "運動戶外",
    "__玩具育兒": "玩具育兒",
    "__其他":     "其他",
}

# ── 關鍵字規則 ────────────────────────────────────────────────
RULES = [
    ("__食品飲料", [
        "咖啡","茶","飲料","汽水","果汁","牛奶","奶茶","豆漿","優酪","氣泡水",
        "零食","餅乾","洋芋片","巧克力","果凍","泡芙","蛋捲","米菓","威化",
        "米漢堡","蝦餅","雞肉","豬肉","牛肉","魚","蝦","海鮮","蛋","奶酪",
        "豆腐","泡麵","麵條","油","醬","醋","酒","啤酒","威士忌","葡萄酒",
        "蜂蜜","果乾","堅果","燕麥","罐頭","冷凍","冷藏","乾酪","起司",
        "布丁","冰淇淋","濃湯","乳酪","沙士","拿鐵","糖","鹽","巧達",
        "Tree Top","VONO","Binggrae","Barista","Starbucks",
    ]),
    ("__健康美妝", [
        "維他命","維生素","保健","益生菌","膠原蛋白","葉黃素","魚油","蔘",
        "葡萄糖胺","洗髮","護髮","沐浴","牙膏","牙刷","面膜","乳液","乳霜",
        "精華","防曬","卸妝","洗面","香水","護唇","隱形眼鏡","生物素",
        "蔓越莓","UC-II","Natrol","Webber","Redoxon","Centrum","BRAND",
    ]),
    ("__服飾時尚", [
        "上衣","褲","裙","鞋","靴","包包","手提","T恤","Polo","外套","夾克",
        "內衣","內褲","睡衣","帽子","圍巾","行李箱","洋裝","連身",
        "Adidas","Nike","Lacoste","Timberland","Skechers","Palladium",
        "Kangol","Puma","Tommy","Columbia","North Face",
    ]),
    ("__家電_3C", [
        "電視","冰箱","洗衣機","冷氣","空氣清淨","除濕","吹風機","電風扇",
        "耳機","喇叭","螢幕","印表機","電池","充電","LED","燈","行車紀錄",
        "顯示器","掃地機","電鍋","果汁機","咖啡機","烤箱","微波",
        "Samsung","LG","Sony","Panasonic","Dyson","Honeywell","Philips",
        "TCL","Hisense","Sharp","Electrolux","Whirlpool","Tescom",
    ]),
    ("__生活用品", [
        "洗碗","洗衣精","柔軟精","清潔","除臭","漂白","垃圾袋","衛生紙",
        "濕紙巾","蚊香","殺蟲","狗","貓","寵物","小蘇打","去污","廚房紙巾",
        "除濕袋","Clorox","Ariel","Tide","汰漬","舒潔","好奇","幫寶適",
        "Bounty","Pine-Sol","威滅",
    ]),
    ("__家具餐廚", [
        "鍋","平底鍋","湯鍋","炒鍋","餐盤","碗","杯","保鮮盒","便當",
        "刀","砧板","剪刀","桌","椅","沙發","床","收納","層架","衣架",
        "掛勾","地墊","窗簾","棉被","枕頭","毛巾","浴巾","升降桌",
        "Staub","Zwilling","Tefal","Neoflam","WMF","Corelle",
    ]),
    ("__運動戶外", [
        "露營","帳篷","登山","游泳","瑜珈","健身","腳踏車","球","拍",
        "釣魚","海灘","遮陽","背包","水壺","Coleman","折疊椅","海灘椅",
        "Wilson","Michelin","輪胎","機油","Castrol",
    ]),
    ("__玩具育兒", [
        "玩具","積木","Lego","娃娃","益智","拼圖","嬰兒","奶粉","尿布",
        "奶瓶","童裝","兒童","Huggies","幫寶適","好奇","嬰兒",
    ]),
]


def classify_by_rules(name: str) -> str:
    """關鍵字規則分類，回傳分類 key 或 '__其他'"""
    name_lower = name.lower()
    for cat, keywords in RULES:
        if any(kw.lower() in name_lower for kw in keywords):
            return cat
    return "__其他"


def classify_batch_with_ai(names: list) -> dict:
    """用 Claude API 批次分類，回傳 {name: cat_key}"""
    if not API_KEY:
        return {}

    cats_desc = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    prompt = (
        f"將以下好市多商品分類到最適合的分類。\n\n可用分類：\n{cats_desc}\n\n"
        "每行輸出：商品名稱\\t分類key\n只輸出結果，不要說明。\n\n商品：\n"
        + "\n".join(names)
    )

    body = json.dumps({
        "model": API_MODEL,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={"Content-Type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        text = result["content"][0]["text"].strip()
        out = {}
        for line in text.split("\n"):
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[1].strip() in CATEGORIES:
                    out[parts[0].strip()] = parts[1].strip()
        return out
    except Exception as e:
        print(f"  ⚠️  AI 分類失敗：{e}")
        return {}


def get_unclassified() -> list:
    """取得需要分類的商品（分類是優惠類型或空的）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT DISTINCT p.商品連結, p.商品名稱
        FROM products p
        LEFT JOIN category_overrides co ON co.商品連結 = p.商品連結
        WHERE co.card_id IS NULL
          AND (p.分類 IN ('精選優惠','限時優惠','其他','') OR p.分類 IS NULL)
          AND p.商品名稱 != '' AND p.商品連結 != ''
        ORDER BY p.crawl_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_classifications(classified: dict, dry_run: bool = False) -> int:
    """將分類結果存入 DB"""
    if dry_run:
        return 0
    conn = sqlite3.connect(DB_PATH)
    count = 0
    for link, cat in classified.items():
        name = classified.get(link + "_name", "")
        card_id = "c_" + re.sub(r"[^a-zA-Z0-9_]", "_",
                    link.replace("https://", "").replace("http://", ""))[-50:]
        conn.execute("""
            INSERT INTO category_overrides (card_id, 商品名稱, 商品連結, 細分類, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(card_id) DO UPDATE SET
                細分類 = excluded.細分類, updated_at = excluded.updated_at
        """, (card_id, name, link, cat))
        count += 1
    conn.commit()
    conn.close()
    return count


def run(dry_run: bool = False, limit: int = 200, batch_size: int = 20):
    products = get_unclassified()[:limit]
    print(f"需要分類：{len(products)} 個商品")

    rule_results  = {}   # {link: cat}
    uncertain     = []   # 規則分不出來的，交給 AI

    # 1. 規則分類
    for p in products:
        cat = classify_by_rules(p["商品名稱"])
        if cat != "__其他":
            rule_results[p["商品連結"]] = cat
        else:
            uncertain.append(p)

    print(f"  規則分類：{len(rule_results)} 個")
    print(f"  不確定（送 AI）：{len(uncertain)} 個")

    # 2. AI 補強（只處理規則分不出來的）
    ai_results = {}
    if uncertain and API_KEY:
        print(f"  呼叫 Claude API...")
        for i in range(0, len(uncertain), batch_size):
            batch = uncertain[i:i+batch_size]
            names = [p["商品名稱"] for p in batch]
            result = classify_batch_with_ai(names)
            for p in batch:
                cat = result.get(p["商品名稱"], "__其他")
                ai_results[p["商品連結"]] = cat
            time.sleep(0.5)
        print(f"  AI 分類完成")
    elif uncertain:
        # 沒有 API key，不確定的放入其他
        for p in uncertain:
            ai_results[p["商品連結"]] = "__其他"

    # 3. 合併結果
    all_results = {**rule_results, **ai_results}

    # 統計
    from collections import Counter
    stats = Counter(all_results.values())
    print("\n分類結果：")
    for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {CATEGORIES.get(cat, cat).ljust(10)}: {cnt} 個")

    if dry_run:
        print("\n（dry-run 模式，不寫入 DB）")
        return

    # 4. 存入 DB（帶商品名稱）
    conn = sqlite3.connect(DB_PATH)
    count = 0
    name_map = {p["商品連結"]: p["商品名稱"] for p in products}
    for link, cat in all_results.items():
        name = name_map.get(link, "")
        card_id = "c_" + re.sub(r"[^a-zA-Z0-9_]", "_",
                    link.replace("https://", "").replace("http://", ""))[-50:]
        conn.execute("""
            INSERT INTO category_overrides (card_id, 商品名稱, 商品連結, 細分類, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(card_id) DO UPDATE SET
                細分類 = excluded.細分類, updated_at = excluded.updated_at
        """, (card_id, name, link, cat))
        count += 1
    conn.commit()
    conn.close()
    print(f"\n✅ 寫入 DB：{count} 筆")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="商品自動分類")
    parser.add_argument("--dry-run", action="store_true", help="只看結果不寫入")
    parser.add_argument("--limit",   type=int, default=200, help="最多處理幾筆")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
