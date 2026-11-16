"""價格規則回歸測試（2026-11-16 原價錯誤修正）。執行：/usr/bin/python3 -m unittest tests.test_price_rules"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper import parse_number
from verify_prices import check_price_invariants


class PriceRules(unittest.TestCase):
    def test_parse_number_takes_first_price_only(self):
        self.assertEqual(parse_number("$1,349 $1,349 $1,349 $1,079"), 1349)  # 曾被串成 1349134913491079
        self.assertEqual(parse_number("1,349.00"), 1349)                       # 曾變成 134900
        self.assertEqual(parse_number("商品已折價$395"), 395)
        self.assertIsNone(parse_number(""))

    def test_invariants_accept_official_triplets(self):
        good = [{"原價": 1969, "折扣金額": 395, "折扣後售價": 1574},      # 990255 善存
                {"原價": 24999, "折扣金額": 5000, "折扣後售價": 19999},   # 161519 Samsung
                {"原價": 17999, "折扣金額": 3600, "折扣後售價": 14399}]   # 159183 LG
        ok, bad = check_price_invariants(good)
        self.assertEqual((len(ok), len(bad)), (3, 0))

    def test_invariants_reject_double_discount_and_concat(self):
        bad_in = [{"原價": 1574, "折扣金額": 395, "折扣後售價": 1179},     # 舊錯誤：原價=折後價
                  {"原價": 104910491049, "折扣金額": 210, "折扣後售價": 104910490839},
                  {"原價": 100, "折扣金額": 10, "折扣後售價": 100}]        # 售價不低於原價
        ok, bad = check_price_invariants(bad_in)
        self.assertEqual(len(bad), 2)  # 第一筆算術自洽（1574-395=1179），不變式抓不到，靠爬蟲規則與官網比對把關


if __name__ == "__main__":
    unittest.main()
