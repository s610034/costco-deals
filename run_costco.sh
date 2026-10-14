#!/bin/bash
# 好市多折扣週報
cd /Users/ericchen/Documents/testthing/costco-deals
source "$(dirname "$0")/lib_net.sh"
mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/costco_deals_${TS}.log"
ERR="logs/costco_deals_${TS}_err.log"
touch "$LOG" "$ERR"
echo "[$(date)] 好市多腳本啟動" >> "$LOG"

attempt=0
while : ; do
  wait_for_network "$LOG"
  log_start=$(wc -c < "$LOG"); err_start=$(wc -c < "$ERR")
  /usr/bin/env python3 run_costco.py >> "$LOG" 2>> "$ERR"
  rc=$?
  [ "$rc" -eq 0 ] && break

  # 只在「網路類失敗」且「尚未進入存檔階段(Step 2)」才重試：
  # 過了 Step 2 代表資料已寫入/可能已推播，整支重跑會重複寫入與重複推播
  new_log=$(slice_since "$LOG" "$log_start"); new_err=$(slice_since "$ERR" "$err_start")
  if [ "$attempt" -lt "$MAX_RETRIES" ] \
     && ! printf '%s' "$new_log" | grep -q "【Step 2】" \
     && printf '%s\n%s\n' "$new_log" "$new_err" | is_network_failure; then
    attempt=$((attempt + 1))
    echo "[$(date)] 🔁 網路類失敗（exit $rc），${RETRY_DELAY} 秒後第 ${attempt}/${MAX_RETRIES} 次重試" >> "$LOG"
    sleep "$RETRY_DELAY"
    continue
  fi
  echo "[$(date)] ❌ 結束碼 $rc，不再重試（attempt=$attempt）" >> "$LOG"
  break
done

echo "[$(date)] 好市多腳本結束（exit $rc，重試 $attempt 次）" >> "$LOG"

# 保留最近 30 天，避免無限累積
find logs -name "costco_deals_*.log" -mtime +30 -delete 2>/dev/null
exit "$rc"
