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
_FALLBACK_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8928610067:AAGaDRiAPSBEoeQ0apjMKITsS6Yg4hZjt-E")
TG_TOKEN   = COSTCO_TG_TOKEN if COSTCO_TG_TOKEN else _FALLBACK_TOKEN
TG_CHAT_ID = COSTCO_TG_CHAT_ID

TG_MAX_LEN = 4000

# ── Line ──────────────────────────────────────────────────
LINE_TOKEN   = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")


# ── Telegram ──────────────────────────────────────────────

def tg_send(text: str) -> bool:
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
    bot_label = "好市多專用Bot" if COSTCO_TG_TOKEN else "台股Bot(暫用)"
    print(f"  📤 Telegram 發送（{bot_label}，共 {total} 段）")
    for i, chunk in enumerate(chunks, 1):
        ok = tg_send(chunk)
        print(f"    {'✅' if ok else '❌'} 第 {i}/{total} 段")
        if i < total:
            time.sleep(0.5)


# ── Line ──────────────────────────────────────────────────

def line_send(text: str) -> bool:
    if not LINE_TOKEN or not LINE_USER_ID:
        print("  ⚠️  Line Token / User ID 未設定，跳過 Line 推播")
        print("     → 請在 .env 設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_USER_ID")
        return False
    url = "https://api.line.me/v2/bot/message/push"
    payload = json.dumps({
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  ❌ Line 發送失敗：{e}")
        return False


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
    print(f"使用 Token：{'好市多專用' if COSTCO_TG_TOKEN else '台股Bot(fallback)'}")
    ok = tg_send(test_msg)
    print("Telegram:", "✅" if ok else "❌")
