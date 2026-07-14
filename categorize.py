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

# 載入 .env（排程執行時 shell 不會自動載入，導致 ANTHROPIC_API_KEY 為空、AI 分類從未生效）
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

DB_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'costco_history.db')
API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
API_MODEL  = "claude-haiku-4-5-20251001"   # 分類任務用 Haiku 即可，成本約為 Sonnet 的 1/3
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-flash-lite-latest"  # 別名自動指向最新 Flash-Lite，避免模型淘汰造成 404

# ── 分類規則：與前端共用同一份（generate_html.CATEGORY_RULES），避免兩套規則打架 ──
# 分類 key 使用與前端 data-cat 相同的 sanitize 規則（re.sub(r"[^\w]", "_", 顯示名稱)）
# 例："🐾 寵物用品" → "__寵物用品"
from generate_html import CATEGORY_RULES, OTHER_CATEGORY

def _cat_id(display_name: str) -> str:
    return re.sub(r"[^\w]", "_", display_name)

# ── 分類定義（衍生自前端 CATEGORY_RULES，唯一規則來源）─────────
# key = 前端 data-cat id（如 "__寵物用品"），value = 顯示名稱（去 emoji）
CATEGORIES = { _cat_id(c): c.split(" ", 1)[-1] for c, _ in CATEGORY_RULES }
CATEGORIES[_cat_id(OTHER_CATEGORY)] = "其他"


def classify_by_rules(name: str) -> str:
    """關鍵字規則分類（與前端 classify_product 同一份規則），回傳分類 key 或 '__其他'"""
    name_lower = name.lower()
    for cat, keywords in CATEGORY_RULES:
        if any(kw.lower() in name_lower for kw in keywords):
            return _cat_id(cat)
    return _cat_id(OTHER_CATEGORY)


def _build_prompt(names: list) -> str:
    cat_examples = {
        "__寵物用品": "貓砂、飼料、寵物床、潔牙骨",
        "__食品飲料": "生鮮、零食、飲料、調味料、酒類",
        "__保健美妝": "維他命、保健食品、保養品、個人清潔",
        "__家電_3C":  "家電、手機、電腦周邊、電池燈具",
        "__生活用品": "清潔用品、紙品、收納、廚房衛浴耗材",
        "__服飾寢具": "衣鞋包、寢具、毛巾",
        "__玩具育兒": "玩具、嬰幼兒用品、童裝",
        "___運動戶外": "健身、露營、球類、汽車用品",
    }
    cats_desc = "\n".join(
        f"- {k}（例：{cat_examples.get(k, CATEGORIES[k])}）"
        for k in CATEGORIES if k != _cat_id(OTHER_CATEGORY)
    )
    numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
    return (
        "你是好市多商品分類專家。將以下商品分類到最適合的一個分類。\n"
        "判斷依據：商品的主要用途與使用對象。品牌名可作參考"
        "（例：貓倍麗/Cat Chow 是寵物品牌 → 寵物用品，即使名稱含「雞肉」「鮭魚」也不是食品）。\n"
        "寧可根據線索推測，真的完全無法判斷才用 " + _cat_id(OTHER_CATEGORY) + "。\n\n"
        f"可用分類：\n{cats_desc}\n- {_cat_id(OTHER_CATEGORY)}\n\n"
        "每行輸出：編號<TAB>分類key（例：1\t__食品飲料）。只輸出結果，不要說明。\n\n"
        f"商品清單：\n{numbered}"
    )


def _parse_ai_lines(text: str, names: list) -> dict:
    out = {}
    for line in text.split("\n"):
        m = re.match(r"^(\d+)[\t.\s]+(\S+)", line.strip())
        if not m:
            continue
        idx, key = int(m.group(1)) - 1, m.group(2).strip()
        if 0 <= idx < len(names) and key in CATEGORIES:
            out[names[idx]] = key
    return out


def _call_claude(prompt: str) -> str:
    body = json.dumps({
        "model": API_MODEL, "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"Content-Type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["content"][0]["text"].strip()


def _call_gemini(prompt: str) -> str:
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.1},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def ai_provider() -> str:
    """回傳可用的 AI 供應商名稱，皆未設定回傳空字串"""
    if API_KEY:
        return "claude"
    if GEMINI_KEY:
        return "gemini"
    return ""


def classify_batch_with_ai(names: list) -> dict:
    """用 AI 批次分類，回傳 {name: cat_key}。
    供應商：ANTHROPIC_API_KEY（Claude）優先，否則 GEMINI_API_KEY（Gemini 免費層）。
    使用編號對應而非名稱對應，避免 AI 改寫商品名稱導致結果對不回原商品。"""
    provider = ai_provider()
    if not provider:
        return {}
    prompt = _build_prompt(names)
    try:
        text = _call_claude(prompt) if provider == "claude" else _call_gemini(prompt)
        return _parse_ai_lines(text, names)
    except Exception as e:
        print(f"  ⚠️  AI 分類失敗（{provider}）：{e}")
        return {}


def get_unclassified() -> list:
    """取得需要分類的商品（分類是優惠類型或空的）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT DISTINCT p.商品連結, p.商品名稱, p.商品編號
        FROM products p
        LEFT JOIN category_overrides co ON co.商品連結 = p.商品連結
        WHERE co.card_id IS NULL
          AND (p.分類 IN ('精選優惠','限時優惠','其他','') OR p.分類 IS NULL)
          AND p.商品名稱 != '' AND p.商品連結 != ''
        ORDER BY p.crawl_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
    if uncertain and ai_provider():
        print(f"  呼叫 AI 分類（{ai_provider()}）...")
        for i in range(0, len(uncertain), batch_size):
            batch = uncertain[i:i+batch_size]
            names = [p["商品名稱"] for p in batch]
            result = classify_batch_with_ai(names)
            for p in batch:
                cat = result.get(p["商品名稱"], _cat_id(OTHER_CATEGORY))
                ai_results[p["商品連結"]] = cat
            # Gemini 免費層約 15 RPM，批次間隔放寬避免 429
            time.sleep(5 if ai_provider() == "gemini" else 0.5)
        print(f"  AI 分類完成")
    elif uncertain:
        # 沒有 API key，不確定的放入其他
        print("  ⚠️  未設定 ANTHROPIC_API_KEY / GEMINI_API_KEY，AI 補強停用（不確定商品將留在「其他」）")
        for p in uncertain:
            ai_results[p["商品連結"]] = _cat_id(OTHER_CATEGORY)

    # 3. 統計（規則 + AI 合併看整體分佈）
    all_results = {**rule_results, **ai_results}
    from collections import Counter
    stats = Counter(all_results.values())
    print("\n分類結果：")
    for cat, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {CATEGORIES.get(cat, cat).ljust(10)}: {cnt} 個")

    if dry_run:
        print("\n（dry-run 模式，不寫入 DB）")
        return

    # 4. 只把「AI 分類且非其他」的結果寫入 override
    #    規則分得出來的不寫：前端 classify_product 用同一份規則會得到相同結果，
    #    寫進去只是重複資料，還會蓋掉使用者未來的手動修改空間
    info_map = {p["商品連結"]: p for p in products}
    conn = sqlite3.connect(DB_PATH)
    count = 0
    for link, cat in ai_results.items():
        if cat == _cat_id(OTHER_CATEGORY):
            continue  # AI 也分不出來的不寫，讓它留在「其他」
        p = info_map.get(link, {})
        name = p.get("商品名稱", "")
        code = p.get("商品編號", "") or ""
        # card_id 規則與 generate_html 完全一致
        if code:
            card_id = "p_" + code
        else:
            card_id = "c_" + re.sub(r"[^\w]", "_", link[-35:])
        conn.execute("""
            INSERT INTO category_overrides (card_id, 商品名稱, 商品連結, 細分類, updated_at)
            VALUES (?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(card_id) DO UPDATE SET
                細分類 = excluded.細分類, updated_at = excluded.updated_at
        """, (card_id, name, link, cat))
        count += 1
    conn.commit()
    conn.close()
    ai_effective = sum(1 for c in ai_results.values() if c != _cat_id(OTHER_CATEGORY))
    print(f"\n✅ 寫入 DB（僅 AI 分類結果）：{count} 筆")
    print(f"📋 分類摘要：待分類 {len(products)}｜規則命中 {len(rule_results)}（不寫DB，前端同規則自動分）｜"
          f"AI 判定 {ai_effective}｜AI 也無法判定 {len(ai_results) - ai_effective}｜本次寫入DB {count} 筆")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="商品自動分類")
    parser.add_argument("--dry-run", action="store_true", help="只看結果不寫入")
    parser.add_argument("--limit",   type=int, default=200, help="最多處理幾筆")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
