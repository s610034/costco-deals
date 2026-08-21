#!/bin/bash
# batch_verify_prices.sh
# 批次補充 products_master 原價，每次 500 個
cd /Users/ericchen/Documents/testthing/costco-deals
mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/costco_verify_${TS}.log"
ERR="logs/costco_verify_${TS}_err.log"
echo "[$(date)] 批次補充原價啟動" >> "$LOG"
/usr/bin/env python3 batch_verify_prices.py --size 500 >> "$LOG" 2>> "$ERR"
echo "[$(date)] 批次補充原價結束" >> "$LOG"

find logs -name "costco_verify_*.log" -mtime +30 -delete 2>/dev/null
