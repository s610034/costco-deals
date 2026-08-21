#!/bin/bash
# 好市多折扣週報
cd /Users/ericchen/Documents/testthing/costco-deals
mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/costco_deals_${TS}.log"
ERR="logs/costco_deals_${TS}_err.log"
echo "[$(date)] 好市多腳本啟動" >> "$LOG"
/usr/bin/env python3 run_costco.py >> "$LOG" 2>> "$ERR"
echo "[$(date)] 好市多腳本結束" >> "$LOG"

# 保留最近 30 天，避免無限累積
find logs -name "costco_deals_*.log" -mtime +30 -delete 2>/dev/null
