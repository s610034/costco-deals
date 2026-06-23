#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
line_id_finder.py
小工具：掃描 webhook.site 最近收到的 LINE webhook 請求，
自動解析出個人 User ID 和群組 Group ID，並可選擇直接加入 .env

使用前置：
  1. 確認 .env 裡有設定 WEBHOOK_SITE_TOKEN（webhook.site 網址裡的那段 UUID）
     例如 https://webhook.site/26ea2ee4-ff22-4b78-b6b7-c5f22093c8cf
     → WEBHOOK_SITE_TOKEN=26ea2ee4-ff22-4b78-b6b7-c5f22093c8cf
  2. 請新成員加好友（或把官方帳號邀進群組）後說一句話

執行方式：
  python3 line_id_finder.py                # 列出最近收到的 ID，不寫入 .env
  python3 line_id_finder.py --add          # 列出後互動詢問是否加入 .env
"""

import os, sys, json, urllib.request, argparse

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env() -> dict:
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def fetch_recent_requests(token: str, per_page: int = 30) -> list:
    url = f"https://webhook.site/token/{token}/requests?sorting=newest&per_page={per_page}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return data.get("data", [])


def parse_line_ids(requests_list: list) -> dict:
    """從每個 webhook 請求的 content 解析出 userId / groupId，附上文字內容跟時間"""
    found = {"users": {}, "groups": {}}
    for req in requests_list:
        content = req.get("content", "")
        if not content:
            continue
        try:
            body = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue
        for event in body.get("events", []):
            source = event.get("source", {})
            text = event.get("message", {}).get("text", "") or f"[{event.get('type', '')}]"
            created = req.get("created_at", "")

            uid = source.get("userId")
            gid = source.get("groupId")

            if gid:
                found["groups"].setdefault(gid, []).append((created, text))
            elif uid:
                found["users"].setdefault(uid, []).append((created, text))
    return found


def update_env_list(key: str, new_id: str) -> bool:
    """把 new_id 加進 .env 裡 key 對應的逗號分隔清單（不重複加入）"""
    env = load_env()
    existing = [x.strip() for x in env.get(key, "").split(",") if x.strip()]
    if new_id in existing:
        print(f"  ℹ️  {new_id[:12]}... 已經在 {key} 裡了")
        return False
    existing.append(new_id)
    new_value = ",".join(existing)

    with open(ENV_PATH) as f:
        lines = f.readlines()
    found_line = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={new_value}\n"
            found_line = True
            break
    if not found_line:
        lines.append(f"{key}={new_value}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)
    print(f"  ✅ 已加入 {key}：{new_id[:12]}...")
    return True


def main():
    parser = argparse.ArgumentParser(description="從 webhook.site 找出 LINE User/Group ID")
    parser.add_argument("--add", action="store_true", help="互動式詢問是否加入 .env")
    args = parser.parse_args()

    env = load_env()
    token = env.get("WEBHOOK_SITE_TOKEN", "")
    if not token:
        print("❌ 請先在 .env 設定 WEBHOOK_SITE_TOKEN（webhook.site 網址裡的 UUID）")
        sys.exit(1)

    print(f"🔍 查詢 webhook.site/{token} 最近的請求...")
    try:
        requests_list = fetch_recent_requests(token)
    except Exception as e:
        print(f"❌ 查詢失敗：{e}")
        sys.exit(1)

    found = parse_line_ids(requests_list)

    existing_users = set(x.strip() for x in env.get("LINE_USER_IDS", "").split(",") if x.strip())
    existing_groups = set(x.strip() for x in env.get("LINE_GROUP_IDS", "").split(",") if x.strip())

    print(f"\n📋 找到 {len(found['users'])} 個個人、{len(found['groups'])} 個群組\n")

    print("── 個人 User ID ──")
    for uid, events in found["users"].items():
        tag = "（已在清單）" if uid in existing_users else "（新）"
        last_text = events[-1][1][:30]
        print(f"  {uid}  {tag}  最近訊息：{last_text}")
        if args.add and uid not in existing_users:
            ans = input(f"    要加入 LINE_USER_IDS 嗎？(y/N) ").strip().lower()
            if ans == "y":
                update_env_list("LINE_USER_IDS", uid)

    print("\n── 群組 Group ID ──")
    for gid, events in found["groups"].items():
        tag = "（已在清單）" if gid in existing_groups else "（新）"
        last_text = events[-1][1][:30]
        print(f"  {gid}  {tag}  最近訊息：{last_text}")
        if args.add and gid not in existing_groups:
            ans = input(f"    要加入 LINE_GROUP_IDS 嗎？(y/N) ").strip().lower()
            if ans == "y":
                update_env_list("LINE_GROUP_IDS", gid)

    if not args.add:
        print("\n💡 提示：加上 --add 參數可以互動式加入 .env")


if __name__ == "__main__":
    main()
