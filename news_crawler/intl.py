"""Bản tin quốc tế theo quốc gia / khu vực từ 5 báo: Financial Times, Bloomberg, Nikkei Asia, WSJ, Reuters.

Chạy: python -m news_crawler.intl [--hours 24] [--enrich 700] [--out reports/quoc-te.html] [--json x.json]

1. Thu tin: RSS/sitemap của 5 báo + Google News (truy vấn sẵn có của crawler và truy vấn "site:" theo nước / loại tin).
   Chỉ giữ tin do 5 báo này đăng.
2. Làm giàu nội dung: tin chỉ có tiêu đề (bài trả phí) -> tìm cùng tiêu đề trên Bing News, lấy bài khớp nhất từ trang
   không thu phí (Yahoo Finance, CNBC, AP, MarketWatch...), tóm tắt 2 ý; không tải được bài thì dùng đoạn mô tả của Bing.
3. Phân theo quốc gia / khu vực, trong mỗi nước chia: M&A, huy động vốn, vĩ mô - lãi suất, thị trường,
   năng lượng - hàng hóa, chính trị - địa chính trị, doanh nghiệp - công nghệ.
"""
import argparse
import hashlib
import html
import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlparse

from . import extract as X
from .crawl import Opts, crawl_all
from .digest import bullets as make_bullets, shorten
from .extract import VN_TZ
from .fetch import Fetcher
from .mna import deal_usd, is_deal
from .render import build_items, is_junk

OUTLETS = {"ft": "Financial Times", "bloomberg": "Bloomberg", "wsj": "The Wall Street Journal",
           "nikkei": "Nikkei Asia", "reuters": "Reuters"}
SITES = {"ft": "ft.com", "bloomberg": "bloomberg.com", "wsj": "wsj.com", "nikkei": "asia.nikkei.com", "reuters": "reuters.com"}
_OUTLET_RX = re.compile(r"financial times|^ft(?:\.com)?$|bloomberg|wall street journal|^wsj|nikkei|reuters", re.I)
PAYWALL = re.compile(r"(?:^|\.)(?:ft\.com|bloomberg\.com|wsj\.com|nikkei\.com|reuters\.com|barrons\.com|economist\.com|"
                     r"nytimes\.com|washingtonpost\.com|theinformation\.com|bloomberglaw\.com|businessweek\.com)$")


def outlet_of(name):
    n = (name or "").lower()
    for k, v in (("financial times", "Financial Times"), ("ft", "Financial Times"), ("bloomberg", "Bloomberg"),
                 ("wall street journal", "The Wall Street Journal"), ("wsj", "The Wall Street Journal"),
                 ("nikkei", "Nikkei Asia"), ("reuters", "Reuters")):
        if n == k or n.startswith(k + ".") or (len(k) > 3 and k in n):
            return v
    return None


# ------------------------------------------------------------------ quốc gia / khu vực
# (id, nhãn, vùng, regex phân biệt hoa thường — tên nước, thủ đô, ngân hàng trung ương, chỉ số, doanh nghiệp lớn)
COUNTRIES = [
    ("us", "Mỹ", "Châu Mỹ", r"\bU\.?S\.?\b|\bUS\b|United States|Americans?\b|Washington|Wall Street|White House|\bFed\b|Federal Reserve|"
     r"Treasur(?:y|ies)|Trump|Congress|Senate|S&P 500|Nasdaq|\bDow\b|New York|California|Texas|Pentagon|Powell|"
     r"Nvidia|Apple|Microsoft|Alphabet|Google|Amazon|\bMeta\b|Tesla|OpenAI|Anthropic|JPMorgan|Goldman|Morgan Stanley|"
     r"BlackRock|Blackstone|\bKKR\b|Apollo|Berkshire|Citigroup|Bank of America|Wells Fargo|Exxon|Chevron|Boeing|"
     r"\bIntel\b|\bAMD\b|Oracle|Pfizer|Eli Lilly|Walmart|Netflix|Disney|Broadcom|Micron|Qualcomm|SpaceX|\bxAI\b|CoreWeave|"
     r"Carlyle|Citadel|Fortress|Silver Lake|Warner|Paramount|Starbucks|McDonald|Ford\b|General Motors|\bGM\b|Nike|JetBlue|"
     r"PG&E|Take-Two|Kalshi|Polymarket|Intercontinental Exchange|\bNYSE\b|McCormick|BofA|Medline|Coatue|Cisco|Salesforce|"
     r"\bIBM\b|\bDell\b|\bUber\b|Airbnb|Coca-Cola|Pepsi|Procter|Johnson & Johnson|Merck|AbbVie|UnitedHealth|\bCVS\b|"
     r"Home Depot|Costco|\bVisa\b|Mastercard|PayPal|Comcast|Verizon|AT&T|T-Mobile|Delta Air|United Airlines|American Airlines|"
     r"Caterpillar|Deere|Honeywell|Lockheed|Raytheon|\bRTX\b|Northrop|General Electric|Moderna|Gilead|Amgen|Skydance|"
     r"Palantir|Snowflake|Coinbase|Robinhood|Schwab|Vanguard|Fidelity|State Street|Bridgewater|Two Sigma|Millennium|"
     r"Democrat|Republican|GOP\b|Pelosi|Vance\b|Rubio|Bessent|Lutnick|D\.C\.|Alabama|Alaska|Arizona|Arkansas|Colorado|"
     r"Connecticut|Florida|Georgia(?! the)|Hawaii|Idaho|Illinois|Chicago|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|"
     r"Maryland|Massachusetts|Boston|Michigan|Detroit|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|Las Vegas|"
     r"New Hampshire|New Jersey|New Mexico|North Carolina|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|"
     r"Tennessee|Utah|Vermont|Virginia|Wisconsin|Wyoming|Silicon Valley|Seattle|San Francisco|Los Angeles|Houston|Miami|"
     r"Atlanta|Dallas|Denver|Phoenix|Philadelphia|Pittsburgh"),
    ("ca", "Canada", "Châu Mỹ", r"Canada|Canadian|Toronto|Ottawa|Carney|Bank of Canada|\bRBC\b|Royal Bank of Canada|TD Bank|"
     r"Brookfield|Shopify|Enbridge|Alberta|Scotiabank|Desjardins|iA Financial|Quebec|Telus|Rogers|Montreal|Vancouver|"
     r"Manulife|Sun Life|Suncor|Canadian Natural|TransAlta|Strathcona|GFL"),
    ("latam", "Mỹ Latinh", "Châu Mỹ", r"Brazil|Brazilian|Mexico|Mexican|Argentin|Milei|Chile|Chilean|Colombia|Peru\b|"
     r"Venezuela|Latin America|Lula|Sheinbaum|Petrobras|\bVale\b|Ecopetrol|Paraguay|Uruguay|Panama"),
    ("uk", "Anh", "Châu Âu", r"Britain|British|\bUK\b|U\.K\.|England|London|Bank of England|\bBoE\b|Reeves|Starmer|FTSE|"
     r"HSBC|Barclays|Lloyds|NatWest|\bBP\b|\bShell\b|AstraZeneca|Unilever|\bGSK\b|Rolls-Royce|Vodafone|Burnham|EasyJet|"
     r"Scotland|Scottish|Standard Chartered|Diageo|Tesco"),
    ("eu", "EU - Eurozone", "Châu Âu", r"European Union|\bEU\b|Eurozone|euro area|\bECB\b|Lagarde|European Commission|"
     r"Brussels|von der Leyen|\bEurope\b|European"),
    ("de", "Đức", "Châu Âu", r"German(?:y)?|Berlin|Frankfurt|Bundesbank|\bMerz\b|\bDAX\b|Siemens|Volkswagen|\bBMW\b|"
     r"Mercedes|Deutsche Bank|Commerzbank|Allianz|\bSAP\b|Bayer|BASF|Porsche|Rheinmetall|Lufthansa|Munich Re|\bRWE\b|KNDS"),
    ("fr", "Pháp", "Châu Âu", r"France|French|Paris|Macron|CAC 40|LVMH|TotalEnergies|BNP Paribas|Soci[ée]t[ée] G[ée]n[ée]rale|"
     r"Cr[ée]dit Agricole|\bAXA\b|Airbus|L'Or[ée]al|Herm[èe]s|Danone|Renault|Sanofi|Kering"),
    ("it_es", "Ý - Tây Ban Nha - Bồ Đào Nha", "Châu Âu", r"Ital(?:y|ian)|\bRome\b|Milan|Meloni|Spain|Spanish|Madrid|UniCredit|"
     r"Intesa|Banco BPM|Monte dei Paschi|\bMPS\b|Santander|BBVA|Iberdrola|\bEnel\b|\bEni\b|Ferrari|Stellantis|Generali|Portug"),
    ("ch_nl", "Thụy Sĩ - Hà Lan - Bắc Âu - châu Âu khác", "Châu Âu",
     r"Switzerland|Swiss|Zurich|\bUBS\b|Nestl[ée]|Novartis|\bRoche\b|Netherlands|Dutch|Amsterdam|\bASML\b|\bING\b|Belgi|"
     r"Sweden|Swedish|Norw|Denmark|Danish|Novo Nordisk|Finland|Finnish|Poland|Polish|Austria|Ireland|Irish|Greece|Greek|"
     r"Czech|Hungar|Orlen|Equinor|Ericsson|Nokia|Volvo|Maersk|AkzoNobel|Heineken|Philips|Adyen|Prosus|Slovak|Romania|"
     r"Serbia|Bulgaria|Croatia|Slovenia|Baltic|Estonia|Latvia|Lithuania|Iceland|IKEA|Iceye|Spotify|Klarna|H&M"),
    ("ru_ua", "Nga - Ukraine", "Châu Âu", r"Russia|Russian|Moscow|Kremlin|Putin|Ukrain|Kyiv|Kiev|Zelensky|Gazprom|Rosneft"),
    ("cn", "Trung Quốc", "Châu Á", r"China|Chinese|Beijing|Shanghai|Shenzhen|Xi Jinping|\bXi\b|\bPBOC\b|People's Bank of China|"
     r"\byuan\b|renminbi|Alibaba|Tencent|\bBYD\b|Huawei|\bCATL\b|Xiaomi|Baidu|JD\.com|\bPDD\b|Pinduoduo|ByteDance|TikTok|"
     r"DeepSeek|\bSMIC\b|Geely|\bNIO\b|Sinopec|PetroChina|\bICBC\b|Evergrande|Vanke|Country Garden|Meituan|Li Auto|Xpeng|"
     r"Kuaishou|CSI 300|Sinochem|Huaxin"),
    ("hk", "Hồng Kông", "Châu Á", r"Hong Kong|\bHKEX\b|Hang Seng|\bHKMA\b|John Lee|CK Hutchison|\bAIA\b|Cathay Pacific|Jardine"),
    ("tw", "Đài Loan", "Châu Á", r"Taiwan|Taipei|\bTSMC\b|Foxconn|Hon Hai|MediaTek|Lai Ching-te"),
    ("jp", "Nhật Bản", "Châu Á", r"Japan|Japanese|Tokyo|Osaka|\bBOJ\b|Bank of Japan|Ueda|Takaichi|Nikkei 225|Topix|\byen\b|"
     r"Toyota|SoftBank|\bSony\b|Nintendo|Honda|Nissan|Mitsubishi|Mitsui|Sumitomo|\bMUFG\b|Mizuho|Hitachi|Panasonic|"
     r"Fast Retailing|Uniqlo|Seven & i|Nomura|\bNTT\b|\bKDDI\b|Rakuten|\bJSR\b|Keyence|Tokyo Electron|Kioxia|Kokuyo"),
    ("kr", "Hàn Quốc", "Châu Á", r"South Korea|Korean?\b|Seoul|Bank of Korea|Kospi|\bwon\b|Samsung|SK Hynix|Hyundai|\bLG\b|"
     r"\bKia\b|Naver|Kakao|Lee Jae Myung|POSCO|Lotte|Hanwha|Coupang"),
    ("in", "Ấn Độ", "Châu Á", r"India|Indian|New Delhi|Delhi|Mumbai|\bModi\b|\bRBI\b|Reserve Bank of India|rupee|Sensex|Nifty|"
     r"Reliance|\bTata\b|Adani|Infosys|Wipro|\bHDFC\b|ICICI|Bajaj|Zomato|Paytm|\bJio\b|Mahindra|IIFL|Vedanta"),
    ("sg", "Singapore", "Đông Nam Á", r"Singapore|\bMAS\b|Monetary Authority of Singapore|Temasek|\bGIC\b|\bDBS\b|OCBC|\bUOB\b|"
     r"\bGrab\b|Sea Ltd|Shopee|CapitaLand|Keppel|Singtel|Wilmar|\bSGX\b"),
    ("vn", "Việt Nam", "Đông Nam Á", r"Vietnam|Viet Nam|Hanoi|Ho Chi Minh|VinFast|Vingroup|To Lam|Vietcombank|Masan"),
    ("id", "Indonesia", "Đông Nam Á", r"Indonesia|Jakarta|Prabowo|Bank Indonesia|rupiah|Danantara|\bGoTo\b|\bAstra\b|Pertamina|Bayan"),
    ("my", "Malaysia", "Đông Nam Á", r"Malaysia|Kuala Lumpur|\bAnwar\b|Bank Negara|ringgit|Petronas|Maybank|\bCIMB\b|Najib|"
     r"Sarawak|1MDB"),
    ("th", "Thái Lan", "Đông Nam Á", r"Thailand|\bThai\b|Bangkok|Bank of Thailand|\bbaht\b|\bPTT\b|CP Group|Charoen Pokphand|Anutin"),
    ("ph", "Philippines", "Đông Nam Á", r"Philippine|Filipino|Manila|Marcos|Bangko Sentral|\bAyala\b|SM Investments|Ramon Ang|"
     r"San Miguel|Jollibee"),
    ("asia_other", "Châu Á khác (Nam Á, Trung Á, Mông Cổ...)", "Châu Á",
     r"Sri Lanka|Pakistan|Bangladesh|Nepal|Mongolia|Papua New Guinea|Kazakhstan|Uzbekistan|Kyrgyz|Tajik|Turkmen|"
     r"Afghanistan|Cambodia|Laos|Myanmar|North Korea|Pyongyang|Kim Jong"),
    ("au", "Úc - New Zealand", "Châu Á", r"Australia|Sydney|Melbourne|\bRBA\b|Reserve Bank of Australia|Albanese|\bASX\b|\bBHP\b|"
     r"Rio Tinto|Macquarie|Commonwealth Bank|New Zealand|\bRBNZ\b|Qantas|Woodside|Fortescue|Westpac|\bANZ\b|Yarra"),
    ("gulf", "Vùng Vịnh (Saudi, UAE, Qatar)", "Trung Đông - châu Phi", r"Saudi|Riyadh|Aramco|\bPIF\b|Public Investment Fund|\bUAE\b|"
     r"Emirat|Abu Dhabi|Dubai|Mubadala|ADNOC|\bADIA\b|\bADQ\b|Qatar|Doha|\bQIA\b|Kuwait|Bahrain|\bOman\b|\bMGX\b|\bG42\b"),
    ("me", "Trung Đông khác (Israel, Iran, Thổ Nhĩ Kỳ...)", "Trung Đông - châu Phi", r"Israel|Netanyahu|\bGaza\b|\bIran|Tehran|"
     r"Hezbollah|Lebanon|Syria|\bIraq|Turkey|Turkish|Erdogan|Egypt|Yemen|Houthi|Jordan"),
    ("af", "Châu Phi", "Trung Đông - châu Phi", r"Africa|Nigeria|Kenya|Ethiopia|Ghana|Namibia|Mozambique|Morocco|Angola|Zambia"),
]
_CRX = [(cid, re.compile(rx)) for cid, _, _, rx in COUNTRIES]
COUNTRY = {cid: (lab, reg) for cid, lab, reg, _ in COUNTRIES}
COUNTRY["global"] = ("Toàn cầu - đa quốc gia", "Toàn cầu")
REGION_ORDER = ["Châu Mỹ", "Châu Âu", "Châu Á", "Đông Nam Á", "Trung Đông - châu Phi", "Toàn cầu"]


def country_of(title, lead=""):
    best, best_key = "global", None
    for cid, rx in _CRX:
        mt = list(rx.finditer(title))
        ml = rx.findall(lead[:500])
        if not mt and not ml:
            continue
        score = 3 * len(mt) + len(ml)
        key = (score, -(mt[0].start() if mt else 999))
        if best_key is None or key > best_key:
            best, best_key = cid, key
    return best


# Thông cáo báo chí, lịch sự kiện, thể thao, văn hóa - đời sống: không đưa vào bản tin
INTL_JUNK = re.compile(
    r"company announcement|eqs-news|\bannounces? (?:date|conference call|distribution|annual meeting|its \d|webcast)|"
    r"declares (?:distribution|dividend)|webinar|\bwatch bloomberg|market talk|roundup:|daily briefing|best books|"
    r"festival|symphony|scents?\b|transaction in own shares|mandatory notification|share lending|disavows|"
    r"to (?:host|hold) (?:investor|conference) call|to join virtual|fireside chat|podcast|\bquiz\b|crossword|"
    r"\bMLS\b|\bLIV\b|\bDP World Tour\b|semi-final|quarter-final|\bseed\b|\bNFL\b|\bNBA\b|\bNHL\b|\bMLB\b|"
    r"Rams|Dodgers|Yankees|Lakers|Mbappe|Griezmann|Messi|Ronaldo|hamstring|\bgolf\b|tennis|Wimbledon|Formula One|\bF1\b|"
    r"Premier League|Champions League|World Cup|Olympic|recipe|restaurant review|fashion week|\bnovel\b|film review|"
    r"how to spend|lunch with the ft|style\b|wine|vintage|horoscope", re.I)


# ------------------------------------------------------------------ nhóm chủ đề trong mỗi nước
CATS = [
    ("mna", "M&A - mua bán sáp nhập", None),
    ("funding", "Huy động vốn - IPO - trái phiếu - gọi vốn", re.compile(
        r"\bIPO\b|initial public offering|\blisting\b|\blists?\b .{0,15}\bshares\b|raises? \$|rais(?:e|es|ed|ing) .{0,25}"
        r"(?:billion|million|\bbn\b|fund)|funding round|Series [A-F]\b|valuation|bond (?:sale|issue|offering|deal|market debut)|"
        r"sells? .{0,20}bonds|notes? (?:offering|sale)|debt (?:sale|offering|deal)|\bloans?\b|financing|private credit|"
        r"fundrais|capital rais|rights (?:issue|offering)|placement|share sale|stock sale|convertible|refinanc|green bond|"
        r"sukuk|syndicated|credit facility|\bSPAC\b|go(?:es|ing)? public|float(?:ation)?\b", re.I)),
    ("energy", "Năng lượng - hàng hóa", re.compile(
        r"\boil\b|crude|\bOPEC|natural gas|\bgas\b(?! station)|\bLNG\b|energy|power plant|\bsolar\b|wind(?:farm| farm|power)?\b|"
        r"nuclear|\bcoal\b|copper|lithium|nickel|iron ore|commodit|\bmining\b|\bminers?\b|metals?\b|aluminium|aluminum|"
        r"\bwheat\b|soybean|cocoa|coffee", re.I)),
    ("macro", "Vĩ mô - ngân hàng trung ương - thương mại", re.compile(
        r"central bank|\bFed\b|Federal Reserve|\bECB\b|\bBOJ\b|Bank of (?:England|Japan|Korea|Canada|Thailand)|\bPBOC\b|\bRBI\b|"
        r"\bRBA\b|interest rates?|rate (?:hike|cut|rise|increase|decision)|inflation|\bCPI\b|\bGDP\b|econom|recession|jobs\b|"
        r"unemployment|payroll|deficit|budget|fiscal|tariff|trade (?:deal|war|surplus|deficit|talks|truce)|exports?\b|"
        r"imports?\b|stimulus|consumer (?:spending|confidence|prices)|retail sales|manufacturing|PMI\b|wages?\b|housing", re.I)),
    ("markets", "Thị trường tài chính", re.compile(
        r"\bstocks?\b|\bshares\b|equit|\bindex\b|indices|S&P|Nasdaq|\bDow\b|FTSE|Nikkei 225|Topix|Hang Seng|Kospi|Sensex|"
        r"markets?\b|traders?|investors?|\bbonds?\b|Treasur|yields?\b|currenc|dollar|\byen\b|\byuan\b|\beuro\b|\bgold\b|"
        r"bitcoin|crypto|hedge funds?|sell-?off|rally|volatil|ETF", re.I)),
    ("politics", "Chính trị - địa chính trị - pháp lý", re.compile(
        r"election|president|prime minister|parliament|congress|senate|minister|government|sanction|\bwar\b|military|"
        r"missile|attack|ceasefire|peace|talks|protest|court|lawsuit|impeach|summit|diplomat|security|defen[cs]e|spy|"
        r"regulator|antitrust|probe|investigat|\bban\b|bans|law\b|legislation|policy|vote|strike", re.I)),
    ("corp", "Doanh nghiệp - công nghệ", None),
]
CAT = {cid: lab for cid, lab, _ in CATS}


_LEGAL = re.compile(r"\bfine[sd]?\b|collusion|probe|lawsuit|\bsues?\b|\bsued\b|charged|indict|sanction|"
                    r"settle(?:s|d|ment)|fraud|penalt", re.I)


def category_of(title, lang="en"):
    if _LEGAL.search(title):
        return "politics"
    if is_deal(title, lang):
        return "mna"
    for cid, _, rx in CATS:
        if rx is not None and rx.search(title):
            return cid
    return "corp"


# ------------------------------------------------------------------ thu tin
_SITE_TERMS = ["China", "Japan", "India", "South Korea", "Taiwan", "Hong Kong", "Singapore", "Indonesia", "Malaysia",
               "Thailand", "Philippines", "Vietnam", "Australia", "Saudi Arabia", "UAE", "Qatar", "Israel", "Iran",
               "Russia", "Ukraine", "Germany", "France", "Italy", "Spain", "UK", "European Union", "Canada", "Brazil",
               "Mexico", "Africa", "acquisition", "merger", "takeover", "IPO", "bond sale", "raises funding",
               "private equity", "central bank", "earnings", "Fed"]


def site_queries():
    return [(f"site:{site} {term}", oid) for oid, site in SITES.items() for term in _SITE_TERMS]


def gnews_site(fetcher, hours, workers=6):
    days = max(1, round(hours / 24))

    def run(job):
        q, oid = job
        url = f"https://news.google.com/rss/search?q={quote_plus(q + f' when:{days}d')}&hl=en-US&gl=US&ceid=US:en"
        out = []
        for it in X.parse_feed(fetcher.get(url, ttl=1800) or ""):
            title = it["title"]
            m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", title)
            if m:
                title = m.group(1)
            out.append(dict(source_id=oid, source=OUTLETS[oid], group="INTL", tier=1, lang="en", url=it["url"],
                            title=title.strip(), desc="", paras=[], ts=it["ts"], via="gnews", company_hint=None))
        return out

    arts = []
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(run, site_queries()):
            arts += part
    return arts


def collect(fetcher, hours, full=False):
    o = Opts()
    o.hours = hours
    if full:
        o.max_sections, o.max_pages, o.max_articles = 120, 8, 800
    arts, reps = crawl_all(fetcher, o, only=set(OUTLETS))
    arts += gnews_site(fetcher, hours)
    cutoff = time.time() - hours * 3600
    keep = []
    for a in arts:
        name = outlet_of(a.get("source")) or (OUTLETS.get(a.get("source_id")) if a.get("source_id") in OUTLETS else None)
        if not name or (a.get("ts") and a["ts"] < cutoff):
            continue
        a["source"] = name
        keep.append(a)
    return keep, reps


# ------------------------------------------------------------------ làm giàu nội dung
_STOP = set("the a an of to in on for and with as at by from is are be its it this that after over into amid says said "
            "will new more than up down out".split())


def _toks(t):
    return {w for w in re.findall(r"[a-z0-9$€£]+", t.lower()) if w not in _STOP and len(w) > 1}


def _bing(fetcher, title):
    q = " ".join(title.split()[:14])
    xml = fetcher.get(f"https://www.bing.com/news/search?q={quote_plus(q)}&format=rss", ttl=6 * 3600) or ""
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        g = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1]
        link = html.unescape(g("link"))
        u = parse_qs(urlparse(link).query).get("url", [link])[0]
        out.append(dict(title=html.unescape(g("title")), url=u, desc=html.unescape(g("description")),
                        source=html.unescape(g("News:Source")), ts=X.parse_date(g("pubDate"))))
    return out


def enrich_one(fetcher, it):
    """-> (bullets, (nguồn, url)) hoặc None."""
    tk = _toks(it["title"])
    best = []
    for r in _bing(fetcher, it["title"]):
        host = urlparse(r["url"]).netloc.lower().removeprefix("www.")
        if not host or PAYWALL.search(host) or outlet_of(r["source"]):
            continue
        if r["ts"] and it.get("ts") and abs(r["ts"] - it["ts"]) > 4 * 86400:
            continue
        rt = _toks(r["title"] + " " + r["desc"][:200])
        inter = len(tk & rt)
        if inter >= 3 and inter / max(1, len(tk)) >= 0.35:
            best.append((inter / max(1, len(tk)), r))
    if not best:
        return None
    best.sort(key=lambda x: -x[0])
    for _, r in best[:2]:  # thử tải bài đầy đủ
        if "msn.com" in r["url"]:
            continue
        page = fetcher.get(r["url"])
        if not page:
            continue
        try:
            a = X.parse_article(page, r["url"], {})
        except Exception:
            continue
        if sum(len(p) for p in a["paras"]) >= 400:
            b = make_bullets(it["title"], a.get("desc") or r["desc"], a["paras"], it.get("topic", ""))
            if b and b[0]:
                return b, (r["source"] or urlparse(r["url"]).netloc, r["url"])
    descs = [shorten(r["desc"]) for _, r in best if len(r["desc"]) > 60]
    descs = list(dict.fromkeys(descs))[:2]
    if descs:
        r = best[0][1]
        return (descs + [""])[:2], (r["source"] or urlparse(r["url"]).netloc, r["url"])
    return None


def enrich(fetcher, items, limit, workers=8):
    todo = [i for i in items if not (i.get("bullets") and i["bullets"][0])][:limit]

    def run(it):
        try:
            return it, enrich_one(fetcher, it)
        except Exception:
            return it, None

    n = 0
    with ThreadPoolExecutor(workers) as ex:
        for it, res in ex.map(run, todo):
            if res:
                it["bullets"], it["enriched_from"] = res
                n += 1
    return n, len(todo)


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mut:#5c6370;--line:#e3e6ea;--acc:#0b63ce;--chip:#eef2f6;
--l5:#b42318;--l4:#dc6803;--l3:#ca8a04;--l2:#475467;--l1:#98a2b3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111317;--card:#1a1d22;--ink:#e8eaed;--mut:#9aa1ac;
--line:#2b2f36;--acc:#6aa8ff;--chip:#232831;--l5:#f97066;--l4:#fdb022;--l3:#facc15;--l2:#98a2b3;--l1:#667085}}
:root[data-theme="dark"]{--bg:#111317;--card:#1a1d22;--ink:#e8eaed;--mut:#9aa1ac;--line:#2b2f36;--acc:#6aa8ff;--chip:#232831;
--l5:#f97066;--l4:#fdb022;--l3:#facc15;--l2:#98a2b3;--l1:#667085}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:22px;margin:4px 0}.mut{color:var(--mut);font-size:13px}
h2{font-size:19px;margin:30px 0 6px;padding-top:6px;border-top:2px solid var(--line)}h2 small{color:var(--mut);font-weight:400;font-size:13px}
h3{font-size:15px;margin:16px 0 6px;color:var(--acc)}a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.nav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.nav a{background:var(--chip);color:var(--ink);padding:3px 9px;border-radius:999px;font-size:12.5px}
.nav a b{color:var(--l5);margin-left:4px}.nav span{font-size:12px;color:var(--mut);width:100%;margin-top:6px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.bar input{flex:1;min-width:180px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.bar button{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);cursor:pointer}
.bar button.on{background:var(--ink);color:var(--bg)}
.it{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.it .t{font-weight:600}.it ul{margin:6px 0 0;padding-left:18px}.it li{margin:3px 0}
.lv{display:inline-block;font-size:11px;font-weight:700;border-radius:6px;padding:1px 6px;color:#fff;margin-right:6px}
.lv5{background:var(--l5)}.lv4{background:var(--l4)}.lv3{background:var(--l3)}.lv2{background:var(--l2)}.lv1{background:var(--l1)}
.val{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 5px;margin-left:4px;color:var(--mut)}
.src{font-size:12.5px;color:var(--mut);margin-top:3px}.from{font-size:12px;color:var(--mut);margin-top:4px;font-style:italic}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:10px 0}
.kpi div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}.kpi b{font-size:20px;display:block}
[hidden]{display:none!important}
"""
JS = """
const q=document.getElementById('q'),bs=[...document.querySelectorAll('.bar button')];let lv=1;
function ap(){const s=q.value.trim().toLowerCase();let n=0;
document.querySelectorAll('.it').forEach(e=>{const ok=(+e.dataset.l>=lv)&&(!s||e.textContent.toLowerCase().includes(s));e.hidden=!ok;if(ok)n++});
document.querySelectorAll('section.cat').forEach(c=>c.hidden=!c.querySelector('.it:not([hidden])'));
document.querySelectorAll('section.cn').forEach(c=>c.hidden=!c.querySelector('.it:not([hidden])'));
document.getElementById('cnt').textContent=n+' tin'}
bs.forEach(b=>b.onclick=()=>{lv=+b.dataset.m;bs.forEach(x=>x.classList.toggle('on',x===b));ap()});
let tm;q.oninput=()=>{clearTimeout(tm);tm=setTimeout(ap,200)};ap();
"""


def _t(ts):
    return datetime.fromtimestamp(ts, VN_TZ).strftime("%H:%M %d/%m") if ts else ""


def _val(it):
    v = it.get("deal_usd")
    if not v:
        return ""
    s = f"~{v / 1000:.1f} tỷ USD" if v >= 1000 else f"~{v:.0f} triệu USD"
    return f"<span class=val>{s.replace('.', ',')}</span>"


def _card(it):
    e = html.escape
    b = [x for x in (it.get("bullets") or []) if x]
    body = "<ul>" + "".join(f"<li>{e(x)}</li>" for x in b) + "</ul>" if b else \
        "<div class=from>(Chỉ có tiêu đề — chưa tìm được bài tương tự để lấy nội dung)</div>"
    fr = it.get("enriched_from")
    frm = f"<div class=from>Nội dung tóm tắt từ bài tương tự trên <a href='{e(fr[1])}' target=_blank rel=noopener>{e(fr[0])}</a></div>" if fr else ""
    others = ", ".join(f"<a href='{e(u)}' target=_blank rel=noopener>{e(s)}</a>" for s, u in (it.get("others") or [])[:4]
                       if outlet_of(s))
    return (f"<div class=it data-l={it['level']}><div class=t><span class='lv lv{it['level']}'>{it['level']}</span>"
            f"<a href='{e(it['url'])}' target=_blank rel=noopener>{e(it['title'])}</a>{_val(it)}</div>"
            f"<div class=src>{e(it['source'])} · {_t(it.get('ts'))}{' · cùng đưa tin: ' + others if others else ''}</div>"
            f"{body}{frm}</div>")


def render(items, hours, now, stats):
    e = html.escape
    by = defaultdict(lambda: defaultdict(list))
    for it in items:
        by[it["country"]][it["cat"]].append(it)
    order = sorted(by, key=lambda c: (REGION_ORDER.index(COUNTRY[c][1]), -sum(len(v) for v in by[c].values())))
    out = [f"<title>Bản tin quốc tế</title><style>{CSS}</style><main>",
           f"<h1>Bản tin quốc tế theo quốc gia · {datetime.fromtimestamp(now, VN_TZ):%d/%m/%Y}</h1>",
           f"<div class=mut>Financial Times · Bloomberg · Nikkei Asia · The Wall Street Journal · Reuters · {hours} giờ qua "
           f"(đến {datetime.fromtimestamp(now, VN_TZ):%H:%M %d/%m})</div>"]
    src = Counter(i["source"] for i in items)
    out.append("<div class=kpi>" + f"<div><b>{len(items)}</b>tin</div>" + "".join(
        f"<div><b>{n}</b>{e(s)}</div>" for s, n in src.most_common()) +
        f"<div><b>{stats['enriched']}</b>tin được bổ sung nội dung từ nguồn khác</div></div>")
    nav = ""
    for reg in REGION_ORDER:
        cs = [c for c in order if COUNTRY[c][1] == reg]
        if cs:
            nav += f"<span>{e(reg)}</span>" + "".join(
                f"<a href='#c-{c}'>{e(COUNTRY[c][0])}<b>{sum(len(v) for v in by[c].values())}</b></a>" for c in cs)
    mna = sum(len(by[c]["mna"]) for c in by)
    fund = sum(len(by[c]["funding"]) for c in by)
    out.append(f"<div class=nav>{nav}<span>Theo loại tin: {mna} tin M&A · {fund} tin huy động vốn (IPO, trái phiếu, gọi vốn)</span></div>")
    out.append("<div class=bar><input id=q placeholder='Lọc theo từ khoá, công ty, nước…'>"
               "<button data-m=1 class=on>Tất cả</button><button data-m=3>Từ 3</button><button data-m=4>Từ 4</button>"
               "<button data-m=5>Chỉ 5</button><span id=cnt class=mut></span></div>")
    for c in order:
        n = sum(len(v) for v in by[c].values())
        out.append(f"<section class=cn id='c-{c}'><h2>{e(COUNTRY[c][0])} <small>{n} tin · {e(COUNTRY[c][1])}</small></h2>")
        for cat, _, _ in CATS:
            lst = by[c].get(cat)
            if not lst:
                continue
            lst.sort(key=lambda r: (-r["level"], -(r.get("deal_usd") or 0), -(r.get("ts") or 0)))
            out.append(f"<section class=cat><h3>{e(CAT[cat])} · {len(lst)}</h3>" + "".join(_card(i) for i in lst) + "</section>")
        out.append("</section>")
    out.append("<p class=mut>Phương pháp: tin lấy từ RSS của các báo và Google News (lọc đúng 5 báo). Tin bài trả phí chỉ có "
               "tiêu đề được tìm trên Bing News; nếu có bài cùng nội dung ở trang không thu phí thì tóm tắt từ bài đó (ghi rõ nguồn). "
               "Mỗi tin xếp vào nước được nhắc nhiều nhất trong tiêu đề; mức độ 1–5 do thuật toán chấm.</p></main>")
    out.append(f"<script>{JS}</script>")
    return "\n".join(out)


def dedupe(items):
    """Gộp tin cùng sự kiện (tiêu đề trùng >= 50% từ) trong cùng nước; giữ tin điểm cao, thêm link vào 'cùng đưa tin'."""
    kept, sigs = [], []
    for it in sorted(items, key=lambda r: (-r["score"], -(len((r.get("bullets") or [""])[0])))):
        tk = _toks(it["title"])
        dup = None
        for k, (c, s) in enumerate(sigs):
            if c == it["country"] and tk and len(tk & s) / max(1, len(tk | s)) >= 0.5:
                dup = kept[k]
                break
        if dup:
            dup.setdefault("others", [])
            dup["others"] = list(dup["others"]) + [(it["source"], it["url"])]
            if not (dup.get("bullets") and dup["bullets"][0]) and it.get("bullets") and it["bullets"][0]:
                dup["bullets"], dup["enriched_from"] = it["bullets"], it.get("enriched_from")
            continue
        kept.append(it)
        sigs.append((it["country"], tk))
    return kept


def classify(items):
    out = []
    for it in items:
        if INTL_JUNK.search(it["title"]):
            continue
        lead = " ".join(it.get("bullets") or [])
        it["country"] = country_of(it["title"], lead)
        it["cat"] = category_of(it["title"], it.get("lang", "en"))
        it["deal_usd"] = deal_usd(it["title"]) if it["cat"] in ("mna", "funding") else None
        out.append(it)
    return dedupe(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="news_crawler.intl")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--enrich", type=int, default=700, help="số tin chỉ có tiêu đề tối đa được bổ sung nội dung")
    ap.add_argument("--out", default="reports/quoc-te.html")
    ap.add_argument("--json")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--from-json", help="dựng lại từ JSON của lần chạy trước (không crawl lại), làm giàu tiếp tin còn thiếu")
    o = ap.parse_args(argv)
    t0 = time.time()
    f = Fetcher(cache_dir=o.cache)
    if o.from_json:
        d = json.load(open(o.from_json, encoding="utf-8"))
        items, now = d["items"], d["now"]
        for it in items:
            it.setdefault("lang", "en")
            it["others"] = [tuple(x) for x in it.get("others") or []]
            if it.get("enriched_from"):
                it["enriched_from"] = tuple(it["enriched_from"])
        n0 = sum(1 for i in items if i.get("enriched_from"))
    else:
        arts, reps = collect(f, o.hours, o.full)
        now = time.time()
        items = [i for i in build_items(arts, now) if not is_junk(i)]
        n0 = 0
        print(f"{len(arts)} bài của 5 báo", flush=True)
    items = classify(items)
    items.sort(key=lambda r: (-r["score"], -(r["ts"] or 0)))
    print(f"{len(items)} sự kiện sau lọc và gộp trùng; làm giàu nội dung…", flush=True)
    n, tried = enrich(f, items, o.enrich)
    n += n0
    print(f"  bổ sung nội dung {n}/{tried} tin chỉ có tiêu đề", flush=True)
    os.makedirs(os.path.dirname(o.out) or ".", exist_ok=True)
    open(o.out, "w", encoding="utf-8").write(render(items, o.hours, now, dict(enriched=n)))
    if o.json:
        keep = ("title", "url", "source", "ts", "bullets", "others", "level", "score", "topic", "country", "cat",
                "deal_usd", "enriched_from", "titans", "lang")
        json.dump(dict(items=[{k: i.get(k) for k in keep} for i in items], now=now, hours=o.hours),
                  open(o.json, "w", encoding="utf-8"), ensure_ascii=False)
    c = Counter(i["country"] for i in items)
    print("Theo nước:", dict(c.most_common()))
    print("Theo loại:", dict(Counter(i["cat"] for i in items)))
    print(f"Xong sau {time.time() - t0:.0f}s -> {o.out}")


if __name__ == "__main__":
    main()
