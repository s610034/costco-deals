#!/bin/bash
# lib_net.sh — 排程 wrapper 共用：等網路就緒 + 判斷是否為網路類失敗
#
# 背景：launchd 09:15 觸發時 Mac 常剛從睡眠喚醒，網路還沒起來，Playwright 直接
# ERR_INTERNET_DISCONNECTED／DNS 失敗，整支排程白跑（連 Telegram 告警也送不出去）。
# 2026-09-28～10-12 七次排程有五次是這樣失敗。用法：source 本檔後呼叫各函式。

NET_CHECK_URL="${NET_CHECK_URL:-https://www.costco.com.tw/}"
NET_WAIT_MAX="${NET_WAIT_MAX:-600}"        # 等網路最長秒數
NET_WAIT_INTERVAL="${NET_WAIT_INTERVAL:-15}"
MAX_RETRIES="${MAX_RETRIES:-2}"            # 網路類失敗最多重試次數
RETRY_DELAY="${RETRY_DELAY:-30}"           # 重試前先歇幾秒

# 網路是否通：只要拿得到任何 HTTP 狀態碼（含 403）就算通，000 代表 DNS/連線失敗
net_ok() {
  local code
  code=$(curl -s -o /dev/null --max-time 8 -w '%{http_code}' "$NET_CHECK_URL" 2>/dev/null)
  [ -n "$code" ] && [ "$code" != "000" ]
}

# wait_for_network <log_file>：等到網路通或逾時；逾時回傳 1（呼叫端仍會照常執行一次，保留原本的失敗紀錄）
wait_for_network() {
  local log="$1" waited=0
  net_ok && return 0
  echo "[$(date)] ⏳ 網路尚未就緒，等待中（最長 ${NET_WAIT_MAX} 秒）" >> "$log"
  while [ "$waited" -lt "$NET_WAIT_MAX" ]; do
    sleep "$NET_WAIT_INTERVAL"
    waited=$((waited + NET_WAIT_INTERVAL))
    if net_ok; then
      echo "[$(date)] 🌐 網路已就緒（等了 ${waited} 秒）" >> "$log"
      return 0
    fi
  done
  echo "[$(date)] ⚠️ 等了 ${NET_WAIT_MAX} 秒網路仍未就緒，仍嘗試執行一次" >> "$log"
  return 1
}

# slice_since <file> <offset>：印出 offset 之後新增的內容（只分析「這一次嘗試」產生的輸出）
slice_since() {
  tail -c +$(( $2 + 1 )) "$1" 2>/dev/null
}

# is_network_failure：從 stdin 判斷內容是否含網路類錯誤特徵
# （含首頁載入逾時 Page.goto Timeout：2026-10-14 補原價因此崩潰卻沒被重試）
is_network_failure() {
  grep -qE "ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION_(RESET|REFUSED|TIMED_OUT|CLOSED)|ERR_TIMED_OUT|Page\.goto: Timeout [0-9]+ms exceeded|nodename nor servname|Temporary failure in name resolution"
}
