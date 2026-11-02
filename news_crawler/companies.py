"""Top 50 doanh nghiệp vốn hóa lớn nhất: Việt Nam, Mỹ, Trung Quốc, châu Âu.

Mỗi doanh nghiệp: (tên hiển thị, [tên/mã nhận diện trong tiêu đề — phân biệt hoa thường], truy vấn Google News).
Danh sách ước tính theo vốn hóa gần đây, có thể lệch vài mã so với bảng xếp hạng chính thức — sửa tự do.
Tin nhắc tới một doanh nghiệp trong danh sách được xếp vào mục doanh nghiệp đó (theo thứ hạng vốn hóa).
"""
import re

MARKETS = [
    dict(id="co_vn", label="Top 50 vốn hóa Việt Nam", lang="vi", weight=1.4),
    dict(id="co_us", label="Top 50 vốn hóa Mỹ", lang="en", weight=1.3),
    dict(id="co_cn", label="Top 50 vốn hóa Trung Quốc", lang="en", weight=1.3),
    dict(id="co_eu", label="Top 50 vốn hóa châu Âu", lang="en", weight=1.3),
]
for _m in MARKETS:
    _m["spec"] = 0


def _vn(tk, name, *alias):
    return (f"{tk} · {name}", [tk, name, *alias], f'"{name}" OR "{tk}"')


def _en(name, *alias, q=None):
    return (name, [name, *alias], q or f'"{name}"')


COMPANIES = {
    "co_vn": [
        _vn("VCB", "Vietcombank"), _vn("BID", "BIDV"), _vn("VHM", "Vinhomes"), _vn("VIC", "Vingroup"),
        _vn("CTG", "VietinBank", "Vietinbank"), _vn("HPG", "Hòa Phát", "Hoà Phát", "Hoa Phat"), _vn("FPT", "FPT"),
        _vn("TCB", "Techcombank"), _vn("MBB", "MB Bank", "MBBank", "Ngân hàng Quân đội", "Ngân hàng MB"),
        _vn("GAS", "PV Gas", "PV GAS"), _vn("VPB", "VPBank"), _vn("ACB", "ACB"), _vn("MSN", "Masan"),
        _vn("VNM", "Vinamilk"), _vn("LPB", "LPBank"), _vn("HDB", "HDBank"), _vn("GVR", "Cao su Việt Nam", "VRG"),
        _vn("SAB", "Sabeco"), _vn("BSR", "Lọc hóa dầu Bình Sơn", "Bình Sơn", "Dung Quất"), _vn("VJC", "Vietjet"),
        _vn("PLX", "Petrolimex"), _vn("STB", "Sacombank"), _vn("SSB", "SeABank"), _vn("MWG", "Thế Giới Di Động",
        "Thế giới Di động", "Bách Hóa Xanh"), _vn("SHB", "SHB"), _vn("VIB", "VIB"), _vn("TPB", "TPBank"),
        _vn("POW", "PV Power"), _vn("BCM", "Becamex"), _vn("VRE", "Vincom Retail"), _vn("HVN", "Vietnam Airlines"),
        _vn("DGC", "Hóa chất Đức Giang", "Đức Giang"), _vn("MCH", "Masan Consumer"), _vn("ACV", "Tổng công ty Cảng hàng không",
        "ACV"), _vn("VEA", "VEAM"), _vn("OCB", "OCB"), _vn("EIB", "Eximbank"), _vn("KDH", "Khang Điền"),
        _vn("PNJ", "PNJ"), _vn("REE", "REE"), _vn("SSI", "Chứng khoán SSI", "SSI"), _vn("GEX", "Gelex"),
        _vn("NVL", "Novaland"), _vn("MSB", "MSB"), _vn("VPL", "Vinpearl"), _vn("TCX", "TCBS", "Chứng khoán Techcom"),
        _vn("VCI", "Vietcap"), _vn("KBC", "Kinh Bắc Group", "KBC"), _vn("DXG", "Đất Xanh"), _vn("FRT", "FPT Retail", "Long Châu"),
    ],
    "co_us": [
        _en("Nvidia", "NVIDIA"), _en("Microsoft"), _en("Apple", q='"Apple Inc" OR "Apple stock" OR "Apple shares"'),
        _en("Alphabet", "Google"), _en("Amazon"), _en("Meta", "Meta Platforms", "Facebook", q='"Meta Platforms" OR "Meta stock"'),
        _en("Broadcom"), _en("Tesla"), _en("Berkshire Hathaway", "Warren Buffett"), _en("Eli Lilly", "Lilly"),
        _en("JPMorgan", "JPMorgan Chase", "J.P. Morgan", "Jamie Dimon"), _en("Walmart"), _en("Visa", q='"Visa Inc" OR "Visa stock"'),
        _en("Oracle"), _en("Mastercard"), _en("Exxon Mobil", "ExxonMobil", "Exxon"), _en("Netflix"), _en("Costco"),
        _en("UnitedHealth"), _en("Johnson & Johnson", "J&J"), _en("Home Depot"), _en("Procter & Gamble", "P&G"),
        _en("Bank of America", "BofA"), _en("AbbVie"), _en("Palantir"), _en("AMD", "Advanced Micro Devices"),
        _en("Coca-Cola"), _en("Salesforce"), _en("Cisco"), _en("Chevron"), _en("Wells Fargo"), _en("IBM"),
        _en("Philip Morris"), _en("Abbott"), _en("Goldman Sachs"), _en("Morgan Stanley"), _en("Merck"),
        _en("T-Mobile"), _en("McDonald's"), _en("Thermo Fisher"), _en("Intuit"), _en("ServiceNow"),
        _en("American Express", "Amex"), _en("Caterpillar"), _en("Disney", "Walt Disney"), _en("Qualcomm"),
        _en("Micron"), _en("GE Aerospace"), _en("Uber"), _en("Intel"),
    ],
    "co_cn": [
        _en("Tencent"), _en("Alibaba"), _en("ICBC", "Industrial and Commercial Bank of China"),
        _en("Kweichow Moutai", "Moutai"), _en("China Construction Bank", "CCB"), _en("Agricultural Bank of China"),
        _en("Bank of China"), _en("PetroChina"), _en("China Mobile"), _en("CATL", "Contemporary Amperex"),
        _en("BYD"), _en("Xiaomi"), _en("Ping An"), _en("China Merchants Bank"), _en("Meituan"),
        _en("PDD", "Pinduoduo", "Temu"), _en("NetEase"), _en("JD.com"), _en("Baidu"), _en("CNOOC"),
        _en("Sinopec"), _en("China Shenhua", "Shenhua"), _en("Zijin Mining", "Zijin"), _en("China Life"),
        _en("Midea"), _en("Bank of Communications"), _en("Postal Savings Bank of China"), _en("Industrial Bank"),
        _en("SMIC", "Semiconductor Manufacturing International"), _en("Cambricon"), _en("China Yangtze Power", "Yangtze Power"),
        _en("Wuliangye"), _en("Haier"), _en("Gree"), _en("Luxshare"), _en("Foxconn Industrial Internet"),
        _en("Trip.com"), _en("Li Auto"), _en("NIO"), _en("Xpeng", "XPeng"), _en("Anta"), _en("Kuaishou"),
        _en("BeiGene", "BeOne"), _en("Hengrui"), _en("Mindray"), _en("CITIC Securities"), _en("Hikvision"),
        _en("ByteDance", "TikTok"), _en("Huawei"), _en("Geely"),
    ],
    "co_eu": [
        _en("ASML"), _en("SAP", q='"SAP SE" OR "SAP shares"'), _en("Novo Nordisk"), _en("LVMH"), _en("Nestlé", "Nestle"),
        _en("Roche"), _en("Novartis"), _en("AstraZeneca"), _en("Shell", q='"Shell plc" OR "Shell profit" OR "Shell shares"'),
        _en("HSBC"), _en("Siemens"), _en("Hermès", "Hermes"), _en("L'Oréal", "L'Oreal"), _en("TotalEnergies"),
        _en("Unilever"), _en("Allianz"), _en("Schneider Electric"), _en("Airbus"), _en("Deutsche Telekom"),
        _en("Santander"), _en("BNP Paribas"), _en("UBS"), _en("Rheinmetall"), _en("Safran"), _en("Sanofi"),
        _en("Siemens Energy"), _en("Iberdrola"), _en("Inditex", "Zara"), _en("ABB"), _en("Richemont"),
        _en("Prosus"), _en("BP", q='"BP plc" OR "BP profit" OR "BP shares"'), _en("GSK"), _en("Rolls-Royce"),
        _en("British American Tobacco"), _en("Rio Tinto"), _en("Munich Re"), _en("UniCredit"),
        _en("Intesa Sanpaolo"), _en("Zurich Insurance"), _en("Ferrari"), _en("Enel"), _en("Spotify"),
        _en("Volkswagen", "VW"), _en("Mercedes-Benz"), _en("BMW"), _en("Equinor"), _en("Barclays"),
        _en("Deutsche Bank"), _en("AXA"),
    ],
}

MARKET_BY_ID = {m["id"]: m for m in MARKETS}

# regex nhận diện: tên riêng, khớp đúng chữ hoa
_RX = []
for _mid, _lst in COMPANIES.items():
    for _rank, (_label, _aliases, _q) in enumerate(_lst):
        _rx = re.compile(r"(?<![\w.])(?:" + "|".join(re.escape(a) for a in sorted(_aliases, key=len, reverse=True))
                         + r")(?![\w])")
        _RX.append((_mid, _rank, _label, _rx))


# tên dễ trùng từ thường trong tiếng Việt -> chỉ khớp với tin tiếng Anh
_EN_ONLY = {"Visa", "Meta", "Shell", "BP", "Gree", "Anta", "NIO", "Lilly", "Zara", "AXA", "Roche", "Uber", "Merck",
            "Abbott", "Disney", "Ferrari", "Enel", "Prosus", "Industrial Bank", "Ping An", "Intel", "Oracle", "Amazon"}


def find_company(title, lang=None):
    """-> (market_id, rank, label) của doanh nghiệp nhắc tới sớm nhất trong tiêu đề (tên dài hơn thắng nếu cùng vị trí)."""
    best = None
    for mid, rank, label, rx in _RX:
        for m in rx.finditer(title):
            if lang == "vi" and m.group(0) in _EN_ONLY:
                continue
            key = (m.start(), -len(m.group(0)))
            if best is None or key < best[0]:
                best = (key, mid, rank, label)
            break
    return best[1:] if best else None


def gnews_jobs():
    """-> list[(query, locale, (market_id, label))] cho Google News."""
    jobs = []
    for mid, lst in COMPANIES.items():
        loc = "hl=vi&gl=VN&ceid=VN:vi" if mid == "co_vn" else "hl=en-US&gl=US&ceid=US:en"
        for label, aliases, q in lst:
            jobs.append((q, loc, (mid, label)))
    return jobs
