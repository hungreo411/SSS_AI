"""Tóm tắt 2 bullet (trích xuất, không bịa) + gom tin trùng giữa các báo."""
import re
from collections import defaultdict

from .topics import TOPIC_BY_ID, _MAGNITUDE

_PREFIX = re.compile(r"^\s*\(?(?:[A-ZĐ][\w.]{1,15}(?:\.vn|\.com|\.net)?|TTO|VTV\.vn|Chinhphu\.vn|ĐTCK|VnEconomy|"
                     r"Dân trí|NLĐO|PLO|SGGPO|TTXVN|VOV\.VN|CafeF|Vietstock|VietNamNet)\)?\s*[-–—:]\s+")
_SPLIT = re.compile(r"(?<=[.!?…])[\"”']?\s+")
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
    body_sents = [x for p in paras for x in sentences(p)]
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


def cluster(articles, threshold=0.42):
    """Gán art['cluster'] = id; trả về dict id -> list[art]. Tin cùng sự kiện ở nhiều báo gom lại."""
    parent = list(range(len(articles)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sh = [_shingles(a["title"]) for a in articles]
    index = defaultdict(list)
    for i, s in enumerate(sh):
        cand = defaultdict(int)
        for g in s:
            for j in index[g]:
                cand[j] += 1
        for j, c in cand.items():
            if c >= 2 and c / len(s | sh[j]) >= threshold:
                parent[find(i)] = find(j)
        for g in s:
            if len(index[g]) < 200:
                index[g].append(i)
    groups = defaultdict(list)
    for i, a in enumerate(articles):
        groups[find(i)].append(a)
    return groups
