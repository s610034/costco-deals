#!/bin/bash
# batch_verify_prices.sh
# 批次補充 products_master 原價，每次 500 個
cd /Users/ericchen/Documents/testthing/costco-deals
source "$(dirname "$0")/lib_net.sh"
mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/costco_verify_${TS}.log"
ERR="logs/costco_verify_${TS}_err.log"
touch "$LOG" "$ERR"
echo "[$(date)] 批次補充原價啟動" >> "$LOG"

attempt=0
while : ; do
  wait_for_network "$LOG"
  log_start=$(wc -c < "$LOG"); err_start=$(wc -c < "$ERR")
  /usr/bin/env python3 batch_verify_prices.py --size 500 >> "$LOG" 2>> "$ERR"
  rc=$?
  [ "$rc" -eq 0 ] && break

  # 補原價是逐筆 upsert，重跑只會接著補還缺的，可安全重試
  new_log=$(slice_since "$LOG" "$log_start"); new_err=$(slice_since "$ERR" "$err_start")
  if [ "$attempt" -lt "$MAX_RETRIES" ] && printf '%s\n%s\n' "$new_log" "$new_err" | is_network_failure; then
    attempt=$((attempt + 1))
    echo "[$(date)] 🔁 網路類失敗（exit $rc），${RETRY_DELAY} 秒後第 ${attempt}/${MAX_RETRIES} 次重試" >> "$LOG"
    sleep "$RETRY_DELAY"
    continue
  fi
  break
done

echo "[$(date)] 批次補充原價結束（exit $rc，重試 $attempt 次）" >> "$LOG"
find logs -name "costco_verify_*.log" -mtime +30 -delete 2>/dev/null
exit "$rc"
