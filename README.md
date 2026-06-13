# 好市多折扣週報 — Hermes 交接文件

## 🌐 網頁
👉 https://s610034.github.io/costco-deals/

---

## 📁 專案位置
```
~/Documents/testthing/costco-deals/
├── run_costco.py        # 主執行腳本（完整流程）
├── scraper.py           # Playwright 爬蟲（官網三個折扣頁）
├── costco_search.py     # 官網搜尋補充（社群商品補圖片/原價）
├── daybuy_monitor.py    # daybuy @daybuy Telegram 頻道爬蟲
├── ptt_monitor.py       # PTT hypermall 板爬蟲
├── generate_html.py     # 產生 HTML 報告
├── formatter.py         # Telegram 摘要格式
├── database.py          # SQLite 歷史資料庫
├── deploy.py            # GitHub Pages 部署
├── notify.py            # Telegram 推播
├── rebuild_html.py      # 用 DB 重新產生 HTML（不重新爬蟲）
├── run_costco.sh        # launchd 用的 shell wrapper
├── .env                 # Token 設定（不在 git）
├── data/                # JSON + SQLite + overrides
└── docs/index.html      # GitHub Pages 靜態網頁
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
Step 0：初始化 DB + 從 GitHub 同步前端分類覆蓋（overrides.json）
Step 1：Playwright 爬官網三頁
  ├── 限時優惠 https://costco.com.tw/c/hot-buys        (~46 筆)
  ├── 精選優惠 https://costco.com.tw/Deals/c/Coupon    (~43 筆)
  └── 把握優惠 https://costco.com.tw/While-Supplies-Last/c/Toogood
               （只取有折扣金額的，通常 0 筆，為線上限定）
Step 1.5：daybuy @daybuy Telegram 頻道補充（純 requests）
Step 1.6：PTT hypermall 板補充（pttweb.cc，純 requests）
  └── 只處理 30 天內文章，解析多商品格式
Step 1.7：社群商品去官網搜尋補充圖片/原價
  └── costco_search.py → search?q=商品名稱
Step 2：存 JSON + 存 SQLite DB
Step 3：從 DB 撈最近 30 天商品（去重合併）
Step 4：generate_html.py → docs/index.html
Step 5：deploy.py → GitHub Pages
Step 6：Telegram 推播
```

---

## 🗄️ 資料庫（SQLite）
- 位置：`data/costco_history.db`
- 表：`products`（爬取歷史）、`category_overrides`（前端分類覆蓋）
- 不會清空，每次執行只新增當天資料
- `rebuild_html.py` 讀 DB 重建 HTML（不重爬，用於修 HTML 樣式）

---

## 🌐 GitHub 相關檔案
- `data/config.json`：編輯密碼 hash（跨設備同步）
- `data/overrides.json`：前端分類覆蓋（使用者手動改的分類）
- `docs/index.html`：GitHub Pages 首頁

---

## 🖥️ 網頁功能
- Header 篩選：限時優惠 / 精選優惠
- 商品分類 Tab（8 個分類 + 其他）+ 橫向滾動（sticky）
- 商品搜尋
- 手動修改分類（登入後才能編輯，密碼 Eric99316125）
- 分類修改同步到 GitHub overrides.json（需在瀏覽器 Console 設定 Token）
- 優惠期間標籤（有日期顯示日期，把握優惠顯示🔥）
- 歷史折扣天數顯示

---

## 📋 注意事項
- Python 3.9：不支援 `int | None`，用 `Optional[int]`；f-string 不能有反斜線
- 官網是 Angular SPA，用 `domcontentloaded` + sleep 等待（不用 networkidle）
- Playwright page 要先去首頁接受 cookie 才能渲染商品頁
- launchd plist：`~/Library/LaunchAgents/com.ericchen.costcodeals.plist`
- `.env` 不在 git，需手動建立
- `data/` 在 `.gitignore`，但 `config.json` 和 `overrides.json` 用 `-f` force add

---

## 📋 待辦清單
1. **社群商品搜尋補充優化** — 部分商品原價抓不到（笑牛乾酪、嘉實多機油等）
2. **優惠週 → 多商品展開** — PTT 優惠週文章已可解析多商品
3. **Line 推播** — `.env` 填入 `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_USER_ID`
4. **daybuy 圖片補充** — daybuy 訊息有時附有圖片連結，可以嘗試抓取

---

## 🚀 快速指令
```bash
# 手動執行完整流程
cd ~/Documents/testthing/costco-deals && python3 run_costco.py

# 只重建 HTML（不重爬，用現有 DB 資料）
cd ~/Documents/testthing/costco-deals && python3 rebuild_html.py

# 單獨測試各來源
python3 daybuy_monitor.py
python3 ptt_monitor.py
python3 costco_search.py

# 查看 DB 統計
python3 -c "
import sqlite3, datetime
conn = sqlite3.connect('data/costco_history.db')
rows = conn.execute('SELECT crawl_date, COUNT(*) FROM products GROUP BY crawl_date ORDER BY crawl_date DESC LIMIT 10').fetchall()
for r in rows: print(r[0], r[1], '筆')
"
```
