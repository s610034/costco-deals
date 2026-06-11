# 好市多折扣週報

每週自動爬取 [costco.com.tw](https://www.costco.com.tw) 折扣商品，整理成手機友善的網頁並推播 Telegram 通知。

## 網頁
👉 https://s610034.github.io/costco-deals/

## 功能
- 每週一 08:00 自動執行
- 爬取限時優惠、精選優惠三個折扣頁
- 只保留有折扣金額的商品（自動過濾無折扣 / 線上限定）
- 商品依類別分類（食品飲料、家電3C、生活用品⋯⋯）
- 產生手機優先的響應式 HTML 報告
- 自動部署到 GitHub Pages
- Telegram 推播 TOP5 摘要 + 網頁連結

## 技術架構
- Python 3.9 + Playwright（爬蟲）
- GitHub Pages（靜態網頁 hosting）
- Telegram Bot API（推播）
- macOS launchd / crontab（排程）
