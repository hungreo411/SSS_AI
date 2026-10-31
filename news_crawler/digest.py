"""Tóm tắt 2 bullet (trích xuất, không bịa) + gom tin trùng giữa các báo."""
import re
from collections import defaultdict

from .topics import TOPIC_BY_ID, _MAGNITUDE

_PREFIX = re.compile(r"^\s*\(?(?:[A-ZĐ][\w.]{1,15}(?:\.vn|\.com|\.net)?|TTO|VTV\.vn|Chinhphu\.vn|ĐTCK|VnEconomy|"
                     r"Dân trí|NLĐO|PLO|SGGPO|TTXVN|VOV\.VN|CafeF|Vietstock|VietNamNet)\)?\s*[-–—:]\s+")
_SPLIT = re.compile(r"(?<=[.!?…])[\"”']?\s+")
# Câu quảng cáo, bản quyền, kêu gọi đặt mua... lẫn trong thân bài -> bỏ
_BOILER = re.compile(r"đặt mua|ấn phẩm|bản quyền|chúng tôi xin thông báo|đăng ký nhận|theo dõi (?:kênh|fanpage)|"
                     r"hotline|liên hệ quảng cáo|subscribe|sign up|newsletter|all rights reserved|cookie", re.IGNORECASE)
MAX_BULLET = 260


def sentences(text):
    out, buf = [], ""
    for piece in _SPLIT.split(text or ""):
        buf = (buf + " " + piece).strip() if buf else piece.strip()
        if len(buf) >= 40:
            out.append(buf)
            buf = ""
    if buf:
        if out and len(buf) < 40:
            out[-1] += " " + buf
        else:
            out.append(buf)
    return out


def shorten(s, n=MAX_BULLET):
    s = _PREFIX.sub("", s.strip())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-–") + "…"


def _tokens(s):
    return set(re.findall(r"\w{2,}", s.lower()))


def _overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def bullets(title, desc, paras, topic_id):
    """-> [bullet1, bullet2] (bullet2 có thể rỗng nếu báo chỉ có tóm tắt)."""
    desc = _PREFIX.sub("", desc or "").strip()
    if _BOILER.search(desc):
        desc = ""
    body_sents = [x for p in paras for x in sentences(p) if not _BOILER.search(x)]
    if len(desc) < 40 or _overlap(desc, title) > 0.9:
        desc = body_sents[0] if body_sents else desc
    d_sents = sentences(desc)
    b1 = d_sents[0] if d_sents else ""
    if len(b1) < 90 and len(d_sents) > 1:
        b1 = b1 + " " + d_sents[1]
    b1 = shorten(b1)

    topic = TOPIC_BY_ID.get(topic_id, {})
    regs = [rx for rx, _ in topic.get("_re", [])]
    best, best_s = "", 0.0
    for i, sent in enumerate(body_sents[:40]):
        if len(sent) < 50 or _overlap(sent, b1) > 0.6 or _overlap(sent, title) > 0.8:
            continue
        sc = 0.0
        if re.search(r"\d", sent):
            sc += 1.5
        if _MAGNITUDE.search(sent):
            sc += 1.5
        sc += sum(len(rx.findall(sent)) for rx in regs) * 0.8
        sc += 1.0 if i < 6 else 0.4 if i < 15 else 0
        sc -= 0.5 if len(sent) > 350 else 0
        if sc > best_s:
            best, best_s = sent, sc
    if not best:
        rest = [x for x in d_sents[1:] if _overlap(x, b1) < 0.6] if len(b1) < len(desc) else []
        best = rest[0] if rest else ""
    return [b1, shorten(best) if best else ""]


# ------------------------------------------------------------------ gom tin trùng
def _shingles(title):
    w = re.findall(r"\w+", title.lower())
    return {" ".join(w[i:i + 2]) for i in range(len(w) - 1)} or set(w)


def _uni(text):
    return {w for w in re.findall(r"\w{2,}", text.lower()) if not w.isdigit() or len(w) > 2}


def cluster(articles, threshold=0.42):
    """Gán cụm cho tin cùng sự kiện ở nhiều báo; trả về dict id -> list[art].

    Hai bài là một nếu: (1) tiêu đề trùng >= 42% cặp từ liền nhau, hoặc (2) tiêu đề trùng >= 55% từ đơn
    (ít nhất 4 từ chung; hoặc >= 45% với 5 từ chung), hoặc (3) câu mở đầu trùng >= 60% từ (câu dài >= 60 ký tự).
    """
    parent = list(range(len(articles)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    def link(keys, test):
        index = defaultdict(list)
        for i, s in enumerate(keys):
            if not s:
                continue
            cand = defaultdict(int)
            for g in s:
                for j in index[g]:
                    cand[j] += 1
            for j, c in cand.items():
                if find(i) != find(j) and test(s, keys[j], c):
                    union(i, j)
            for g in s:
                if len(index[g]) < 300:
                    index[g].append(i)

    sh = [_shingles(a["title"]) for a in articles]
    link(sh, lambda s, t, c: c >= 2 and c / len(s | t) >= threshold)
    uni = [_uni(a["title"]) for a in articles]
    link(uni, lambda s, t, c: (c >= 4 and c / len(s | t) >= 0.55) or (c >= 5 and c / len(s | t) >= 0.45))
    leads = [_uni(a["bullets"][0]) if len(a.get("bullets", [""])[0]) >= 60 else set() for a in articles]
    link(leads, lambda s, t, c: c >= 8 and c / len(s | t) >= 0.6)
    groups = defaultdict(list)
    for i, a in enumerate(articles):
        groups[find(i)].append(a)
    return groups
