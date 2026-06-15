#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_classify.py
用 Claude API 對商品自動分類
只處理分類是「精選優惠」「限時優惠」「其他」「」的商品
不確定的放入「其他」讓使用者手動調整
"""
import sqlite3, json, time, re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'costco_history.db')

# 分類對照表（細分類 → 主分類）
VALID_CATS = {
    '__食品飲料':  '食品飲料',
    '__家電_3C':   '家電3C',
    '__生活用品':  '生活用品',
    '__健康美妝':  '健康美妝',
    '__服飾時尚':  '服飾時尚',
    '__家具餐廚':  '家具餐廚',
    '__運動戶外':  '運動戶外',
    '__玩具育兒':  '玩具育兒',
    '__其他':      '其他',
}

CLASSIFY_PROMPT = """你是好市多商品分類專家。根據商品名稱，將商品分到最適合的分類。

可用分類（請只回傳 key）：
- __食品飲料：食物、飲料、零食、咖啡、酒、調味料等
- __家電_3C：電視、電腦、手機、家電、音響、相機等
- __生活用品：清潔用品、衛生紙、洗碗精、除濕機、寵物用品等
- __健康美妝：保健食品、維他命、化妝品、護膚、洗髮等
- __服飾時尚：衣服、鞋子、包包、內衣、睡衣等
- __家具餐廚：家具、廚具、鍋具、餐具、收納等
- __運動戶外：運動器材、露營、戶外用品、健身等
- __玩具育兒：玩具、嬰兒用品、童裝、奶粉等
- __其他：以上都不符合

請分類以下商品，每行一個，格式：商品名稱\t分類key

商品列表：
{products}

只輸出結果，不要說明。"""


def get_products_to_classify(limit=50):
    """取得需要分類的商品（分類是優惠類型或其他的）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT DISTINCT p.商品連結, p.商品名稱, p.分類
        FROM products p
        LEFT JOIN category_overrides co ON co.card_id = (
            'c_' || replace(replace(replace(replace(replace(
                replace(p.商品連結, 'https://', ''), 'http://', ''),
                '/', '_'), '.', '_'), ':', '_'), '-', '_')
        )
        WHERE co.card_id IS NULL
          AND (p.分類 IN ('精選優惠','限時優惠','其他','') OR p.分類 IS NULL)
          AND p.商品名稱 != ''
          AND p.商品連結 != ''
        ORDER BY p.crawl_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def classify_with_claude(product_names: list) -> dict:
    """呼叫 Claude API 分類商品"""
    import urllib.request

    products_text = '\n'.join(product_names)
    prompt = CLASSIFY_PROMPT.format(products=products_text)

    body = json.dumps({
        'model': 'claude-sonnet-4-6',
        'max_tokens': 1000,
        'messages': [{'role': 'user', 'content': prompt}]
    }).encode()

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())

    text = result['content'][0]['text'].strip()

    # 解析結果
    classifications = {}
    for line in text.split('\n'):
        if '\t' in line:
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[0].strip()
                cat = parts[1].strip()
                if cat in VALID_CATS:
                    classifications[name] = cat
    return classifications


def apply_classifications(rows, classifications: dict):
    """把分類結果存到 category_overrides"""
    conn = sqlite3.connect(DB_PATH)
    count = 0

    for row in rows:
        name = row['商品名稱']
        link = row['商品連結']
        cat = classifications.get(name)
        if not cat:
            continue

        # 產生 card_id（跟前端一致的邏輯）
        card_id = 'c_' + re.sub(r'[^a-zA-Z0-9_]', '_',
                    link.replace('https://', '').replace('http://', ''))[-50:]

        conn.execute("""
            INSERT INTO category_overrides (card_id, 商品名稱, 商品連結, 細分類, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(card_id) DO UPDATE SET
                細分類 = excluded.細分類,
                updated_at = excluded.updated_at
        """, (card_id, name, link, cat))
        count += 1
        print(f"  [{VALID_CATS[cat]}] {name[:40]}")

    conn.commit()
    conn.close()
    return count


def run(limit=50, batch_size=20):
    rows = get_products_to_classify(limit)
    print(f"需要分類：{len(rows)} 個商品")

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        names = [r['商品名稱'] for r in batch]
        print(f"\n批次 {i//batch_size+1}（{len(names)} 個）...")

        try:
            result = classify_with_claude(names)
            count = apply_classifications(batch, result)
            total += count
            print(f"  ✅ 分類 {count} 個")
        except Exception as e:
            print(f"  ⚠️ API 錯誤：{e}")

        if i + batch_size < len(rows):
            time.sleep(1)

    print(f"\n✅ 完成！共分類 {total} 個商品")
    return total


if __name__ == '__main__':
    run(limit=100)
