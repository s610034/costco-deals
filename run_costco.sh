#!/bin/bash
# 好市多折扣週報
echo "[$(date)] 好市多腳本啟動" >> /tmp/costco_deals.log
cd /Users/ericchen/Documents/testthing/costco-deals
/usr/bin/env python3 run_costco.py >> /tmp/costco_deals.log 2>> /tmp/costco_deals_err.log
echo "[$(date)] 好市多腳本結束" >> /tmp/costco_deals.log
