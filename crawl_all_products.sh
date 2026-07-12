#!/bin/bash
# crawl_all_products.sh
# 全量爬取官網所有商品，更新 products_master 資料庫
echo "[$(date)] 全量商品爬蟲啟動" >> /tmp/costco_crawl_all.log
cd /Users/ericchen/Documents/testthing/costco-deals
/usr/bin/env python3 crawl_all_products.py >> /tmp/costco_crawl_all.log 2>> /tmp/costco_crawl_err.log
echo "[$(date)] 全量商品爬蟲結束" >> /tmp/costco_crawl_all.log

# 推播完成摘要（需先載入.env，否則token讀不到會靜默失敗）
tail -12 /tmp/costco_crawl_all.log | grep -E "處理分類|掃描商品|寫入 DB|全新商品|master 總數" > /tmp/crawl_all_summary.txt
/usr/bin/python3 -c "
import sys, os
sys.path.insert(0, '.')
os.chdir('/Users/ericchen/Documents/testthing/costco-deals')

with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ[k.strip()] = v.strip()

from notify import line_send, tg_send
with open('/tmp/crawl_all_summary.txt') as f:
    summary = f.read().strip()
msg = '📦 好市多全量爬蟲完成' + chr(10) + summary
line_send(msg)
tg_send(msg)
"
