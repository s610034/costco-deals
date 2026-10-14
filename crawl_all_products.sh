#!/bin/bash
# crawl_all_products.sh
# 全量爬取官網所有商品，更新 products_master 資料庫
cd /Users/ericchen/Documents/testthing/costco-deals
source "$(dirname "$0")/lib_net.sh"
mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/costco_crawl_all_${TS}.log"          # 爬蟲本體自己寫入（每次嘗試開頭會清空，所以重試用獨立檔名）
WRAP="logs/costco_crawl_all_${TS}_wrap.log"    # wrapper 自己的狀態訊息（等網路、重試）
ERR="logs/costco_crawl_all_${TS}_err.log"
touch "$ERR"
echo "[$(date)] 全量商品爬蟲啟動" >> "$WRAP"

attempt=0
CUR_LOG="$LOG"
extra_args=""
while : ; do
  wait_for_network "$WRAP"
  err_start=$(wc -c < "$ERR")
  CRAWL_LOG_FILE="$CUR_LOG" /usr/bin/env python3 crawl_all_products.py $extra_args >> /dev/null 2>> "$ERR"
  rc=$?
  [ "$rc" -eq 0 ] && break

  new_err=$(slice_since "$ERR" "$err_start")
  if [ "$attempt" -lt "$MAX_RETRIES" ] && printf '%s\n' "$new_err" | is_network_failure; then
    attempt=$((attempt + 1))
    # 重試改用 --resume：已完成的分類不重爬（進度記錄在 data/crawl_state.json）
    extra_args="--resume"
    CUR_LOG="${LOG%.log}_retry${attempt}.log"
    echo "[$(date)] 🔁 網路類失敗（exit $rc），${RETRY_DELAY} 秒後第 ${attempt}/${MAX_RETRIES} 次重試（--resume）" >> "$WRAP"
    sleep "$RETRY_DELAY"
    continue
  fi
  break
done

echo "[$(date)] 全量商品爬蟲結束（exit $rc，重試 $attempt 次）" >> "$WRAP"
find logs -name "costco_crawl_all_*.log" -mtime +30 -delete 2>/dev/null

# 失敗就不要推播「完成」：爬蟲本身崩潰時已自行發失敗通知，這裡再發「完成」會誤導
if [ "$rc" -ne 0 ]; then
  echo "[$(date)] ❌ 最終失敗，略過完成推播" >> "$WRAP"
  exit "$rc"
fi

# 推播完成摘要（需先載入.env，否則token讀不到會靜默失敗）
tail -12 "$CUR_LOG" | grep -E "處理分類|掃描商品|寫入 DB|全新商品|master 總數" > /tmp/crawl_all_summary.txt
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
