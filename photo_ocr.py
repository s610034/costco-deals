# -*- coding: utf-8 -*-
"""
photo_ocr.py — 賣場價牌照片 OCR（方案三）
用 Gemini 免費層視覺能力讀出價牌上的：商品編號、特價、折扣、原價、期限。
配對策略：以 OCR 讀到的商品編號為準（位置配對只當備援），
解決 daybuy 文章「照片在連結前」造成的錯位問題。
結果以照片 URL 為 key 快取於 data/photo_ocr_cache.json，每週只 OCR 新照片。
"""
import os, json, base64, time, re, urllib.request, urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "data", "photo_ocr_cache.json")
GEMINI_MODEL = "gemini-flash-lite-latest"

def _gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

_PROMPT = (
    "這是好市多賣場的價牌照片。讀出以下資訊，只輸出 JSON、不要其他文字：\n"
    '{"商品編號": "數字字串"或null, "特價": 數字或null, "折扣": 數字或null, '
    '"原價": 數字或null, "期限": "MM/DD"或null}\n'
    "說明：特價=結帳價格，折扣=折抵金額（如「省70」「-70」），"
    "原價=特價+折扣（價牌上的劃線價），期限=優惠截止日。讀不到的欄位填 null。"
)

def _ocr_one(img_url, key):
    """OCR 單張照片，失敗回傳 {}"""
    try:
        safe_url = urllib.parse.quote(img_url, safe=":/?&=%")
        req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0"})
        img_data = urllib.request.urlopen(req, timeout=25).read()
        if len(img_data) > 4000000:
            return {}
        body = json.dumps({
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/jpeg",
                                 "data": base64.b64encode(img_data).decode()}},
                {"text": _PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 300, "temperature": 0},
        }).encode()
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % GEMINI_MODEL,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        text = r["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"```(?:json)?|```", "", text).strip()
        data = json.loads(text)
        out = {}
        code = data.get("商品編號")
        if code and re.fullmatch(r"\d{4,9}", str(code)):
            out["ocr_編號"] = str(code)
        for k in ("特價", "折扣", "原價"):
            v = data.get(k)
            if isinstance(v, (int, float)) and 0 < v < 1000000:
                out[k] = int(v)
        exp = data.get("期限")
        if exp and re.match(r"^\d{1,2}/\d{1,2}$", str(exp)):
            out["期限"] = str(exp)
        return out
    except Exception as e:
        print("    ⚠️ OCR 失敗（%s）：%s" % (img_url[-30:], e))
        return {}

def _load_cache():
    try:
        return json.load(open(CACHE_PATH, encoding="utf-8"))
    except Exception:
        return {}

def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def enrich_photo_deals_with_ocr(deals, max_new=200, sleep_seconds=4.2):
    """對照片價商品做 OCR，把價格附回 deals。
    - 快取：同一張照片只 OCR 一次
    - 配對：優先用 OCR 讀到的商品編號對回 deals；讀不到編號才信任位置配對
    - Gemini 免費層約 15 RPM → 每張間隔 4.2 秒
    """
    key = _gemini_key()
    if not key:
        print("  ⚠️ 未設定 GEMINI_API_KEY，照片價格 OCR 停用")
        return deals

    cache = _load_cache()
    todo = [d for d in deals if d.get("照片URL") and d["照片URL"] not in cache]
    todo = todo[:max_new]
    if todo:
        print("  🔍 照片 OCR：%d 張新照片（快取已有 %d）..." % (len(todo), len(cache)))
    done = 0
    for d in todo:
        cache[d["照片URL"]] = _ocr_one(d["照片URL"], key)
        done += 1
        if done % 20 == 0:
            print("    …%d/%d" % (done, len(todo)))
            _save_cache(cache)
        time.sleep(sleep_seconds)
    _save_cache(cache)

    by_code = {}
    for url, r in cache.items():
        if r.get("ocr_編號"):
            by_code.setdefault(r["ocr_編號"], (url, r))

    matched = mismatched = positional = 0
    for d in deals:
        code = d.get("商品編號", "")
        hit = by_code.get(code)
        if hit:
            url, r = hit
            d["照片URL"] = url  # 修正錯位：換成真正屬於此商品的照片
            for k in ("特價", "折扣", "原價", "期限"):
                if r.get(k):
                    d[k] = r[k]
            matched += 1
            continue
        r = cache.get(d.get("照片URL", ""), {})
        if r.get("ocr_編號") and r["ocr_編號"] != code:
            mismatched += 1  # 照片不屬於此商品，不附價格
        elif r:
            for k in ("特價", "折扣", "原價", "期限"):
                if r.get(k):
                    d[k] = r[k]
            positional += 1
    print("  ✅ OCR 配對：編號精確 %d、位置備援 %d、錯位剔除 %d" % (matched, positional, mismatched))
    return deals

if __name__ == "__main__":
    import sys
    from sighting_monitor import fetch_sighting_photo_deals
    deals = fetch_sighting_photo_deals(7)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    deals = enrich_photo_deals_with_ocr(deals, max_new=n)
    priced = [d for d in deals if d.get("特價") or d.get("折扣")]
    print("\n有價格的照片商品：%d/%d" % (len(priced), len(deals)))
    for d in priced[:8]:
        print("  #%s %s 特價%s 折%s 期限%s" % (
            d["商品編號"], d["商品名稱"][:24], d.get("特價"), d.get("折扣"), d.get("期限")))
