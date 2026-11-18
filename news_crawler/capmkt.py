"""Thị trường vốn Việt Nam: huy động vốn lớn, phát hành trái phiếu, chào bán cổ phần / IPO, quỹ đầu tư rót vốn.

Chỉ áp dụng cho tin về Việt Nam. Thứ tự ưu tiên (sau M&A): phát hành trái phiếu > chào bán cổ phần > quỹ đầu tư > huy động vốn.
Tin thị trường trái phiếu chung (đáo hạn, chậm trả, quy định) giữ ở topic "trai_phieu".
"""
import re

from .regions import detect_region, is_vietnam

CAP_TOPICS = [
    dict(id="vn_funding", label="Huy động vốn lớn - vay hợp vốn, tăng vốn", weight=1.4, spec=0),
    dict(id="tp_phat_hanh", label="Doanh nghiệp phát hành trái phiếu", weight=1.4, spec=0),
    dict(id="chao_ban", label="Chào bán cổ phần - IPO - phát hành riêng lẻ", weight=1.4, spec=0),
    dict(id="quy_vn", label="Quỹ đầu tư rót vốn vào Việt Nam", weight=1.4, spec=0),
]
CAP_IDS = [t["id"] for t in CAP_TOPICS]

# Truy vấn Google News riêng: (truy vấn, ngôn ngữ)
CAP_QUERIES = [(q, "vi") for q in [
    "vay hợp vốn", "khoản vay quốc tế ngân hàng", "IFC ngân hàng Việt Nam", "ADB tài trợ", "huy động vốn tập đoàn",
    "tăng vốn điều lệ ngân hàng", "phát hành trái phiếu", "huy động thành công trái phiếu", "lô trái phiếu",
    "chào bán trái phiếu ra công chúng", "trái phiếu doanh nghiệp", "chậm trả lãi trái phiếu", "chào bán cổ phiếu",
    "phát hành riêng lẻ cổ phiếu", "IPO", "đấu giá cổ phần", "chào bán cổ phần", "quỹ ngoại", "quỹ đầu tư rót vốn",
    "Dragon Capital", "VinaCapital", "Mekong Capital", "quỹ đầu tư mạo hiểm", "startup Việt gọi vốn",
    "quỹ ETF cơ cấu"]] + [(q, "en") for q in [
    "Vietnam syndicated loan", "Vietnamese bank loan IFC", "Vietnam bond issuance", "Vietnam IPO",
    "Vietnam private equity investment", "Vietnam startup raises", "Vietnam fund invests"]]

_RULES = [
    ("tp_phat_hanh", re.compile(
        r"phát hành (?:thành công )?(?:\d[\d.,]*\s*(?:tỷ|nghìn tỷ|triệu)[^,;:]{0,20})?(?:lô )?trái phiếu|"
        r"huy động (?:thành công )?(?:\d[\d.,]*\s*(?:tỷ|nghìn tỷ|triệu)[^,;:]{0,20}\s)?(?:từ |qua |bằng )?(?:kênh )?trái phiếu|"
        r"chào bán (?:\d[\d.,]*\s*(?:tỷ|triệu)[^,;:]{0,20})?trái phiếu|lô trái phiếu|trái phiếu .{0,20}(?:chảy|về)|"
        r"(?:dự kiến|kế hoạch|muốn|sắp|tiếp tục) phát hành .{0,25}trái phiếu|"
        r"\b(?:bond|notes?) (?:issue|issuance|offering|sale)\b|\bissues? .{0,20}bonds?\b|\bprices? .{0,20}bonds?\b", re.I)),
    ("chao_ban", re.compile(
        r"chào bán (?:thêm |hơn |gần )?(?:\d[\d.,]*\s*(?:triệu|tỷ) )?(?:cổ phiếu|cổ phần|cp\b)|"
        r"phát hành (?:thêm |hơn |gần )?(?:\d[\d.,]*\s*(?:triệu|tỷ) )?(?:cổ phiếu|cổ phần|cp\b)(?! quỹ)|"
        r"phát hành riêng lẻ|\bIPO\b|niêm yết lần đầu|chào sàn|lên sàn|đấu giá (?:\d[\d.,]*\s*(?:triệu) )?cổ phần|"
        r"cổ phần hóa|quyền mua cổ phiếu|tăng vốn (?:điều lệ )?(?:qua|bằng) (?:phát hành|chào bán)|"
        r"\b(?:share|stock) (?:sale|offering)\b|\blisting\b", re.I)),
    ("quy_vn", re.compile(
        r"quỹ (?:ngoại|đầu tư|ETF|mạo hiểm|PE|tư nhân|ngoại)\b.{0,40}(?:rót|đầu tư|mua|gom|chi|nâng sở hữu|thoái|bán|giải ngân|"
        r"cổ đông lớn|đăng ký)|"
        r"(?:rót|đổ) (?:vốn|tiền) vào .{0,30}(?:startup|công ty|doanh nghiệp)|vòng gọi vốn|gọi vốn (?:thành công|Series|vòng)|"
        r"\bSeries [A-E]\b|Dragon Capital|VinaCapital|Mekong Capital|Warburg Pincus|Pyn Elite|Vietnam Holding|"
        r"Templeton|\bVEIL\b|Kusto|Jaccar|Openspace|Do Ventures|ThinkZone|\bTPG\b|Bain Capital|"
        r"\bprivate equity\b|\bventure capital\b|\braises? \$|\bfunding round\b|\bETF\b.{0,30}(?:cơ cấu|mua|bán|giải ngân)", re.I)),
    ("vn_funding", re.compile(
        r"vay hợp vốn|khoản vay (?:hợp vốn|quốc tế|nước ngoài|xanh|bền vững|ưu đãi|\d)|tín dụng (?:xanh |hợp vốn )?từ (?:IFC|ADB|JBIC|"
        r"DFC|Proparco|FMO|AIIB|WB|Ngân hàng Thế giới)|\bIFC\b|\bADB\b.{0,30}(?:tài trợ|cho vay|khoản vay|vay)|\bJBIC\b|\bProparco\b|"
        r"\bFMO\b|\bDEG\b|huy động (?:thành công )?\d[\d.,]*\s*(?:triệu|tỷ) USD|tăng vốn điều lệ|bơm vốn|tăng vốn lên|"
        r"\bsyndicated loan\b|\bloan (?:from|facility)\b|\bsecures? .{0,30}(?:loan|financing)\b|\bterm loan\b", re.I)),
]
_NOT = re.compile(r"cổ phiếu quỹ|mua lại cổ phiếu|lừa đảo|mạo danh|giả mạo|tin đồn|cảnh báo", re.I)


def _is_vn(a):
    t, d = a["title"], a.get("desc") or ""
    if is_vietnam(t, d):
        return True
    if a.get("lang", "vi") == "vi":
        region, _ = detect_region(t, "")
        return region is None  # báo Việt, tiêu đề không nêu nước ngoài -> tin trong nước
    return False


def classify_cap(a):
    """-> id mục thị trường vốn hoặc None."""
    t = a["title"]
    if _NOT.search(t) or not _is_vn(a):
        return None
    for tid, rx in _RULES:
        if rx.search(t):
            return tid
    return None


def assign_cap(a, topic_by_id):
    """Tin thị trường vốn VN -> mục tương ứng; chủ đề cũ thành nhãn phụ. Trả về True nếu đã gán."""
    if a.get("topic") in ("hien_tang",) or str(a.get("topic", "")).startswith("ma_"):
        return False
    tid = classify_cap(a)
    if not tid:
        return False
    old = a.get("topic")
    if old and old in topic_by_id and old != tid and not a.get("sub"):
        a["sub"] = topic_by_id[old]["label"]
    a["topic"] = tid
    return True
