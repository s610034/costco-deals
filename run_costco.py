#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_costco.py
好市多折扣週報 — 主執行腳本
流程：爬取 → 儲存 → 產生 HTML → 部署 GitHub Pages → 推播摘要
"""

import os
import sys
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and val and key not in os.environ:
                os.environ[key] = val

load_env()

from scraper import scrape_all, save_json
from formatter import format_summary
from generate_html import generate_html
from deploy import deploy
from notify import tg_send

DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
PAGE_URL  = "https://s610034.github.io/costco-deals/"


def run():
    start = datetime.datetime.now()
    today = start.strftime("%Y%m%d")
    print(f"\n{'='*50}")
    print(f"🛒 好市多折扣週報啟動")
    print(f"⏰ {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # Step 1：爬取
    print("【Step 1】爬取好市多折扣頁面...")
    try:
        products = scrape_all()
    except Exception as e:
        print(f"❌ 爬取失敗：{e}")
        tg_send(f"⚠️ 好市多折扣週報失敗\n爬取錯誤：{e}")
        return False

    if not products:
        tg_send("⚠️ 好市多折扣週報：本週未抓到折扣商品")
        return False

    # Step 2：儲存 JSON
    print(f"\n【Step 2】儲存資料...")
    try:
        save_json(products, DATA_DIR)
    except Exception as e:
        print(f"⚠️  JSON 儲存失敗（繼續）：{e}")

    # Step 3：產生 HTML
    print(f"\n【Step 3】產生 HTML 報告...")
    html_path = os.path.join(DOCS_DIR, f"costco_{today}.html")
    try:
        generate_html(products, html_path)
    except Exception as e:
        print(f"❌ HTML 產生失敗：{e}")
        tg_send(f"⚠️ 好市多折扣週報 HTML 產生失敗：{e}")
        return False

    # Step 4：部署到 GitHub Pages
    print(f"\n【Step 4】部署到 GitHub Pages...")
    deployed = deploy()

    # Step 5：Telegram 推播摘要
    print(f"\n【Step 5】推播 Telegram 摘要...")
    summary = format_summary(products)
    report_url = f"{PAGE_URL}costco_{today}.html"
    msg = summary + f"\n\n📱 完整折扣清單（手機可看）：\n{report_url}"
    if not deployed:
        msg += "\n\n⚠️ 注意：GitHub Pages 部署失敗，連結可能尚未更新"
    tg_send(msg)
    print("  ✅ Telegram 已發送")

    elapsed = (datetime.datetime.now() - start).seconds
    print(f"\n{'='*50}")
    print(f"✅ 完成！{len(products)} 項折扣，耗時 {elapsed} 秒")
    print(f"🌐 {report_url}")
    print(f"{'='*50}\n")
    return True


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
