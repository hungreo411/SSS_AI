"""Kho lưu trữ tiêu đề bài báo theo sitemap lịch sử (đầy đủ mọi bài, có tiêu đề có dấu).

Tuổi Trẻ, Thanh Niên, VTV dùng chung CMS: sitemap 5 ngày/tệp kèm <image:title>.
Dùng cho phân tích dài hạn (tần suất xuất hiện, chủ đề) — Google News RSS chỉ trả vài tin cho ngày cũ.

    from news_crawler.archive import load_archive
    rows = load_archive("2026-01-01", "2026-11-10")  # list[{outlet,url,title,ts}]
"""
import calendar
import gzip
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from .extract import VN_TZ

OUTLETS = {
    "tuoitre": ("Tuổi Trẻ", "https://tuoitre.vn/StaticSitemaps/sitemaps-{y}-{m}-{a}-{b}.xml"),
    "thanhnien": ("Thanh Niên", "https://thanhnien.vn/sitemaps/sitemaps-{y}-{m}-{a}-{b}.xml"),
    "vtv": ("VTV", "https://vtv.vn/sitemaps/sitemaps-{y}-{m}-{a}-{b}.xml"),
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_URL = re.compile(r"<url>\s*<loc>([^<]+)</loc>(.*?)</url>", re.S)
_TITLE = re.compile(r"<image:title>(.*?)</image:title>", re.S)
_LASTMOD = re.compile(r"<lastmod>([^<]+)</lastmod>")
_ID_OLD = re.compile(r"-(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\d*\.htm")      # tuoitre đến 6/2026: 2026MMDDhhmm...
_ID_NEW = re.compile(r"-\d{3}(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\d*\.htm")    # 185/100 + yyMMddhhmm...


def _windows(y, m):
    last = calendar.monthrange(y, m)[1]
    return [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, last)]


def _parse(xml, outlet):
    out = []
    for loc, body in _URL.findall(xml):
        t = _TITLE.search(body)
        title = html.unescape(t.group(1)) if t else ""
        title = re.sub(r"^<!\[CDATA\[|\]\]>$", "", title.strip()).strip()
        if not title:
            continue
        ts = None
        lm = _LASTMOD.search(body)
        if lm:
            try:
                ts = datetime.fromisoformat(lm.group(1).strip()).timestamp()
            except ValueError:
                ts = None
        if ts is None:
            m = _ID_OLD.search(loc) or _ID_NEW.search(loc)
            if not m:
                continue
            g = list(map(int, m.groups()))
            if g[0] < 100:
                g[0] += 2000
            ts = datetime(*g, tzinfo=VN_TZ).timestamp()
        out.append(dict(outlet=outlet, url=loc.strip(), title=title, ts=ts))
    return out


def _fetch(job, cache_dir):
    outlet, y, m, a, b = job
    path = os.path.join(cache_dir, f"v2-{outlet}-{y}-{m:02d}-{a:02d}.json.gz")
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    url = OUTLETS[outlet][1].format(y=y, m=m, a=a, b=b)
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        r.encoding = "utf-8"
        rows = _parse(r.text, outlet)
    except Exception as e:  # tệp chưa có (tương lai) hoặc lỗi mạng: không cache
        print("  !", url, e)
        return []
    end = datetime(y, m, b, 23, 59, tzinfo=VN_TZ).timestamp()
    if end < datetime.now(VN_TZ).timestamp() - 86400:  # chỉ cache khoảng thời gian đã đóng
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    return rows


def load_archive(start, end, outlets=None, cache_dir=".cache/archive", workers=6):
    os.makedirs(cache_dir, exist_ok=True)
    s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    jobs = []
    y, m = s.year, s.month
    while (y, m) <= (e.year, e.month):
        for a, b in _windows(y, m):
            for o in outlets or OUTLETS:
                jobs.append((o, y, m, a, b))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    rows, seen = [], set()
    t0, t1 = s.replace(tzinfo=VN_TZ).timestamp(), e.replace(tzinfo=VN_TZ).timestamp() + 86400
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(lambda j: _fetch(j, cache_dir), jobs):
            for r in part:
                if r["url"] not in seen and t0 <= r["ts"] < t1:
                    seen.add(r["url"])
                    rows.append(r)
    rows.sort(key=lambda r: r["ts"])
    return rows
