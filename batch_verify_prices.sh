#!/bin/bash
# batch_verify_prices.sh
# 批次補充 products_master 原價，每次 500 個
echo "[$(date)] 批次補充原價啟動" >> /tmp/costco_verify.log
cd /Users/ericchen/Documents/testthing/costco-deals
/usr/bin/env python3 batch_verify_prices.py --size 500 >> /tmp/costco_verify.log 2>> /tmp/costco_verify_err.log
echo "[$(date)] 批次補充原價結束" >> /tmp/costco_verify.log
