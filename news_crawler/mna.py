"""Thương vụ M&A: nhận diện tin mua bán - sáp nhập, chia theo khu vực, ước giá trị thương vụ.

Tin được nhận diện là M&A được chuyển sang mục "Thương vụ M&A · <khu vực>" (chủ đề gốc thành nhãn phụ).
Khu vực: Việt Nam, Đông Nam Á, châu Á & Trung Đông, châu Âu, châu Mỹ.
"""
import re

from .regions import TITANS, detect_region, is_vietnam

MNA_TOPICS = [
    dict(id="ma_vn", label="M&A · Việt Nam", weight=1.4, spec=0),
    dict(id="ma_sea", label="M&A · Đông Nam Á", weight=1.3, spec=0),
    dict(id="ma_asia", label="M&A · Châu Á & Trung Đông", weight=1.3, spec=0),
    dict(id="ma_eu", label="M&A · Châu Âu", weight=1.3, spec=0),
    dict(id="ma_am", label="M&A · Châu Mỹ", weight=1.3, spec=0),
]
MNA_IDS = [t["id"] for t in MNA_TOPICS]

# Truy vấn Google News riêng cho M&A: (truy vấn, ngôn ngữ)
MNA_QUERIES = [(q, "vi") for q in [
    "M&A", "thương vụ M&A", "mua lại cổ phần", "thâu tóm", "chuyển nhượng vốn", "thoái vốn", "chào mua công khai",
    "về tay nước ngoài", "mua lại công ty", "sáp nhập ngân hàng"]] + [(q, "en") for q in [
    "acquisition billion", "agrees to acquire", "merger agreement", "takeover bid", "private equity buyout",
    "to buy stake", "Vietnam acquisition", "Singapore acquisition", "Indonesia acquisition", "Malaysia acquisition",
    "Thailand acquisition", "Philippines acquisition", "Japan acquisition", "Korea acquisition", "India acquisition",
    "China acquisition", "Hong Kong takeover", "Saudi acquisition", "UAE acquisition", "UK takeover",
    "Europe merger", "Germany acquisition", "France acquisition", "US merger deal", "Canada acquisition",
    "Brazil acquisition", "Latin America acquisition"]]

_DEAL_VI = re.compile(
    r"\bM&A\b|mua lại(?! cổ phiếu quỹ| trái phiếu| nhà| xe| căn| đất| hàng)|thâu tóm|"
    r"sáp nhập (?:công ty|ngân hàng|doanh nghiệp|hai|các công ty|vào [A-ZĐ]|với [A-ZĐ])|"
    r"hợp nhất (?:công ty|ngân hàng|doanh nghiệp|hai)|"
    r"chuyển nhượng (?:\d+(?:[.,]\d+)?\s?% )?(?:vốn|cổ phần|phần vốn|toàn bộ|dự án)|thoái (?:toàn bộ )?vốn|"
    r"mua (?:thêm )?(?:\d+(?:[.,]\d+)?\s?% )?(?:cổ phần|vốn|phần vốn)|nắm quyền kiểm soát|chào mua công khai|mua trọn|"
    r"về tay (?:nước ngoài|ngoại|tập đoàn|quỹ|người [A-ZĐ]|đại gia|ông lớn)|thương vụ (?:mua|bán|M&A|thâu tóm)|"
    r"bán (?:lại )?(?:mảng|công ty con|\d+(?:[.,]\d+)?\s?% cổ phần|toàn bộ cổ phần|toàn bộ vốn)|"
    r"(?:đề nghị|lời) mua lại|liên doanh với|"
    r"mua (?:lại )?(?:danh mục|công ty|doanh nghiệp|mảng|nhà máy|chuỗi|thương hiệu|ngân hàng|dự án)")
_DEAL_EN = re.compile(
    r"\bacquir(?:e|es|ed|ing)\b|\bacquisitions?\b|\bto buy\b|\bbuys\b|\bbuying\b|\bbought\b|\bbuyouts?\b|\bmergers?\b|"
    r"\bmerg(?:e|es|ed|ing)\b|\btakeovers?\b|\btake over\b|\bbids? for\b|\bdeal for\b|\bstake in\b|\bstake sale\b|"
    r"\bsells? (?:its |a |the |\w+ )?(?:stake|unit|business|division|arm|subsidiary)\b|\bdivest|\bspin[- ]?offs?\b|"
    r"\bcarve[- ]?outs?\b|\bin talks to (?:buy|acquire|merge|sell)\b|\bagree(?:s|d)? to (?:buy|acquire|sell|merge)\b|"
    r"\bnod for .* deal\b|\bto sell\b .*\b(?:to|unit|stake)\b", re.I)
_NOT_DEAL = re.compile(
    r"buy ?back|share repurchase|buys? (?:back )?(?:shares|stock)\b|(?:stocks?|shares) to buy|should you buy|buy rating|"
    r"buy the dip|\bbuys? [\d,.]+ (?:shares|cổ phiếu)|insider|picks up .* stock|tickets?|buy now|buy a (?:home|house|car)|"
    r"homebuyers?|draft pick|\bNFL\b|\bNBA\b|\bMLB\b|transfer fee|cầu thủ|bóng đá|chuyển nhượng cầu thủ|"
    r"cổ phiếu quỹ|sáp nhập (?:tỉnh|xã|phường|huyện|trường|bộ|đơn vị hành chính)|mua lại xe|"
    r"Ukraine|annex|sáp nhập Liên bang Nga|lãnh thổ|buying opportunit|buy equities|\bbuys? more\b|\bbought by\b|"
    r"buy, sell,? or hold|whether to buy|not buying|too late to buy|buys? (?:\w+ )?(?:stock|batteries)\b|"
    r"treasury shares|passive stake|pares stake|land buys|takeover (?:night|chatter)|gta|take over if|"
    r"mua lại (?:trước hạn|cổ phiếu|\d)|mua lại .*trái phiếu|ESOP|danh hiệu|cũ nát|"
    r"\bacquisition corp\b|options to", re.I)
# tiếng Anh: phải có dấu hiệu doanh nghiệp/tài chính để tránh tin thể thao, đời sống
_CORP = re.compile(r"\$|€|£|¥|\bbillion\b|\bmillion\b|\bbn\b|\bcompany\b|\bfirm\b|\bgroup\b|\bbank\b|\bfunds?\b|"
                   r"\bholdings?\b|\binc\b|\bcorp\b|\bplc\b|\bunit\b|\bstake\b|\bbusiness\b|\bstartup\b|\bmaker\b|"
                   r"\bretailer\b|\binsurer\b|\blender\b|\boperator\b|\bdeveloper\b|\bbrand\b|\bchain\b|\bprivate equity\b|"
                   r"\bshareholders?\b|\bboard\b|\bregulators?\b|\bantitrust\b|\bportfolio\b|\bassets?\b", re.I)
_TITAN_ANY = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for v in TITANS.values() for n in sorted(v, key=len, reverse=True))
                        + r")(?![\w])")


def is_deal(title, lang="vi"):
    if not title or _NOT_DEAL.search(title):
        return False
    if _DEAL_VI.search(title):
        return True
    if _DEAL_EN.search(title):
        return bool(_CORP.search(title) or _TITAN_ANY.search(title) or lang == "vi")
    return False


_SEA = re.compile(r"singapore|xin-?ga-?po|indonesia|jakarta|malaysia|kuala lumpur|thái lan|thailand|bangkok|"
                  r"philippines|philippine|manila|myanmar|campuchia|cambodia|\blào\b|\blaos\b|brunei|đông nam á|"
                  r"southeast asia|\basean\b|Temasek|\bGIC\b|\bDBS\b|OCBC|\bUOB\b|Grab|Sea Ltd|CapitaLand|Keppel|"
                  r"Petronas|Maybank|CIMB|Ayala|SM Investments|Charoen Pokphand|\bCP Group\b|ThaiBev|"
                  r"Central Group|Gojek|GoTo|Astra", re.I)
_AMERICAS = re.compile(r"canada|canadian|brazil|brasil|mexico|mexican|argentina|chile|colombia|peru|latin america|"
                       r"latam|toronto|são paulo|sao paulo", re.I)
_MAP = {"r_my": "ma_am", "r_eu": "ma_eu", "r_sg": "ma_sea", "r_tq": "ma_asia", "r_hk": "ma_asia", "r_gulf": "ma_asia",
        "r_asia": "ma_asia"}


# tên riêng không dấu kiểu nước ngoài ở đầu tiêu đề tiếng Việt ("Argenx mua lại...", "NTT bán...")
_FOREIGN_NAME = re.compile(r"^(?:Cổ phiếu\s+)?(?:[A-Z][A-Za-z&.\-]+\s?){1,3}(?=\s(?:mua|bán|thâu tóm|sáp nhập|muốn|chi|ký|công bố|"
                           r"tăng|giảm|lên kế hoạch|báo cáo|hoàn tất))")
_VN_SHORT = re.compile(r"\bViệt\b|người Việt|doanh nghiệp Việt|thương hiệu Việt|hàng Việt")


def _vn_company(title):
    from .companies import find_company
    from .topics import find_vn100
    co = find_company(title, "vi")
    return bool((co and co[0] == "co_vn") or find_vn100(title))


def deal_region(title, desc="", lang="vi"):
    if is_vietnam(title, "") or _VN_SHORT.search(title) or (lang == "vi" and _vn_company(title)):
        return "ma_vn"
    if _SEA.search(title):
        return "ma_sea"
    region, _ = detect_region(title, desc)
    if region:
        return _MAP.get(region, "ma_asia")
    if _AMERICAS.search(title):
        return "ma_am"
    # báo Việt, không nêu nước / tên riêng nước ngoài nào -> coi là thương vụ trong nước
    if is_vietnam(title, desc) or (lang == "vi" and not _FOREIGN_NAME.search(title)):
        return "ma_vn"
    return None


_USD = 26_300
_MONEY = re.compile(r"(?:US)?\$\s?(\d+(?:[.,]\d+)?)\s*(trillion|tn|billion|bn|b\b|million|mn|m\b)|"
                    r"(?:€|£)\s?(\d+(?:[.,]\d+)?)\s*(billion|bn|million|mn)|"
                    r"(\d+(?:[.,]\d+)?)\s*(tỷ USD|tỷ đô|triệu USD|nghìn tỷ đồng|nghìn tỷ|ngàn tỷ|tỷ đồng|tỷ Yên|tỷ yên)", re.I)


_NOT_SIZE = re.compile(r"dư nợ|nợ vay|nợ phải trả|tổng nợ|doanh thu|lợi nhuận|\blãi\b|\blỗ\b|vốn hóa|tài sản|"
                       r"revenue|profit|loss|debt of|market cap|AUM|assets under", re.I)


_AFTER_SIZE = re.compile(r"\s*(?:in )?(?:assets under management|AUM|in assets|tài sản quản lý)", re.I)


def deal_usd(title):
    """Giá trị thương vụ ước tính (triệu USD) theo số tiền lớn nhất trong tiêu đề, hoặc None."""
    best = None
    for m in _MONEY.finditer(title or ""):
        # số tiền là dư nợ / kết quả kinh doanh, không phải giá trị thương vụ
        if _NOT_SIZE.search((title or "")[max(0, m.start() - 25):m.start()]) or \
                _AFTER_SIZE.match((title or "")[m.end():m.end() + 30]):
            continue
        if m.group(1):
            v, u = float(m.group(1).replace(",", ".")), m.group(2).lower()
            v *= {"trillion": 1e6, "tn": 1e6, "billion": 1e3, "bn": 1e3, "b": 1e3}.get(u, 1)
        elif m.group(3):
            v, u = float(m.group(3).replace(",", ".")), m.group(4).lower()
            v *= 1.1 * (1e3 if u in ("billion", "bn") else 1)
        else:
            raw, u = m.group(5), m.group(6).lower()
            v = float(raw.replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw) else float(raw.replace(",", "."))
            if u in ("tỷ usd", "tỷ đô"):
                v *= 1e3
            elif u in ("nghìn tỷ đồng", "nghìn tỷ", "ngàn tỷ"):
                v *= 1e12 / _USD / 1e6
            elif u == "tỷ đồng":
                v *= 1e9 / _USD / 1e6
            elif u in ("tỷ yên",):
                v *= 1e9 / 150 / 1e6
        best = max(best or 0, v)
    return best


def assign_mna(a, topic_by_id):
    """Tin M&A -> mục M&A theo khu vực; chủ đề cũ thành nhãn phụ. Trả về True nếu đã gán."""
    if a.get("topic") in ("hien_tang",) or not is_deal(a["title"], a.get("lang", "vi")):
        return False
    region = deal_region(a["title"], a.get("desc") or "", a.get("lang", "vi"))
    if not region:
        return False
    old = a.get("topic")
    if old and old in topic_by_id and not a.get("sub"):
        a["sub"] = topic_by_id[old]["label"]
    a["topic"] = region
    a["deal_usd"] = deal_usd(a["title"])
    return True


def deal_bonus(usd):
    """Điểm cộng mức độ theo quy mô thương vụ."""
    if not usd:
        return 0
    return 1.5 if usd >= 10_000 else 1.0 if usd >= 1_000 else 0.5 if usd >= 100 else 0
