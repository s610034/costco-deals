#!/bin/bash
# launch_costco.sh
# 開一個新的 Terminal 視窗，即時顯示好市多折扣週報執行狀況

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="/tmp/costco_deals.log"

osascript <<EOF
tell application "Terminal"
    activate
    set newTab to do script "echo '🛒 好市多折扣週報啟動中...' && echo '' && cd '$SCRIPT_DIR' && python3 run_costco.py; echo ''; echo '✅ 執行完畢，按任意鍵關閉'; read"
    set custom title of newTab to "好市多折扣週報"
end tell
EOF
