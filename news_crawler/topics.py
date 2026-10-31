"""Phân loại topic + chấm điểm mức độ quan trọng (rule-based, không cần AI).

Mỗi topic:
  strong / normal / weak : từ khoá (không phân biệt hoa thường) — trọng số 2 / 1 / 0.5
  cs                     : từ khoá phân biệt hoa thường (mã CK, "AI", "FED"...) — trọng số 2
  exclude                : nếu tiêu đề chứa các cụm này thì bỏ qua topic
  spec                   : hệ số "độ cụ thể" — topic hẹp thắng topic rộng khi chọn topic chính
  weight                 : điểm nền khi chấm mức độ quan trọng
Từ khoá ở tiêu đề được nhân đôi. Topic được gán nếu tổng điểm >= MIN_SCORE.
Chỉnh sửa thoải mái — thứ tự trong TOPICS là thứ tự hiển thị trong báo cáo.
"""
import re

MIN_SCORE = 2.0

# Danh sách ~100 doanh nghiệp vốn hoá lớn (VN100, có thể lệch so với rổ chính thức kỳ mới nhất — sửa tại đây).
VN100 = {
    "VCB": "Vietcombank", "BID": "BIDV", "CTG": "VietinBank", "TCB": "Techcombank", "MBB": "MB Bank",
    "ACB": "ACB", "VPB": "VPBank", "HDB": "HDBank", "STB": "Sacombank", "SHB": "SHB", "TPB": "TPBank",
    "VIB": "VIB", "LPB": "LPBank", "MSB": "MSB", "OCB": "OCB", "EIB": "Eximbank", "SSB": "SeABank",
    "NAB": "Nam A Bank", "VIC": "Vingroup", "VHM": "Vinhomes", "VRE": "Vincom Retail", "VPL": "Vinpearl",
    "HPG": "Hòa Phát", "HSG": "Hoa Sen", "NKG": "Nam Kim", "FPT": "FPT", "CMG": "CMC", "MWG": "Thế Giới Di Động",
    "FRT": "FPT Retail", "DGW": "Digiworld", "PNJ": "PNJ", "MSN": "Masan", "MCH": "Masan Consumer",
    "VNM": "Vinamilk", "SAB": "Sabeco", "KDC": "Kido", "GAS": "PV Gas", "PLX": "Petrolimex", "POW": "PV Power",
    "PVD": "PV Drilling", "PVT": "PVTrans", "BSR": "Lọc hóa dầu Bình Sơn", "PVS": "PTSC", "GVR": "Cao su Việt Nam",
    "DPM": "Đạm Phú Mỹ", "DCM": "Đạm Cà Mau", "DGC": "Hóa chất Đức Giang", "CSV": "Hóa chất cơ bản miền Nam",
    "VJC": "Vietjet", "HVN": "Vietnam Airlines", "ACV": "ACV", "GMD": "Gemadept", "VSC": "Viconship",
    "HAH": "Hải An", "VTP": "Viettel Post", "SSI": "Chứng khoán SSI", "VCI": "Vietcap", "HCM": "Chứng khoán HSC",
    "VND": "VNDirect", "SHS": "Chứng khoán SHS", "VIX": "Chứng khoán VIX", "MBS": "Chứng khoán MB",
    "BVH": "Bảo Việt", "BMI": "Bảo Minh", "REE": "REE", "GEX": "Gelex", "GEE": "Gelex Electric", "PC1": "PC1",
    "NT2": "Nhơn Trạch 2", "KBC": "Kinh Bắc", "IDC": "IDICO", "SZC": "Sonadezi Châu Đức", "BCM": "Becamex",
    "SIP": "Sài Gòn VRG", "NLG": "Nam Long", "KDH": "Khang Điền", "DXG": "Đất Xanh", "NVL": "Novaland",
    "PDR": "Phát Đạt", "DIG": "DIC Corp", "CEO": "CEO Group", "HDG": "Hà Đô", "KOS": "Kosy", "DXS": "Đất Xanh Services",
    "CTD": "Coteccons", "HHV": "Đèo Cả", "VCG": "Vinaconex", "CII": "CII", "LCG": "Lizen", "FCN": "Fecon",
    "VHC": "Vĩnh Hoàn", "ANV": "Nam Việt", "DBC": "Dabaco", "HAG": "Hoàng Anh Gia Lai", "PAN": "PAN Group",
    "TCH": "Tài chính Hoàng Huy", "EVF": "EVNFinance", "TLG": "Thiên Long", "VGC": "Viglacera", "BWE": "Nước Bình Dương",
    "PHR": "Cao su Phước Hòa", "DPR": "Cao su Đồng Phú", "VCF": "Vinacafe", "TCX": "Chứng khoán Techcom",
}
# Mã dễ nhầm với từ thông dụng -> chỉ khớp qua tên doanh nghiệp
_AMBIGUOUS_TICKERS = {"VND", "GAS", "HCM", "PAN", "CEO", "POW", "CII"}
# Tên dễ trùng địa danh / từ thông dụng -> không dùng để khớp
_AMBIGUOUS_NAMES = {"Hải An", "Kinh Bắc", "PAN Group", "CEO Group", "Nam Kim", "Hà Đô", "Đất Xanh", "Thiên Long"}
_VN100_NAMES = sorted({n for n in VN100.values() if len(n) > 3 and n not in _AMBIGUOUS_NAMES},
                      key=len, reverse=True)
_VN100_TICKERS = [t for t in VN100 if t not in _AMBIGUOUS_TICKERS]

T = dict  # alias cho gọn

TOPICS = [
    T(id="bau_cu_my", label="Bầu cử giữa kỳ Mỹ", spec=3.0, weight=1.8,
      strong=["bầu cử giữa kỳ", "bầu cử giữa nhiệm kỳ", "midterm", "midterms", "midterm elections",
              "senate race", "house race", "governor race", "gubernatorial", "battleground state",
              "bỏ phiếu sớm", "early voting", "election day", "ngày bầu cử", "ballot measure"],
      normal=["hạ viện mỹ", "thượng viện mỹ", "đảng dân chủ", "đảng cộng hòa", "democrats", "republicans",
              "gop", "cử tri mỹ", "thăm dò dư luận", "poll shows", "polls show", "swing state", "bang chiến trường",
              "house majority", "senate majority", "kiểm soát quốc hội"],
      weak=["trump", "bầu cử", "election", "voters", "cử tri"]),
    T(id="chinh_tri_tq", label="Bầu cử & nhân sự Trung Quốc", spec=2.5, weight=1.4,
      strong=["tập cận bình", "xi jinping", "hội nghị trung ương 4", "hội nghị toàn thể", "plenum", "politburo",
              "ban thường vụ bộ chính trị trung quốc", "đảng cộng sản trung quốc", "chinese communist party",
              "communist party of china", "quân ủy trung ương", "central military commission", "nhân đại toàn quốc",
              "national people's congress", "chính hiệp", "cppcc", "đại hội đảng 21", "21st party congress",
              "bầu cử đài loan", "taiwan election", "hong kong election", "bầu cử hồng kông", "kmt", "quốc dân đảng"],
      normal=["lý cường", "li qiang", "bắc kinh", "beijing", "trung nam hải", "zhongnanhai", "ccp", "cpc",
              "thanh trừng", "purge", "anti-corruption campaign", "lại thanh đức", "lai ching-te"],
      weak=["trung quốc", "china", "chinese"]),
    T(id="bct_vn", label="Bộ Chính trị Việt Nam", spec=2.5, weight=2.0,
      strong=["bộ chính trị", "ban bí thư", "tổng bí thư", "ủy viên bộ chính trị", "uỷ viên bộ chính trị",
              "ban chấp hành trung ương", "hội nghị trung ương", "thường trực ban bí thư", "ủy ban kiểm tra trung ương",
              "ban tổ chức trung ương", "vietnam politburo", "communist party of vietnam", "đại hội xiv", "đại hội đảng"],
      normal=["tô lâm", "to lam", "nghị quyết số", "kết luận số", "chỉ thị số", "bổ nhiệm", "điều động", "kỷ luật đảng",
              "thi hành kỷ luật", "chủ tịch nước", "chủ tịch quốc hội", "thủ tướng chính phủ", "nhân sự cấp cao"],
      weak=["trung ương", "đảng ủy", "bí thư"],
      exclude=["trung quốc", "tập cận bình", "triều tiên", "lào", "cuba", "china", "xi jinping"]),
    T(id="chinh_sach_vn", label="Chính trị - Chính sách - Quốc hội VN", spec=1.2, weight=1.3,
      strong=["quốc hội thông qua", "kỳ họp thứ", "dự thảo luật", "luật sửa đổi", "nghị định số", "thông tư số",
              "nghị quyết của chính phủ", "công điện", "chỉ thị của thủ tướng", "tinh gọn bộ máy", "sáp nhập tỉnh",
              "chính quyền địa phương hai cấp", "chính quyền 2 cấp"],
      normal=["quốc hội", "đại biểu quốc hội", "ủy ban thường vụ quốc hội", "chính phủ", "thủ tướng", "phó thủ tướng",
              "nghị định", "nghị quyết", "bộ trưởng", "luật", "chính sách", "ban hành", "national assembly", "prime minister"],
      weak=["ubnd", "hđnd", "tỉnh"]),
    T(id="tttc", label="Trung tâm tài chính quốc tế", spec=3.0, weight=1.6,
      strong=["trung tâm tài chính quốc tế", "trung tâm tài chính khu vực", "trung tâm tài chính", "international financial centre",
              "international financial center", "financial hub", "nghị quyết 222", "ifc tại việt nam", "ifc đà nẵng",
              "ifc tp.hcm", "cơ chế sandbox", "thử nghiệm có kiểm soát"],
      normal=["sandbox", "tài sản số", "tài sản mã hóa", "sàn giao dịch tài sản", "đặc khu kinh tế", "ngân hàng số",
              "fintech", "sàn giao dịch hàng hóa quốc tế"],
      weak=["thu hút dòng vốn", "định chế tài chính"]),
    T(id="vn100", label="Doanh nghiệp VN100", spec=2.0, weight=1.2,
      strong=[], normal=[], weak=["cổ phiếu", "doanh nghiệp niêm yết", "lợi nhuận", "doanh thu", "đhđcđ", "cổ tức"],
      special="vn100"),
    T(id="chung_khoan", label="Chứng khoán Việt Nam", spec=1.4, weight=1.1,
      strong=["vn-index", "vnindex", "vn30", "hnx-index", "upcom", "nâng hạng thị trường", "ftse russell",
              "ủy ban chứng khoán", "ubcknn", "thanh khoản thị trường", "hose", "hnx", "krx"],
      normal=["chứng khoán", "cổ phiếu", "phiên giao dịch", "margin", "ipo", "niêm yết", "trái phiếu doanh nghiệp",
              "công ty chứng khoán", "vietnam stocks", "vietnamese stocks"],
      weak=["nhà đầu tư", "thị trường"]),
    T(id="vi_mo", label="Kinh tế vĩ mô", spec=1.3, weight=1.4,
      strong=["gdp", "tăng trưởng kinh tế", "lạm phát", "cpi", "chỉ số giá tiêu dùng", "pmi", "cán cân thương mại",
              "kim ngạch xuất khẩu", "kim ngạch xuất nhập khẩu", "thu ngân sách", "bội chi", "nợ công", "tổng cục thống kê",
              "cục thống kê", "inflation", "gdp growth", "recession", "nonfarm payrolls", "jobs report", "economic growth",
              "trade surplus", "trade deficit", "consumer prices", "imf", "world bank", "ngân hàng thế giới", "adb"],
      normal=["kinh tế vĩ mô", "xuất khẩu", "nhập khẩu", "tiêu dùng", "bán lẻ", "sản xuất công nghiệp", "iip",
              "ngân sách", "chính sách tài khóa", "thuế", "economy", "economic", "unemployment", "thất nghiệp"],
      weak=["tăng trưởng", "kinh tế"]),
    T(id="lai_suat", label="Lãi suất - Tiền tệ - Ngân hàng", spec=1.8, weight=1.5,
      strong=["lãi suất", "lãi suất điều hành", "lãi suất huy động", "lãi suất cho vay", "ngân hàng nhà nước",
              "nhnn", "tín phiếu", "thị trường mở", "omo", "tăng trưởng tín dụng", "room tín dụng", "liên ngân hàng",
              "fomc", "cục dự trữ liên bang", "interest rate", "interest rates", "rate cut", "rate hike", "rate cuts",
              "powell", "ecb", "bank of japan", "pboc", "lợi suất trái phiếu", "treasury yields", "bond yields",
              "cắt giảm lãi suất", "tăng lãi suất", "monetary policy", "chính sách tiền tệ"],
      normal=["tín dụng", "ngân hàng", "tiền gửi", "nợ xấu", "thanh khoản ngân hàng", "central bank", "yield", "lợi suất"],
      cs=["Fed", "FED", "BOJ", "SBV"]),
    T(id="ty_gia_vang", label="Tỷ giá - Vàng - Hàng hoá", spec=1.5, weight=1.2,
      strong=["tỷ giá", "giá vàng", "vàng miếng", "vàng sjc", "usd/vnd", "đồng usd", "chỉ số dxy", "dxy",
              "giá dầu", "dầu brent", "dầu wti", "opec", "gold price", "oil price", "oil prices", "dollar index"],
      normal=["vàng", "đô la", "nhân dân tệ", "yên nhật", "giá cà phê", "giá gạo", "giá thép", "copper", "đồng (kim loại)",
              "commodities", "gold", "crude"],
      weak=["giá"]),
    T(id="von_ngoai", label="Dòng vốn nước ngoài", spec=2.0, weight=1.5,
      strong=["khối ngoại", "nhà đầu tư nước ngoài", "bán ròng", "mua ròng", "foreign investors", "foreign inflows",
              "foreign outflows", "net selling", "net buying", "capital outflows", "capital inflows", "room ngoại",
              "dòng vốn ngoại", "dòng vốn nước ngoài", "vốn ngoại"],
      normal=["dòng vốn", "rút vốn", "capital flows", "hot money", "giới hạn sở hữu nước ngoài", "foreign ownership"],
      weak=["nước ngoài", "foreign"]),
    T(id="quy_dau_tu", label="Các quỹ đầu tư", spec=2.0, weight=1.3,
      strong=["quỹ đầu tư", "quỹ etf", "quỹ mở", "quỹ ngoại", "dragon capital", "vinacapital", "pyn elite", "kim vietnam",
              "fubon", "vaneck", "diamond etf", "vfmvn30", "vfmvn diamond", "ftse vietnam", "temasek", "gic",
              "quỹ đầu tư quốc gia", "sovereign wealth fund", "private equity", "hedge fund", "mekong capital",
              "warburg pincus", "kkr", "blackrock", "quỹ hưu trí", "pension fund", "quỹ đầu tư mạo hiểm", "venture capital"],
      normal=["etf", "quỹ", "fund manager", "asset manager", "danh mục đầu tư", "nav"],
      weak=["quỹ"]),
    T(id="fdi", label="FDI", spec=2.0, weight=1.4,
      strong=["fdi", "vốn đầu tư trực tiếp nước ngoài", "đầu tư trực tiếp nước ngoài", "foreign direct investment",
              "vốn fdi", "dự án fdi", "vốn đăng ký", "vốn giải ngân fdi", "giấy chứng nhận đăng ký đầu tư",
              "chuyển dịch chuỗi cung ứng", "supply chain shift", "china plus one"],
      normal=["samsung", "lg", "foxconn", "intel", "nvidia việt nam", "khu công nghiệp", "nhà đầu tư nhật bản",
              "nhà đầu tư hàn quốc", "nhà đầu tư singapore", "nhà đầu tư trung quốc", "nhà máy", "đầu tư nước ngoài",
              "investment in vietnam", "factory"],
      weak=["nhà đầu tư"]),
    T(id="dau_tu_cong", label="Đầu tư công", spec=1.6, weight=1.4,
      strong=["đầu tư công", "giải ngân vốn đầu tư công", "giải ngân", "vốn đầu tư công", "kế hoạch đầu tư công",
              "dự án trọng điểm", "công trình trọng điểm", "đường sắt tốc độ cao", "sân bay long thành", "cao tốc bắc - nam",
              "cao tốc bắc nam", "đường sắt lào cai", "public investment", "ppp", "đối tác công tư"],
      normal=["cao tốc", "đường sắt", "sân bay", "khởi công", "khánh thành", "thông xe", "nhà thầu", "dự án giao thông",
              "hạ tầng giao thông", "bộ xây dựng", "infrastructure"],
      weak=["dự án", "hạ tầng"]),
    T(id="ha_tang_hcm", label="Hạ tầng TP.HCM", spec=2.2, weight=1.4,
      strong=["vành đai 3", "vành đai 4", "metro số 1", "metro số 2", "tuyến metro", "bến thành - suối tiên",
              "bến thành - tham lương", "cảng cần giờ", "cảng trung chuyển cần giờ", "lấn biển cần giờ", "thủ thiêm",
              "tân sơn nhất", "nhà ga t3", "cao tốc tp.hcm", "tp.hcm - mộc bài", "tp.hcm - long thành",
              "tp.hcm - trung lương", "quốc lộ 13", "quốc lộ 22", "đường sắt đô thị tp.hcm", "đường sắt thủ thiêm",
              "nút giao an phú", "rạch chiếc", "ho chi minh city metro", "hcmc metro"],
      normal=["metro", "đường sắt đô thị", "tod", "cầu cần giờ", "cầu thủ thiêm", "kênh nhiêu lộc", "chống ngập",
              "thủ đức", "bình dương", "dĩ an", "thuận an"],
      weak=["tp.hcm", "tphcm", "tp hcm", "thành phố hồ chí minh", "ho chi minh city", "hcmc", "sài gòn"],
      context=["hạ tầng", "dự án", "giao thông", "cao tốc", "đường", "cầu", "quy hoạch", "đầu tư", "khởi công", "vốn"]),
    T(id="cai_mep", label="Cái Mép - Bình Giã - Châu Đức - Hồ Tràm", spec=3.0, weight=1.5,
      strong=["cái mép", "thị vải", "cái mép hạ", "bình giã", "châu đức", "hồ tràm", "xuyên mộc", "long sơn",
              "phú mỹ", "biên hòa - vũng tàu", "biên hòa – vũng tàu", "bà rịa - vũng tàu", "bà rịa – vũng tàu",
              "cai mep", "ho tram", "khu thương mại tự do cái mép", "côn đảo", "đất đỏ", "long hải", "ngãi giao",
              "kim long", "cảng vũng tàu", "sân bay hồ tràm", "sân bay côn đảo"],
      normal=["vũng tàu", "bà rịa", "baria vung tau", "vung tau", "khu thương mại tự do", "free trade zone", "ftz",
              "cảng nước sâu", "cảng biển", "logistics"],
      weak=[]),
    T(id="bds", label="Bất động sản", spec=1.2, weight=1.0,
      strong=["bất động sản", "thị trường nhà ở", "giá nhà", "chung cư", "căn hộ", "đất nền", "nhà ở xã hội",
              "khu đô thị", "real estate", "property market", "home prices", "housing market"],
      normal=["nhà đất", "dự án nhà ở", "sổ hồng", "giao dịch đất", "đấu giá đất", "giá đất", "bảng giá đất", "property"],
      weak=["nhà ở"]),
    T(id="thuong_mai", label="Thương mại & thuế quan", spec=1.6, weight=1.4,
      strong=["thuế quan", "thuế đối ứng", "tariff", "tariffs", "trade war", "chiến tranh thương mại", "trade deal",
              "hiệp định thương mại", "wto", "chống bán phá giá", "anti-dumping", "export controls", "kiểm soát xuất khẩu",
              "ustr", "section 301"],
      normal=["fta", "evfta", "cptpp", "rcep", "trade talks", "đàm phán thương mại", "xuất khẩu sang mỹ", "trade"],
      weak=["thương mại"]),
    T(id="kinh_te_tq", label="Kinh tế Trung Quốc", spec=1.8, weight=1.2,
      strong=["kinh tế trung quốc", "china's economy", "chinese economy", "nhân dân tệ", "yuan", "renminbi",
              "evergrande", "country garden", "vanke", "kích thích kinh tế trung quốc", "china stimulus",
              "chinese exports", "xuất khẩu của trung quốc"],
      normal=["pboc", "ngân hàng nhân dân trung quốc", "bất động sản trung quốc", "china property", "deflation",
              "giảm phát", "hang seng", "shanghai composite"],
      weak=["trung quốc", "china"]),
    T(id="chinh_tri_my", label="Chính trị - Chính sách Mỹ", spec=1.4, weight=1.3,
      strong=["nhà trắng", "white house", "tổng thống mỹ", "us president", "quốc hội mỹ", "us congress",
              "chính phủ mỹ đóng cửa", "government shutdown", "supreme court", "tòa án tối cao mỹ", "executive order",
              "sắc lệnh"],
      normal=["trump", "washington", "bộ trưởng tài chính mỹ", "treasury secretary", "biden", "vance"],
      weak=["mỹ", "us", "american"]),
    T(id="dia_chinh_tri", label="Địa chính trị & xung đột", spec=1.4, weight=1.4,
      strong=["ukraine", "nga", "russia", "putin", "zelensky", "israel", "gaza", "hamas", "iran", "biển đông",
              "south china sea", "nato", "trừng phạt", "sanctions", "triều tiên", "north korea", "eo biển đài loan",
              "taiwan strait", "ngừng bắn", "ceasefire", "xung đột", "chiến sự", "tên lửa", "missile", "drone attack"],
      normal=["ngoại giao", "thượng đỉnh", "summit", "g7", "g20", "apec", "asean", "liên hợp quốc", "united nations",
              "geopolitical", "địa chính trị", "military", "quân sự"],
      weak=["thế giới"]),
    T(id="cong_nghe", label="Công nghệ - AI - Bán dẫn", spec=1.4, weight=1.1,
      strong=["trí tuệ nhân tạo", "artificial intelligence", "bán dẫn", "semiconductor", "chip", "nvidia", "openai",
              "trung tâm dữ liệu", "data center", "data centre", "anthropic", "tsmc", "chuyển đổi số"],
      normal=["công nghệ", "technology", "startup", "big tech", "apple", "microsoft", "google", "meta", "tesla"],
      cs=["AI"]),
    T(id="phap_luat", label="Thanh tra - Pháp luật - Chống tham nhũng", spec=1.6, weight=1.3,
      strong=["kết luận thanh tra", "thanh tra chính phủ", "khởi tố", "bắt tạm giam", "truy tố", "tham nhũng",
              "đại án", "xét xử", "tuyên án", "cáo trạng", "thất thoát", "lãng phí", "sai phạm", "bộ công an",
              "c03", "cơ quan cảnh sát điều tra", "thanh tra"],
      normal=["vi phạm", "điều tra", "tòa án", "xử phạt", "lừa đảo", "thao túng", "kiểm toán nhà nước"],
      weak=["pháp luật"]),
    T(id="kinh_te", label="Kinh tế - Doanh nghiệp (khác)", spec=0.8, weight=1.0,
      strong=["doanh nghiệp", "kinh doanh", "lợi nhuận", "doanh thu", "thị trường", "business", "earnings",
              "profit", "revenue", "markets", "stocks", "wall street", "s&p 500", "nasdaq", "dow jones"],
      normal=["kinh tế", "đầu tư", "tài chính", "economy", "investment", "finance", "company"],
      weak=[]),
]
OTHER = dict(id="khac", label="Thời sự khác", spec=0, weight=0.6)
from .regions import REGIONS  # noqa: E402
TOPIC_BY_ID = {t["id"]: t for t in TOPICS + REGIONS + [OTHER]}
# Thứ tự hiển thị: Việt Nam trước, rồi thế giới theo quốc gia. kinh_te_tq / chinh_tri_my được gộp vào Trung Quốc / Mỹ.
_VN_ORDER = ["bct_vn", "chinh_sach_vn", "tttc", "vn100", "chung_khoan", "vi_mo", "lai_suat", "ty_gia_vang", "von_ngoai",
             "quy_dau_tu", "fdi", "dau_tu_cong", "ha_tang_hcm", "cai_mep", "bds", "thuong_mai", "phap_luat", "kinh_te"]
_WORLD_ORDER = ["bau_cu_my", "r_my", "chinh_tri_tq", "r_tq", "r_hk", "r_eu", "r_sg", "r_gulf", "r_asia",
                "dia_chinh_tri", "cong_nghe", "kinh_te_tq", "chinh_tri_my"]
DISPLAY = [("Việt Nam", _VN_ORDER), ("Thế giới theo quốc gia", _WORLD_ORDER)]


def _kw_regex(words, flags=re.IGNORECASE):
    words = [w for w in words if w]
    if not words:
        return None
    alt = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alt + r")(?!\w)", flags)


for _t in TOPICS:
    _t["_re"] = [(r, w) for r, w in (
        (_kw_regex(_t.get("strong", [])), 2.0),
        (_kw_regex(_t.get("normal", [])), 1.0),
        (_kw_regex(_t.get("weak", [])), 0.5),
        (_kw_regex(_t.get("cs", []), 0), 2.0),
    ) if r]
    _t["_ex"] = _kw_regex(_t.get("exclude", []))
    _t["_ctx"] = _kw_regex(_t.get("context", []))

_VN100_NAME_RE = _kw_regex(_VN100_NAMES)
_VN100_TICKER_RE = re.compile(r"(?<![\w.])(" + "|".join(_VN100_TICKERS) + r")(?![\w])")
_NAME_TO_TICKER = {}
for _tk, _nm in VN100.items():
    _NAME_TO_TICKER.setdefault(_nm.lower(), _tk)


def find_vn100(text):
    """Trả về danh sách mã VN100 được nhắc tới."""
    found = set(m.group(1) for m in _VN100_TICKER_RE.finditer(text))
    for m in _VN100_NAME_RE.finditer(text):
        tk = _NAME_TO_TICKER.get(m.group(0).lower())
        if tk:
            found.add(tk)
    return sorted(found)


def _hits(rx, text):
    return len(rx.findall(text)) if rx else 0


def score_topics(title, body):
    """Trả về {topic_id: score} cho các topic đạt ngưỡng."""
    scores = {}
    for t in TOPICS:
        if t["_ex"] and t["_ex"].search(title):
            continue
        s = 0.0
        for rx, w in t["_re"]:
            # tiêu đề x2, thân bài: mỗi từ khoá tính tối đa 3 lần để tránh bài dài lấn át
            s += 2 * w * _hits(rx, title) + w * min(_hits(rx, body), 3)
        if t.get("special") == "vn100":
            tick_title, tick_body = find_vn100(title), find_vn100(body[:1500])
            s += 2.5 * len(tick_title) + 0.8 * min(len(tick_body), 3)
            if not tick_title and not tick_body:
                s = 0
        if t["_ctx"] is not None and s > 0:
            # topic địa danh rộng (TP.HCM) cần thêm ngữ cảnh hạ tầng
            strong_hit = any(_hits(rx, title + " " + body) for rx, w in t["_re"] if w >= 2)
            if not strong_hit and not t["_ctx"].search(title):
                s = min(s, MIN_SCORE - 0.1)
        if s >= MIN_SCORE:
            scores[t["id"]] = s
    return scores


def classify(title, body):
    """Topic chính + các topic phụ (tối đa 3)."""
    scores = score_topics(title, body)
    if not scores:
        return OTHER["id"], [], scores
    ranked = sorted(scores, key=lambda k: scores[k] * TOPIC_BY_ID[k]["spec"], reverse=True)
    return ranked[0], ranked[1:4], scores


# ---------------------------------------------------------------- mức độ quan trọng
_IMPACT = _kw_regex([
    "bộ chính trị", "tổng bí thư", "thủ tướng", "quốc hội thông qua", "nghị quyết", "phê duyệt", "chính thức",
    "khởi công", "thông qua", "lần đầu tiên", "kỷ lục", "cao nhất", "thấp nhất", "khẩn", "hỏa tốc", "đột biến",
    "cắt giảm lãi suất", "tăng lãi suất", "giữ nguyên lãi suất", "nâng hạng", "bán ròng", "mua ròng", "tỷ usd",
    "nghìn tỷ", "ngàn tỷ", "phá sản", "khởi tố", "bắt tạm giam", "sáp nhập", "thoái vốn", "chiến tranh", "trừng phạt",
    "thuế quan", "quy hoạch", "chủ trương đầu tư", "breaking", "record", "first time", "billion", "trillion",
    "rate cut", "rate hike", "wins", "victory", "results", "sanctions", "tariffs", "collapse", "crisis", "khủng hoảng",
    "default", "vỡ nợ", "plunge", "surge", "lao dốc", "bứt phá", "tăng vọt", "giảm sâu",
])
_MAGNITUDE = re.compile(r"\d[\d.,]*\s*(?:tỷ|nghìn tỷ|ngàn tỷ|triệu usd|%|billion|trillion|bn|tn)", re.IGNORECASE)

LEVELS = [(5.0, 5, "Rất cao"), (4.0, 4, "Cao"), (3.0, 3, "Trung bình"), (2.0, 2, "Thấp"), (-99, 1, "Tham khảo")]


def importance(art, n_sources, now_ts):
    t = TOPIC_BY_ID[art["topic"]]
    s = t["weight"]
    s += min(_hits(_IMPACT, art["title"]) * 0.6 + _hits(_IMPACT, art.get("summary", "")) * 0.2, 2.0)
    if _MAGNITUDE.search(art["title"]):
        s += 0.4
    s += min(0.6 * (n_sources - 1), 2.4)  # nhiều báo cùng đưa tin
    s += {1: 0.6, 2: 0.3}.get(art.get("tier", 3), 0)
    s += 0.25 * len(art.get("topics2", []))
    if art.get("ts"):
        age_h = (now_ts - art["ts"]) / 3600
        s += 0.4 if age_h < 6 else 0.2 if age_h < 24 else 0
    for th, lv, label in LEVELS:
        if s >= th:
            return lv, label, round(s, 2)
