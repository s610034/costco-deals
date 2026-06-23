#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database.py
SQLite 資料庫：儲存每週折扣商品歷史，可查詢商品上次折扣時間與價格變化
"""

import sqlite3
import os
import datetime
from typing import List, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "costco_history.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建立資料表（若不存在）"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products_master (
            商品編號      TEXT PRIMARY KEY,
            商品名稱      TEXT NOT NULL,
            分類          TEXT,
            細分類        TEXT,
            原價          INTEGER,
            折扣金額      INTEGER,
            折扣後售價    INTEGER,
            圖片URL       TEXT,
            商品連結      TEXT,
            最後更新      TEXT,
            資料來源      TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_date    TEXT NOT NULL,
            商品名稱      TEXT NOT NULL,
            分類          TEXT,
            細分類        TEXT,
            原價          INTEGER,
            折扣金額      INTEGER,
            折扣幅度      TEXT,
            折扣後售價    INTEGER,
            優惠期間      TEXT,
            實體賣場      INTEGER DEFAULT 0,
            圖片URL       TEXT,
            商品連結      TEXT,
            抓取時間      TEXT,
            商品編號      TEXT,
            討論連結      TEXT DEFAULT ""
        );

        CREATE TABLE IF NOT EXISTS category_overrides (
            card_id       TEXT PRIMARY KEY,
            商品名稱      TEXT,
            商品連結      TEXT,
            細分類        TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_name      ON products(商品名稱);
        CREATE INDEX IF NOT EXISTS idx_date      ON products(crawl_date);
        CREATE INDEX IF NOT EXISTS idx_link      ON products(商品連結);
    """)
    conn.commit()
    conn.close()
    print("✅ 資料庫初始化完成")


def upsert_products(products: List[Dict], crawl_date: str = None) -> int:
    """
    將本週商品寫入資料庫
    同一個商品連結在同一抓取日期只寫一次（避免重複）
    回傳新增筆數
    """
    if crawl_date is None:
        crawl_date = datetime.datetime.now().strftime("%Y%m%d")

    conn = get_conn()
    inserted = 0
    for p in products:
        link = p.get("商品連結", "")
        code = p.get("商品編號", "")

        # 有商品編號：用商品編號+日期去重（避免官網版+daybuy版重複）
        if code:
            exists = conn.execute(
                "SELECT id, 優惠期間, 商品編號, 原價, 折扣金額, 圖片URL, 討論連結, 商品連結 FROM products WHERE crawl_date=? AND 商品編號=?",
                (crawl_date, code)
            ).fetchone()
            # 官網連結優先：如果已存 daybuy 版但現在有官網版，更新連結
            if exists and "costco.com.tw/p/" in link and "costco.com.tw/p/" not in (exists["商品連結"] or ""):
                conn.execute("UPDATE products SET 商品連結=? WHERE id=?", (link, exists["id"]))
        else:
            exists = conn.execute(
                "SELECT id, 優惠期間, 商品編號, 原價, 折扣金額, 圖片URL, 討論連結, 商品連結 FROM products WHERE crawl_date=? AND 商品連結=?",
                (crawl_date, link)
            ).fetchone()
        if exists:
            updates = []
            vals = []
            # 有新的優惠期間就更新
            new_period = p.get("優惠期間", "")
            if new_period and not exists["優惠期間"]:
                updates.append("優惠期間=?")
                vals.append(new_period)
            # 有新的商品編號就更新
            new_code = p.get("商品編號", "")
            if new_code and not exists["商品編號"]:
                updates.append("商品編號=?")
                vals.append(new_code)
            # 有新的原價（從詳情頁驗證過的）就更新
            new_orig = p.get("原價")
            if new_orig and new_orig != exists["原價"]:
                updates.append("原價=?")
                vals.append(new_orig)
                # 同步更新折扣後售價和折扣幅度
                new_disc = p.get("折扣金額") or exists["折扣金額"]
                if new_disc and new_orig:
                    updates.append("折扣後售價=?")
                    vals.append(new_orig - new_disc)
                    updates.append("折扣幅度=?")
                    vals.append(str(round(new_disc/new_orig*100, 1)) + "%")
            # 有新的圖片也更新
            new_img = p.get("圖片URL", "")
            if new_img and not exists["圖片URL"]:
                updates.append("圖片URL=?")
                vals.append(new_img)
            # 有新的討論連結就更新
            new_disc_url = p.get("討論連結", "")
            if new_disc_url and not exists["討論連結"]:
                updates.append("討論連結=?")
                vals.append(new_disc_url)
            if updates:
                vals.append(exists["id"])
                conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE id=?", vals)
            continue

        conn.execute("""
            INSERT INTO products
              (crawl_date, 商品名稱, 分類, 細分類, 原價, 折扣金額, 折扣幅度,
               折扣後售價, 優惠期間, 實體賣場, 圖片URL, 商品連結, 抓取時間, 商品編號, 討論連結)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            crawl_date,
            p.get("商品名稱", ""),
            p.get("分類", ""),
            p.get("細分類", ""),
            p.get("原價"),
            p.get("折扣金額"),
            p.get("折扣幅度", ""),
            p.get("折扣後售價"),
            p.get("優惠期間", ""),
            1 if p.get("實體賣場") else 0,
            p.get("圖片URL", ""),
            p.get("商品連結", ""),
            p.get("抓取時間", ""),
            p.get("商品編號", ""),
            p.get("討論連結", ""),
        ))
        inserted += 1

    conn.commit()
    conn.close()
    print(f"💾 資料庫新增 {inserted} 筆（本日已有的略過）")
    return inserted


def update_product_category(card_id: str, new_category: str,
                             product_name: str = "", product_link: str = "") -> bool:
    """
    從前端收到使用者修改的分類，寫入 category_overrides 表
    同時更新 products 表中對應商品的細分類（最新一筆）
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    try:
        # 寫入 overrides 表（主鍵為 card_id，相同 card_id 覆蓋舊值）
        conn.execute("""
            INSERT INTO category_overrides (card_id, 商品名稱, 商品連結, 細分類, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                細分類=excluded.細分類,
                updated_at=excluded.updated_at
        """, (card_id, product_name, product_link, new_category, now))

        # 同步更新 products 表最新一筆（依商品名稱或連結比對）
        if product_link:
            conn.execute("""
                UPDATE products SET 細分類=?
                WHERE 商品連結=?
                  AND crawl_date=(
                    SELECT MAX(crawl_date) FROM products WHERE 商品連結=?
                  )
            """, (new_category, product_link, product_link))
        elif product_name:
            conn.execute("""
                UPDATE products SET 細分類=?
                WHERE 商品名稱=?
                  AND crawl_date=(
                    SELECT MAX(crawl_date) FROM products WHERE 商品名稱=?
                  )
            """, (new_category, product_name, product_name))

        conn.commit()
        return True
    except Exception as e:
        print(f"❌ update_product_category 失敗：{e}")
        return False
    finally:
        conn.close()


def get_all_category_overrides() -> Dict[str, str]:
    """取得所有已覆蓋的分類（card_id → 細分類）"""
    conn = get_conn()
    rows = conn.execute("SELECT card_id, 細分類 FROM category_overrides").fetchall()
    conn.close()
    return {r["card_id"]: r["細分類"] for r in rows}


def get_history(product_link: str) -> List[Dict]:
    """查詢某商品的歷史折扣紀錄（依日期排序）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT crawl_date, 原價, 折扣金額, 折扣後售價, 折扣幅度, 優惠期間
        FROM products
        WHERE 商品連結 = ?
        ORDER BY crawl_date DESC
    """, (product_link,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_seen(product_link: str, before_date: str) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("""
        SELECT crawl_date, 原價, 折扣金額, 折扣後售價, 折扣幅度
        FROM products
        WHERE 商品連結 = ? AND crawl_date < ?
        ORDER BY crawl_date DESC
        LIMIT 1
    """, (product_link, before_date)).fetchone()
    conn.close()
    return dict(row) if row else None


def enrich_with_history(products: List[Dict], today: str = None) -> List[Dict]:
    """為每個商品附加歷史資訊（上次折扣日期、天數、價格變化）"""
    if today is None:
        today = datetime.datetime.now().strftime("%Y%m%d")

    # 同時套用資料庫中儲存的分類覆蓋
    overrides = get_all_category_overrides()

    enriched = []
    for p in products:
        link = p.get("商品連結", "")
        last = get_last_seen(link, today)

        if last:
            last_date = datetime.datetime.strptime(last["crawl_date"], "%Y%m%d")
            this_date = datetime.datetime.strptime(today, "%Y%m%d")
            days_diff = (this_date - last_date).days

            last_sale  = last.get("折扣後售價")
            this_sale  = p.get("折扣後售價")
            if last_sale and this_sale:
                change = this_sale - last_sale
                change_str = f"↑${abs(change):,}" if change > 0 else (f"↓${abs(change):,}" if change < 0 else "持平")
            else:
                change_str = "-"

            p["上次折扣日期"]   = last["crawl_date"]
            p["距上次折扣天數"] = days_diff
            p["上次折扣後售價"] = last_sale
            p["價格變化"]       = change_str
        else:
            p["上次折扣日期"]   = None
            p["距上次折扣天數"] = None
            p["上次折扣後售價"] = None
            p["價格變化"]       = "首次出現"

        enriched.append(p)
    return enriched


def get_summary_stats(crawl_date: str = None) -> Dict:
    if crawl_date is None:
        crawl_date = datetime.datetime.now().strftime("%Y%m%d")
    conn = get_conn()
    total  = conn.execute("SELECT COUNT(*) FROM products WHERE crawl_date=?", (crawl_date,)).fetchone()[0]
    repeat = conn.execute("""
        SELECT COUNT(*) FROM products p
        WHERE p.crawl_date=?
          AND EXISTS (
              SELECT 1 FROM products p2
              WHERE p2.商品連結=p.商品連結 AND p2.crawl_date < ?
          )
    """, (crawl_date, crawl_date)).fetchone()[0]
    new    = total - repeat
    conn.close()
    return {"total": total, "new": new, "repeat": repeat, "date": crawl_date}


if __name__ == "__main__":
    init_db()
    stats = get_summary_stats()
    print(f"本日統計：{stats}")
    overrides = get_all_category_overrides()
    print(f"已有分類覆蓋：{len(overrides)} 筆")


def get_products_last_n_days(days: int = 30) -> List[Dict]:
    """
    從 DB 撈最近 N 天內出現過的所有商品。
    同一商品（同商品連結）只保留最新一次的資料。
    """
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
    conn = get_conn()
    # 取每個商品連結最新一筆
    rows = conn.execute("""
        SELECT p.*
        FROM products p
        INNER JOIN (
            SELECT 商品連結, MAX(crawl_date) AS max_date
            FROM products
            WHERE crawl_date >= ?
            GROUP BY 商品連結
        ) latest ON p.商品連結 = latest.商品連結
                    AND p.crawl_date = latest.max_date
        ORDER BY p.折扣金額 DESC NULLS LAST
    """, (cutoff,)).fetchall()
    conn.close()

    products = []
    for r in rows:
        p = dict(r)
        # 把 DB 欄位轉成 generate_html 期望的格式
        p["實體賣場"] = bool(p.get("實體賣場"))
        p.setdefault("分類", "精選優惠")
        p.setdefault("細分類", "")
        p.setdefault("討論連結", "")
        p.setdefault("ptt_標題", "")
        p.setdefault("距上次折扣天數", None)
        p.setdefault("價格變化", "")
        products.append(p)

    print(f"📦 從 DB 撈取最近 {days} 天商品：{len(products)} 筆（去重後）")
    return products


def upsert_master(products: List[Dict], source: str = "scraper") -> int:
    """
    把商品資料同步到 products_master（永久商品資料庫）
    有商品編號的才寫入，用 INSERT OR REPLACE 更新
    """
    import datetime as _dt
    conn = get_conn()
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for p in products:
        code = p.get("商品編號", "")
        name = p.get("商品名稱", "")
        if not code or not name:
            continue
        conn.execute("""
            INSERT INTO products_master
                (商品編號, 商品名稱, 分類, 細分類, 原價, 折扣金額, 折扣後售價,
                 圖片URL, 商品連結, 最後更新, 資料來源)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(商品編號) DO UPDATE SET
                商品名稱    = CASE WHEN length(excluded.商品名稱) > length(商品名稱) THEN excluded.商品名稱 ELSE 商品名稱 END,
                原價        = COALESCE(excluded.原價, 原價),
                折扣金額    = COALESCE(excluded.折扣金額, 折扣金額),
                折扣後售價  = COALESCE(excluded.折扣後售價, 折扣後售價),
                圖片URL     = COALESCE(NULLIF(excluded.圖片URL,''), 圖片URL),
                商品連結    = COALESCE(NULLIF(excluded.商品連結,''), 商品連結),
                最後更新    = excluded.最後更新,
                資料來源    = excluded.資料來源
        """, (
            code, name,
            p.get("分類", ""), p.get("細分類", ""),
            p.get("原價"), p.get("折扣金額"), p.get("折扣後售價"),
            p.get("圖片URL", ""), p.get("商品連結", ""),
            now, source
        ))
        count += 1
    conn.commit()
    return count


def get_master_product(code: str) -> Optional[Dict]:
    """從 master 表查單一商品"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM products_master WHERE 商品編號=?", (code,)
    ).fetchone()
    if not row:
        return None
    return dict(row)


def get_master_count() -> int:
    """取得 master 表商品總數"""
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) FROM products_master").fetchone()[0]


def get_discussion_map() -> dict:
    """取得商品編號 → daybuy/PTT 討論連結的對照表"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT 商品編號, 討論連結
        FROM products
        WHERE 商品編號 != '' AND 討論連結 != '' AND 討論連結 IS NOT NULL
        GROUP BY 商品編號
    """).fetchall()
    return {r[0]: r[1] for r in rows}


def enrich_discussion_links(products: List[Dict]) -> List[Dict]:
    """
    補充商品的 討論連結、官網連結、圖片URL：
    - daybuy/PTT 來源：補充官網連結 (/p/商品編號)
    - 官網來源：從 DB 找同商品編號的 daybuy 討論連結
    - 所有商品：沒有圖片時從 products_master 找（之前任何時候爬過就有）
    """
    disc_map = get_discussion_map()

    conn = get_conn()
    img_rows = conn.execute(
        "SELECT 商品編號, 圖片URL FROM products_master WHERE 商品編號 != '' AND 圖片URL != ''"
    ).fetchall()
    img_map = {r[0]: r[1] for r in img_rows}

    for p in products:
        code = p.get("商品編號", "")
        link = p.get("商品連結", "")
        if not code:
            continue
        if "daybuy.tw" in link or "pttweb" in link:
            if not p.get("官網連結"):
                p["官網連結"] = f"https://www.costco.com.tw/p/{code}"
        if not p.get("討論連結") and code in disc_map:
            p["討論連結"] = disc_map[code]
        if not p.get("圖片URL") and code in img_map:
            p["圖片URL"] = img_map[code]
    return products
