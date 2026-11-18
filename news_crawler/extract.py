"""Bóc tách: link chuyên mục / bài viết / phân trang, RSS & sitemap, nội dung bài."""
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

try:  # tuỳ chọn: bóc nội dung tốt hơn nếu đã cài
    import trafilatura
except Exception:  # pragma: no cover
    trafilatura = None

VN_TZ = timezone(timedelta(hours=7))

# Chuyên mục không liên quan tới mục tiêu (giải trí, thể thao...) — không đi vào
SECTION_BLACKLIST = re.compile(
    r"(?:^|/)(the-thao|bong-da|giai-tri|sao|showbiz|du-lich|suc-khoe|song-khoe|giao-duc|tuyen-sinh|doi-song|gia-dinh|"
    r"xe|oto|o-to|xe-may|game|am-thuc|gioi-tre|nhip-song-tre|thoi-trang|lam-dep|tam-su|cuoi|hai-huoc|ban-doc|"
    r"video|podcast|photo|anh|emagazine|e-magazine|longform|multimedia|tv|truyen-hinh|lien-he|quang-cao|"
    r"rss|tim-kiem|search|login|dang-nhap|dang-ky|tac-gia|author|tag|tags|chu-de|topic|event|su-kien|"
    r"horoscope|tu-vi|phong-thuy|van-hoa|nghe-thuat|sport|sports|lifestyle|entertainment|travel|style|food|"
    r"arts|culture|fashion|puzzles|crossword|games|weather|thoi-tiet|newsletters?|subscribe|account|privacy|"
    r"terms|about|careers|contact|help|faq)(/|$|\.|-)",
    re.IGNORECASE)
NON_HTML = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|mp4|mp3|zip|css|js|ico|xml|rss)(\?|$)", re.IGNORECASE)
GENERIC_ARTICLE = [
    re.compile(r"-\d{5,}(\.\w{2,5})?/?$"),                 # slug-123456.htm
    re.compile(r"/(19|20)\d\d/\d{1,2}/(\d{1,2}/)?[\w-]{12,}"),  # /2026/10/31/slug
    re.compile(r"/[a-z0-9]+(?:-[a-z0-9]+){5,}(\.\w{2,5})?/?$"),  # slug dài >= 6 từ
    re.compile(r"-(post|p|a|ar|news|d)\d{4,}(\.\w{2,5})?$"),
]
NEXT_TEXT = re.compile(r"^(trang sau|tiếp|xem thêm|next|older|›|»|>)$", re.IGNORECASE)


def soup_of(html):
    return BeautifulSoup(html, "lxml")


def norm_url(u):
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    path = re.sub(r"/{2,}", "/", p.path)
    # bỏ tham số tracking, giữ tham số phân trang
    q = "&".join(x for x in p.query.split("&") if x and not x.lower().startswith(("utm_", "fbclid", "gidzl", "ref=")))
    return urlunparse((p.scheme, p.netloc.lower(), path, "", q, ""))


def base_domain(host):
    host = host.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def same_site(url, home):
    h, root = base_domain(urlparse(url).netloc), base_domain(urlparse(home).netloc)
    return h == root or h.endswith("." + root)


def is_article_url(url, src):
    if NON_HTML.search(url):
        return False
    rx = src.get("_article_rx")
    if rx is not None and not src.get("_article_rx_failed"):
        return bool(rx.search(url))
    path = urlparse(url).path
    if SECTION_BLACKLIST.search(path.split("/")[1] if path.count("/") > 1 else ""):
        return False
    return any(r.search(path) for r in GENERIC_ARTICLE)


def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_listing(html, page_url, src):
    """-> (articles[(url, anchor)], sections[url], next_url, feeds[url])"""
    s = soup_of(html)
    arts, secs, feeds, seen = [], [], [], set()
    for link in s.select('link[rel="alternate"]'):
        t = (link.get("type") or "").lower()
        if "rss" in t or "atom" in t:
            href = norm_url(urljoin(page_url, link.get("href", "")))
            if href:
                feeds.append(href)
    for a in s.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        u = norm_url(urljoin(page_url, href))
        if not u or u in seen or not same_site(u, src["home"]):
            continue
        seen.add(u)
        text = clean_text(a.get_text(" "))
        if not text:
            text = clean_text(a.get("title", ""))
        if u.endswith((".rss",)) or "/rss" in u and u.endswith(".xml"):
            feeds.append(u)
        elif is_article_url(u, src):
            arts.append((u, text))
        else:
            path = urlparse(u).path.strip("/")
            depth = len([x for x in path.split("/") if x])
            if 1 <= depth <= 2 and len(path) <= 60 and not SECTION_BLACKLIST.search(path) \
                    and not NON_HTML.search(u) and "?" not in u:
                secs.append(u)
    nxt = None
    ln = s.select_one('link[rel="next"], a[rel="next"]')
    if ln and ln.get("href"):
        nxt = norm_url(urljoin(page_url, ln["href"]))
    else:
        for a in s.find_all("a", href=True):
            if NEXT_TEXT.match(clean_text(a.get_text())):
                nxt = norm_url(urljoin(page_url, a["href"]))
                break
    return arts, secs, nxt, feeds


def page_url(section_url, n, tpl):
    """Áp mẫu phân trang: {stem}{ext} = URL tách đuôi, {url} = URL không '/', {urls} = URL có '/'."""
    if not tpl:
        return None
    u = section_url.rstrip("/")
    m = re.match(r"^(.*?)(\.(?:htm|html|chn|aspx|php))?$", u)
    return tpl.format(stem=m.group(1), ext=m.group(2) or "", url=u, urls=u + "/", n=n)


# ------------------------------------------------------------------ ngày giờ
_VN_DATE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](20\d\d)(?:[ ,\-|]*(?:lúc\s*)?(\d{1,2})[:hH](\d{2}))?")
_VN_DATE2 = re.compile(r"(\d{1,2}):(\d{2})\D{1,12}(\d{1,2})[/-](\d{1,2})[/-](20\d\d)")


def parse_date(s):
    """-> timestamp (float) hoặc None."""
    if not s:
        return None
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=VN_TZ)).timestamp()
    except ValueError:
        pass
    try:
        d = parsedate_to_datetime(s)
        if d:
            return (d if d.tzinfo else d.replace(tzinfo=VN_TZ)).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    m = _VN_DATE2.search(s)
    if m:
        hh, mm, dd, mo, yy = map(int, m.groups())
        try:
            return datetime(yy, mo, dd, hh, mm, tzinfo=VN_TZ).timestamp()
        except ValueError:
            return None
    m = _VN_DATE.search(s)
    if m:
        dd, mo, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
        try:
            return datetime(yy, mo, dd, hh, mm, tzinfo=VN_TZ).timestamp()
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ RSS / Atom / sitemap
def parse_feed(xml):
    """-> list[{url,title,summary,ts,source_name}] — chấp nhận RSS, Atom, sitemap (kể cả news sitemap)."""
    s = BeautifulSoup(xml, "xml")
    out = []
    for it in s.find_all(["item", "entry"]):
        link = it.find("link")
        url = None
        if link is not None:
            url = link.get("href") or clean_text(link.get_text())
        if not url and it.find("guid"):
            url = clean_text(it.find("guid").get_text())
        title = clean_text(BeautifulSoup(it.find("title").get_text(), "lxml").get_text(" ")) if it.find("title") else ""
        desc_tag = it.find("description") or it.find("summary") or it.find("content")
        desc = ""
        if desc_tag is not None:
            desc = clean_text(BeautifulSoup(desc_tag.get_text(), "lxml").get_text(" "))
        dt = it.find("pubDate") or it.find("published") or it.find("updated") or it.find("dc:date") or it.find("date")
        src_tag = it.find("source")
        out.append(dict(url=url, title=title, summary=desc, ts=parse_date(dt.get_text()) if dt else None,
                        source_name=clean_text(src_tag.get_text()) if src_tag is not None else None))
    if out:
        return out
    # sitemap
    for u in s.find_all("url"):
        loc = u.find("loc")
        if not loc:
            continue
        t = u.find("news:title") or u.find("title")
        d = u.find("news:publication_date") or u.find("publication_date") or u.find("lastmod")
        out.append(dict(url=clean_text(loc.get_text()), title=clean_text(t.get_text()) if t else "",
                        summary="", ts=parse_date(d.get_text()) if d else None, source_name=None))
    return out


def parse_sitemap_index(xml):
    """-> list[(url, ts)] của sitemap con."""
    s = BeautifulSoup(xml, "xml")
    res = []
    for sm in s.find_all("sitemap"):
        loc = sm.find("loc")
        if loc:
            lm = sm.find("lastmod")
            res.append((clean_text(loc.get_text()), parse_date(lm.get_text()) if lm else None))
    return res


# ------------------------------------------------------------------ bài viết
def _meta(s, *names):
    for n in names:
        tag = s.find("meta", attrs={"property": n}) or s.find("meta", attrs={"name": n}) \
              or s.find("meta", attrs={"itemprop": n})
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return ""


def _jsonld_dates(s):
    for tag in s.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("datePublished"):
                    return d["datePublished"]
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return None


def strip_site_suffix(title, src_name=""):
    parts = re.split(r"\s+[|\-–—]\s+", title)
    if len(parts) > 1 and len(parts[-1]) <= 35:
        tail = parts[-1].lower()
        name = (src_name or "").lower()
        if any(w and w in tail for w in name.split()[:2]) or re.search(r"\.(vn|com|net|org)", tail) \
                or tail in ("báo điện tử chính phủ", "tuổi trẻ online", "báo thanh niên"):
            return " - ".join(parts[:-1])
    return title


def parse_article(html, url, src):
    s = soup_of(html)
    for bad in s(["script", "style", "noscript", "iframe", "figure", "figcaption", "aside", "form"]):
        bad.decompose()
    title = _meta(s, "og:title", "twitter:title") or (clean_text(s.h1.get_text()) if s.h1 else "") \
        or (clean_text(s.title.get_text()) if s.title else "")
    title = strip_site_suffix(title, src.get("name", ""))
    desc = _meta(s, "og:description", "description", "twitter:description")
    ts = parse_date(_meta(s, "article:published_time", "pubdate", "datePublished", "publishdate",
                          "article:published", "dc.date.issued", "date")) \
        or parse_date(_jsonld_dates(s) or "")
    if ts is None:
        tm = s.find("time")
        if tm:
            ts = parse_date(tm.get("datetime") or tm.get_text())
    paras = []
    sel = src.get("content_sel")
    if sel:
        paras = [clean_text(p.get_text(" ")) for p in s.select(sel)]
    if sum(len(p) for p in paras) < 200:
        paras = _densest_paragraphs(s)
    if sum(len(p) for p in paras) < 200 and trafilatura is not None:
        txt = trafilatura.extract(html) or ""
        paras = [clean_text(x) for x in txt.split("\n")]
    if ts is None:  # ngày giờ dạng chữ trong trang (VD: "Thứ sáu, 31/10/2026, 08:30 (GMT+7)")
        for cls in ("date", "time", "publish", "detail-time", "date-time"):
            el = s.find(class_=re.compile(cls))
            if el:
                ts = parse_date(el.get_text(" "))
                if ts:
                    break
    paras = [p for p in paras if len(p) > 30 and not p.lower().startswith(("ảnh:", "nguồn:", "video:", "xem thêm"))]
    return dict(title=title, desc=desc, paras=paras, ts=ts)


def _densest_paragraphs(s):
    best, best_len = None, 0
    for el in s.find_all(["article", "div", "section", "main"]):
        ps = el.find_all("p", recursive=False)
        ln = sum(len(p.get_text()) for p in ps)
        if ln > best_len:
            best, best_len = el, ln
    if not best:
        return []
    return [clean_text(p.get_text(" ")) for p in best.find_all("p", recursive=False)]
