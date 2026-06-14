#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup

urls = [
    ('好市多5/11-6/7優惠週商品分享', 'https://www.pttweb.cc/bbs/hypermall/M.1779184003.A.4D2'),
    ('生啤酒樂事洋芋片', 'https://www.pttweb.cc/bbs/hypermall/M.1775037154.A.0ED'),
    ('這期特價的牛肉捲', 'https://www.pttweb.cc/bbs/hypermall/M.1766834637.A.126'),
]

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

for title, url in urls:
    print(f'\n=== {title} ===')
    print(f'URL: {url}')
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f'Status: {r.status_code}, Length: {len(r.text)}')
        soup = BeautifulSoup(r.text, 'html.parser')

        # 試各種 selector
        found = False
        for sel in ['.article-content', '#main-content', '.e7-article-content',
                    '[class*="article"]', '.post-content', 'article', '.content']:
            el = soup.select_one(sel)
            if el:
                text = el.get_text('\n').strip()
                if len(text) > 50:
                    print(f'Selector: {sel}, len: {len(text)}')
                    print(text[:400])
                    found = True
                    break

        if not found:
            # 看所有 class 含 article 的元素
            els = soup.find_all(class_=lambda c: c and 'article' in c.lower() if c else False)
            print(f'article-related elements: {len(els)}')
            for el in els[:3]:
                print(f'  {el.get("class")} len={len(el.get_text())}')

            # 抓 body 文字
            body = soup.body
            if body:
                text = body.get_text('\n').strip()
                print(f'Body text (first 300):')
                print(text[:300])
    except Exception as e:
        print(f'Error: {e}')
