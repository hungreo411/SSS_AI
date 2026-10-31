"""Gom bài -> sự kiện -> chấm điểm -> xuất 1 file HTML tĩnh."""
import html
from collections import Counter
from datetime import datetime

from .digest import bullets, cluster
from .extract import VN_TZ
from .topics import OTHER, TOPIC_BY_ID, TOPICS, classify, importance


def build_items(arts, now_ts):
    seen, uniq = set(), []
    for a in arts:
        if a["url"] in seen or not a["title"]:
            continue
        seen.add(a["url"])
        uniq.append(a)
    for a in uniq:
        text = (a["desc"] + " " + " ".join(a["paras"]))[:6000]
        a["topic"], a["topics2"], _ = classify(a["title"], text)
        a["bullets"] = bullets(a["title"], a["desc"], a["paras"], a["topic"])
        a["summary"] = " ".join(a["bullets"])
    items = []
    for group in cluster(uniq).values():
        group.sort(key=lambda a: (a["via"] == "gnews", not a["paras"], a["tier"], -(len(a["bullets"][1]))))
        rep = dict(group[0])
        topics = Counter(a["topic"] for a in group if a["topic"] != OTHER["id"])
        if rep["topic"] == OTHER["id"] and topics:
            rep["topic"] = topics.most_common(1)[0][0]
            rep["bullets"] = bullets(rep["title"], rep["desc"], rep["paras"], rep["topic"])
        # tin chỉ có tiêu đề (Google News / báo trả phí): mượn sapo của bài cùng sự kiện nếu có
        if not rep["bullets"][0]:
            donor = next((a for a in group[1:] if a["bullets"][0]), None)
            if donor:
                rep["bullets"] = donor["bullets"]
        srcs = {}
        for a in group:
            srcs.setdefault(a["source"], a["url"])
        rep["others"] = [(s, u) for s, u in srcs.items() if s != rep["source"]]
        rep["n_sources"] = len(srcs)
        rep["ts"] = max((a["ts"] for a in group if a["ts"]), default=None)
        rep["level"], rep["level_label"], rep["score"] = importance(rep, rep["n_sources"], now_ts)
        items.append(rep)
    items.sort(key=lambda r: (-r["score"], -(r["ts"] or 0)))
    return items


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#16181d;--muted:#667085;--line:#e4e7ec;--accent:#b42318;--link:#1d4ed8;
--l5:#b42318;--l4:#dc6803;--l3:#ca8a04;--l2:#475467;--l1:#98a2b3;--chip:#eef2f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1115;--card:#171a21;--text:#e6e8ec;
--muted:#98a2b3;--line:#2a2f3a;--accent:#f97066;--link:#7ab0ff;--l5:#f97066;--l4:#fdb022;--l3:#facc15;--l2:#98a2b3;
--l1:#667085;--chip:#222733}}
:root[data-theme="dark"]{--bg:#0f1115;--card:#171a21;--text:#e6e8ec;--muted:#98a2b3;--line:#2a2f3a;--accent:#f97066;
--link:#7ab0ff;--l5:#f97066;--l4:#fdb022;--l3:#facc15;--l2:#98a2b3;--l1:#667085;--chip:#222733}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px;display:flex;gap:8px;align-items:baseline}
h2 small{color:var(--muted);font-weight:400;font-size:13px}.meta{color:var(--muted);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0}nav a{background:var(--chip);color:var(--text);text-decoration:none;
padding:4px 10px;border-radius:999px;font-size:12.5px}nav a b{color:var(--accent);margin-left:4px}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px}.bar input,.bar select{padding:7px 10px;border:1px solid var(--line);
border-radius:8px;background:var(--card);color:var(--text);font:inherit}.bar input{flex:1;min-width:200px}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;vertical-align:top;padding:9px 12px;
border-bottom:1px solid var(--line)}th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);
background:var(--card);position:sticky;top:0}tr:last-child td{border-bottom:0}
td.t{width:13%;font-size:12.5px;color:var(--muted)}td.h{width:32%}td.c{width:44%}td.l{width:11%;white-space:nowrap}
td.h a{color:var(--text);font-weight:600;text-decoration:none}td.h a:hover{color:var(--link);text-decoration:underline}
.src{font-size:12px;color:var(--muted);margin-top:3px}.src a{color:var(--link);text-decoration:none}
ul{margin:0;padding-left:18px}li{margin:0 0 3px}
.lv{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600;color:#fff}
.lv5{background:var(--l5)}.lv4{background:var(--l4)}.lv3{background:var(--l3);color:#1a1a1a}.lv2{background:var(--l2)}
.lv1{background:var(--l1)}.dots{display:block;font-size:11px;color:var(--muted);margin-top:3px;letter-spacing:1px}
details{margin-top:26px}summary{cursor:pointer;font-weight:600}
.rep td{font-size:12.5px}.fail{color:var(--accent)}.tag{font-size:11px;color:var(--muted)}
"""

JS = """
const q=document.getElementById('q'),lv=document.getElementById('lv');
function f(){const s=q.value.toLowerCase().trim(),m=+lv.value;
document.querySelectorAll('tr[data-l]').forEach(r=>{const ok=(+r.dataset.l>=m)&&(!s||r.textContent.toLowerCase().includes(s));
r.style.display=ok?'':'none'})}
q.addEventListener('input',f);lv.addEventListener('change',f);
"""


def _e(s):
    return html.escape(s or "", quote=True)


def _time(ts):
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%H:%M %d/%m") if ts else "—"


def _row(it, show_topic=True):
    t = TOPIC_BY_ID[it["topic"]]
    tags = ", ".join(TOPIC_BY_ID[x]["label"] for x in it["topics2"][:2])
    others = ""
    if it["others"]:
        links = ", ".join(f'<a href="{_e(u)}" target="_blank" rel="noopener">{_e(s)}</a>' for s, u in it["others"][:6])
        more = f" +{len(it['others']) - 6}" if len(it["others"]) > 6 else ""
        others = f" · cùng đưa tin: {links}{more}"
    bl = [b for b in it["bullets"] if b]
    content = "<ul>" + "".join(f"<li>{_e(b)}</li>" for b in bl) + "</ul>" if bl else \
        '<span class="tag">(Nguồn chỉ cung cấp tiêu đề — mở link để đọc)</span>'
    dots = "●" * it["level"] + "○" * (5 - it["level"])
    topic_cell = f'<td class="t">{_e(t["label"])}' + (f'<div class="tag">+ {_e(tags)}</div>' if tags else "") + "</td>" \
        if show_topic else f'<td class="t">{_e(t["label"])}</td>'
    return (f'<tr data-l="{it["level"]}">{topic_cell}'
            f'<td class="h"><a href="{_e(it["url"])}" target="_blank" rel="noopener">{_e(it["title"])}</a>'
            f'<div class="src">{_e(it["source"])} · {_time(it["ts"])}{others}</div></td>'
            f'<td class="c">{content}</td>'
            f'<td class="l"><span class="lv lv{it["level"]}">{it["level"]} · {_e(it["level_label"])}</span>'
            f'<span class="dots">{dots}</span></td></tr>')


def _table(rows):
    return ('<div class="tw"><table><thead><tr><th>Topic</th><th>Tiêu đề báo</th><th>Nội dung chính</th>'
            f'<th>Mức độ</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def render(items, reports, opts, now_ts, top_n=30):
    by_topic = {t["id"]: [] for t in TOPICS + [OTHER]}
    for it in items:
        by_topic[it["topic"]].append(it)
    n_src_ok = sum(1 for r in reports if r["status"] == "ok")
    n_arts = sum(r["articles"] for r in reports)
    gen = datetime.fromtimestamp(now_ts, VN_TZ).strftime("%H:%M ngày %d/%m/%Y")
    nav = "".join(f'<a href="#{t["id"]}">{_e(t["label"])}<b>{len(by_topic[t["id"]])}</b></a>'
                  for t in TOPICS if by_topic[t["id"]])
    nav += f'<a href="#khac">{OTHER["label"]}<b>{len(by_topic["khac"])}</b></a>' if by_topic["khac"] else ""

    top = [it for it in items if it["topic"] != OTHER["id"]][:top_n]
    parts = [f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Bản tin tổng hợp {gen[-10:]}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Bản tin tổng hợp</h1>
<div class="meta">Cập nhật {gen} · khung {opts.hours} giờ gần nhất · {n_src_ok}/{len(reports)} nguồn đọc được ·
{n_arts} bài đã đọc → {len(items)} sự kiện (đã gộp tin trùng giữa các báo)</div>
<nav>{nav}</nav>
<div class="bar"><input id="q" placeholder="Lọc theo từ khoá, mã CK, tên báo…">
<select id="lv"><option value="1">Mọi mức độ</option><option value="3">Từ 3 · Trung bình</option>
<option value="4">Từ 4 · Cao</option><option value="5">Chỉ 5 · Rất cao</option></select></div>
<h2 id="top">Tiêu điểm <small>{len(top)} tin quan trọng nhất</small></h2>{_table([_row(i) for i in top])}"""]
    for t in TOPICS:
        rows = by_topic[t["id"]]
        if rows:
            parts.append(f'<h2 id="{t["id"]}">{_e(t["label"])} <small>{len(rows)} tin</small></h2>'
                         + _table([_row(i) for i in rows]))
    if by_topic["khac"]:
        parts.append(f'<details id="khac"><summary>{OTHER["label"]} ({len(by_topic["khac"])} tin chưa khớp topic)</summary>'
                     + _table([_row(i) for i in by_topic["khac"]]) + "</details>")
    rep_rows = "".join(
        f'<tr><td>{_e(r["name"])}</td><td>{_e(r["group"])}</td>'
        f'<td class="{"" if r["status"] == "ok" else "fail"}">{"OK" if r["status"] == "ok" else "Lỗi"}</td>'
        f'<td>{r["feeds"]}</td><td>{r["sections"]}</td><td>{r["pages"]}</td><td>{r["candidates"]}</td>'
        f'<td>{r["articles"]}</td><td>{_e(r["note"])}</td></tr>' for r in reports)
    parts.append(f"""<details class="rep"><summary>Tình trạng quét từng nguồn</summary><div class="tw"><table>
<thead><tr><th>Nguồn</th><th>Nhóm</th><th>Trạng thái</th><th>RSS</th><th>Chuyên mục</th><th>Trang</th>
<th>Link tìm thấy</th><th>Bài trong khung giờ</th><th>Ghi chú</th></tr></thead><tbody>{rep_rows}</tbody></table></div>
</details><p class="meta">Tóm tắt là câu trích nguyên văn từ bài (sapo + câu nhiều dữ kiện nhất). Mức độ quan trọng
chấm tự động theo topic, từ khoá tác động, quy mô số liệu, uy tín nguồn và số báo cùng đưa tin.</p>
</div><script>{JS}</script></body></html>""")
    return "".join(parts)
