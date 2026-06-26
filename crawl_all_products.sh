#!/bin/bash
# crawl_all_products.sh
# 全量爬取官網所有商品，更新 products_master 資料庫
echo "[$(date)] 全量商品爬蟲啟動" >> /tmp/costco_crawl_all.log
cd /Users/ericchen/Documents/testthing/costco-deals
/usr/bin/env python3 crawl_all_products.py >> /tmp/costco_crawl_all.log 2>> /tmp/costco_crawl_err.log
echo "[$(date)] 全量商品爬蟲結束" >> /tmp/costco_crawl_all.log

# 推播完成摘要
SUMMARY=$(tail -10 /tmp/costco_crawl_all.log | grep -E "處理分類|商品總計|master 增加")
/usr/bin/python3 -c "
import sys
sys.path.insert(0, '.')
from notify import line_send, tg_send
msg = '📦 好市多全量爬蟲完成\n$SUMMARY'
line_send(msg)
tg_send(msg)
"
