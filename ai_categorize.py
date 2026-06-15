#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_categorize.py
用 Claude API 對 products 表裡分類是「其他」的商品自動分類
結果寫入 category_overrides 表，並更新 overrides.json 到 GitHub
"""

import os, sys, json, time, re, sqlite3, urllib.request, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 分類定義
CATEGORIES = {
    "food":     "食品飲料",
    "elec":     "家電3C",
    "health":   "健康美妝",
    "cloth":    "服飾時尚",
    "home":     "生活用品",
    "kitchen":  "家具餐廚",
    "outdoor":  "運動戶外",
    "baby":     "母嬰寵物",
    "other":    "其他",
}

CAT_EXAMPLES = """
食品飲料(food)：咖啡、茶、零食、洋芋片、飲料、牛奶、優格、餅乾、果凍、蛋捲、海苔、泡麵、冷凍食品、肉品、海鮮、蛋、蜂蜜、酒
家電3C(elec)：電視、冰箱、洗衣機、空氣清淨機、吹風機、充電器、電池、耳機、音響、掃地機器人、除濕機
健康美妝(health)：維他命、魚油、益生菌、葉黃素、膠原蛋白、洗髮精、護髮、沐浴乳、牙膏、面膜、乳霜、隱形眼鏡
服飾時尚(cloth)：上衣、褲子、鞋子、內衣、運動服、外套、睡衣、內褲、洋裝、背包、手提包
生活用品(home)：衛生紙、濕紙巾、洗衣精、清潔劑、除濕袋、收納箱、地墊、燈具、蠟燭、垃圾袋、保鮮盒
家具餐廚(kitchen)：鍋具、刀具、砧板、保溫杯、餐碗、桌子、椅子、床組、寢具、棉被、枕頭
運動戶外(outdoor)：帳篷、露營椅、行李箱、籃球、自行車、瑜珈墊、健身器材、泳裝、登山鞋、遮陽傘
母嬰寵物(baby)：紙尿褲、嬰兒濕巾、嬰兒服、玩具、寵物食品、貓砂、狗零食
其他(other)：輪胎、汽車用品、辦公文具、書籍、珠寶、藝術品、不確定的商品
"""

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    env = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env

def ai_categorize_batch(product_names: list) -> dict:
    """
    用 Claude API 批次分類商品
    回傳 {商品名稱: cat_id} 的 dict
    """
    if not product_names:
        return {}

    prompt = f"""你是好市多商品分類專家。根據以下分類說明，幫每個商品選擇最適合的分類代碼。

分類說明：
{CAT_EXAMPLES}

規則：
1. 只能選以下代碼之一：food, elec, health, cloth, home, kitchen, outdoor, baby, other
2. 不確定的選 other
3. 只回傳 JSON，格式：{{"商品名稱": "分類代碼", ...}}
4. 不要有任何說明文字

商品列表：
{chr(10).join(f'- {name}' for name in product_names)}"""

    env = load_env()
    
    try:
        body = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        
        text = data["content"][0]["text"].strip()
        # 清除可能的 markdown
        text = re.sub(r"```json\s*|\s*```", "", text).strip()
        result = json.loads(text)
        # 驗證都是有效的 cat_id
        valid = {k: v for k, v in result.items() if v in CATEGORIES}
        return valid

    except Exception as e:
        print(f"  ⚠️  AI 分類失敗：{e}")
        return {}


def run_ai_categorize(limit: int = 100):
    """
    對 products 表裡分類是「其他」的商品做 AI 分類
    """
    from database import get_conn, init_db, update_product_category, get_master_count

    init_db()
    conn = get_conn()

    # 找今日有折扣且分類是「其他」的商品
    rows = conn.execute("""
        SELECT DISTINCT 商品名稱, 商品連結, 商品編號
        FROM products
        WHERE (細分類 IS NULL OR 細分類 = '')
          AND (折扣金額 IS NOT NULL OR 折扣後售價 IS NOT NULL)
          AND crawl_date >= date('now', '-30 days')
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"找到 {len(rows)} 個「其他」分類的折扣商品")
    if not rows:
        return

    # 批次處理（每次 20 個）
    batch_size = 20
    all_results = {}

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        names = [r[0] for r in batch]
        print(f"\n  批次 {i//batch_size+1}：分類 {len(names)} 個商品...")
        results = ai_categorize_batch(names)
        all_results.update(results)
        print(f"  → 成功分類 {len(results)} 個")
        for name, cat in results.items():
            print(f"    {name[:40].ljust(40)} → {CATEGORIES[cat]}({cat})")
        time.sleep(0.5)

    # 寫入 DB 和 overrides
    print(f"\n寫入分類結果...")
    updated = 0
    overrides = {}

    for row in rows:
        name, link, code = row[0], row[1], row[2]
        cat_code = all_results.get(name)
        if not cat_code or cat_code == "other":
            continue

        cat_name = CATEGORIES[cat_code]

        # 更新 products 表
        conn.execute(
            "UPDATE products SET 分類=? WHERE 商品名稱=? AND (分類='其他' OR 分類 IS NULL OR 分類='')",
            (cat_name, name)
        )

        # 更新 products_master 表
        conn.execute(
            "UPDATE products_master SET 分類=? WHERE 商品名稱=? AND (分類='其他' OR 分類 IS NULL OR 分類='')",
            (cat_name, name)
        )

        # 產生 card_id（跟前端一致）
        card_id = "c_" + re.sub(r"[^a-z0-9]", "_", link.lower())
        overrides[card_id] = {"cat": cat_name, "name": name, "link": link}
        updated += 1

    conn.commit()
    print(f"✅ 更新 {updated} 個商品分類")

    if not overrides:
        return

    # 合併到現有 overrides.json 並推上 GitHub
    overrides_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overrides.json")
    existing = {}
    if os.path.exists(overrides_path):
        with open(overrides_path) as f:
            existing = json.load(f)

    existing.update(overrides)
    with open(overrides_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  本地 overrides.json 更新（共 {len(existing)} 筆）")

    # 推上 GitHub
    env = load_env()
    token = env.get("GITHUB_TOKEN", "")
    if token:
        try:
            content_str = json.dumps(existing, ensure_ascii=False, indent=2)
            encoded = base64.b64encode(content_str.encode()).decode()

            # 先取得目前的 SHA
            get_req = urllib.request.Request(
                "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(get_req, timeout=10) as r:
                sha = json.loads(r.read()).get("sha", "")

            put_req = urllib.request.Request(
                "https://api.github.com/repos/s610034/costco-deals/contents/data/overrides.json",
                data=json.dumps({
                    "message": f"ai: 自動分類 {updated} 個商品",
                    "content": encoded,
                    "sha": sha
                }).encode(),
                headers={
                    "Authorization": f"token {token}",
                    "Content-Type": "application/json"
                },
                method="PUT"
            )
            with urllib.request.urlopen(put_req, timeout=15) as r:
                json.loads(r.read())
            print(f"  ✅ 推上 GitHub（共 {len(existing)} 筆）")
        except Exception as e:
            print(f"  ⚠️  推 GitHub 失敗：{e}")


if __name__ == "__main__":
    run_ai_categorize(limit=100)
