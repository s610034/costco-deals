#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
costco_search.py
用官網搜尋功能查商品，取得商品編號
給 PTT 商品補充商品編號用
"""
import re, time
from typing import Optional, Dict

BASE = "https://www.costco.com.tw"


def search_product(name: str, page) -> Optional[Dict]:
    """
    用商品名稱去官網搜尋，回傳最佳匹配的商品編號和連結
    name: 商品名稱（關鍵字即可，不需要完整）
    page: Playwright page 物件
    """
    # 取前幾個有效關鍵字搜尋（避免太長導致無結果）
    # 去掉數量/規格描述，只保留品牌/商品名
    keywords = re.sub(r'\d+[公克毫升入片粒瓶罐公斤]+.*$', '', name).strip()
    keywords = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', keywords).strip()
    keywords = ' '.join(keywords.split()[:4])  # 最多4個詞

    if not keywords:
        return None

    url = f"{BASE}/search?q={keywords.replace(' ', '+')}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except Exception:
        return None

    results = page.evaluate("""() => {
        const seen = new Set();
        const items = [];
        for (const a of document.querySelectorAll('a[href*="/p/"]')) {
            const href = a.getAttribute('href') || '';
            const m = href.match(/\\/p\\/(\\d+)/);
            if (!m || seen.has(m[1])) continue;
            seen.add(m[1]);

            // 找商品卡片
            let card = a;
            for (let i = 0; i < 7; i++) {
                const par = card.parentElement;
                if (!par || par.querySelectorAll('a[href*="/p/"]').length > 2) break;
                card = par;
            }
            const name = a.getAttribute('title') || card.querySelector('[class*=name],[class*=title]')?.innerText?.trim() || '';
            const img = card.querySelector('img')?.src || '';
            let fullHref = href.startsWith('http') ? href : 'https://www.costco.com.tw' + href;

            items.push({code: m[1], name: name.slice(0,60), img, href: fullHref});
        }
        return items.slice(0, 8);
    }""")

    if not results:
        return None

    # 找最佳匹配（名稱相似度最高的）
    name_lower = name.lower()
    best = None
    best_score = 0

    for r in results:
        if not r['name']:
            continue
        r_lower = r['name'].lower()
        # 計算關鍵字匹配分數
        score = 0
        for kw in keywords.lower().split():
            if kw in r_lower:
                score += 1
        # 長度相似加分
        len_ratio = min(len(name), len(r['name'])) / max(len(name), len(r['name']))
        score += len_ratio

        if score > best_score:
            best_score = score
            best = r

    # 至少要有一個關鍵字匹配
    if best and best_score >= 1.0:
        return {
            "商品編號": best['code'],
            "商品名稱_官網": best['name'],
            "圖片URL": best['img'],
            "官網連結": best['href'],
        }

    return None


def enrich_ptt_products(ptt_products: list, page) -> list:
    """
    對 PTT 解析出的商品，去官網搜尋取得商品編號
    有商品編號後再驗證是否有折扣
    """
    from verify_prices import verify_product_price

    enriched = []
    for p in ptt_products:
        name = p.get("商品名稱", "")
        code = p.get("商品編號", "")

        # 已有商品編號的直接驗證
        if not code:
            print(f"  🔍 搜尋官網：{name[:35]}")
            result = search_product(name, page)
            if result:
                code = result["商品編號"]
                p["商品編號"]    = code
                p["圖片URL"]     = p.get("圖片URL") or result["圖片URL"]
                p["官網連結"]    = result["官網連結"]
                p["商品名稱"]    = result["商品名稱_官網"] or name
                print(f"    → #{code} {result['商品名稱_官網'][:35]}")
            else:
                print(f"    → 找不到對應商品，跳過")
                continue

        # 去詳情頁確認目前是否有折扣
        verify = verify_product_price(code, page)
        if verify and verify.get("折扣金額"):
            p["原價"]       = verify["原價"]
            p["折扣金額"]   = verify["折扣金額"]
            p["折扣後售價"] = verify["折扣後售價"]
            p["折扣幅度"]   = verify.get("折扣幅度") or p.get("折扣幅度", "")
            if not p.get("官網連結"):
                p["官網連結"] = verify["官網連結"]
            p["商品連結"]   = p.get("商品連結") or p["官網連結"]
            enriched.append(p)
            print(f"  ✅ #{code} {p['商品名稱'][:30]} 折=${verify['折扣金額']}")
        else:
            print(f"  ❌ #{code} {p.get('商品名稱','')[:30]} 官網目前無折扣，跳過")

    return enriched
