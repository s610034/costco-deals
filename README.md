# 好市多折扣週報 — Hermes 交接文件
最後更新：2026-06-26

## 🌐 網頁
👉 https://s610034.github.io/costco-deals/

## 📊 目前狀態快照（2026-06-26）
- products_master：6,152 個商品，原價覆蓋 43.7%，圖片覆蓋 99.4%
- 分類「其他」佔比：1.7%（已大幅整理，曾高達 74%）
- 人工分類覆蓋：245 筆（category_overrides 表）
- 三個輸出通路全部運作中：GitHub Pages、Telegram、LINE（多人+群組架構）

---

## 📁 專案位置與檔案
```
~/Documents/testthing/costco-deals/
├── run_costco.py          # 主執行腳本（完整流程：爬取→驗證→存DB→產生HTML→部署→推播）
├── scraper.py              # Playwright 爬蟲（官網三個折扣頁：限時/精選/把握優惠）
├── daybuy_monitor.py        # daybuy @daybuy Telegram 頻道爬蟲
├── ptt_monitor.py            # PTT hypermall 板爬蟲
├── sighting_monitor.py        # daybuy 賣場目擊情報爬蟲
├── costco_search.py           # 官網搜尋（PTT商品補商品編號用）
├── verify_prices.py           # 用商品編號去官網詳情頁驗證原價+折扣+圖片
├── batch_verify_prices.py     # 批次補充 products_master 原價（Hermes排程用）
├── crawl_all_products.py      # 全量爬取官網所有商品（週一三五排程）
├── categorize.py               # 商品自動分類（規則優先，可選AI輔助）
├── generate_html.py            # 產生 HTML 報告（約1100行）
├── database.py                  # SQLite 資料庫操作
├── deploy.py                     # GitHub Pages 部署
├── notify.py                      # Telegram + LINE 推播（multicast多人+群組）
├── rebuild_html.py                 # 用 DB 重建 HTML（不重新爬蟲）
├── line_id_finder.py                # 從webhook.site找新好友/群組的LINE ID
├── formatter.py                      # Telegram 摘要格式
├── run_costco.sh / crawl_all_products.sh / batch_verify_prices.sh
├── .env                                # 所有Token設定（不在git，內容見下方）
└── data/
    ├── costco_history.db              # 主資料庫
    ├── config.json                     # 密碼hash（跨設備同步）
    └── overrides.json                   # 分類覆蓋（跟DB雙向同步GitHub）
```

## 🔑 .env 內容（敏感資訊已遮蔽，實際值在本機檔案）
```
COSTCO_TG_TOKEN=             # Telegram bot token
COSTCO_TG_CHAT_ID=843096573
LINE_CHANNEL_ACCESS_TOKEN=   # LINE Messaging API token
LINE_USER_IDS=                # 逗號分隔，多個人推播用multicast
LINE_GROUP_IDS=                 # 逗號分隔，多個群組各自push
GITHUB_TOKEN=                    # 推送GitHub Pages用
EDITOR_PASSWORD=                  # 網頁編輯分類用的密碼
WEBHOOK_SITE_TOKEN=                 # line_id_finder.py查新好友ID用
```

---

## ⏰ 排程總覽

### launchd（Mac本機，開機才會跑）
| 排程 | 時間 | 任務 |
|---|---|---|
| com.ericchen.costcodeals | 週一三 09:15 | run_costco.py（折扣週報主流程） |
| com.ericchen.costcodeals.crawlall | 週一三 09:45 + 週五 09:15 | crawl_all_products.py（全量爬蟲） |
| com.ericchen.costcodeals.verifyprices | 週一三五 10:30 | batch_verify_prices.py --size 500（舊版，跟Hermes排程重複，待整理） |
| com.ericchen.lmstudio.server | 開機時 | LM Studio API server常駐 |

### Hermes cron（不需要Mac開機才跑，常駐gateway）
| 排程ID | 名稱 | 時間 | 腳本 |
|---|---|---|---|
| 582f60946d51 | costco-batch-verify-prices | 週一三五 11:00 | ~/.hermes/scripts/costco_batch_verify.sh |
| 1ab03710c06e | costco-categorize | 週一三五 11:45 | ~/.hermes/scripts/costco_categorize.sh |

**重要**：這兩個Hermes排程都是 `no-agent` 模式（純跑腳本，不經過LLM，不會出現編造/幻覺問題）。
背景啟動主任務後另開一個監看程序（costco_verify_watcher.py），真正跑完才會推播LINE+Telegram完成摘要。
原本11:00/11:30會撞期造成DB lock，已改為11:00/11:45錯開。

### GitHub Actions（備援，Mac沒開機時用）
`.github/workflows/costco-deals.yml`：週一三 09:15 UTC+8，public repo完全免費無限制。

---

## 🛒 資料來源與處理流程
1. **官網折扣頁**（限時/精選/把握優惠）→ scraper.py 直接爬
2. **daybuy Telegram頻道**（@daybuy）→ 解析訊息，補商品編號去官網驗證
3. **PTT hypermall板** → 解析商品名稱 → costco_search.py 搜尋取得編號 → verify_prices.py驗證有無折扣
4. **daybuy賣場目擊情報** → 補充「實體賣場限定」標記
5. **daybuy隱藏優惠懶人包/品牌特展** → **目前無自動化**，每週一三由我（Claude）用Chrome MCP人工看圖分析，
   寫入DB時標記 `資料來源='hidden_sighting'`，前端顯示「🏪賣場隱藏」標籤+確認日期提示
6. **daybuy網站偶爾500錯誤時**：可用 Hermes 的 browser toolset 透過搜尋引擎找內容繞過
   （已驗證可行：`hermes -z "用瀏覽器搜尋..." -t browser`）

## 🏷️ 分類系統重要原則
- `分類`欄位 = 折扣類型（限時優惠/精選優惠/其他），跟商品種類無關
- `細分類`欄位 = 商品種類（食品飲料/服飾時尚/家電3C等），這才是前端tab分類依據
- **card_id 統一用商品編號**（`p_商品編號`格式），不要用連結截斷字串
  （這是修過的重大bug：舊版用連結最後35字元當key，同商品因連結長度差異產生多個衝突key）
- `資料來源='hidden_sighting'` 的商品（人工confirm的賣場隱藏優惠）：
  - 折扣金額/優惠期間視為「暫時性快照」，不是永久狀態
  - 不受「只顯示今日資料」限制，優惠期間內(14天緩衝)持續顯示
  - 圖片優先用官網圖（如果有），沒有才用daybuy現場照片

## ⚠️ 已知重大bug修復記錄（避免重蹈覆轍）
1. **官網改版**：折扣class從`.savings`變成`.discount-row-message`，已修復scraper.py
2. **前端atob()解碼缺UTF-8步驟**：每次讀取GitHub上現有分類時把中文讀成亂碼再寫回去，
   這是「編輯分類後又自己變亂碼」反覆發生的根本原因，已修正為TextDecoder("utf-8")
3. **verify_product_price從未抓圖片**：只驗證價格，後來補上圖片邏輯，且用alt屬性比對
   商品名稱避免抓到頁面推薦商品的錯誤圖片
4. **rebuild_html.py執行順序陷阱**：每次會先拉GitHub舊資料覆寫DB，若DB剛被手動改過、
   還沒推送到GitHub就跑rebuild，會被蓋掉。正確順序：改DB→立即推送GitHub→才跑rebuild

---

## 🤖 Hermes Agent 整合狀態
- **costco-deals skill**：已安裝在主profile和manager profile兩邊
  （`~/.hermes/skills/costco-deals/` 和 `~/.hermes/profiles/manager/skills/costco-deals/`）
- **SOUL.md**（主+manager）已加入好市多專案說明，並有「鐵則」：
  好市多任務第一步必須`skill_view(name='costco-deals')`，不准自行猜測指令/參數
- **已知行為問題**：偶爾仍會退化成自己嘗試讀取底層腳本（如verify_prices.py）而非用skill裡的
  正確入口（batch_verify_prices.py），遇到時直接糾正：「請先載入costco-deals skill」
- **LM Studio本地fallback**：已裝llama-3-taiwan-8b-instruct（繁中優化），server常駐自動啟動

---

## 📲 LINE推播架構
- Messaging API（非LINE Notify，已停用），官方帳號「好市多特價」
- `LINE_USER_IDS`：multicast一次推給所有個人（逗號分隔多個）
- `LINE_GROUP_IDS`：群組不支援multicast，逐個群組各push一次（計費=人數×次數，留意額度）
- 新增好友/群組：對方說一句話後執行 `python3 line_id_finder.py --add`，從webhook.site抓ID
- webhook.site只保留7天資料，之後考慮換Cloudflare Workers做永久+即時記錄（尚未實作）

---

## 📋 待辦事項
1. 原價覆蓋率持續提升（目前43.7%，每次排程+385~450個）
2. launchd的verifyprices排程跟Hermes排程重複，考慮移除其中一個
3. LINE群組推播尚未實測（目前只驗證過個人推播）
4. 考慮Cloudflare Workers取代webhook.site，做到加好友即時自動記錄
5. generate_html.py已1100行，可考慮拆分HTML模板
6. 每週一、三daybuy隱藏優惠懶人包人工分析（非自動化，需Eric在對話中提出）
