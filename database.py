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
    # timeout + WAL + busy_timeout：多個排程（週報/補原價/分類）可能同時讀寫，
    # 避免 "database is locked" 直接崩潰（P4）
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def acquire_pipeline_lock(name: str = "costco_pipeline", wait_seconds: int = 600):
    """跨排程互斥鎖（flock）。取得回傳檔案握把（呼叫端須保存引用直到程序結束），
    等待逾時回傳 None。用於避免 run_costco / batch_verify / categorize 同時執行。"""
    import fcntl, time as _time
    lock_path = f"/tmp/{name}.lock"
    f = open(lock_path, "w")
    deadline = _time.time() + wait_seconds
    waited = False
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.seek(0); f.truncate(); f.write(str(os.getpid())); f.flush()
            if waited:
                print("🔓 取得排程鎖，繼續執行")
            return f
        except OSError:
            if not waited:
                print(f"⏳ 其他排程執行中（{lock_path}），等待中…（最長 {wait_seconds//60} 分鐘）")
                waited = True
            if _time.time() >= deadline:
                f.close()
                return None
            _time.sleep(10)


def init_db():
    """建立資料表（若不存在），並自動補上既有資料庫缺少的欄位（schema migration）"""
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
            資料來源      TEXT,
            折扣最後確認日 TEXT
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
            討論連結      TEXT DEFAULT "",
            資料來源      TEXT DEFAULT ""
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

    # === Schema migration：自動補上既有資料庫缺少的欄位 ===
    # CREATE TABLE IF NOT EXISTS 只在資料表「不存在」時生效，
    # 若資料表已存在但缺少新欄位（程式更新後），要用 ALTER TABLE 手動補上，
    # 否則會在查詢時出現 "no such column" 崩潰。
    required_columns = {
        "products": {
            "資料來源": "TEXT DEFAULT ''",
        },
        "products_master": {
            "資料來源": "TEXT",
            "折扣最後確認日": "TEXT",
        },
    }
    for table, cols in required_columns.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_def in cols.items():
            if col_name not in existing:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    print(f"  🔧 schema migration：{table}.{col_name} 已自動補上")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️  schema migration 失敗 {table}.{col_name}：{e}")
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
    return canonicalize_products(products)


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


def canonicalize_products(products: list) -> list:
    """顯示層正名與最終去重（不修改 DB 原始資料）：
    1. 有商品編號者，商品名稱以 products_master 官方名稱為準
       （修正社群爬蟲把敘述句當名稱的髒資料，如「這包 卜蜂紅燒棒腿」）
    2. 以商品編號做最終去重（同商品可能因官網/daybuy 連結不同而重複），
       保留優先序：有折扣金額 > 官網連結 > 較新；被捨棄那筆的討論連結/限定門市補進保留筆
    """
    conn = get_conn()
    master_names = dict(conn.execute(
        "SELECT 商品編號, 商品名稱 FROM products_master WHERE 商品編號 != ''"
    ).fetchall())
    conn.close()

    renamed = 0
    for p in products:
        code = p.get("商品編號", "")
        mname = master_names.get(code)
        if code and mname and mname != p.get("商品名稱"):
            p["商品名稱"] = mname
            renamed += 1

    def _score(p):
        return (
            1 if p.get("折扣金額") else 0,
            1 if "costco.com.tw" in (p.get("商品連結") or "") else 0,
            p.get("crawl_date") or "",
        )

    result, by_code = [], {}
    deduped = 0
    for p in products:
        code = p.get("商品編號", "")
        if not code:
            result.append(p)
            continue
        if code not in by_code:
            by_code[code] = p
            result.append(p)
        else:
            keep = by_code[code]
            drop = p
            if _score(p) > _score(keep):
                result[result.index(keep)] = p
                by_code[code] = p
                keep, drop = p, keep
            for f in ("討論連結", "限定門市", "優惠期間", "圖片URL"):
                if not keep.get(f) and drop.get(f):
                    keep[f] = drop[f]
            deduped += 1
    if renamed or deduped:
        print(f"🧹 正名 {renamed} 筆（master 官方名稱）、依商品編號去重 {deduped} 筆")
    return result
