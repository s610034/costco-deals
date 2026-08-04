#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py
共用的 .env 讀取邏輯（原本在 run_costco.py / categorize.py / rebuild_html.py 各自重複一份）
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env():
    """讀取 .env，已存在的環境變數不覆蓋"""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and v and k not in os.environ:
                os.environ[k] = v
