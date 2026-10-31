"""Phân tin quốc tế theo quốc gia / khu vực + nhận diện các "titans" (định chế tài chính, quỹ, tập đoàn lớn).

Tin nhắc tới Việt Nam vẫn nằm ở topic Việt Nam. Tin nước ngoài được đưa vào topic quốc gia,
topic gốc (lãi suất, công nghệ, địa chính trị...) giữ lại làm nhãn phụ.
Tin về một titan được xếp vào quốc gia đặt trụ sở của titan đó.
"""
import re

REGIONS = [
    dict(id="r_my", label="Mỹ", weight=1.4),
    dict(id="r_tq", label="Trung Quốc", weight=1.4),
    dict(id="r_hk", label="Hồng Kông", weight=1.3),
    dict(id="r_eu", label="Châu Âu - Anh", weight=1.3),
    dict(id="r_sg", label="Singapore", weight=1.3),
    dict(id="r_gulf", label="Dubai - UAE & vùng Vịnh", weight=1.3),
    dict(id="r_asia", label="Nhật - Hàn - Ấn & châu Á khác", weight=1.1),
]
for _r in REGIONS:
    _r["spec"] = 0

# Định chế tài chính, quỹ, ngân hàng, tập đoàn lớn -> khu vực đặt trụ sở (sửa/thêm tự do)
TITANS = {
    "r_my": ["JPMorgan", "J.P. Morgan", "Goldman Sachs", "Morgan Stanley", "Citigroup", "Citi", "Bank of America",
             "Wells Fargo", "BlackRock", "Blackstone", "KKR", "Apollo Global", "Carlyle", "Vanguard", "State Street",
             "Fidelity", "Berkshire Hathaway", "Warren Buffett", "Bridgewater", "Citadel", "Brookfield",
             "Apple", "Microsoft", "Nvidia", "Alphabet", "Google", "Amazon", "Meta", "Tesla", "Elon Musk", "Broadcom",
             "Oracle", "OpenAI", "Anthropic", "ExxonMobil", "Exxon", "Chevron", "Walmart", "Intel", "AMD", "Boeing",
             "Mastercard", "Netflix", "Qualcomm", "Micron", "Pfizer", "Eli Lilly", "UnitedHealth"],
    "r_eu": ["BNP Paribas", "HSBC", "Deutsche Bank", "UBS", "Barclays", "Santander", "Société Générale", "Societe Generale",
             "ING", "Allianz", "AXA", "Amundi", "Standard Chartered", "Lloyds", "NatWest", "UniCredit", "Intesa Sanpaolo",
             "LVMH", "ASML", "SAP", "Siemens", "Shell", "BP", "TotalEnergies", "Nestlé", "Nestle", "Novo Nordisk",
             "Volkswagen", "Mercedes-Benz", "BMW", "Airbus", "Norges Bank", "Norway's sovereign wealth fund",
             "quỹ tài sản quốc gia Na Uy", "EQT", "Roche", "Novartis", "Unilever", "AstraZeneca", "Stellantis"],
    "r_tq": ["ICBC", "China Construction Bank", "Agricultural Bank of China", "Bank of China", "China Investment Corp",
             "Alibaba", "Tencent", "BYD", "Huawei", "CATL", "Xiaomi", "PetroChina", "Sinopec", "Evergrande",
             "Country Garden", "Vanke", "DeepSeek", "ByteDance", "TikTok", "JD.com", "Pinduoduo", "PDD", "Baidu",
             "SMIC", "Ant Group", "Geely", "China Mobile"],
    "r_hk": ["HKEX", "Hang Seng", "AIA Group", "CK Hutchison", "Sun Hung Kai", "HKMA", "Cathay Pacific", "Jardine"],
    "r_sg": ["Temasek", "GIC", "DBS", "OCBC", "UOB", "Singtel", "Grab", "Sea Ltd", "CapitaLand", "Keppel",
             "Monetary Authority of Singapore", "Wilmar"],
    "r_gulf": ["Mubadala", "ADIA", "Abu Dhabi Investment Authority", "ADQ", "Emaar", "DP World", "Emirates NBD",
               "Investment Corporation of Dubai", "DIFC", "ADNOC", "G42", "MGX", "Saudi Aramco", "Aramco",
               "Public Investment Fund", "PIF", "Qatar Investment Authority", "QIA", "First Abu Dhabi Bank"],
    "r_asia": ["Toyota", "SoftBank", "MUFG", "Mitsubishi UFJ", "Mizuho", "SMBC", "Sumitomo Mitsui", "Sony",
               "Nippon Steel", "Nikkei 225", "Samsung", "SK Hynix", "Hyundai", "LG Electronics", "TSMC", "Foxconn",
               "Reliance Industries", "Tata", "Adani", "Infosys"],
}

# Từ khóa nhận diện quốc gia / khu vực (không phân biệt hoa thường)
_PRE = r"(?:của|tại|ở|sang|với|từ|nước|người|tổng thống|thủ tướng|chính phủ|kinh tế|thị trường|quốc hội|bộ trưởng|quân đội|" \
       r"phía|giới chức|chứng khoán|cổ phiếu|trái phiếu|doanh nghiệp|ngân hàng|thuế quan|hãng|tập đoàn|công ty|quỹ|lãnh đạo|" \
       r"đồng minh|đại sứ|ngoại trưởng|đặc phái viên|cử tri|bầu cử)"
KEYWORDS = {
    "r_my": [r"hoa kỳ", _PRE + r" mỹ(?![\w])", r"mỹ(?=[,.;:)]|\s+-\s)", r"mỹ và", r"phố wall", r"nhà trắng", r"washington",
             r"ông trump", r"donald trump", r"\bfed\b", r"cục dự trữ liên bang", r"lầu năm góc", r"thung lũng silicon",
             r"united states", r"\bu\.s\.", r"\bus\b(?= (?:economy|stocks|treasury|president|senate|house|election|military|"
             r"inflation|jobs|tariffs?|dollar|markets?|government|congress|officials?|trade))", r"america(?:n|ns)?\b",
             r"wall street", r"white house", r"pentagon", r"new york", r"california", r"texas", r"silicon valley",
             r"s&p 500", r"nasdaq", r"dow jones", r"federal reserve", r"midterms?\b", r"congress", r"senate"],
    "r_tq": [r"trung quốc", r"bắc kinh", r"thượng hải", r"thâm quyến", r"tập cận bình", r"nhân dân tệ", r"\bchina\b",
             r"chinese", r"beijing", r"shanghai", r"shenzhen", r"xi jinping", r"\byuan\b", r"\bpboc\b", r"renminbi"],
    "r_hk": [r"hồng kông", r"hong kong", r"hang seng", r"\bhkex\b", r"\bhkma\b"],
    "r_eu": [r"châu âu", r"liên minh châu âu", r"eurozone", r"\becb\b", r"\beu\b", r"european", r"\beurope\b",
             r"london", r"paris", r"berlin", r"brussels", r"britain", r"british", r"\buk\b", r"germany", r"german",
             r"france", r"french", r"italy", r"italian", r"spain", r"spanish", r"netherlands", r"dutch", r"switzerland",
             r"swiss", r"thụy sĩ", r"hà lan", r"tây ban nha", r"italia", r"vương quốc anh", r"luân đôn",
             _PRE + r" (?:đức|pháp(?! luật| lý| nhân| chế| quyền| định| điển| y)|anh quốc|italy|ý)(?![\w])",
             r"thủ tướng merz", r"tổng thống macron", r"macron", r"merz", r"starmer", r"lagarde", r"von der leyen"],
    "r_sg": [r"singapore", r"xin-?ga-?po"],
    "r_gulf": [r"dubai", r"\buae\b", r"abu dhabi", r"emirates", r"tiểu vương quốc ả rập", r"ả rập xê út", r"saudi",
               r"qatar", r"doha", r"vùng vịnh", r"gulf states?", r"riyadh"],
    "r_asia": [r"nhật bản", r"tokyo", r"\bjapan", r"hàn quốc", r"seoul", r"\bkorea", r"ấn độ", r"\bindia", r"new delhi",
               r"đài loan", r"taiwan", r"indonesia", r"thái lan", r"thailand", r"malaysia", r"philippines", r"úc\b",
               r"australia"],
}
_KW_RX = {k: re.compile("|".join(v), re.IGNORECASE) for k, v in KEYWORDS.items()}
_TITAN_RX = {}
_TITAN_NAME = {}
for _rid, _names in TITANS.items():
    for _n in _names:
        _TITAN_NAME[_n] = (_rid, _n)
    # tên riêng -> khớp đúng chữ hoa để tránh nhầm từ thường (apple, shell, grab...)
    _TITAN_RX[_rid] = re.compile(
        r"(?<![\w])(?:" + "|".join(re.escape(n) for n in sorted(_names, key=len, reverse=True)) + r")(?![\w])")

VN_RX = re.compile(r"việt nam|vietnam|vietnamese|\bvn\b|tp\.?\s?hcm|hà nội|hanoi|ho chi minh|đà nẵng|"
                   r"hải phòng|trong nước|chính phủ việt|bộ chính trị|quốc hội việt", re.IGNORECASE)

REGION_BY_ID = {r["id"]: r for r in REGIONS}
REGION_IDS = [r["id"] for r in REGIONS]


def find_titans(text):
    """-> list[(region_id, tên)] các titan được nhắc tới."""
    out = []
    for rid, rx in _TITAN_RX.items():
        for m in rx.finditer(text):
            item = _TITAN_NAME.get(m.group(0), (rid, m.group(0)))
            if item not in out:
                out.append(item)
    return out


def detect_region(title, desc):
    """-> (region_id | None, [tên titan])"""
    lead = (desc or "")[:600]
    score = {}
    for rid, rx in _KW_RX.items():
        s = 2 * len(rx.findall(title)) + len(rx.findall(lead))
        if s:
            score[rid] = s
    titans = find_titans(title + " " + lead)
    for rid, _ in titans:
        score[rid] = score.get(rid, 0) + 2
    if not score:
        return None, [n for _, n in titans]
    best = max(score, key=score.get)
    return (best if score[best] >= 2 else None), [n for _, n in titans]


def is_vietnam(title, desc):
    return bool(VN_RX.search(title) or VN_RX.search((desc or "")[:400]))
