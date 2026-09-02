#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy.py
將 docs/ 資料夾推送到 GitHub Pages
Token 從 .env 讀取，不寫死在程式碼中
"""

import os
import subprocess
import datetime
import base64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GITHUB_USER  = "s610034"
GITHUB_REPO  = "costco-deals"
CLEAN_REMOTE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}.git"


def run(cmd: str, cwd: str = BASE_DIR) -> tuple:
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def deploy() -> bool:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("❌ GITHUB_TOKEN 未設定，請在 .env 加入 GITHUB_TOKEN=你的token")
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
