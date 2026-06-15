#!/bin/bash
# crawl_all_products.sh
# 全量爬取官網所有商品，更新 products_master 資料庫
echo "[$(date)] 全量商品爬蟲啟動" >> /tmp/costco_crawl_all.log
cd /Users/ericchen/Documents/testthing/costco-deals
/usr/bin/env python3 crawl_all_products.py >> /tmp/costco_crawl_all.log 2>> /tmp/costco_crawl_err.log
echo "[$(date)] 全量商品爬蟲結束" >> /tmp/costco_crawl_all.log
