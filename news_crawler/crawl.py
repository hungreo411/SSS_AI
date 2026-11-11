"""Điều phối: mỗi báo -> RSS + trang chủ -> chuyên mục -> phân trang -> sitemap -> từng bài -> tiêu đề + nội dung."""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urljoin, urlparse

from . import extract as X
from .companies import gnews_jobs as company_jobs
from .capmkt import CAP_QUERIES
from .mna import MNA_QUERIES
from .sources import GNEWS_TOPIC_QUERIES, SOURCES

FEED_TTL = 900  # RSS / trang chuyên mục cache 15 phút


class Opts:
    hours = 24
    max_sections = 40
    max_pages = 3
    max_articles = 250
    sitemap = True
    gnews = True
    workers = 6
    verbose = False
    keep_undated = True
    companies = True   # quét Google News cho top 50 vốn hóa VN / Mỹ / Trung Quốc / châu Âu
    per_company = 15   # số tin tối đa lấy mỗi mã


def log(opts, *a):
    if opts.verbose:
        print(*a, flush=True)


def _prepare(src):
    src.setdefault("sections", [])
    src.setdefault("rss", [])
    src.setdefault("tier", 3)
    src.setdefault("lang", "vi")
    src.setdefault("fetch_article", True)
    if src.get("article_re") and "_article_rx" not in src:
        src["_article_rx"] = re.compile(src["article_re"])
    return src


def _feed_items(fetcher, url, src, cands, via):
    xml = fetcher.get(url, ttl=FEED_TTL)
    if not xml:
        return 0
    n = 0
    for it in X.parse_feed(xml):
        u = X.norm_url(it["url"] or "") if it["url"] else None
        if not u or not it["title"] and via != "sitemap":
            continue
        if via == "sitemap" and not X.same_site(u, src["home"]):
            continue
        c = cands.setdefault(u, dict(url=u, via=via))
        c.setdefault("title", it["title"])
        c.setdefault("summary", it["summary"])
        if it["ts"] and not c.get("ts"):
            c["ts"] = it["ts"]
        n += 1
    return n


def _sitemaps(fetcher, src, cands, cutoff, opts):
    home = src["home"]
    root = f"{urlparse(home).scheme}://{urlparse(home).netloc}"
    robots = fetcher.get(root + "/robots.txt", ttl=86400) or ""
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots) or [root + "/sitemap.xml"]
    # ưu tiên sitemap tin tức
    maps.sort(key=lambda u: (0 if re.search(r"news|tin-moi|latest|today", u, re.I) else 1))
    n, visited = 0, 0
    for sm in maps[:6]:
        xml = fetcher.get(sm, ttl=FEED_TTL)
        visited += 1
        if not xml:
            continue
        children = X.parse_sitemap_index(xml)
        if children:
            children.sort(key=lambda c: (c[1] or 0, bool(re.search(r"news|20\d\d", c[0]))), reverse=True)
            fresh = [c for c in children if not c[1] or c[1] >= cutoff - 86400][:4]
            for cu, _ in fresh:
                n += _feed_items(fetcher, cu, src, cands, "sitemap")
        else:
            n += _feed_items(fetcher, sm, src, cands, "sitemap")
    log(opts, f"  [{src['id']}] sitemap: {n} url")
    return n


def crawl_source(src, fetcher, opts, cutoff):
    _prepare(src)
    rep = dict(id=src["id"], name=src["name"], group=src.get("group", ""), feeds=0, sections=0, pages=0,
               candidates=0, articles=0, status="ok", note="")
    cands = {}  # url -> info (dict giữ thứ tự phát hiện)

    # 1) Trang chủ: link bài, chuyên mục, RSS tự khai báo
    home_html = fetcher.get(src["home"], ttl=FEED_TTL)
    secs, feeds = [], list(src["rss"])
    if home_html:
        arts, secs, _, f2 = X.parse_listing(home_html, src["home"], src)
        if src.get("_article_rx") is not None and len(arts) < 3:
            src["_article_rx_failed"] = True  # regex cấu hình không khớp -> dùng heuristic chung
            arts, secs, _, f2 = X.parse_listing(home_html, src["home"], src)
        feeds += [f for f in f2 if f not in feeds]
        for u, t in arts:
            cands.setdefault(u, dict(url=u, title=t, via="home"))
        rep["pages"] += 1

    # 2) RSS
    for f in feeds[:25]:
        if _feed_items(fetcher, f, src, cands, "rss"):
            rep["feeds"] += 1

    # 3) Chuyên mục + phân trang
    if src["fetch_article"]:
        conf = [urljoin(src["home"], s) for s in src["sections"]]
        seen, sec_list = set(), []
        for s in conf + secs:
            s = X.norm_url(s)
            if s and s not in seen and s.rstrip("/") != src["home"].rstrip("/"):
                seen.add(s)
                sec_list.append(s)
        sec_list = sec_list[:opts.max_sections]

        def walk(sec_url):
            found, pages, url = [], 0, sec_url
            for n in range(1, opts.max_pages + 1):
                html = fetcher.get(url, ttl=FEED_TTL)
                if not html:
                    break
                pages += 1
                arts, _, nxt, _ = X.parse_listing(html, url, src)
                new = [(u, t) for u, t in arts if u not in cands]
                found += arts
                if not new and n > 1:
                    break
                url = X.page_url(sec_url, n + 1, src.get("page_tpl")) or nxt
                if not url:
                    break
            return sec_url, found, pages

        with ThreadPoolExecutor(opts.workers) as ex:
            for sec_url, found, pages in ex.map(walk, sec_list):
                rep["pages"] += pages
                if found:
                    rep["sections"] += 1
                for u, t in found:
                    c = cands.setdefault(u, dict(url=u, title=t, via="section"))
                    c.setdefault("section", sec_url)

    # 4) Sitemap tin mới
    if opts.sitemap and src.get("sitemap"):
        _sitemaps(fetcher, src, cands, cutoff, opts)

    rep["candidates"] = len(cands)
    if not cands:
        rep["status"] = "fail"
        rep["note"] = fetcher.errors.get(urlparse(src["home"]).netloc, "không lấy được link nào")
        return [], rep

    # 5) Lọc theo thời gian, ưu tiên bài có ngày mới nhất
    pool = [c for c in cands.values() if not c.get("ts") or c["ts"] >= cutoff]
    pool.sort(key=lambda c: (c.get("ts") is None, -(c.get("ts") or 0)))
    pool = pool[:opts.max_articles]

    def to_article(c, parsed=None):
        p = parsed or {}
        title = p.get("title") or c.get("title") or ""
        return dict(source_id=src["id"], source=src["name"], group=src.get("group", ""), tier=src["tier"],
                    lang=src["lang"], url=c["url"], title=X.clean_text(title),
                    desc=p.get("desc") or c.get("summary") or "", paras=p.get("paras") or [],
                    ts=p.get("ts") or c.get("ts"), via=c.get("via"))

    out = []
    if not src["fetch_article"]:
        out = [to_article(c) for c in pool if c.get("title")]
    else:
        def grab(c):
            html = fetcher.get(c["url"])
            if not html:
                return to_article(c) if c.get("title") and c.get("summary") else None
            return to_article(c, X.parse_article(html, c["url"], src))

        with ThreadPoolExecutor(opts.workers) as ex:
            for a in ex.map(grab, pool):
                if a and len(a["title"]) >= 15:
                    out.append(a)
    # bài không có ngày từ trang chủ/chuyên mục thường là trang tĩnh (giới thiệu, hồ sơ...) -> bỏ
    out = [a for a in out if (a["ts"] and a["ts"] >= cutoff)
           or (not a["ts"] and opts.keep_undated and a["via"] in ("rss", "gnews"))]
    rep["articles"] = len(out)
    log(opts, f"  [{src['id']}] {rep['sections']} chuyên mục, {rep['pages']} trang, "
              f"{rep['candidates']} link, {rep['articles']} bài trong khung giờ")
    return out, rep


# ------------------------------------------------------------------ Google News (quét bổ sung)
_TIER1_NAMES = re.compile(r"reuters|bloomberg|financial times|wall street journal|wsj|nikkei|economist|"
                          r"associated press|ap news|new york times|chính phủ|nhân dân|ttxvn|vietnamplus|quốc hội",
                          re.IGNORECASE)


def crawl_gnews(fetcher, opts, sources):
    days = max(1, round(opts.hours / 24))
    jobs = []
    for q in GNEWS_TOPIC_QUERIES["vi"]:
        jobs.append((q, "hl=vi&gl=VN&ceid=VN:vi", None))
    for q in GNEWS_TOPIC_QUERIES["en"]:
        jobs.append((q, "hl=en-US&gl=US&ceid=US:en", None))
    for q in GNEWS_TOPIC_QUERIES.get("titans", []):
        jobs.append((q, "hl=en-US&gl=US&ceid=US:en", None))
    for q, lang in MNA_QUERIES + CAP_QUERIES:  # thương vụ M&A + thị trường vốn VN: Việt Nam, Đông Nam Á, châu Á, châu Âu, châu Mỹ
        jobs.append((q, "hl=vi&gl=VN&ceid=VN:vi" if lang == "vi" else "hl=en-US&gl=US&ceid=US:en", None))
    for s in sources:
        if s.get("gnews_site"):
            jobs.append((f"site:{s['gnews_site']}", "hl=en-US&gl=US&ceid=US:en", s))
    jobs = [(q, loc, src, None, None) for q, loc, src in jobs]
    if opts.companies:  # top 50 vốn hóa VN / Mỹ / Trung Quốc / châu Âu: mỗi mã một truy vấn
        for q, loc, hint in company_jobs():
            jobs.append((q, loc, None, hint, opts.per_company))

    def run(job):
        q, loc, src, hint, limit = job
        url = f"https://news.google.com/rss/search?q={quote_plus(q + f' when:{days}d')}&{loc}"
        xml = fetcher.get(url, ttl=FEED_TTL)
        res = []
        for it in X.parse_feed(xml or "")[:limit]:
            title, name = it["title"], it.get("source_name")
            m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", title)
            if m:
                title, name = m.group(1), name or m.group(2)
            name = (name or "Google News").strip()
            res.append(dict(source_id=src["id"] if src else "gnews", source=src["name"] if src else name,
                            group=src.get("group", "INTL") if src else "GNEWS",
                            tier=src["tier"] if src else (1 if _TIER1_NAMES.search(name) else 3),
                            lang="en" if "hl=en" in loc else "vi", url=it["url"], title=title,
                            desc="", paras=[], ts=it["ts"], via="gnews", company_hint=hint))
        return res

    out = []
    with ThreadPoolExecutor(opts.workers) as ex:
        for res in ex.map(run, jobs):
            out += res
    log(opts, f"  [gnews] {len(jobs)} truy vấn, {len(out)} tin")
    return out, len(jobs)


def crawl_all(fetcher, opts, only=None):
    cutoff = time.time() - opts.hours * 3600
    srcs = [s for s in SOURCES if not only or s["id"] in only]
    arts, reps = [], []
    with ThreadPoolExecutor(min(8, max(1, len(srcs)))) as ex:
        futs = {ex.submit(crawl_source, s, fetcher, opts, cutoff): s for s in srcs}
        for f in as_completed(futs):
            s = futs[f]
            try:
                a, r = f.result()
            except Exception as e:  # một báo lỗi không làm hỏng cả báo cáo
                a, r = [], dict(id=s["id"], name=s["name"], group=s.get("group", ""), status="fail",
                                note=f"{type(e).__name__}: {e}", feeds=0, sections=0, pages=0, candidates=0,
                                articles=0)
            arts += a
            reps.append(r)
            print(f"  {'✓' if r['status'] == 'ok' else '✗'} {r['name']}: {r['articles']} bài"
                  + (f" ({r['note']})" if r["note"] else ""), flush=True)
    if opts.gnews:
        g, nq = crawl_gnews(fetcher, opts, srcs)
        g = [a for a in g if not a["ts"] or a["ts"] >= cutoff]
        arts += g
        reps.append(dict(id="gnews", name="Google News (quét theo topic + báo trả phí)", group="GNEWS",
                         status="ok" if g else "fail", note="" if g else "không có kết quả", feeds=nq,
                         sections=0, pages=0, candidates=len(g), articles=len(g)))
    order = {s["id"]: i for i, s in enumerate(SOURCES)}
    reps.sort(key=lambda r: order.get(r["id"], 999))
    return arts, reps
