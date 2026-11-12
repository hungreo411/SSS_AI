"""Chạy: python -m news_crawler [--hours 24] [--full] [--only vnexpress,cafef] [--out reports/x.html]"""
import argparse
import os
import time
from datetime import datetime

from .crawl import Opts, crawl_all
from .extract import VN_TZ
from .fetch import Fetcher
from .render import build_items, render, select_balanced, select_top
from .sources import SOURCES


def main(argv=None):
    ap = argparse.ArgumentParser(prog="news_crawler", description="Crawl toàn bộ chuyên mục các báo -> 1 file HTML tĩnh")
    ap.add_argument("--hours", type=int, default=24, help="khung thời gian tin (giờ), mặc định 24")
    ap.add_argument("--full", action="store_true", help="quét sâu: 120 chuyên mục, 8 trang/chuyên mục, 800 bài/báo")
    ap.add_argument("--max-sections", type=int, help="số chuyên mục tối đa mỗi báo (mặc định 40)")
    ap.add_argument("--max-pages", type=int, help="số trang mỗi chuyên mục (mặc định 3)")
    ap.add_argument("--max-articles", type=int, help="số bài tối đa đọc mỗi báo (mặc định 250)")
    ap.add_argument("--only", help="chỉ chạy các nguồn này (id, cách nhau dấu phẩy)")
    ap.add_argument("--no-gnews", action="store_true", help="tắt quét bổ sung Google News")
    ap.add_argument("--no-sitemap", action="store_true", help="tắt đọc sitemap")
    ap.add_argument("--min-level", type=int, default=1, help="chỉ xuất tin có mức độ >= N (1-5)")
    ap.add_argument("--top", type=int, help="chỉ giữ N tin quan trọng nhất (chọn lọc trên mọi topic)")
    ap.add_argument("--balanced", type=int, help="chọn khoảng N tin quan trọng: mỗi topic ~20 tin, mỗi doanh nghiệp top 50 ~2 tin")
    ap.add_argument("--cap-per-topic", type=int, default=15, help="với --top: tối đa bao nhiêu tin mỗi topic (mặc định 15)")
    ap.add_argument("--out", help="file HTML đầu ra (mặc định reports/ban-tin-YYYYMMDD-HHMM.html)")
    ap.add_argument("--cache", default=".cache", help="thư mục cache")
    ap.add_argument("--cache-only", action="store_true", help="dựng lại bản tin từ cache, không tải mới")
    ap.add_argument("--json", help="xuất thêm danh sách tin ra file JSON (để duyệt / chọn lọc thủ công)")
    ap.add_argument("--list", action="store_true", help="liệt kê nguồn rồi thoát")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    if a.list:
        for s in SOURCES:
            print(f"{s['id']:<20} {s.get('group', ''):<6} {s['name']}")
        return 0

    o = Opts()
    o.hours, o.verbose = a.hours, a.verbose
    if a.full:
        o.max_sections, o.max_pages, o.max_articles = 120, 8, 800
    o.max_sections = a.max_sections or o.max_sections
    o.max_pages = a.max_pages or o.max_pages
    o.max_articles = a.max_articles or o.max_articles
    o.gnews, o.sitemap = not a.no_gnews, not a.no_sitemap
    only = set(a.only.split(",")) if a.only else None

    t0 = time.time()
    fetcher = Fetcher(cache_dir=a.cache, verbose=a.verbose)
    fetcher.offline = a.cache_only
    print(f"Quét {len(only) if only else len(SOURCES)} nguồn, khung {o.hours}h …", flush=True)
    arts, reps = crawl_all(fetcher, o, only)
    now = time.time()
    items = [i for i in build_items(arts, now) if i["level"] >= a.min_level]
    if a.top:
        items = select_top(items, a.top, a.cap_per_topic)
    elif a.balanced:
        items = select_balanced(items, a.balanced)
    out = a.out or os.path.join("reports", datetime.now(VN_TZ).strftime("ban-tin-%Y%m%d-%H%M.html"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(items, reps, o, now))
    if a.json:
        import json
        keep = ("topic", "sub", "titans", "title", "url", "source", "ts", "bullets", "others", "level", "score",
                "n_sources", "lang", "tier", "company", "crank", "deal_usd")
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"items": [{k: i.get(k) for k in keep} for i in items], "reports": reps, "hours": o.hours,
                       "now": now}, f, ensure_ascii=False)
    print(f"Xong sau {time.time() - t0:.0f}s: {len(arts)} bài -> {len(items)} sự kiện. "
          f"HTTP ok={fetcher.stats['ok']} lỗi={fetcher.stats['fail']} cache={fetcher.stats['cache']}")
    print(f"File: {os.path.abspath(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
