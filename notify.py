#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify.py
將折扣清單同時推播到 Telegram（好市多專用 Bot）與 Line
"""

import os
import json
import urllib.request
import time

# ── Telegram：好市多專用 Bot ──────────────────────────────
# 建立新 Bot：跟 @BotFather 說 /newbot，取得 Token 後填入 .env
COSTCO_TG_TOKEN   = os.environ.get("COSTCO_TG_TOKEN", "")      # 好市多專用 Bot Token
COSTCO_TG_CHAT_ID = os.environ.get("COSTCO_TG_CHAT_ID", "843096573")  # 預設沿用同一個 chat_id

# 若還沒建新 Bot，暫時 fallback 到台股 Bot
TG_TOKEN   = COSTCO_TG_TOKEN  # 沒有設定就不發送，不 fallback 到其他 bot
TG_CHAT_ID = COSTCO_TG_CHAT_ID

TG_MAX_LEN = 4000

# ── Line ──────────────────────────────────────────────────
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
# 多個接收對象：個人 User ID（逗號分隔）+ 群組 ID（逗號分隔）
LINE_USER_IDS  = [u.strip() for u in os.environ.get("LINE_USER_IDS", os.environ.get("LINE_USER_ID", "")).split(",") if u.strip()]
LINE_GROUP_IDS = [g.strip() for g in os.environ.get("LINE_GROUP_IDS", "").split(",") if g.strip()]


# ── Telegram ──────────────────────────────────────────────

def tg_send(text: str) -> bool:
    if not TG_TOKEN:
        print("  ⚠️  COSTCO_TG_TOKEN 未設定，跳過 Telegram 推播")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"  ❌ Telegram 發送失敗：{e}")
        return False


def tg_send_chunked(text: str) -> None:
    lines = text.split("\n")
    chunks, cur, cur_len = [], [], 0
    for line in lines:
        ll = len(line) + 1
        if cur_len + ll > TG_MAX_LEN and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [line], ll
        else:
            cur.append(line)
            cur_len += ll
    if cur:
        chunks.append("\n".join(cur))

    total = len(chunks)
    print(f"  📤 Telegram 發送（共 {total} 段）")
    for i, chunk in enumerate(chunks, 1):
        ok = tg_send(chunk)
        print(f"    {'✅' if ok else '❌'} 第 {i}/{total} 段")
        if i < total:
            time.sleep(0.5)


# ── Line ──────────────────────────────────────────────────

def _line_post(url: str, body: dict) -> bool:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        print(f"  ❌ Line 發送失敗：{e.code} {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ Line 發送失敗：{e}")
        return False


def line_send(text: str) -> bool:
    """
    推播給所有個人(multicast，一次API呼叫送多人，不限聊天室訊息計費規則)
    + 所有群組(各自 push，因為群組不支援 multicast)
    """
    if not LINE_TOKEN or (not LINE_USER_IDS and not LINE_GROUP_IDS):
        print("  ⚠️  Line Token / 收件人未設定，跳過 Line 推播")
        print("     → 請在 .env 設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_USER_IDS / LINE_GROUP_IDS")
        return False

    all_ok = True

    # 個人：multicast 一次送給所有人（最多 500 人/次）
    if LINE_USER_IDS:
        ok = _line_post("https://api.line.me/v2/bot/message/multicast", {
            "to": LINE_USER_IDS,
            "messages": [{"type": "text", "text": text}],
        })
        print(f"    {'✅' if ok else '❌'} 個人推播（{len(LINE_USER_IDS)} 人）")
        all_ok = all_ok and ok

    # 群組：不支援 multicast，逐個群組各發一次
    # 注意：群組推播的訊息計費 = 群組人數 × 發送次數，留意免費額度消耗
    for gid in LINE_GROUP_IDS:
        ok = _line_post("https://api.line.me/v2/bot/message/push", {
            "to": gid,
            "messages": [{"type": "text", "text": text}],
        })
        print(f"    {'✅' if ok else '❌'} 群組推播（{gid[:10]}...）")
        all_ok = all_ok and ok

    return all_ok


def line_send_chunked(text: str) -> None:
    MAX = 4800
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)]
    total = len(chunks)
    print(f"  📤 Line 發送（共 {total} 段）")
    for i, chunk in enumerate(chunks, 1):
        ok = line_send(chunk)
        print(f"    {'✅' if ok else '❌'} 第 {i}/{total} 段")
        if i < total:
            time.sleep(0.5)


# ── 主推播函式 ────────────────────────────────────────────

def notify_all(summary: str, full_message: str) -> None:
    combined = summary + "\n\n" + full_message
    print("\n📣 開始推播...")

    print("\n[Telegram]")
    tg_send_chunked(combined)

    print("\n[Line]")
    line_send_chunked(combined)

    print("\n✅ 推播完成")


if __name__ == "__main__":
    test_msg = "🛒 好市多折扣測試\n這是來自 Hermes 的好市多專用 Bot 測試！"
    print(f"使用 Token：{'好市多專用' if COSTCO_TG_TOKEN else '(未設定)'}")
    ok = tg_send(test_msg)
    print("Telegram:", "✅" if ok else "❌")
