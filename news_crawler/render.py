"""Gom bài -> sự kiện -> chấm điểm -> xuất 1 file HTML tĩnh."""
import html
from collections import Counter
from datetime import datetime

from .digest import bullets, cluster
from .extract import VN_TZ
from .regions import REGION_BY_ID, detect_region, is_vietnam
from .topics import DISPLAY, OTHER, TOPIC_BY_ID, classify, importance

# Topic gắn chặt với Việt Nam: giữ nguyên nếu bài có nhắc Việt Nam
_KEEP_TOPICS = {"bau_cu_my", "chinh_tri_tq"}
_ABSORB = {"kinh_te_tq": "r_tq", "chinh_tri_my": "r_my"}


def assign_region(a):
    """Tin nước ngoài -> topic quốc gia (topic gốc thành nhãn phụ). Tin có Việt Nam giữ topic Việt Nam."""
    region, titans = detect_region(a["title"], a["desc"] or " ".join(a["paras"][:2]))
    a["titans"] = titans
    a["sub"] = None
    if a["topic"] in _KEEP_TOPICS:
        return
    if is_vietnam(a["title"], a["desc"]) and a["topic"] not in _ABSORB:
        return
    if a["topic"] in _ABSORB and not region:
        region = _ABSORB[a["topic"]]
    if region:
        if a["topic"] != OTHER["id"]:
            a["sub"] = TOPIC_BY_ID[a["topic"]]["label"]
        a["topic"] = region


def build_items(arts, now_ts):
    seen, uniq = set(), []
    for a in arts:
        # bỏ tiêu đề rác quá ngắn ("Vietnam Economy", "Văn nghệ - Thể thao"...)
        if a["url"] in seen or len(a["title"].split()) < 4:
            continue
        seen.add(a["url"])
        uniq.append(a)
    for a in uniq:
        text = (a["desc"] + " " + " ".join(a["paras"]))[:6000]
        a["topic"], a["topics2"], _ = classify(a["title"], text)
        a["bullets"] = bullets(a["title"], a["desc"], a["paras"], a["topic"])
        a["summary"] = " ".join(a["bullets"])
        assign_region(a)
    items = []
    for group in cluster(uniq).values():
        group.sort(key=lambda a: (a["via"] == "gnews", not a["paras"], a["tier"], -(len(a["bullets"][1]))))
        rep = dict(group[0])
        topics = Counter(a["topic"] for a in group if a["topic"] != OTHER["id"])
        if rep["topic"] == OTHER["id"] and topics:
            donor_t = topics.most_common(1)[0][0]
            donor = next(a for a in group if a["topic"] == donor_t)
            rep["topic"], rep["sub"] = donor_t, donor.get("sub")
            rep["bullets"] = bullets(rep["title"], rep["desc"], rep["paras"], rep["topic"])
        rep["titans"] = sorted({n for a in group for n in a.get("titans", [])})
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
        if rep["titans"] and rep["level"] < 5:
            rep["score"] += 0.5
            rep["level"], rep["level_label"] = _level(rep["score"])
        items.append(rep)
    items.sort(key=lambda r: (-r["score"], -(r["ts"] or 0)))
    return items


def _level(score):
    from .topics import LEVELS
    for th, lv, label in LEVELS:
        if score >= th:
            return lv, label


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
.ng{display:flex;flex-wrap:wrap;gap:6px;align-items:center;width:100%}.ng>span{font-size:11px;text-transform:uppercase;
letter-spacing:.05em;color:var(--muted);margin-right:4px}nav{flex-direction:column;gap:8px}
h2.grp{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin-top:36px;border-top:2px solid var(--line);padding-top:14px}
.ti{font-size:11px;color:var(--link);margin-top:2px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line)}
.lvb{display:flex;gap:4px}.lvb button{font:inherit;font-size:13px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;
background:var(--card);color:var(--text);cursor:pointer}.lvb button[aria-pressed="true"]{background:var(--text);color:var(--bg);border-color:var(--text)}
.cnt{font-size:12.5px;color:var(--muted);align-self:center}[hidden]{display:none!important}
.rep td{font-size:12.5px}.fail{color:var(--accent)}.tag{font-size:11px;color:var(--muted)}
@media (max-width:720px){table{min-width:0}thead{display:none}tbody tr{display:grid;grid-template-columns:1fr auto;gap:4px 10px;padding:12px;border-bottom:1px solid var(--line)}
tbody td{border:0;padding:0;width:auto!important}td.t{order:1}td.l{order:2;text-align:right}td.h{order:3;grid-column:1/-1}td.c{order:4;grid-column:1/-1}.tw{overflow-x:visible}}
"""

JS = r"""
(function(){
var q=document.getElementById('q'),info=document.getElementById('cnt'),btns=[].slice.call(document.querySelectorAll('.lvb button'));
var rows=[].slice.call(document.querySelectorAll('tr[data-l]'));
var txt=rows.map(function(r){return r.textContent.toLowerCase()}),lvl=rows.map(function(r){return +r.getAttribute('data-l')});
var secs=[].slice.call(document.querySelectorAll('h2[id]')).map(function(h){var b=h.nextElementSibling;
  return {h:h,box:b,sm:h.querySelector('small'),rows:b?[].slice.call(b.querySelectorAll('tr[data-l]')):[],
          chip:document.querySelector('nav a[href="#'+h.id+'"]')}}).filter(function(s){return s.box});
var kh=document.getElementById('khac'),khRows=kh?[].slice.call(kh.querySelectorAll('tr[data-l]')):[],
    khSum=kh?kh.querySelector('summary'):null,khChip=document.querySelector('nav a[href="#khac"]');
var grps=[].slice.call(document.querySelectorAll('h2.grp'));
var m=1,timer=null;
function vis(list){var n=0;for(var i=0;i<list.length;i++)if(!list[i].hidden)n++;return n}
function setChip(a,n){if(!a)return;var b=a.querySelector('b');if(b)b.textContent=n;a.hidden=!n}
function run(){
  var t=q.value.trim().toLowerCase(),shown=0;
  for(var i=0;i<rows.length;i++){var ok=lvl[i]>=m&&(!t||txt[i].indexOf(t)>=0);rows[i].hidden=!ok;if(ok)shown++}
  secs.forEach(function(s){var n=vis(s.rows);s.h.hidden=s.box.hidden=!n;
    if(s.sm)s.sm.textContent=n+' tin';setChip(s.chip,n)});
  if(kh){var n=vis(khRows);kh.hidden=!n;if(khSum)khSum.textContent='Thời sự khác ('+n+' tin chưa khớp topic)';setChip(khChip,n)}
  grps.forEach(function(g){var el=g.nextElementSibling,any=false;
    while(el&&!(el.tagName==='H2'&&el.classList.contains('grp'))&&el.id!=='khac'){if(el.tagName==='H2'&&!el.hidden)any=true;el=el.nextElementSibling}
    g.hidden=!any});
  document.querySelectorAll('nav .ng').forEach(function(g){g.hidden=!g.querySelector('a:not([hidden])')});
  info.textContent=(m>1||t)?('Đang hiện '+shown+' / '+rows.length+' tin'):(rows.length+' tin');
}
btns.forEach(function(b){b.addEventListener('click',function(){m=+b.getAttribute('data-m');
  btns.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false')});run()})});
q.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(run,200)});
run();
})();
"""


def _e(s):
    return html.escape(s or "", quote=True)


def _time(ts):
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%H:%M %d/%m") if ts else "—"


def _row(it, show_topic=True):
    t = TOPIC_BY_ID[it["topic"]]
    tags = it.get("sub") or ", ".join(TOPIC_BY_ID[x]["label"] for x in it["topics2"][:2]
                                      if x != it["topic"] and x in TOPIC_BY_ID)
    titan = ", ".join(it.get("titans", [])[:4])
    others = ""
    if it["others"]:
        links = ", ".join(f'<a href="{_e(u)}" target="_blank" rel="noopener">{_e(s)}</a>' for s, u in it["others"][:6])
        more = f" +{len(it['others']) - 6}" if len(it["others"]) > 6 else ""
        others = f" · cùng đưa tin: {links}{more}"
    bl = [b for b in it["bullets"] if b]
    content = "<ul>" + "".join(f"<li>{_e(b)}</li>" for b in bl) + "</ul>" if bl else \
        '<span class="tag">(Nguồn chỉ cung cấp tiêu đề — mở link để đọc)</span>'
    dots = "●" * it["level"] + "○" * (5 - it["level"])
    topic_cell = (f'<td class="t">{_e(t["label"])}' + (f'<div class="tag">· {_e(tags)}</div>' if tags else "")
                  + (f'<div class="ti">{_e(titan)}</div>' if titan else "") + "</td>")
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
    top = [it for it in items if it["topic"] != OTHER["id"]][:top_n]
    top_ids = {id(it) for it in top}
    by_topic = {k: [] for k in TOPIC_BY_ID}
    for it in items:
        if id(it) not in top_ids:  # tin ở Tiêu điểm không lặp lại bên dưới
            by_topic[it["topic"]].append(it)
    n_src_ok = sum(1 for r in reports if r["status"] == "ok")
    n_arts = sum(r["articles"] for r in reports)
    gen = datetime.fromtimestamp(now_ts, VN_TZ).strftime("%H:%M ngày %d/%m/%Y")
    nav = ""
    for group, order in DISPLAY:
        chips = "".join(f'<a href="#{k}">{_e(TOPIC_BY_ID[k]["label"])}<b>{len(by_topic[k])}</b></a>'
                        for k in order if by_topic[k])
        nav += f'<div class="ng"><span>{group}</span>{chips}</div>'
    if by_topic["khac"]:
        nav += f'<div class="ng"><span>Khác</span><a href="#khac">{OTHER["label"]}<b>{len(by_topic["khac"])}</b></a></div>'
    parts = [f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Bản tin tổng hợp {gen[-10:]}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Bản tin tổng hợp</h1>
<div class="meta">Cập nhật {gen} · khung {opts.hours} giờ gần nhất · {n_src_ok}/{len(reports)} nguồn đọc được ·
{n_arts} bài đã đọc → {len(items)} sự kiện, mỗi sự kiện hiện một lần (đã gộp tin trùng giữa các báo)</div>
<nav>{nav}</nav>
<div class="bar"><input id="q" type="search" placeholder="Lọc theo từ khoá, mã CK, tên báo, JPMorgan…" aria-label="Lọc tin">
<div class="lvb" role="group" aria-label="Lọc theo mức độ"><button type="button" data-m="1" aria-pressed="true">Tất cả</button>
<button type="button" data-m="3" aria-pressed="false">Từ 3</button><button type="button" data-m="4" aria-pressed="false">Từ 4</button>
<button type="button" data-m="5" aria-pressed="false">Chỉ 5</button></div><span id="cnt" class="cnt"></span></div>
<h2 id="top">Tiêu điểm <small>{len(top)} tin quan trọng nhất (không lặp lại ở các mục dưới)</small></h2>{_table([_row(i) for i in top])}"""]
    for group, order in DISPLAY:
        if any(by_topic[k] for k in order):
            parts.append(f'<h2 class="grp">{group}</h2>')
        for k in order:
            rows = by_topic[k]
            if rows:
                parts.append(f'<h2 id="{k}">{_e(TOPIC_BY_ID[k]["label"])} <small>{len(rows)} tin</small></h2>'
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
