"""Báo cáo hạ tầng theo tỉnh/thành Việt Nam (34 đơn vị hành chính sau sáp nhập 7/2025).

Chạy: python -m news_crawler.infra [--days 30] [--out reports/ha-tang.html] [--notes notes.html] [--cache-only]

1. Quét Google News (tiếng Việt) theo từng tỉnh: tên mới + tên tỉnh cũ đã sáp nhập + địa danh trọng điểm
   (Long Thành, Cần Giờ, Phú Quốc, Vân Đồn...), cộng thêm các báo cáo JSON có sẵn trong reports/.
2. Giữ tin về xây dựng hạ tầng, gán vào tỉnh theo địa danh trong tiêu đề, gộp tin trùng.
3. Trích vốn đầu tư nêu trong tiêu đề/tóm tắt, rồi xếp hạng tỉnh và vùng theo số sự kiện + tổng vốn.
"""
import argparse
import glob
import html
import json
import math
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote_plus

from . import extract as X
from .digest import _shingles, _uni
from .extract import VN_TZ
from .fetch import Fetcher

USD_VND = 26_300  # quy đổi gần đúng 1 USD -> đồng

REGIONS = [
    ("dbsh", "Đồng bằng sông Hồng"),
    ("tdmn", "Trung du và miền núi phía Bắc"),
    ("btb", "Bắc Trung Bộ và Duyên hải miền Trung"),
    ("tn", "Tây Nguyên"),
    ("dnb", "Đông Nam Bộ"),
    ("dbscl", "Đồng bằng sông Cửu Long"),
]
REGION_NAME = dict(REGIONS)

# (id, tên hiện hành, vùng, tên tỉnh cũ đã nhập vào, địa danh/dự án trọng điểm trong tỉnh)
PROVINCES = [
    ("hn", "Hà Nội", "dbsh", [], ["Thủ đô", "Nội Bài", "Hòa Lạc", "Sóc Sơn", "Đông Anh", "Gia Lâm", "Long Biên",
                                  "Mê Linh", "Thường Tín", "Cầu Giấy", "Hoàn Kiếm", "Tứ Liên", "Trần Hưng Đạo"]),
    ("hp", "Hải Phòng", "dbsh", ["Hải Dương"], ["Lạch Huyện", "Đình Vũ", "Cát Hải", "Cát Bà", "Tiên Lãng", "Đồ Sơn",
                                               "Thủy Nguyên", "Chí Linh", "Kinh Môn"]),
    ("qn", "Quảng Ninh", "dbsh", [], ["Vân Đồn", "Hạ Long", "Móng Cái", "Cẩm Phả", "Uông Bí", "Đông Triều", "Quảng Yên"]),
    ("bn", "Bắc Ninh", "dbsh", ["Bắc Giang"], ["Gia Bình", "Từ Sơn", "Yên Phong", "Quế Võ", "Việt Yên"]),
    ("hy", "Hưng Yên", "dbsh", ["Thái Bình"], ["Phố Hiến", "Văn Giang", "Thái Thụy"]),
    ("nb", "Ninh Bình", "dbsh", ["Hà Nam", "Nam Định"], ["Phủ Lý", "Tràng An", "Hoa Lư", "Kim Sơn", "Hải Hậu"]),
    ("pt", "Phú Thọ", "tdmn", ["Vĩnh Phúc", "Hòa Bình"], ["Việt Trì", "Vĩnh Yên", "Phúc Yên", "Tam Đảo"]),
    ("lc", "Lào Cai", "tdmn", ["Yên Bái"], ["Sa Pa", "Sapa", "Bát Xát"]),
    ("tng", "Thái Nguyên", "tdmn", ["Bắc Kạn", "Bắc Cạn"], ["Sông Công", "Phổ Yên"]),
    ("tq", "Tuyên Quang", "tdmn", ["Hà Giang"], ["Na Hang"]),
    ("ls", "Lạng Sơn", "tdmn", [], ["Đồng Đăng", "Hữu Nghị", "Tân Thanh"]),
    ("cb", "Cao Bằng", "tdmn", [], ["Trà Lĩnh"]),
    ("sl", "Sơn La", "tdmn", [], ["Mộc Châu"]),
    ("db", "Điện Biên", "tdmn", [], []),
    ("lch", "Lai Châu", "tdmn", [], []),
    ("th", "Thanh Hóa", "btb", [], ["Nghi Sơn", "Sầm Sơn", "Thọ Xuân"]),
    ("na", "Nghệ An", "btb", [], ["TP Vinh", "TP. Vinh", "thành phố Vinh", "sân bay Vinh", "Cửa Lò", "Đô Lương"]),
    ("ht", "Hà Tĩnh", "btb", [], ["Vũng Áng", "Sơn Dương", "Kỳ Anh"]),
    ("qt", "Quảng Trị", "btb", ["Quảng Bình"], ["Đồng Hới", "Hòn La", "Phong Nha", "Mỹ Thủy", "Đông Hà"]),
    ("hue", "Huế", "btb", ["Thừa Thiên Huế", "Thừa Thiên - Huế"], ["Chân Mây", "Phú Bài", "Lăng Cô"]),
    ("dn", "Đà Nẵng", "btb", ["Quảng Nam"], ["Liên Chiểu", "Chu Lai", "Hội An", "Tam Kỳ", "Hòa Vang", "Sơn Trà"]),
    ("qng", "Quảng Ngãi", "btb", ["Kon Tum"], ["Dung Quất", "Lý Sơn", "Bờ Y"]),
    ("kh", "Khánh Hòa", "btb", ["Ninh Thuận"], ["Nha Trang", "Cam Ranh", "Vân Phong", "Phan Rang", "Bắc Vân Phong"]),
    ("gl", "Gia Lai", "tn", ["Bình Định"], ["Quy Nhơn", "Pleiku", "Nhơn Hội", "Phù Cát", "An Nhơn"]),
    ("dl", "Đắk Lắk", "tn", ["Phú Yên"], ["Buôn Ma Thuột", "Tuy Hòa", "Vũng Rô", "Bãi Gốc"]),
    ("ld", "Lâm Đồng", "tn", ["Đắk Nông", "Bình Thuận"], ["Đà Lạt", "Phan Thiết", "Liên Khương", "Bảo Lộc",
                                                          "Tà Nung", "Mũi Né", "Gia Nghĩa"]),
    ("hcm", "TP.HCM", "dnb", ["Bình Dương", "Bà Rịa - Vũng Tàu", "Bà Rịa-Vũng Tàu", "Bà Rịa – Vũng Tàu"],
     ["TP.HCM", "TPHCM", "TP HCM", "TP. HCM", "TP. Hồ Chí Minh", "TP.Hồ Chí Minh", "Thành phố Hồ Chí Minh",
      "thành phố Hồ Chí Minh", "Sài Gòn", "HCMC", "Ho Chi Minh City", "Cần Giờ", "Thủ Thiêm", "Thủ Đức",
      "Vũng Tàu", "Côn Đảo", "Bà Rịa", "Cái Mép", "Thị Vải", "Phú Mỹ", "Hồ Tràm", "Châu Đức", "Bình Giã",
      "Long Sơn", "Củ Chi", "Nhà Bè", "Tân Sơn Nhất", "Thủ Dầu Một", "Dĩ An", "Bến Cát", "Thuận An", "Bàu Bàng",
      "Tân Uyên", "Bến Thành", "Hóc Môn", "Bình Chánh"]),
    ("dni", "Đồng Nai", "dnb", ["Bình Phước"], ["Long Thành", "Nhơn Trạch", "Biên Hòa", "Đồng Xoài", "Trảng Bom",
                                                "Chơn Thành", "Hoa Lư - Bình Phước"]),
    ("tni", "Tây Ninh", "dnb", ["Long An"], ["Bến Lức", "Cần Giuộc", "Đức Hòa", "Mộc Bài", "Xa Mát"]),
    ("ct", "Cần Thơ", "dbscl", ["Sóc Trăng", "Hậu Giang"], ["Trần Đề", "Vị Thanh", "Ô Môn"]),
    ("vl", "Vĩnh Long", "dbscl", ["Bến Tre", "Trà Vinh"], ["Định An"]),
    ("dt", "Đồng Tháp", "dbscl", ["Tiền Giang"], ["Mỹ Tho", "Cao Lãnh", "Sa Đéc", "Gò Công"]),
    ("cm", "Cà Mau", "dbscl", ["Bạc Liêu"], ["Năm Căn", "Hòn Khoai"]),
    ("ag", "An Giang", "dbscl", ["Kiên Giang"], ["Phú Quốc", "Rạch Giá", "Long Xuyên", "Châu Đốc", "Hà Tiên"]),
]
PROV = {p[0]: p for p in PROVINCES}

# Từ khóa nhận diện tin hạ tầng / đầu tư xây dựng (so trên tiêu đề viết thường)
INFRA = re.compile(
    r"cao tốc|đường sắt|metro|đường vành đai|vành đai|quốc lộ|tỉnh lộ|\bcầu\b|cây cầu|hầm |hầm chui|nút giao|"
    r"sân bay|cảng hàng không|\bcảng\b|bến cảng|logistics|khu công nghiệp|\bkcn\b|cụm công nghiệp|hạ tầng|"
    r"khởi công|động thổ|thông xe|khánh thành|thông tuyến|giải phóng mặt bằng|gpmb|tái định cư|đầu tư công|"
    r"giải ngân|khu đô thị|khu kinh tế|nhà máy điện|điện gió|điện mặt trời|nhiệt điện|\blng\b|thủy điện|"
    r"điện hạt nhân|đường dây|trạm biến áp|thủy lợi|\bkè\b|hồ chứa|cấp nước|nhà máy nước|xử lý nước|"
    r"trung tâm dữ liệu|data center|tàu điện|tuyến đường|mở rộng đường|nâng cấp đường|làm đường|dự án|"
    r"nhà ở xã hội|lấn biển|xử lý rác|đốt rác|bến xe|nhà ga|đường ven biển|trục động lực|"
    r"expressway|railway|airport|seaport|industrial park|infrastructure|bridge|metro line|ring road",
    re.I)
# Tin không phải đầu tư hạ tầng
NOT_INFRA = re.compile(
    r"tai nạn|va chạm|tông |\bcháy\b|hỏa hoạn|khởi tố|bắt giữ|\bbắt\b|truy nã|xét xử|hầu tòa|lừa đảo|trộm|cướp|"
    r"tử vong|thi thể|đuối nước|\bchết\b|ma túy|xổ số|bóng đá|giá vàng|giá xăng|thời tiết|mở bán|bảng giá|"
    r"giá chung cư|giá căn hộ|giá đất tăng|cho thuê|tuyển dụng|tuyển sinh|vé máy bay|chuyến bay|hoãn chuyến|"
    r"học sinh|ung thư|bệnh nhân|kết quả xổ|lịch cúp|du lịch hè|ẩm thực|clip|video:|\[video\]|ảnh:|"
    r"mưa lớn|ngập|lũ |bão |sạt lở|động đất|cảnh báo thời tiết|vụ án|điều tra|sai phạm|\bphạt\b|xử phạt|"
    r"thủ tục hành chính|tuyên truyền|triển lãm|hội thảo|hội nghị khách hàng|cúp điện|mất điện|xe buýt",
    re.I)
# Tiêu đề có các chữ này thì số tiền thường không phải vốn dự án
NOT_CAPITAL = re.compile(r"thu ngân sách|grdp|kim ngạch|doanh thu|lợi nhuận|tổng thu|xuất khẩu|nhập khẩu|"
                         r"nộp ngân sách|tiền phạt|thất thoát|thiệt hại|chiếm đoạt|tham ô|hối lộ|lương", re.I)
MILESTONE = re.compile(r"khởi công|động thổ|thông xe|khánh thành|thông tuyến|hoàn thành|về đích|"
                       r"phê duyệt|chấp thuận chủ trương|chủ trương đầu tư|cấp phép|cấp giấy chứng nhận|"
                       r"chọn nhà đầu tư|trao quyết định|ký kết|bàn giao mặt bằng|vận hành", re.I)

_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
_MONEY = re.compile(_NUM + r"\s*(triệu tỷ|nghìn tỷ|ngàn tỷ|tỷ USD|tỷ usd|tỷ đô(?:la)?|triệu USD|triệu usd|"
                    r"triệu đô(?:la)?|tỷ đồng|tỷ(?!\s*(?:lệ|trọng|phú|giá|suất)))", re.I)
_MONEY_EN = re.compile(r"(?:US)?\$\s?(\d+(?:\.\d+)?)\s*(billion|bn|million|mn)\b|"
                       r"VND\s?(\d+(?:\.\d+)?)\s*(trillion|billion)\b", re.I)


def _num(s):
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def capital(text):
    """Số vốn lớn nhất nêu trong câu (đơn vị: tỷ đồng), hoặc None."""
    if not text or NOT_CAPITAL.search(text):
        return None
    best = None
    for m in _MONEY.finditer(text):
        v = _num(m.group(1))
        if v is None:
            continue
        u = m.group(2).lower()
        if u == "triệu tỷ":
            v *= 1_000_000
        elif u in ("nghìn tỷ", "ngàn tỷ"):
            v *= 1000
        elif u.startswith("tỷ usd") or u.startswith("tỷ đô"):
            v *= USD_VND / 1  # 1 tỷ USD = 26.300 tỷ đồng
        elif u.startswith("triệu usd") or u.startswith("triệu đô"):
            v *= USD_VND / 1000
        best = max(best or 0, v)
    for m in _MONEY_EN.finditer(text):
        if m.group(1):
            v = float(m.group(1)) * (USD_VND if m.group(2).lower() in ("billion", "bn") else USD_VND / 1000)
        else:
            v = float(m.group(3)) * (1000 if m.group(4).lower() == "trillion" else 1)
        best = max(best or 0, v)
    if best is not None and (best < 1 or best > 3_000_000):  # < 1 tỷ: không phải dự án; > 3 triệu tỷ: số vĩ mô
        return None
    return best


def _ascii(s):
    s = s.replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_EXTRA_EN = {"hn": ["Hanoi"], "dn": ["Danang"], "hcm": ["Saigon"], "hue": ["Hue City"]}
_AMBIG_ASCII = {"Hue", "Vinh", "Hoa Binh", "Thai Binh", "Long An", "An Giang", "Ha Nam", "Phu My", "Ba Ria"}


def _matchers():
    out = []
    for pid, name, _reg, old, places in PROVINCES:
        names = [name] + old + places
        if pid == "hcm":
            names = names[1:]  # "TP.HCM" đã có trong places với nhiều biến thể
        for n in list(names):
            a = _ascii(n)
            if a != n and a not in _AMBIG_ASCII and len(a) > 4:
                names.append(a)
        names += _EXTRA_EN.get(pid, [])
        pat = "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True))
        out.append((pid, re.compile(r"(?<![\w])(?:" + pat + r")(?![\w])")))
    return out


_MATCH = _matchers()
_PACIFIC = re.compile(r"Thái Bình Dương|Thai Binh Duong")
_COMPARE = re.compile(r"(?:lần|hơn|như|bằng|ngang)\s+(?:sân bay\s+|thủy điện\s+|cảng\s+)?(?:Nội Bài|Tân Sơn Nhất|Hòa Bình|"
                      r"Cái Mép|Thủ Thiêm)|cách\s+(?:trung tâm\s+)?(?:Thủ đô\s+|thủ đô\s+)?(?:Hà Nội|TP\.?\s?HCM|"
                      r"TP\. Hồ Chí Minh|Đà Nẵng|Hải Phòng|Cần Thơ)")


def provinces_of(title):
    t = _PACIFIC.sub(" ", title)
    t = _COMPARE.sub(" ", t)
    t = re.sub(r"Hòa Bình(?= (?:và|cho|thế giới|Trung Đông|Ukraine))", " ", t)
    return [pid for pid, rx in _MATCH if rx.search(t)]


def _queries():
    """(truy vấn, tỉnh gợi ý)."""
    tpl = ['"{n}" hạ tầng', '"{n}" khởi công', '"{n}" dự án vốn đầu tư', '"{n}" cao tốc OR đường OR cầu',
           '"{n}" khu công nghiệp OR cảng OR sân bay']
    big = {"hn", "hcm", "dn", "hp", "dni", "bn", "qn", "ct", "kh", "th"}
    out = []
    for pid, name, _reg, old, places in PROVINCES:
        for n in [name if pid != "hcm" else "TP.HCM"] + old:
            for t in tpl:
                out.append((t.format(n=n), pid))
        if pid in big:
            for t in ['"{n}" thông xe OR khánh thành', '"{n}" giải ngân đầu tư công', '"{n}" metro OR vành đai',
                      '"{n}" khu đô thị OR nhà ở xã hội']:
                out.append((t.format(n=name if pid != "hcm" else "TP.HCM"), pid))
        for n in places[:6]:
            if n.startswith(("TP", "Thành phố", "thành phố", "Thủ đô", "HCMC", "Ho Chi")):
                continue
            out.append((f'"{n}" dự án', pid))
    for q in ["khởi công dự án giao thông", "thông xe cao tốc", "đường sắt tốc độ cao Bắc Nam",
              "đường sắt Lào Cai Hà Nội Hải Phòng", "cao tốc Bắc Nam phía Đông", "sân bay Long Thành",
              "giải ngân vốn đầu tư công", "khu công nghiệp mới được phê duyệt", "cảng biển nước sâu",
              "điện hạt nhân Ninh Thuận", "nhà máy điện LNG", "dự án trọng điểm quốc gia", "đường vành đai 4",
              "metro Bến Thành Suối Tiên", "khu thương mại tự do", "trung tâm dữ liệu Việt Nam đầu tư"]:
        out.append((q, None))
    return out


def gnews(fetcher, days, workers=8):
    jobs = _queries()

    def run(job):
        q, hint = job
        url = (f"https://news.google.com/rss/search?q={quote_plus(q + f' when:{days}d')}"
               f"&hl=vi&gl=VN&ceid=VN:vi")
        res = []
        for it in X.parse_feed(fetcher.get(url, ttl=6 * 3600) or ""):
            title, name = it["title"], it.get("source_name")
            m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", title)
            if m:
                title, name = m.group(1), name or m.group(2)
            res.append(dict(title=title.strip(), url=it["url"], source=(name or "Google News").strip(),
                            ts=it["ts"], bullets=["", ""], hint=hint))
        return res

    out = []
    with ThreadPoolExecutor(workers) as ex:
        for res in ex.map(run, jobs):
            out += res
    return out, len(jobs)


def report_pool(report_dir):
    """Tin đã có (kèm tóm tắt) trong các báo cáo JSON cũ."""
    out = []
    for p in glob.glob(os.path.join(report_dir, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for it in d.get("items", []) if isinstance(d, dict) else []:
            if it.get("title") and it.get("url"):
                b = (it.get("bullets") or ["", ""]) + ["", ""]
                out.append(dict(title=it["title"], url=it["url"], source=it.get("source", ""), ts=it.get("ts"),
                                bullets=b[:2], hint=None))
    return out


def group(arts):
    """Gộp tin trùng: mỗi tin chỉ so với tin đại diện của cụm (không nối chuỗi như union-find)."""
    reps, groups, index = [], [], defaultdict(list)
    for a in sorted(arts, key=lambda a: -(len(a["bullets"][0]) > 0)):
        sh, un = _shingles(a["title"]), _uni(a["title"])
        cand = Counter(j for g in sh for j in index[g])
        best = None
        for j, c in cand.most_common(20):
            rsh, run = reps[j]
            cu = len(un & run)
            if (c >= 3 and c / len(sh | rsh) >= 0.5) or (cu >= 5 and cu / len(un | run) >= 0.6):
                best = j
                break
        if best is None:
            best = len(reps)
            reps.append((sh, un))
            groups.append([])
            for g in sh:
                index[g].append(best)
        groups[best].append(a)
    return groups


# vốn tổng hợp / lũy kế / kế hoạch / dự án hủy: không cộng vào vốn dự án
AGGREGATE = re.compile(r"\d+\s*(?:dự án|công trình)|loạt dự án|hàng loạt|các dự án|huy động|thu hút|ghi nhớ|\bMOU\b|"
                       r"\bFDI\b|giải ngân|đầu tư công|kế hoạch vốn|lũy kế|đến năm 20\d\d|đến 20\d\d|giai đoạn 20\d\d|"
                       r"tổng vốn đăng ký|vốn đăng ký|hủy|huỷ|hoãn|dừng|thu hồi|chấm dứt|báo lãi|\blãi\b|trái phiếu|cổ phiếu|"
                       r"vốn hóa|dư nợ|tín dụng|ngân sách", re.I)


def build(arts, since):
    seen, keep = set(), []
    for a in arts:
        t = a["title"]
        if not t or a["url"] in seen or len(t.split()) < 5 or (a.get("ts") and a["ts"] < since):
            continue
        if not a.get("ts"):
            continue
        if not INFRA.search(t) or NOT_INFRA.search(t):
            continue
        pv = provinces_of(t)
        if not pv:
            continue
        seen.add(a["url"])
        a = dict(a, provs=pv)
        keep.append(a)
    events = []
    for g in group(keep):
        g.sort(key=lambda a: (-(len(a["bullets"][0]) > 0), -(a["ts"] or 0)))
        lead = g[0]
        provs = []
        for a in g:
            for p in a["provs"]:
                if p not in provs:
                    provs.append(p)
        cap = agg = None
        for a in g:
            c = capital(a["title"])
            if not c:
                continue
            if AGGREGATE.search(a["title"]):
                agg = max(agg or 0, c)
            elif cap is None or c > cap:
                cap = c
        events.append(dict(title=lead["title"], url=lead["url"], source=lead["source"], ts=max(a["ts"] for a in g),
                           bullet=lead["bullets"][0], n=len({a["source"] for a in g}), provs=provs[:3], cap=cap, agg=agg,
                           milestone=bool(MILESTONE.search(lead["title"])),
                           others=[(a["source"], a["url"]) for a in g[1:4]]))
    events.sort(key=lambda e: -e["ts"])
    return events


_STOP = set("dự án tỷ đồng nghìn triệu usd vốn đầu tư hơn gần khoảng với của cho tại và các có được là trên đã sẽ "
             "này một những mới nhất xây dựng".split())


def _similar(a, b):
    ta = {w for w in _uni(a["title"]) if w not in _STOP and not w.isdigit()}
    tb = {w for w in _uni(b["title"]) if w not in _STOP and not w.isdigit()}
    return len(ta & tb) >= 2


def score(events):
    prov = {pid: dict(id=pid, name=PROV[pid][1], region=PROV[pid][2], events=[], caps={}, ms=0)
            for pid in PROV}
    for e in events:
        for pid in e["provs"]:
            p = prov[pid]
            p["events"].append(e)
            p["ms"] += e["milestone"]
            # một dự án được nhiều tin nhắc (900.000 tỷ / "hơn 1 triệu tỷ") chỉ tính một lần;
            # dự án liên tỉnh chia đều vốn cho các tỉnh nhắc tới
            if e["cap"] and not any(0.85 <= e["cap"] / ev["cap"] <= 1.18 and _similar(e, ev)
                                    for _, ev in p["caps"].values()):
                p["caps"][len(p["caps"])] = (e["cap"] / len(e["provs"]), e)
    rows = list(prov.values())
    for p in rows:
        p["n"] = len(p["events"])
        p["cap"] = sum(v for v, _ in p["caps"].values())
        p["top"] = sorted(p["caps"].values(), key=lambda x: -x[0])[:5]
    mx_n = max(p["n"] for p in rows) or 1
    mx_c = max(math.log1p(p["cap"]) for p in rows) or 1
    mx_m = max(p["ms"] for p in rows) or 1
    for p in rows:
        p["score"] = round(100 * (0.45 * p["n"] / mx_n + 0.40 * math.log1p(p["cap"]) / mx_c + 0.15 * p["ms"] / mx_m), 1)
    rows.sort(key=lambda p: -p["score"])
    regs = []
    for rid, rname in REGIONS:
        mem = [p for p in rows if p["region"] == rid]
        evs = {id(e) for p in mem for e in p["events"]}
        caps = {}
        for p in mem:
            for k, (v, e) in p["caps"].items():
                caps.setdefault(k, 0)
                caps[k] += v
        regs.append(dict(id=rid, name=rname, members=mem, n=len(evs), cap=sum(caps.values()),
                         ms=sum(p["ms"] for p in mem), score=round(sum(p["score"] for p in mem) / max(len(mem), 1), 1)))
    mx_n = max(r["n"] for r in regs) or 1
    mx_c = max(math.log1p(r["cap"]) for r in regs) or 1
    for r in regs:
        r["score"] = round(100 * (0.5 * r["n"] / mx_n + 0.5 * math.log1p(r["cap"]) / mx_c), 1)
    regs.sort(key=lambda r: -r["score"])
    return rows, regs


def fmt_cap(v):
    if not v:
        return "–"
    if v >= 1000:
        return f"{v / 1000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " nghìn tỷ"
    return f"{v:,.0f}".replace(",", ".") + " tỷ"


def _d(ts):
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%d/%m")


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mut:#5c6370;--line:#e3e6ea;--acc:#0b63ce;--bar:#7fb0ea;--hi:#fff4d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111317;--card:#1a1d22;--ink:#e8eaed;
--mut:#9aa1ac;--line:#2b2f36;--acc:#6aa8ff;--bar:#2f5f9a;--hi:#3a3220}}
:root[data-theme="dark"]{--bg:#111317;--card:#1a1d22;--ink:#e8eaed;--mut:#9aa1ac;--line:#2b2f36;--acc:#6aa8ff;
--bar:#2f5f9a;--hi:#3a3220}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:4px 0}h2{font-size:18px;margin:28px 0 8px}h3{font-size:16px;margin:0}
.mut{color:var(--mut);font-size:13px}a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;
overflow:hidden}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--mut);font-weight:600;background:var(--bg)}td.n{text-align:right;white-space:nowrap}
.bar{height:8px;background:var(--bar);border-radius:4px;min-width:2px}
.rk{font-weight:700;width:28px}.reg{font-size:12px;color:var(--mut)}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0}
summary{cursor:pointer;padding:10px 14px;list-style:none;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}summary b{font-size:16px}
details ol{margin:0;padding:0 14px 12px 34px}details li{margin:6px 0}
.cap{background:var(--hi);border-radius:4px;padding:0 5px;font-size:12px;white-space:nowrap}
.cap.agg{background:none;border:1px dashed var(--mut);color:var(--mut)}
.ms{font-size:11px;border:1px solid var(--acc);color:var(--acc);border-radius:4px;padding:0 4px}
.b{color:var(--mut);font-size:13px}.notes p,.notes li{margin:6px 0}
.tw{overflow-x:auto}
@media (max-width:640px){.hide-s{display:none}th,td{padding:6px 5px;font-size:13px}}
"""


JS = """
document.querySelectorAll('table.st').forEach(t=>{const hs=[...t.rows[0].cells];
hs.forEach((h,i)=>{if(i<2)return;h.style.cursor='pointer';h.title='Bấm để sắp xếp';h.onclick=()=>{
const rs=[...t.rows].slice(1);const v=r=>{const c=r.cells[i];return parseFloat(c.dataset.v??c.textContent)||0};
rs.sort((a,b)=>v(b)-v(a));rs.forEach((r,k)=>{r.cells[0].textContent=k+1;t.tBodies[0].appendChild(r)});
hs.forEach(x=>x.style.textDecoration='');h.style.textDecoration='underline'}})});
"""


def render(rows, regs, events, days, now, n_queries, notes_html=""):
    e = html.escape
    since = _d(now - days * 86400)
    tot_cap = sum(p["cap"] for p in rows)
    out = [f"<title>Hạ tầng theo tỉnh thành</title><style>{CSS}</style><main>",
           "<h1>Hạ tầng theo tỉnh, thành Việt Nam</h1>",
           f"<div class=mut>Tin từ {since} đến {_d(now)}/{datetime.fromtimestamp(now, VN_TZ).year} · "
           f"{len(events)} sự kiện hạ tầng (đã gộp tin trùng) · {n_queries} truy vấn Google News + các bản tin đã crawl · "
           f"34 tỉnh, thành sau sáp nhập, tin về tỉnh cũ được tính vào tỉnh mới</div>"]
    if notes_html:
        out.append(f"<div class='card notes'>{notes_html}</div>")
    mx = max(r["score"] for r in regs) or 1
    out.append("<h2>Xếp hạng theo vùng</h2><div class=tw><table class=st><tr><th>#</th><th>Vùng</th><th class=n>Sự kiện</th>"
               "<th class=n>Vốn nêu trong tin</th><th class='n hide-s'>Khởi công, phê duyệt…</th><th>Điểm</th></tr>")
    for i, r in enumerate(regs, 1):
        top = ", ".join(p["name"] for p in sorted(r["members"], key=lambda p: -p["score"])[:3])
        out.append(f"<tr><td class=rk>{i}</td><td><b>{e(r['name'])}</b><div class=reg>Dẫn đầu: {e(top)}</div></td>"
                   f"<td class=n data-v={r['n']}>{r['n']}</td><td class=n data-v={r['cap']:.0f}>{fmt_cap(r['cap'])}</td><td class='n hide-s'>{r['ms']}</td>"
                   f"<td style='min-width:90px'>{r['score']}<div class=bar style='width:{100 * r['score'] / mx:.0f}%'></div></td></tr>")
    out.append("</table></div>")
    mx = rows[0]["score"] or 1
    out.append("<h2>Xếp hạng 34 tỉnh, thành</h2><div class=tw><table class=st><tr><th>#</th><th>Tỉnh/thành</th>"
               "<th class=n>Sự kiện</th><th class=n>Vốn nêu trong tin</th><th class='n hide-s'>Khởi công, phê duyệt…</th>"
               "<th>Điểm</th></tr>")
    for i, p in enumerate(rows, 1):
        old = PROV[p["id"]][3]
        sub = (" (gồm " + ", ".join(old) + ")") if old else ""
        sub = re.sub(r", Bà Rịa-Vũng Tàu, Bà Rịa – Vũng Tàu|, Bắc Cạn|, Thừa Thiên - Huế", "", sub)
        out.append(f"<tr><td class=rk>{i}</td><td><a href='#p-{p['id']}'><b>{e(p['name'])}</b></a>"
                   f"<div class=reg>{e(REGION_NAME[p['region']])}{e(sub)}</div></td><td class=n data-v={p['n']}>{p['n']}</td>"
                   f"<td class=n data-v={p['cap']:.0f}>{fmt_cap(p['cap'])}</td><td class='n hide-s'>{p['ms']}</td>"
                   f"<td style='min-width:90px'>{p['score']}<div class=bar style='width:{100 * p['score'] / mx:.0f}%'></div></td></tr>")
    out.append("</table></div>")
    out.append("<p class=mut>Điểm = 45% số sự kiện + 40% tổng vốn (thang log) + 15% số mốc khởi công, thông xe, phê duyệt, "
               "chọn nhà đầu tư; quy về thang 100 theo tỉnh dẫn đầu. Vốn là con số nêu trong tiêu đề hoặc tóm tắt tin; "
               "một dự án được nhiều tin nhắc lại chỉ tính một lần; dự án liên tỉnh chia đều cho các tỉnh. "
               f"1 USD ≈ {USD_VND:,} đồng. Đây là thước đo độ phủ tin tức, không phải số liệu thống kê chính thức về vốn."
               .replace(",", "."))
    out.append("<h2>Tin theo từng tỉnh, thành</h2>")
    for i, p in enumerate(rows, 1):
        out.append(f"<details id='p-{p['id']}'{' open' if i <= 3 else ''}><summary><b>{i}. {e(p['name'])}</b>"
                   f"<span class=mut>{p['n']} sự kiện · vốn {fmt_cap(p['cap'])}</span></summary>")
        if p["top"]:
            out.append("<div style='padding:0 14px' class=b>Dự án vốn lớn nhất: " + "; ".join(
                f"<a href='{e(ev['url'])}'>{e(ev['title'][:90])}</a> <span class=cap>{fmt_cap(ev['cap'])}</span>"
                for _, ev in p["top"][:3]) + "</div>")
        out.append("<ol>")
        evs = sorted(p["events"], key=lambda x: (-(x["cap"] or 0) * 0 - x["milestone"] - x["n"] / 10, -x["ts"]))
        for ev in evs[:60]:
            extra = "".join(f" · <a href='{e(u)}'>{e(s)}</a>" for s, u in ev["others"][:2])
            capb = (f" <span class=cap>{fmt_cap(ev['cap'])}</span>" if ev["cap"] else
                    f" <span class='cap agg' title='Số tổng hợp, lũy kế hoặc kế hoạch: không cộng vào vốn dự án'>"
                    f"Σ {fmt_cap(ev['agg'])}</span>" if ev.get("agg") else "")
            msb = " <span class=ms>mốc</span>" if ev["milestone"] else ""
            bl = f"<div class=b>{e(ev['bullet'][:220])}</div>" if ev["bullet"] else ""
            out.append(f"<li><a href='{e(ev['url'])}'>{e(ev['title'])}</a>{capb}{msb}"
                       f"<div class=mut>{e(ev['source'])} · {_d(ev['ts'])}{extra}</div>{bl}</li>")
        if len(evs) > 60:
            out.append(f"<li class=mut>… và {len(evs) - 60} tin khác</li>")
        out.append("</ol></details>")
    out.append("</main><script>" + JS + "</script>")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="news_crawler.infra")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="reports/ha-tang-tinh-thanh.html")
    ap.add_argument("--json", help="ghi dữ liệu xếp hạng ra JSON")
    ap.add_argument("--notes", help="file HTML nhận định chèn đầu báo cáo")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--reports", default="reports")
    o = ap.parse_args(argv)
    now = time.time()
    f = Fetcher(cache_dir=o.cache, per_host=3, delay=0.3)
    f.offline = o.cache_only
    arts, nq = gnews(f, o.days)
    print(f"[gnews] {nq} truy vấn, {len(arts)} tin")
    arts += report_pool(o.reports)
    events = build(arts, now - o.days * 86400)
    rows, regs = score(events)
    print(f"{len(events)} sự kiện hạ tầng")
    for i, p in enumerate(rows[:34], 1):
        print(f"{i:2}. {p['name']:<12} {p['n']:4} sự kiện  {fmt_cap(p['cap']):>16}  mốc {p['ms']:3}  điểm {p['score']}")
    for r in regs:
        print(f"   {r['name']:<40} {r['n']:4}  {fmt_cap(r['cap']):>16}  {r['score']}")
    notes = open(o.notes, encoding="utf-8").read() if o.notes else ""
    os.makedirs(os.path.dirname(o.out) or ".", exist_ok=True)
    with open(o.out, "w", encoding="utf-8") as fh:
        fh.write(render(rows, regs, events, o.days, now, nq, notes))
    if o.json:
        slim = [dict({k: v for k, v in p.items() if k not in ("events", "caps", "top")},
                     top=[(v, ev["title"], ev["url"]) for v, ev in p["top"]],
                     events=[{k: ev[k] for k in ("title", "url", "source", "ts", "cap", "agg", "milestone", "provs", "n")}
                             for ev in p["events"]]) for p in rows]
        json.dump(dict(rows=slim, regions=[{k: v for k, v in r.items() if k != "members"} for r in regs],
                       now=now, days=o.days), open(o.json, "w", encoding="utf-8"), ensure_ascii=False)
    print("->", o.out)


if __name__ == "__main__":
    main()
