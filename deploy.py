#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy.py
將 docs/ 資料夾推送到 GitHub Pages
Token 從 .env 讀取，不寫死在程式碼中
"""

import os
import json
import subprocess
import datetime
import base64
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GITHUB_USER  = "s610034"
GITHUB_REPO  = "costco-deals"
CLEAN_REMOTE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}.git"
STATUS_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/docs/status.json"

# 品質閘門閾值：絕對底線 + 相對波動（兩者只要有一個沒過就擋下來）
QUALITY_GATE_ABS_MIN = 30       # 少於這個數字，不管前一次多少都視為嚴重事故
QUALITY_GATE_DROP_RATIO = 0.7   # 這次至少要有前一次的 70%，掉太多視為異常


def run(cmd: str, cwd: str = BASE_DIR) -> tuple:
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _quality_gate() -> tuple:
    """
    部署前的最後防線：拿這次產生的 docs/status.json 跟線上目前的比對，
    避免資料異常貧乏的版本（例如 GitHub Actions 用空白 DB 跑出來的）蓋掉正常版本。
    回傳 (是否放行, 說明文字)。
    - 讀不到本機 status.json：放行（舊版本沒有這個機制，不能因此卡住部署）
    - 讀不到線上 status.json（第一次部署、網路問題）：只檢查絕對底線，不比對相對波動
    - 環境變數 SKIP_QUALITY_GATE=1：強制放行（人工確認過是合理的大幅波動時使用）
    """
    if os.environ.get("SKIP_QUALITY_GATE") == "1":
        return True, "⚠️  SKIP_QUALITY_GATE=1，略過品質閘門"

    local_status_path = os.path.join(BASE_DIR, "docs", "status.json")
    try:
        with open(local_status_path, encoding="utf-8") as f:
            local_count = json.load(f)["item_count"]
    except Exception:
        return True, "ℹ️  找不到本機 status.json，略過品質閘門（可能是舊版本）"

    if local_count < QUALITY_GATE_ABS_MIN:
        return False, f"❌ 品質閘門：這次只有 {local_count} 筆，低於絕對底線 {QUALITY_GATE_ABS_MIN} 筆"

    try:
        with urllib.request.urlopen(STATUS_RAW_URL + f"?t={int(datetime.datetime.now().timestamp())}", timeout=10) as r:
            remote_count = json.loads(r.read())["item_count"]
    except Exception as e:
        return True, f"ℹ️  抓不到線上 status.json（{e}），只檢查絕對底線，本次通過"

    floor = max(QUALITY_GATE_ABS_MIN, remote_count * QUALITY_GATE_DROP_RATIO)
    if local_count < floor:
        return False, (
            f"❌ 品質閘門：這次 {local_count} 筆，線上目前 {remote_count} 筆，"
            f"掉了超過 {int((1 - QUALITY_GATE_DROP_RATIO) * 100)}%（門檻 {int(floor)} 筆）。"
            f"如果確認是合理波動（例如檔期大量到期），設環境變數 SKIP_QUALITY_GATE=1 再跑一次可強制部署。"
        )
    return True, f"✅ 品質閘門通過（這次 {local_count} 筆，線上 {remote_count} 筆）"


def deploy() -> bool:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("❌ GITHUB_TOKEN 未設定，請在 .env 加入 GITHUB_TOKEN=你的token")
        return False

    ok, msg = _quality_gate()
    print(f"  {msg}")
    if not ok:
        try:
            from notify import tg_send
            tg_send(f"🚨 好市多週報部署被品質閘門擋下\n{msg}")
        except Exception:
            pass
        return False

    # 認證用 extraheader 每次指令臨時帶入，不寫進 .git/config（避免 token 明文落地）
    basic = base64.b64encode(f"{GITHUB_USER}:{token}".encode()).decode()
    auth_flag = f'-c http.extraheader="AUTHORIZATION: basic {basic}"'
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"🚀 部署到 GitHub Pages...")

    # remote 維持乾淨無 token 的 URL（若之前殘留過帶 token 的版本，順手清掉）
    run(f'git remote set-url origin "{CLEAN_REMOTE_URL}"')
    run("git add docs/ README.md")

    code, out, err = run(f'git commit -m "📊 自動更新折扣週報 {today}"')
    if code != 0 and ("nothing to commit" in (out + err) or "no changes added to commit" in (out + err)):
        # 這次沒有新變更，但本機仍可能有前次因 pull --rebase 失敗而未推送的 commit，
        # 不能直接視為完成，要繼續往下走 pull + push（push 沒有東西推時本身就是無害的 no-op）
        print("ℹ️  無變更，略過 commit")
    elif code != 0:
        print(f"❌ git commit 失敗：{err}")
        return False
    else:
        print("  ✅ commit 完成")

    # 先同步遠端（避免蓋掉排程/手動部署彼此的 commit），再一般推送
    code, out, err = run(f"git {auth_flag} pull --rebase --autostash origin main")
    if code != 0:
        print(f"❌ git pull --rebase 失敗，中止部署：{err[:200]}")
        run("git rebase --abort")
        return False

    code, out, err = run(f"git {auth_flag} push origin main")
    if code != 0:
        print(f"❌ git push 失敗：{err[:200]}")
        return False

    print(f"  ✅ 推送成功")
    print(f"  🌐 https://{GITHUB_USER}.github.io/{GITHUB_REPO}/")
    return True


if __name__ == "__main__":
    deploy()
