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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GITHUB_USER  = "s610034"
GITHUB_REPO  = "costco-deals"


def run(cmd: str, cwd: str = BASE_DIR) -> tuple:
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def deploy() -> bool:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("❌ GITHUB_TOKEN 未設定，請在 .env 加入 GITHUB_TOKEN=你的token")
        return False

    repo_url = f"https://{GITHUB_USER}:{token}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"🚀 部署到 GitHub Pages...")

    run(f'git remote set-url origin "{repo_url}"')
    run("git add docs/ README.md")

    code, out, err = run(f'git commit -m "📊 自動更新折扣週報 {today}"')
    if code != 0 and "nothing to commit" in (out + err):
        print("ℹ️  無變更，略過 commit")
        return True
    if code != 0:
        print(f"❌ git commit 失敗：{err}")
        return False
    print("  ✅ commit 完成")

    code, out, err = run("git push origin main --force")
    if code != 0:
        print(f"❌ git push 失敗：{err[:200]}")
        return False

    print(f"  ✅ 推送成功")
    print(f"  🌐 https://{GITHUB_USER}.github.io/{GITHUB_REPO}/")
    return True


if __name__ == "__main__":
    deploy()
