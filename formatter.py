#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
formatter.py
Telegram 摘要格式（只發 TOP5，完整資訊看 HTML）
"""

import json
import datetime
import os
from typing import List, Dict, Optional


def _fmt(val: Optional[int]) -> str:
    return f"${val:,}" if val is not None else "–"


def format_summary(products: List[Dict]) -> str:
    """Telegram 用：只發 TOP5 折扣摘要"""
    today = datetime.datetime.now().strftime("%Y/%m/%d")
    week_range = _get_week_range()

    top5 = sorted(
        [p for p in products if p.get("折扣金額")],
        key=lambda x: x["折扣金額"],
        reverse=True
    )[:5]

    lines = [
        f"🛒 好市多折扣週報  {today}",
        f"📅 {week_range}｜共 {len(products)} 項折扣",
        "",
        "🔥 本週 TOP 5 折扣：",
        "",
    ]

    for i, p in enumerate(top5, 1):
        name = p.get("商品名稱", "")
        orig = p.get("原價")
        sale = p.get("折扣後售價")
        amt  = p.get("折扣金額")
        pct  = p.get("折扣幅度", "")
        lines.append(f"{i}. {name}")
        if orig and amt:
            lines.append(f"   {_fmt(orig)} → {_fmt(sale)}  省 ${amt:,}（{pct}）")
        lines.append("")

    lines.append("👇 點下方連結看完整清單")
    return "\n".join(lines)


def _get_week_range() -> str:
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"{monday.strftime('%m/%d')}～{sunday.strftime('%m/%d')}"


def load_latest_json(data_dir: str) -> List[Dict]:
    if not os.path.isdir(data_dir):
        return []
    files = sorted([f for f in os.listdir(data_dir) if f.startswith("costco_deals_") and f.endswith(".json")])
    if not files:
        return []
    latest = os.path.join(data_dir, files[-1])
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)
