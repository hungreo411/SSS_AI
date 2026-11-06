"""Phân tích thông điệp và mức độ xuất hiện của một lãnh đạo qua kho lưu trữ báo (Tuổi Trẻ, Thanh Niên, VTV).

Chạy: python -m news_crawler.leader --from 2026-01-01 --split 2026-06-01 --to 2026-11-06 [--notes n.html] [--out x.html]

- Chọn bài có lãnh đạo trong tiêu đề (tên riêng, hoặc chức danh đứng một mình khi chắc chắn là người đó).
- Tải toàn văn, tách các câu có lời phát biểu ("Tổng Bí thư nhấn mạnh/yêu cầu/chỉ đạo...") và trích dẫn trong ngoặc kép.
- Gán thông điệp theo bộ từ khóa, loại hoạt động, mức độ quan trọng của sự kiện.
- So sánh 2 giai đoạn: tần suất/tháng, tỷ lệ trên 1.000 bài của 3 báo, tỷ trọng thông điệp, mức tham dự sự kiện lớn.
"""
import argparse
import hashlib
import html as H
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

from . import extract as X
from .archive import OUTLETS, UA, load_archive
from .extract import VN_TZ
from .sources import SOURCES

NAME = "Tô Lâm"
_FOREIGN = r"Lào|Trung Quốc|Cuba|Triều Tiên|Tập Cận Bình|Thongloun|Liên Hợp Quốc|LHQ|NATO|ASEAN|Guterres|Campuchia"
_PAST = r"(?:nguyên|Nguyên|cố|Cố|cựu|Cựu|các|Các|những|Những|vị|Vị)\s+$"
# "Tổng Bí thư:" / "Tổng Bí thư, Chủ tịch nước dự..." — chức danh đứng một mình, không kèm tên người khác
_BARE = re.compile(r"Tổng Bí thư(?:,\s*Chủ tịch nước)?(?=\s*(?::|đề nghị|dự |kiểm tra|trao|nói|tiếp|gửi|chủ trì|và |làm việc|"
                   r"thăm|hội đàm|điện đàm|phát biểu|nhấn mạnh|yêu cầu|chỉ đạo|chúc|khẳng định|ký|chứng kiến|gặp|dâng|"
                   r"viếng|công bố|đến |về |cùng|với |tặng|đặt|bấm nút|phát động|đối thoại|trả lời|kêu gọi|$))")


def is_leader(title):
    if NAME in title or "To Lam" in title:
        return True
    for m in _BARE.finditer(title):
        before, after = title[:m.start()], title[m.end():m.end() + 40]
        if re.search(_PAST, before) or re.match(r"\s*(?:" + _FOREIGN + ")", after):
            continue
        if re.search(_FOREIGN, title[max(0, m.start() - 15):m.end() + 25]):
            continue
        return True
    return False


# ---------- tải toàn văn ----------
_SEL = {s["id"]: s for s in SOURCES}


def fetch_body(row, cache_dir=".cache/leader2"):
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, hashlib.sha1(row["url"].encode()).hexdigest() + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    for i in range(3):
        try:
            r = requests.get(row["url"], headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200:
                r.encoding = "utf-8"
                a = X.parse_article(r.text, row["url"], _SEL.get(row["outlet"], {}))
                d = dict(title=a.get("title") or "", desc=a.get("desc") or "", paras=a.get("paras") or [])
                json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
                return d
            if r.status_code in (404, 410):
                break
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return dict(title="", desc="", paras=[])


def fetch_all(rows, workers=6):
    by_host = defaultdict(list)
    for r in rows:
        by_host[r["outlet"]].append(r)

    def run_host(lst):
        out = []
        for r in lst:
            out.append((r["url"], fetch_body(r)))
        return out

    res = {}
    with ThreadPoolExecutor(max(workers, len(by_host))) as ex:
        # mỗi báo 2 luồng để lịch sự
        chunks = []
        for lst in by_host.values():
            chunks += [lst[0::2], lst[1::2]]
        for part in ex.map(run_host, chunks):
            res.update(part)
    return res


def collect(start, end):
    rows = load_archive(start, end)
    sel = [r for r in rows if is_leader(r["title"])]
    return rows, sel


if __name__ == "__main__" and os.environ.get("LEADER_FETCH_ONLY"):
    rows, sel = collect("2026-01-01", "2026-11-06")
    print(len(rows), "bài;", len(sel), "bài về", NAME)
    t = time.time()
    bodies = fetch_all(sel)
    print("tải xong", len(bodies), "bài trong", round(time.time() - t), "giây;",
          sum(1 for b in bodies.values() if b["paras"]), "có nội dung")


# ---------- thông điệp ----------
# (id, nhãn, regex trên văn bản viết thường)
THEMES = [
    ("ky_nguyen", "Kỷ nguyên mới, vươn mình, khát vọng phát triển",
     r"kỷ nguyên (?:mới|vươn mình|phát triển)|vươn mình|khát vọng|hùng cường|thịnh vượng|giàu mạnh|phồn vinh"),
    ("tang_truong", "Tăng trưởng cao, hai con số, mục tiêu 2030–2045",
     r"hai con số|tăng trưởng (?:cao|nhanh|bứt phá)|2045|thu nhập cao|bứt phá|nước phát triển|mô hình tăng trưởng|động lực tăng trưởng"),
    ("the_che", "Thể chế là điểm nghẽn, hoàn thiện pháp luật",
     r"thể chế|điểm nghẽn|hoàn thiện (?:hệ thống )?pháp luật|xây dựng (?:và thi hành )?pháp luật|tư duy (?:lập pháp|xây dựng pháp luật|quản lý)|"
     r"không quản được thì cấm|cơ chế đặc thù|tháo gỡ (?:vướng mắc|điểm nghẽn)|luật hóa"),
    ("bo_may", "Tinh gọn bộ máy, chính quyền 2 cấp, vận hành bộ máy",
     r"bộ máy|tinh gọn|chính quyền (?:địa phương )?(?:hai|2) cấp|sắp xếp (?:tổ chức|đơn vị|lại)|đơn vị hành chính|địa giới|biên chế|sáp nhập"),
    ("can_bo", "Công tác cán bộ, nêu gương, thay người không đáp ứng",
     r"công tác cán bộ|cán bộ|nhân sự|nêu gương|kế cận|thay thế (?:người|những người)|không đáp ứng|dám nghĩ|dám làm|dám chịu trách nhiệm|"
     r"sàng lọc|người giỏi|nhân tài|an toàn là trên hết|đùn đẩy|né tránh"),
    ("xay_dung_dang", "Xây dựng, chỉnh đốn Đảng, tư tưởng, lý luận",
     r"chỉnh đốn đảng|xây dựng đảng|tổ chức đảng|đảng viên|chính trị tư tưởng|công tác tư tưởng|lý luận|tự diễn biến|tự chuyển hóa|"
     r"kiểm tra, giám sát|nghị quyết đại hội|văn kiện|bản lĩnh chính trị|vai trò lãnh đạo của đảng|niềm tin"),
    ("chong_tham_nhung", "Chống tham nhũng, lãng phí, tiêu cực; dự án tồn đọng",
     r"tham nhũng|lãng phí|tiêu cực|thất thoát|chậm tiến độ|đội vốn|tồn đọng|sai phạm|lợi ích nhóm|hợp thức hóa"),
    ("khcn", "Khoa học công nghệ, đổi mới sáng tạo, chuyển đổi số, dữ liệu",
     r"khoa học|công nghệ|đổi mới sáng tạo|chuyển đổi số|số hóa|dữ liệu|trí tuệ nhân tạo|\bai\b|bán dẫn|kinh tế số|không gian mạng|an ninh mạng"),
    ("tu_nhan", "Kinh tế tư nhân, doanh nghiệp, cắt thủ tục",
     r"kinh tế tư nhân|doanh nghiệp|doanh nhân|thủ tục hành chính|giấy phép|môi trường (?:đầu tư |)kinh doanh|cắt giảm|tiền kiểm|hậu kiểm|"
     r"thị trường|nhà đầu tư"),
    ("ha_tang", "Hạ tầng, dự án trọng điểm, logistics, năng lượng",
     r"hạ tầng|cao tốc|đường sắt|sân bay|cảng biển|logistics|năng lượng|điện hạt nhân|dự án trọng điểm|giao thông|quy hoạch|đô thị"),
    ("nhan_dan", "Nhân dân là trung tâm, an sinh, người dân thụ hưởng",
     r"lấy dân làm gốc|dân là gốc|nhân dân là trung tâm|người dân là trung tâm|thụ hưởng|hạnh phúc|an sinh|không để ai bị bỏ lại|"
     r"phục vụ nhân dân|phục vụ người dân|đời sống (?:nhân dân|người dân)|hướng về nhân dân|dân tin|ấm no|nhà ở xã hội|giảm nghèo"),
    ("giao_duc", "Giáo dục, đào tạo, nhân lực chất lượng cao",
     r"giáo dục|đào tạo|nhà giáo|giáo viên|học sinh|thi cử|đại học|nguồn nhân lực|nhân lực chất lượng cao|chảy máu chất xám|học tập"),
    ("y_te_moi_truong", "Y tế, sức khỏe, môi trường sống, thiên tai",
     r"y tế|sức khỏe|thể lực|bệnh viện|thực phẩm|môi trường (?:sống|trong lành|an toàn)|ô nhiễm|khí hậu|thiên tai|trẻ em"),
    ("van_hoa", "Văn hóa, con người, báo chí, đạo đức xã hội",
     r"văn hóa|con người việt nam|báo chí|truyền thông|tử tế|đạo đức|thể thao|bản sắc|giá trị (?:dân tộc|việt nam)"),
    ("quoc_phong", "Quốc phòng – an ninh, lực lượng vũ trang, chủ quyền",
     r"quốc phòng|an ninh|quân đội|công an|lực lượng vũ trang|chủ quyền|bảo vệ tổ quốc|biển đảo|tinh, gọn, mạnh|quốc gia biển|quân chủng|binh chủng"),
    ("doi_ngoai", "Đối ngoại, hội nhập, tự chủ chiến lược",
     r"đối ngoại|hội nhập|ngoại giao|đối tác|tự chủ chiến lược|đa phương|quan hệ (?:hai nước|việt|song phương)|hợp tác (?:quốc tế|song phương|toàn diện)|"
     r"đối tác chiến lược|hòa bình|liên hợp quốc|asean"),
    ("phan_cap", "Phân cấp, phân quyền, địa phương tự quyết",
     r"phân cấp|phân quyền|địa phương quyết|ủy quyền|tự chủ (?:của )?địa phương|địa phương làm"),
    ("hanh_dong", "Hành động thực chất, chống hình thức, đưa nghị quyết vào cuộc sống",
     r"hành động|thực chất|quyết liệt|nói đi đôi với làm|hình thức|phong trào|thành tích|khẩu hiệu|đến cùng|thực thi|tổ chức thực hiện|"
     r"vào cuộc sống|kết quả cụ thể|đo đếm|kiểm đếm|ăn chơi|nói không"),
    ("on_dinh", "Ổn định vĩ mô, kỷ cương, phát triển bền vững",
     r"ổn định|kỷ cương|bền vững|vĩ mô|lạm phát|cân đối lớn|an toàn (?:tài chính|hệ thống)"),
    ("tai_chinh", "Tài chính, thị trường vốn, trung tâm tài chính, ngân sách",
     r"trung tâm tài chính|thị trường (?:vốn|chứng khoán|tài chính)|ngân sách|huy động vốn|nguồn lực tài chính|tín dụng|trái phiếu"),
]
_TH = [(tid, lab, re.compile(rx)) for tid, lab, rx in THEMES]
_SPEECH_VERB = re.compile(r"nhấn mạnh|yêu cầu|chỉ đạo|khẳng định|đề nghị|lưu ý|nêu rõ|chỉ rõ|cho rằng|phát biểu|nhắc|kêu gọi|"
                          r"chia sẻ|mong muốn|gợi mở|đặt vấn đề|định hướng|đánh giá|nhận định|nói|cho biết|nhấn|đề cập|phân tích")


def speech_text(title, paras, cdt_from_ts, ts):
    """Lời của lãnh đạo: tiêu đề dạng 'Tổng Bí thư: ...' + các câu có chủ ngữ là lãnh đạo và động từ phát biểu
    (kèm 2 câu tiếp theo — thường vẫn là lời phát biểu)."""
    subj = r"Tổng Bí thư|Tô Lâm|người đứng đầu Đảng"
    if ts >= cdt_from_ts:
        subj += r"|Chủ tịch nước"
    rs = re.compile(r"(?:" + subj + r")")
    if re.match(r"(?:Toàn văn|Phát biểu|Bài phát biểu|Bài viết|Diễn văn|Phát biểu kết luận|Phát biểu bế mạc|Phát biểu khai mạc)\b", title) \
            or any("toàn văn" in p.lower() for p in paras[:2]):
        return " ".join(paras)  # cả bài là lời của lãnh đạo
    out = []
    if ":" in title and rs.search(title.split(":")[0]):
        out.append(title.split(":", 1)[1])
    sents = []
    for p in paras:
        sents += [s for s in re.split(r"(?<=[.!?…])\s+(?=[A-ZĐ“\"])", p) if s]
    take = 0
    for s in sents:
        if rs.search(s) and _SPEECH_VERB.search(s):
            out.append(s)
            take = 2
        elif take:
            out.append(s)
            take -= 1
        elif re.match(r"^[“\"]", s) and out:
            out.append(s)
    return " ".join(out)


def themes_of(text):
    t = text.lower()
    return {tid: len(rx.findall(t)) for tid, _, rx in _TH if rx.search(t)}


# ---------- loại hoạt động & mức độ quan trọng ----------
_BIG_COUNTRY = r"Mỹ|Hoa Kỳ|Trump|Trung Quốc|Tập Cận Bình|Nga|Putin|Nhật Bản|Pháp|Ấn Độ|Hàn Quốc|Liên minh châu Âu|EU|Đức|Anh|Liên hợp quốc|Liên Hợp Quốc|APEC|G20|ASEAN"
LEVEL_RULES = [
    (5, r"Đại hội (?:XIV|đại biểu toàn quốc|Đảng toàn quốc|lần thứ XIV)|Hội nghị (?:lần thứ \w+ )?(?:Ban Chấp hành )?Trung ương|Hội nghị Trung ương|"
        r"(?:khai mạc|bế mạc) (?:Kỳ họp|kỳ họp)|Quốc khánh|bầu (?:làm )?(?:Chủ tịch nước|Tổng Bí thư)|nhậm chức|tuyên thệ|"
        r"Đại hội đồng Liên hợp quốc|Hội nghị toàn quốc quán triệt|thăm cấp nhà nước|Trump|Tập Cận Bình|Putin"),
    (4, r"Bộ Chính trị|Ban Bí thư|Quân ủy Trung ương|Hội nghị toàn quốc|hội đàm|thăm chính thức|Quốc hội|kỷ niệm \d+ năm|"
        r"bài viết|họp báo|trả lời phỏng vấn|tổng kết|" + _BIG_COUNTRY),
    (3, r"làm việc|kiểm tra|dự lễ|Lễ|khởi công|khánh thành|hội kiến|tiếp|gặp|phát biểu|chỉ đạo|Hội nghị|Đại hội|chủ trì"),
    (2, r"gửi thư|(?<!Bí )\b[Tt]hư (?:chúc|gửi|của|nhân)|điện mừng|chúc mừng|thăm hỏi|chia buồn|dâng hương|viếng|tặng|trao"),
]
_LV = [(lv, re.compile(rx)) for lv, rx in LEVEL_RULES]
TYPES = [
    ("hop_bao", "Họp báo, trả lời phỏng vấn, bài viết", r"họp báo|trả lời phỏng vấn|phỏng vấn|bài viết|tác phẩm|cuốn sách|trả lời báo|trao đổi với báo"),
    ("doi_ngoai", "Đối ngoại (hội đàm, tiếp, thăm nước ngoài)",
     r"hội đàm|hội kiến|điện đàm|tiếp (?:Tổng thống|Thủ tướng|Chủ tịch|Bộ trưởng|Đại sứ|Quốc vương|Nhà vua|đoàn|Tổng Thư ký|lãnh đạo)|"
     r"thăm (?:chính thức|cấp nhà nước|làm việc tại)|gặp (?:Tổng thống|Thủ tướng|Chủ tịch|Quốc vương)|sân bay|Phu nhân|tuyên bố chung|"
     r"Tổng thống|Thủ tướng (?!Lê Minh Hưng|Phạm Minh Chính|Chính phủ)|kiều bào|Đại sứ quán|Liên hợp quốc|ASEAN|APEC"),
    ("hoi_nghi", "Hội nghị Đảng, Quốc hội, Chính phủ", r"Hội nghị|Bộ Chính trị|Ban Bí thư|Trung ương|Quân ủy|Quốc hội|kỳ họp|phiên|Đại hội|Chính phủ"),
    ("dia_phuong", "Làm việc với địa phương, bộ ngành, kiểm tra", r"làm việc|kiểm tra|về thăm|thăm (?!chính thức|cấp nhà nước)|khảo sát"),
    ("phat_bieu", "Phát biểu, chỉ đạo (tiêu đề trích lời)",
     r"(?:Tổng Bí thư|Chủ tịch nước|Tô Lâm)[^:]{0,30}:|phát biểu|chỉ đạo|nhấn mạnh|yêu cầu|đề nghị|khẳng định|kêu gọi|Toàn văn"),
    ("nghi_le", "Lễ kỷ niệm, khởi công, nghi lễ", r"Lễ|lễ|kỷ niệm|dâng hương|viếng|đặt vòng hoa|khởi công|khánh thành|trao|gắn biển"),
    ("thu_dien", "Thư, điện mừng, chúc mừng", r"gửi thư|(?<!Bí )\b[Tt]hư (?:chúc|gửi|của|nhân|cảm ơn)|điện mừng|chúc mừng|"
                                              r"chia buồn|gửi điện"),
]
_TY = [(tid, lab, re.compile(rx)) for tid, lab, rx in TYPES]


def level_of(title, n):
    lv = next((lv for lv, rx in _LV if rx.search(title)), 1)
    return min(5, lv + (1 if n >= 4 and lv < 5 else 0))


def type_of(title):
    return next((tid for tid, _, rx in _TY if rx.search(title)), "khac")


# ---------- sự kiện lớn của cả nước (đo trên toàn bộ kho bài) ----------
MAJOR = [
    ("daihoi", "Đại hội XIV của Đảng", r"Đại hội (?:đại biểu toàn quốc lần thứ XIV|XIV của Đảng|Đảng lần thứ XIV|XIV)"),
    ("hntw", "Hội nghị Trung ương", r"Hội nghị (?:lần thứ (?:nhất|hai|ba|bốn|năm|sáu|\w+) )?(?:Ban Chấp hành )?Trung ương(?: Đảng)?(?: khóa XIV)?|Hội nghị Trung ương \d+"),
    ("quochoi", "Kỳ họp Quốc hội (khai mạc/bế mạc)", r"(?:khai mạc|bế mạc|Khai mạc|Bế mạc) (?:Kỳ họp|kỳ họp)"),
    ("baucu", "Bầu cử Quốc hội, HĐND", r"bầu cử đại biểu Quốc hội|ngày bầu cử|Bầu cử đại biểu Quốc hội"),
    ("tet", "Tết Nguyên đán", r"chúc Tết|Giao thừa|giao thừa|thư chúc Tết"),
    ("dang", "Kỷ niệm thành lập Đảng 3/2", r"năm Ngày thành lập Đảng|thành lập Đảng Cộng sản Việt Nam"),
    ("304", "Kỷ niệm 30/4", r"Giải phóng miền Nam|thống nhất đất nước|30/4|30-4"),
    ("195", "Sinh nhật Bác 19/5", r"Ngày sinh Chủ tịch Hồ Chí Minh|năm Ngày sinh Bác|19/5|19-5"),
    ("277", "Thương binh liệt sĩ 27/7", r"Thương binh Liệt sĩ|Thương binh - Liệt sĩ|27/7|27-7"),
    ("29", "Quốc khánh 2/9", r"Quốc khánh|2/9|2-9|Cách mạng Tháng Tám"),
    ("unga", "Đại hội đồng Liên hợp quốc", r"Đại hội đồng Liên hợp quốc|Đại hội đồng LHQ|Đại hội đồng Liên Hợp Quốc"),
    ("apec_asean", "Hội nghị cấp cao ASEAN / APEC", r"Hội nghị Cấp cao ASEAN|Hội nghị cấp cao ASEAN|APEC"),
    ("hn_toanquoc", "Hội nghị toàn quốc quán triệt nghị quyết", r"Hội nghị toàn quốc (?:quán triệt|học tập|triển khai)"),
]


# ---------- phân tích ----------
def _uni(t):
    return set(re.findall(r"\w+", t.lower())) - {"tổng", "bí", "thư", "chủ", "tịch", "nước", "tô", "lâm", "và", "của", "với", "các",
                                                 "ảnh", "ttxvn", "phát", "biểu", "tại", "những", "là"}


def group_events(arts):
    """Gộp bài cùng sự kiện: cùng cửa sổ 2 ngày và tiêu đề trùng từ đáng kể."""
    arts = sorted(arts, key=lambda a: a["ts"])
    evs = []
    for a in arts:
        u = _uni(a["title"])
        best = None
        for ev in reversed(evs):
            if a["ts"] - ev["ts1"] > 2 * 86400:
                break
            inter = len(u & ev["u"])
            if inter >= 4 and inter / max(1, min(len(u), len(ev["u"]))) >= 0.5:
                best = ev
                break
        if best is None:
            evs.append(dict(arts=[a], u=set(u), ts0=a["ts"], ts1=a["ts"]))
        else:
            best["arts"].append(a)
            best["u"] |= u
            best["ts1"] = a["ts"]
    return evs


def _month(ts):
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%Y-%m")


def _months(start, end):
    s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def analyze(rows, sel, bodies, start, split, end):
    ts_split = datetime.fromisoformat(split).replace(tzinfo=VN_TZ).timestamp()
    ts_start = datetime.fromisoformat(start).replace(tzinfo=VN_TZ).timestamp()
    ts_end = datetime.fromisoformat(end).replace(tzinfo=VN_TZ).timestamp() + 86400
    per = lambda ts: "P1" if ts < ts_split else "P2"
    cdt = min((r["ts"] for r in rows if "Chủ tịch nước Tô Lâm" in r["title"]), default=ts_end)
    arts = []
    for r in sel:
        b = bodies.get(r["url"]) or {}
        real = (b.get("title") or "").strip() or r["title"]
        caption = bool(re.search(r"\(?Ảnh:|Ảnh: |\. Ảnh|- Ảnh", r["title"])) and real != r["title"]
        sp = speech_text(real, b.get("paras") or [], cdt, r["ts"])
        arts.append(dict(r, title=real, caption=r["title"] if caption else "", headline=is_leader(real), speech=sp,
                         body=" ".join(b.get("paras") or [])[:6000]))
    evs = group_events(arts)
    for ev in evs:
        a0 = sorted(ev["arts"], key=lambda a: (-a["headline"], -(":" in a["title"]), -len(a["speech"])))[0]
        ev["title"], ev["url"], ev["ts"] = a0["title"], a0["url"], ev["ts0"]
        ev["n"] = len(ev["arts"])
        ev["outlets"] = sorted({a["outlet"] for a in ev["arts"]})
        ev["level"] = max(level_of(a["title"], ev["n"]) for a in ev["arts"])
        ev["type"] = type_of(" ".join(a["title"] for a in ev["arts"]))
        sp = " ".join(a["speech"] for a in ev["arts"])
        ev["speech"] = len(sp) > 60
        th = themes_of(sp) if ev["speech"] else {}
        ev["themes"] = th
        ev["words"] = len(sp.split()) if ev["speech"] else 0
        ev["per"] = per(ev["ts"])
        q = [a["title"].split(":", 1)[1].strip() for a in ev["arts"] if ":" in a["title"] and a["headline"]
             and re.search(r"Tổng Bí thư|Tô Lâm|Chủ tịch nước", a["title"].split(":")[0])]
        ev["quote"] = max(q, key=len) if q else ""
        # câu trích dẫn ứng viên: tiêu đề trích lời + câu ngắn trong lời phát biểu
        cand = [(1, x) for x in q]
        for a in ev["arts"]:
            for snt in re.split(r"(?<=[.!?…”\"])\s+(?=[A-ZĐ“\"])", a["speech"]):
                snt = snt.strip()
                if 50 <= len(snt) <= 260 and not re.search(r"Ảnh:|TTXVN|Kính thưa|Thưa các", snt):
                    cand.append((0, snt))
        ev["qs"] = cand
        del ev["u"]
    months = _months(start, end)
    tot_m = Counter(_month(r["ts"]) for r in rows)
    # đối chứng: tên trong tiêu đề (cùng cách đo cho cả 3 người)
    CTRL = [("tl", "Tô Lâm", r"Tô Lâm"), ("tt", "Thủ tướng (Phạm Minh Chính → Lê Minh Hưng)", r"Thủ tướng (?:Lê Minh Hưng|Phạm Minh Chính)"),
            ("qh", "Chủ tịch Quốc hội Trần Thanh Mẫn", r"Trần Thanh Mẫn")]
    ctrl = {cid: Counter() for cid, _, _ in CTRL}
    for r in rows:
        for cid, _, rx in CTRL:
            if re.search(rx, r["title"]):
                ctrl[cid][_month(r["ts"])] += 1
    monthly = []
    for m in months:
        mev = [e for e in evs if _month(e["ts"]) == m]
        monthly.append(dict(month=m, total=tot_m[m], arts=sum(1 for a in arts if _month(a["ts"]) == m),
                            events=len(mev), speech=sum(e["speech"] for e in mev),
                            big=sum(e["level"] >= 4 for e in mev),
                            types=Counter(e["type"] for e in mev),
                            ctrl={cid: ctrl[cid][m] for cid in ctrl},
                            themes=Counter(t for e in mev for t in e["themes"])))
    P = {}
    for p, a, b in (("P1", ts_start, ts_split), ("P2", ts_split, ts_end)):
        pe = [e for e in evs if a <= e["ts"] < b]
        pa = [x for x in arts if a <= x["ts"] < b]
        nm = (min(b, time.time()) - a) / 86400 / 30.44
        days = sorted({datetime.fromtimestamp(x["ts"], VN_TZ).date() for x in pa if x["headline"]})
        ndays = round((min(b, time.time()) - a) / 86400)
        gaps, prev = [], datetime.fromtimestamp(a, VN_TZ).date()
        for d in days:
            gaps.append(((d - prev).days - 1, prev, d))
            prev = d
        gaps.append(((datetime.fromtimestamp(min(b, time.time()), VN_TZ).date() - prev).days, prev, None))
        tot = sum(1 for r in rows if a <= r["ts"] < b)
        sp = [e for e in pe if e["speech"]]
        wsum = sum(e["level"] for e in sp) or 1
        th = {}
        for tid, lab, _ in THEMES:
            hit = [e for e in sp if tid in e["themes"]]
            words = sum(e["words"] for e in sp) or 1
            th[tid] = dict(share=len(hit) / max(1, len(sp)), hits=sum(e["themes"][tid] for e in hit) * 1000 / words,
                           wshare=sum(e["level"] for e in hit) / wsum, n=len(hit),
                           quotes=_theme_quotes(hit, tid))
        P[p] = dict(months=nm, days=ndays, arts=len(pa), tot=tot, headline=sum(x["headline"] for x in pa),
                    ctrl={cid: sum(ctrl[cid][_month(r["ts"])] for r in []) for cid in ctrl},
                    events=len(pe), speech=len(sp), big=sum(e["level"] >= 4 for e in pe),
                    big_speech=sum(e["level"] >= 4 and e["speech"] for e in pe),
                    types=Counter(e["type"] for e in pe), present_days=len(days),
                    gap=max(gaps, key=lambda g: g[0]), themes=th,
                    top=sorted(pe, key=lambda e: (-e["level"], -e["n"], -e["ts"]))[:30])
        P[p]["ctrl"] = {cid: sum(v for mm, v in ctrl[cid].items() if a <= datetime.fromisoformat(mm + "-15").replace(tzinfo=VN_TZ).timestamp() < b)
                        for cid in ctrl}
    major = major_events(rows, arts, ts_start, ts_split, ts_end)
    return dict(arts=arts, events=evs, monthly=monthly, P=P, major=major, cdt=cdt, CTRL=CTRL)


_THRX = {tid: re.compile(rx) for tid, _, rx in THEMES}


def _theme_quotes(events, tid, k=4):
    """Câu trích tiêu biểu cho một thông điệp: ưu tiên tiêu đề trích lời, sự kiện cấp cao; câu phải chứa từ khóa thông điệp."""
    rx, out, seen = _THRX[tid], [], set()
    for prio in (1, 0):
        for e in sorted(events, key=lambda e: (-e["level"], -e["n"])):
            for pr, qt in e["qs"]:
                if pr == prio and rx.search(qt.lower()) and qt[:40] not in seen:
                    seen.add(qt[:40])
                    out.append(dict(e, quote=qt.strip(" '\"“”")))
                    break
            if len(out) >= k:
                return out
    return out


def major_events(rows, arts, ts_start, ts_split, ts_end):
    out = []
    for key, lab, rx in MAJOR:
        crx = re.compile(rx)
        days = Counter(datetime.fromtimestamp(r["ts"], VN_TZ).date() for r in rows if crx.search(r["title"]))
        if not days:
            continue
        thr = max(4, sorted(days.values())[-1] * 0.25)
        hot = sorted(d for d, c in days.items() if c >= thr)
        occ = []
        for d in hot:
            if occ and (d - occ[-1][1]).days <= 3:
                occ[-1][1] = d
            else:
                occ.append([d, d])
        for d0, d1 in occ:
            t0 = datetime.combine(d0, datetime.min.time(), VN_TZ).timestamp() - 86400
            t1 = datetime.combine(d1, datetime.min.time(), VN_TZ).timestamp() + 2 * 86400
            n = sum(c for d, c in days.items() if d0 <= d <= d1)
            mine = [a for a in arts if t0 <= a["ts"] < t1 and (crx.search(a["title"]) or crx.search(a["body"][:1500]))]
            out.append(dict(key=key, label=lab, d0=d0, d1=d1, n=n, per="P1" if t0 + 86400 < ts_split else "P2",
                            present=bool(mine), speech=any(len(a["speech"]) > 60 for a in mine),
                            sample=(mine[0]["title"], mine[0]["url"]) if mine else None))
    out.sort(key=lambda x: x["d0"])
    return out


# ---------- HTML ----------
from .infra import CSS as _CSS  # noqa: E402

CSS = _CSS + """
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:10px 0}
.kpi div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.kpi b{font-size:20px;display:block}.up{color:#0a7d32}.dn{color:#c0392b}.eq{color:var(--mut)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .up{color:#5fd38a}:root:not([data-theme="light"]) .dn{color:#ff8a7a}}
.q{font-size:13px;margin:3px 0}.q i{color:var(--mut)}svg text{fill:var(--mut);font-size:10px}
.pill{display:inline-block;font-size:11px;border:1px solid var(--line);border-radius:10px;padding:0 6px;margin:1px;color:var(--mut)}
.lv{font-weight:700}.lv5{color:#c0392b}.lv4{color:#d35400}
"""
TYPE_LAB = dict((t, l) for t, l, _ in TYPES)
TYPE_LAB["khac"] = "Khác"
TH_LAB = dict((t, l) for t, l, _ in THEMES)


def _f(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _chg(a, b):
    if a == 0 and b == 0:
        return "<span class=eq>–</span>"
    if a == 0:
        return "<span class=up>mới</span>"
    r = b / a
    cls, word = ("up", "tăng") if r >= 1.2 else ("dn", "giảm") if r <= 0.83 else ("eq", "giữ")
    return f"<span class={cls}>{'+' if r >= 1 else ''}{_f((r - 1) * 100, 0)}% · {word}</span>"


def _spark(vals, w=120, h=26):
    mx = max(vals) or 1
    bw = w / len(vals)
    return (f"<svg width={w} height={h} viewBox='0 0 {w} {h}' role=img>" + "".join(
        f"<rect x={i * bw + 1:.1f} y={h - 2 - (h - 4) * v / mx:.1f} width={bw - 2:.1f} height={(h - 4) * v / mx + 0.5:.1f} "
        f"fill='{'var(--acc)' if i >= len(vals) - 5 else 'var(--bar)'}' rx=1></rect>" for i, v in enumerate(vals)) + "</svg>")


def _bars(monthly, split_month):
    """Bài có tên trong tiêu đề / 1.000 bài của 3 báo, theo tháng: Tô Lâm (cột) + Thủ tướng, Chủ tịch QH (đường)."""
    W, Hh, pad = 680, 220, 30
    n = len(monthly)
    vals = {cid: [m["ctrl"][cid] * 1000 / max(1, m["total"]) for m in monthly] for cid in ("tl", "tt", "qh")}
    mx = max(max(v) for v in vals.values()) * 1.1 or 1
    bw = (W - pad) / n
    y = lambda v: Hh - 20 - (Hh - 40) * v / mx
    out = [f"<svg viewBox='0 0 {W} {Hh}' width='100%' role=img aria-label='Tần suất xuất hiện theo tháng'>"]
    for k in range(0, 5):
        v = mx * k / 4
        out.append(f"<line x1={pad} x2={W} y1={y(v):.1f} y2={y(v):.1f} stroke='var(--line)'/>"
                   f"<text x=0 y={y(v) + 3:.1f}>{_f(v, 1)}</text>")
    for i, m in enumerate(monthly):
        v = vals["tl"][i]
        x = pad + i * bw
        out.append(f"<rect x={x + 4:.1f} y={y(v):.1f} width={bw - 8:.1f} height={Hh - 20 - y(v):.1f} rx=2 "
                   f"fill='{'var(--acc)' if m['month'] >= split_month else 'var(--bar)'}'><title>{m['month']}: {_f(v, 2)}‰</title></rect>"
                   f"<text x={x + bw / 2 - 8:.1f} y={Hh - 5}>T{int(m['month'][5:])}</text>")
    for cid, col, dash in (("tt", "#d35400", ""), ("qh", "#7f8c8d", "4 3")):
        pts = " ".join(f"{pad + i * bw + bw / 2:.1f},{y(v):.1f}" for i, v in enumerate(vals[cid]))
        out.append(f"<polyline points='{pts}' fill=none stroke='{col}' stroke-width=2 stroke-dasharray='{dash}'/>")
    out.append("</svg><div class=mut>Cột: số bài có tên ông Tô Lâm trong tiêu đề trên 1.000 bài của 3 báo "
               "(cột đậm: giai đoạn 2). Đường cam: Thủ tướng; đường xám đứt: Chủ tịch Quốc hội.</div>")
    return "".join(out)


def render(res, start, split, end, notes=""):
    e = H.escape
    P1, P2 = res["P"]["P1"], res["P"]["P2"]
    sm = split[:7]
    d = lambda ts: datetime.fromtimestamp(ts, VN_TZ).strftime("%d/%m")
    p1lab = f"Giai đoạn 1 ({datetime.fromisoformat(start):%d/%m}–{datetime.fromisoformat(split).replace(day=1).fromordinal(datetime.fromisoformat(split).toordinal() - 1):%d/%m})"
    p2lab = f"Giai đoạn 2 ({datetime.fromisoformat(split):%d/%m}–{datetime.fromisoformat(end):%d/%m})"
    out = [f"<title>Thông điệp Tô Lâm 2026</title><style>{CSS}</style><main>",
           "<h1>Ông Tô Lâm năm 2026: thông điệp và mức độ xuất hiện</h1>",
           f"<div class=mut>Kho đầy đủ {_f(P1['tot'] + P2['tot'], 0)} bài của Tuổi Trẻ, Thanh Niên, VTV từ {start} đến {end} "
           f"(sitemap lưu trữ) · {_f(P1['arts'] + P2['arts'], 0)} bài về ông Tô Lâm, gộp thành {_f(P1['events'] + P2['events'], 0)} sự kiện · "
           f"{p1lab} so với {p2lab}</div>"]
    if notes:
        out.append(f"<div class='card notes'>{notes}</div>")

    def row(lab, a, b, fmt=lambda v: _f(v, 1)):
        return f"<tr><td>{lab}</td><td class=n>{fmt(a)}</td><td class=n>{fmt(b)}</td><td class=n>{_chg(a, b)}</td></tr>"

    pm = lambda P, k: P[k] / P["months"]
    out.append("<h2>1. Mức độ xuất hiện</h2>")
    out.append(_bars(res["monthly"], sm))
    out.append(f"<div class=tw><table><tr><th>Chỉ số (bình quân mỗi tháng)</th><th class=n>GĐ1</th><th class=n>GĐ2</th><th class=n>Thay đổi</th></tr>")
    out.append(row("Bài báo về ông Tô Lâm", pm(P1, "arts"), pm(P2, "arts"), lambda v: _f(v, 0)))
    out.append(row("… trên 1.000 bài của 3 báo (‰)", P1["arts"] * 1000 / P1["tot"], P2["arts"] * 1000 / P2["tot"], lambda v: _f(v, 2)))
    out.append(row("Sự kiện, hoạt động (đã gộp bài trùng)", pm(P1, "events"), pm(P2, "events")))
    out.append(row("Sự kiện có phát biểu, chỉ đạo", pm(P1, "speech"), pm(P2, "speech")))
    out.append(row("Sự kiện lớn (mức 4–5)", pm(P1, "big"), pm(P2, "big")))
    out.append(row("Sự kiện lớn có phát biểu", pm(P1, "big_speech"), pm(P2, "big_speech")))
    for tid, lab, _ in TYPES:
        out.append(row("· " + lab, P1["types"][tid] / P1["months"], P2["types"][tid] / P2["months"]))
    out.append(row("Tỷ lệ ngày có tên trên tiêu đề (%)", P1["present_days"] * 100 / P1["days"], P2["present_days"] * 100 / P2["days"], lambda v: _f(v, 0)))
    for P, lab in ((P1, "GĐ1"), (P2, "GĐ2")):
        g = P["gap"]
    out.append(f"<tr><td>Quãng vắng dài nhất (ngày không có tên trên tiêu đề)</td><td class=n>{P1['gap'][0]}</td>"
               f"<td class=n>{P2['gap'][0]}</td><td class=n class=mut>{P1['gap'][1]:%d/%m}→ · {P2['gap'][1]:%d/%m}→</td></tr>")
    for cid, lab, _ in res["CTRL"][1:]:
        out.append(row(f"Đối chứng: {lab} (bài có tên trên tiêu đề/tháng)", P1["ctrl"][cid] / P1["months"], P2["ctrl"][cid] / P2["months"], lambda v: _f(v, 0)))
    out.append("</table></div>")

    out.append("<h2>2. Có mặt ở các sự kiện lớn của cả nước</h2><div class=tw><table><tr><th>Sự kiện</th><th>Thời gian</th>"
               "<th class=n>Bài 3 báo</th><th>Ông Tô Lâm</th></tr>")
    for m in res["major"]:
        st = ("<b>dự, phát biểu</b>" if m["speech"] else "dự / được nhắc" if m["present"] else "<span class=dn>không thấy trong tin</span>")
        smp = f"<div class=mut><a href='{e(m['sample'][1])}'>{e(m['sample'][0][:100])}</a></div>" if m["sample"] else ""
        dd = f"{m['d0']:%d/%m}" + (f"–{m['d1']:%d/%m}" if m["d1"] != m["d0"] else "")
        out.append(f"<tr><td>{e(m['label'])} <span class=pill>{'GĐ1' if m['per'] == 'P1' else 'GĐ2'}</span></td><td>{dd}</td>"
                   f"<td class=n>{m['n']}</td><td>{st}{smp}</td></tr>")
    out.append("</table></div>")

    out.append("<h2>3. Các thông điệp chính và độ nhấn mạnh</h2>")
    out.append("<p class=mut>Tỷ trọng = % sự kiện có phát biểu của ông nhắc tới thông điệp (trong tiêu đề trích lời hoặc các câu "
               "\"Tổng Bí thư nhấn mạnh/yêu cầu/chỉ đạo…\" trong bài). Cường độ = số lần lặp từ khóa của thông điệp trên 1.000 từ lời phát biểu. "
               "Sắp xếp theo mức độ quan trọng: tỷ trọng có trọng số theo cấp độ sự kiện, cả năm.</p>")
    order = sorted(THEMES, key=lambda t: -(P1["themes"][t[0]]["wshare"] + P2["themes"][t[0]]["wshare"]))
    out.append("<div class=tw><table><tr><th>#</th><th>Thông điệp</th><th class=n>GĐ1</th><th class=n>GĐ2</th><th class=n>Tỷ trọng</th>"
               "<th class=n>Cường độ</th><th class=hide-s>Theo tháng</th></tr>")
    for i, (tid, lab, _) in enumerate(order, 1):
        a, b = P1["themes"][tid], P2["themes"][tid]
        sp = _spark([m["themes"][tid] / max(1, m["speech"]) for m in res["monthly"]])
        out.append(f"<tr><td class=rk>{i}</td><td><a href='#t-{tid}'>{e(lab)}</a></td><td class=n>{_f(a['share'] * 100, 0)}%</td>"
                   f"<td class=n>{_f(b['share'] * 100, 0)}%</td><td class=n>{_chg(a['share'], b['share'])}</td>"
                   f"<td class=n>{_chg(a['hits'], b['hits'])}</td><td class=hide-s>{sp}</td></tr>")
    out.append("</table></div>")
    for tid, lab, _ in order:
        a, b = P1["themes"][tid], P2["themes"][tid]
        out.append(f"<details id='t-{tid}'><summary><b>{e(lab)}</b><span class=mut>GĐ1 {_f(a['share'] * 100, 0)}% "
                   f"({a['n']} sự kiện) → GĐ2 {_f(b['share'] * 100, 0)}% ({b['n']} sự kiện)</span></summary><div style='padding:0 14px 10px'>")
        for P, plab in ((a, "GĐ1"), (b, "GĐ2")):
            out.append(f"<div class=b><b>{plab}</b></div>")
            for ev in P["quotes"]:
                out.append(f"<div class=q>“{e(ev['quote'])}” <i>· {d(ev['ts'])} · mức {ev['level']} · "
                           f"<a href='{e(ev['url'])}'>nguồn</a></i></div>")
            if not P["quotes"]:
                out.append("<div class=q><i>Không có tiêu đề trích lời trực tiếp.</i></div>")
        out.append("</div></details>")

    out.append("<h2>4. Sự kiện quan trọng nhất mỗi giai đoạn</h2>")
    for P, plab in ((P1, p1lab), (P2, p2lab)):
        out.append(f"<h3 style='margin-top:14px'>{plab}</h3><ol>")
        for ev in P["top"]:
            tags = "".join(f"<span class=pill>{e(TH_LAB[t].split(',')[0])}</span>"
                           for t, _ in sorted(ev["themes"].items(), key=lambda x: -x[1])[:4])
            out.append(f"<li><span class='lv lv{ev['level']}'>Mức {ev['level']}</span> · {d(ev['ts'])} · "
                       f"<a href='{e(ev['url'])}'>{e(ev['title'])}</a> <span class=mut>· {TYPE_LAB[ev['type']]} · "
                       f"{ev['n']} bài{' · có phát biểu' if ev['speech'] else ''}</span><div>{tags}</div></li>")
        out.append("</ol>")
    out.append("<h2>Phương pháp và giới hạn</h2><ul class=mut>"
               "<li>Dữ liệu: sitemap lưu trữ đầy đủ của Tuổi Trẻ, Thanh Niên, VTV (mọi bài đã đăng), không phụ thuộc kết quả tìm kiếm. "
               "Bài về ông Tô Lâm: tiêu đề hoặc chú thích ảnh có tên ông, hoặc chức danh \"Tổng Bí thư\" / \"Tổng Bí thư, Chủ tịch nước\" "
               "đứng một mình (đã loại tổng bí thư nước ngoài, \"nguyên/cố Tổng Bí thư\").</li>"
               "<li>Thông điệp được đo trên lời phát biểu được báo trích dẫn, bằng bộ từ khóa; đây là đo tần suất nhắc lại, "
               "không thay thế việc đọc nguyên văn.</li>"
               "<li>Giai đoạn 2 tính đến ngày lấy dữ liệu; các chỉ số đều quy về bình quân mỗi tháng để so sánh.</li>"
               "<li>Số bài phản ánh cách báo chí đưa tin (lịch sự kiện, mùa họp), không đo trực tiếp lịch công tác.</li></ul>")
    out.append("</main>")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="news_crawler.leader")
    ap.add_argument("--from", dest="start", default="2026-01-01")
    ap.add_argument("--split", default="2026-06-01")
    ap.add_argument("--to", dest="end", default=datetime.now(VN_TZ).strftime("%Y-%m-%d"))
    ap.add_argument("--out", default="reports/to-lam-2026.html")
    ap.add_argument("--notes")
    ap.add_argument("--json")
    o = ap.parse_args(argv)
    rows, sel = collect(o.start, o.end)
    print(len(rows), "bài;", len(sel), "bài về", NAME)
    bodies = fetch_all(sel)
    res = analyze(rows, sel, bodies, o.start, o.split, o.end)
    notes = open(o.notes, encoding="utf-8").read() if o.notes else ""
    os.makedirs(os.path.dirname(o.out) or ".", exist_ok=True)
    open(o.out, "w", encoding="utf-8").write(render(res, o.start, o.split, o.end, notes))
    if o.json:
        P = res["P"]
        slim = dict(monthly=[dict(m, types=dict(m["types"]), themes=dict(m["themes"])) for m in res["monthly"]],
                    P={p: dict({k: v for k, v in P[p].items() if k not in ("top", "themes", "gap", "types")},
                               types=dict(P[p]["types"]), gap=[P[p]["gap"][0], str(P[p]["gap"][1]), str(P[p]["gap"][2])],
                               themes={t: dict(share=x["share"], hits=x["hits"], wshare=x["wshare"], n=x["n"],
                                               quotes=[(q["quote"], datetime.fromtimestamp(q["ts"], VN_TZ).strftime("%d/%m"), q["level"]) for q in x["quotes"]])
                                       for t, x in P[p]["themes"].items()},
                               top=[(datetime.fromtimestamp(ev["ts"], VN_TZ).strftime("%d/%m"), ev["level"], ev["type"], ev["n"], ev["speech"],
                                     ev["title"], sorted(ev["themes"])) for ev in P[p]["top"]]) for p in P},
                    major=[dict(m, d0=str(m["d0"]), d1=str(m["d1"])) for m in res["major"]],
                    events=[(datetime.fromtimestamp(ev["ts"], VN_TZ).strftime("%Y-%m-%d"), ev["level"], ev["type"], ev["n"],
                             ev["speech"], ev["title"], ev["quote"], dict(ev["themes"])) for ev in res["events"]])
        json.dump(slim, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, default=str)
    print("->", o.out)


if __name__ == "__main__" and not os.environ.get("LEADER_FETCH_ONLY"):
    main()
