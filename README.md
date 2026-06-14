# 好市多折扣週報 — Hermes 交接文件

## 🌐 網頁
👉 https://s610034.github.io/costco-deals/

---

## 📁 專案位置
```
~/Documents/testthing/costco-deals/
├── run_costco.py         # 主執行腳本（完整流程，8個 Step）
├── scraper.py            # Playwright 爬蟲（官網三個折扣頁）
├── daybuy_monitor.py     # daybuy @daybuy Telegram 頻道爬蟲
├── ptt_monitor.py        # PTT hypermall 板爬蟲
├── sighting_monitor.py   # daybuy 賣場目擊情報爬蟲
├── verify_prices.py      # 用商品編號去官網詳情頁驗證正確原價
├── crawl_all_products.py # 全量爬取官網所有商品（獨立維護任務）
├── generate_html.py      # 產生 HTML 報告
├── database.py           # SQLite 資料庫（含 products_master 表）
├── deploy.py             # GitHub Pages 部署
├── notify.py             # Telegram 推播
├── rebuild_html.py       # 用 DB 重建 HTML（不重新爬蟲）
├── formatter.py          # Telegram 摘要格式
├── run_costco.sh         # launchd 排程用的 shell wrapper
├── launch_costco.sh      # 手動開 Terminal 視窗執行
├── .env                  # Token 設定（不在 git）
├── data/
│   ├── costco_history.db      # 主資料庫（products + products_master）
│   ├── config.json            # 密碼 hash（跨設備同步）
│   ├── overrides.json         # 前端分類覆蓋
│   ├── ptt_cache.json         # PTT 文章快取
│   ├── daybuy_cache.json      # daybuy 快取
│   └── costco_deals_YYYYMMDD.json
└── docs/index.html       # GitHub Pages 首頁
```

---

## ⚙️ 重要設定
```
好市多 Bot Token:  8992203260:AAEhcwZL-Nc2FWnzMr1aykCZu7dbw3wXYaA
Chat ID:          843096573
GitHub Pages:     https://s610034.github.io/costco-deals/
GitHub User:      s610034
GitHub Token:     在 .env 的 GITHUB_TOKEN
編輯密碼:         在 .env 的 EDITOR_PASSWORD（預設 Eric99316125）
Log:              /tmp/costco_deals.log
排程:             週一 + 週三 09:15（launchd）
```

---

## 🔄 執行流程（run_costco.py）

```
Step 0：初始化 DB + 從 GitHub 同步前端分類覆蓋
Step 1：Playwright 爬官網三頁
  ├── 限時優惠 /c/hot-buys（~46筆，有優惠期間 .Wallet）
  ├── 精選優惠 /Deals/c/Coupon（~43筆）
  └── 把握優惠（只取有折扣金額的，通常 0 筆）
Step 1.5：daybuy @daybuy Telegram 補充
  └── 每條訊息去 daybuy.tw 文章補充：原價、商品編號、優惠期間
Step 1.6：PTT hypermall 板補充（只取 30 天內文章，解析多商品格式）
Step 1.7：用商品編號去官網詳情頁驗證正確原價
  └── DB 已有原價的直接套用（節省時間），沒有的才進詳情頁
Step 1.8：daybuy 賣場目擊情報
  └── 補充限定門市標記 + 發現賣場折扣商品
Step 2：存 JSON + 存 SQLite DB + 寫入 products_master
Step 3：從 DB 撈最近 30 天商品（去重合併，有折扣才撈）
Step 4：generate_html.py → docs/index.html
Step 5：deploy.py → GitHub Pages
Step 6：Telegram 推播
```

---

## 🗄️ 資料庫 Schema（SQLite）

### products 表（折扣歷史，時間性資料）
欄位：id, crawl_date, 商品名稱, 分類, 細分類, 原價, 折扣金額, 折扣幅度, 折扣後售價,
      優惠期間, 實體賣場, 圖片URL, 商品連結, 抓取時間, **商品編號**

### products_master 表（永久商品主資料庫）
欄位：商品編號(PK), 商品名稱, 分類, 細分類, 原價, 折扣金額, 折扣後售價, 圖片URL,
      商品連結, 最後更新, 資料來源
- 目前 **5,499 個商品**（100% 有商品編號，99% 有圖片）
- 來源：crawl_all_products 5,188 筆 + scraper_history 47 筆 + daybuy_sighting 264 筆
- 每次 run_costco.py 執行後自動更新

### category_overrides 表（前端分類覆蓋）

---

## 🌐 網頁功能
- Header 篩選：全部 / ⏰限時優惠 / 🏷️精選優惠（可疊加分類 Tab）
- 商品分類 Tab（8類）+ sticky
- 限時/精選優惠小標籤（卡片上顯示）
- 優惠期間標籤（有日期顯示日期）
- 📍縣市限定標籤（限定門市）
- 📰 daybuy 情報頁連結按鈕
- 搜尋功能
- 歷史折扣天數顯示
- 登入（密碼 Eric99316125）→ 手動修改分類，同步到 GitHub overrides.json

---

## 📊 全量商品爬蟲（獨立任務）
```bash
# 完整爬取所有分類（約 24 分鐘）
python3 crawl_all_products.py

# 繼續上次中斷的
python3 crawl_all_products.py --resume

# 測試模式（只爬前5個分類）
python3 crawl_all_products.py --test
```

---

## 🚀 快速指令
```bash
cd ~/Documents/testthing/costco-deals

# 完整流程
python3 run_costco.py

# 只重建 HTML（不重新爬蟲）
python3 rebuild_html.py

# 單獨測試各來源
python3 daybuy_monitor.py
python3 ptt_monitor.py
python3 sighting_monitor.py
python3 verify_prices.py

# 全量爬取官網商品
python3 crawl_all_products.py

# DB 統計
python3 -c "
import sqlite3
conn = sqlite3.connect('data/costco_history.db')
print('products:', conn.execute('SELECT COUNT(*) FROM products').fetchone()[0])
print('master:', conn.execute('SELECT COUNT(*) FROM products_master').fetchone()[0])
"
```

---

## 📋 待辦清單
1. **原價批次補充** — 對 products_master 沒有原價的商品，分批跑 verify_prices
2. **Step 1.7 改用 master** — 直接從 master 取原價，不再進官網詳情頁
3. **分類補完** — MAIN_CAT_MAP 補齊所有 cat_id，讓「其他」分類減少
4. **Line 推播** — `.env` 填入 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_USER_ID`
5. **TORRIDEN 面膜特價** — 每片 $37 不是整組，需修 daybuy 解析邏輯

---

## 📌 注意事項
- Python 3.9：不支援 `int | None`，用 `Optional[int]`
- 官網是 Angular SPA：用 `domcontentloaded` + sleep 等待（不用 networkidle）
- 分類頁 URL 格式：`/c/數字`（不是 `/c/英文名`）
- 子分類才有商品，大分類頁（如 `/c/8`）通常是 0
- launchd plist：`~/Library/LaunchAgents/com.ericchen.costcodeals.plist`
- `.env` 不在 git，需手動建立
