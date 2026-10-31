"""Kiểm thử offline: dựng 1 "tờ báo" giả trên localhost (trang chủ, chuyên mục, phân trang, RSS, sitemap, bài viết)
và chạy toàn bộ pipeline crawl -> phân topic -> tóm tắt -> gom tin -> HTML.

Chạy: python -m unittest discover -s tests -v
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from news_crawler import crawl as C  # noqa: E402
from news_crawler import extract as X  # noqa: E402
from news_crawler.digest import bullets  # noqa: E402
from news_crawler.fetch import Fetcher  # noqa: E402
from news_crawler.render import build_items, render  # noqa: E402
from news_crawler.topics import classify, find_vn100  # noqa: E402

TZ = timezone(timedelta(hours=7))
NOW = datetime.now(TZ)
ISO = lambda h: (NOW - timedelta(hours=h)).isoformat(timespec="seconds")  # noqa: E731

ARTICLES = {
    "/kinh-doanh/lai-suat-huy-dong-giam-1234567.html": (
        "Ngân hàng Nhà nước giữ nguyên lãi suất điều hành, lãi suất huy động tiếp tục giảm", 2,
        "Ngân hàng Nhà nước quyết định giữ nguyên lãi suất điều hành trong tháng 10 nhằm hỗ trợ tăng trưởng.",
        ["Theo thông báo, lãi suất tái cấp vốn giữ ở mức 4,5%/năm.",
         "Tăng trưởng tín dụng toàn hệ thống đến cuối tháng 10 đạt 14,2%, cao nhất 5 năm, tương đương 2,3 triệu tỷ đồng.",
         "Nhiều ngân hàng như Vietcombank, BIDV đã giảm lãi suất huy động kỳ hạn 12 tháng thêm 0,2 điểm phần trăm."]),
    "/kinh-doanh/cang-cai-mep-mo-rong-2345678.html": (
        "Phê duyệt quy hoạch mở rộng cảng Cái Mép Hạ, vốn 2 tỷ USD", 5,
        "Thủ tướng phê duyệt quy hoạch khu bến cảng Cái Mép Hạ và khu thương mại tự do gắn với cảng.",
        ["Dự án có tổng vốn khoảng 2 tỷ USD, dự kiến khởi công năm 2027.",
         "Khu vực Châu Đức và Hồ Tràm được định hướng phát triển công nghiệp, logistics và du lịch.",
         "Tuyến cao tốc Biên Hòa - Vũng Tàu sẽ kết nối trực tiếp tới cảng Cái Mép."]),
    "/thoi-su/bo-chinh-tri-ket-luan-3456789.html": (
        "Bộ Chính trị ban hành kết luận về trung tâm tài chính quốc tế tại TP.HCM", 1,
        "Bộ Chính trị yêu cầu khẩn trương vận hành trung tâm tài chính quốc tế tại TP.HCM và Đà Nẵng.",
        ["Tổng Bí thư Tô Lâm nhấn mạnh trung tâm tài chính quốc tế phải có cơ chế vượt trội.",
         "Theo Nghị quyết 222, các nhà đầu tư được hưởng ưu đãi thuế thu nhập doanh nghiệp 10% trong 30 năm."]),
    "/the-gioi/bau-cu-giua-ky-my-4567890.html": (
        "Bầu cử giữa kỳ Mỹ: đảng Dân chủ và Cộng hòa giằng co ở các bang chiến trường", 3,
        "Còn vài ngày trước bầu cử giữa kỳ, thăm dò cho thấy cuộc đua kiểm soát Hạ viện Mỹ rất sát sao.",
        ["Hơn 40 triệu cử tri đã bỏ phiếu sớm, theo số liệu tổng hợp.",
         "Đảng Cộng hòa cần giữ ít nhất 218 ghế để duy trì đa số tại Hạ viện."]),
    "/kinh-doanh/hpg-lai-quy-3-5678901.html": (
        "HPG báo lãi quý III tăng 40%, khối ngoại mua ròng mạnh", 30,  # ngoài khung 24h -> bị loại
        "Hòa Phát công bố lợi nhuận quý III.", ["Lợi nhuận sau thuế đạt 4.000 tỷ đồng."]),
}
# bài trùng sự kiện từ báo thứ hai (để kiểm tra gom tin)
DUP = {"/tin/cai-mep-ha-quy-hoach-9876543.html": (
    "Thủ tướng phê duyệt quy hoạch mở rộng cảng Cái Mép Hạ, vốn 2 tỷ USD", 4,
    "Quy hoạch cảng Cái Mép Hạ vừa được phê duyệt.", ["Cảng sẽ tiếp nhận tàu 250.000 DWT."])}


def article_html(title, h, sapo, paras):
    ps = "".join(f'<p class="Normal">{p}</p>' for p in paras)
    return f"""<html><head><title>{title} - Báo Thử</title><meta property="og:title" content="{title}">
<meta property="og:description" content="{sapo}"><meta property="article:published_time" content="{ISO(h)}">
</head><body><h1>{title}</h1><article class="fck_detail">{ps}</article></body></html>"""


def make_handler(pages):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path.split("?")[0] + ("?" + self.path.split("?")[1] if "?" in self.path else ""))
            if body is None:
                body = pages.get(self.path.split("?")[0])
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=utf-8" if body.startswith("<?xml")
                             else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    return H


class OfflinePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {}
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.pages))
        port = cls.srv.server_address[1]
        cls.base = f"http://127.0.0.1:{port}"
        b = cls.base
        a = list(ARTICLES)
        for path, (t, h, s, p) in ARTICLES.items():
            cls.pages[path] = article_html(t, h, s, p)
        # trang chủ: menu chuyên mục + 1 bài + link chuyên mục bị blacklist
        cls.pages["/"] = f"""<html><head><link rel="alternate" type="application/rss+xml" href="/rss/tin-moi.rss"></head>
<body><nav><a href="/kinh-doanh">Kinh doanh</a><a href="/thoi-su">Thời sự</a><a href="/the-thao">Thể thao</a></nav>
<a href="{a[2]}">{ARTICLES[a[2]][0]}</a></body></html>"""
        cls.pages["/kinh-doanh"] = f'<html><body><a href="{a[0]}">x</a><a href="{a[4]}">y</a></body></html>'
        cls.pages["/kinh-doanh-p2"] = f'<html><body><a href="{a[1]}">Cái Mép</a></body></html>'
        cls.pages["/kinh-doanh-p3"] = f'<html><body><a href="{a[1]}">Cái Mép</a></body></html>'
        cls.pages["/thoi-su"] = f'<html><body><a href="{a[2]}">BCT</a></body></html>'
        cls.pages["/the-thao"] = '<html><body><a href="/the-thao/tran-dau-1111111.html">bóng đá</a></body></html>'
        cls.pages["/rss/tin-moi.rss"] = f"""<?xml version="1.0" encoding="UTF-8"?><rss><channel>
<item><title>{ARTICLES[a[3]][0]}</title><link>{b}{a[3]}</link><pubDate>{(NOW - timedelta(hours=3)).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>
<description><![CDATA[<p>{ARTICLES[a[3]][2]}</p>]]></description></item></channel></rss>"""
        # báo thứ hai: chỉ có sitemap
        for path, (t, h, s, p) in DUP.items():
            cls.pages[path] = article_html(t, h, s, p)
        cls.pages["/b2/"] = "<html><body>trống</body></html>"
        cls.pages["/robots.txt"] = f"User-agent: *\nSitemap: {b}/sitemap-news.xml\n"
        cls.pages["/sitemap-news.xml"] = f"""<?xml version="1.0" encoding="UTF-8"?><urlset
xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url><loc>{b}{list(DUP)[0]}</loc>
<news:news><news:publication_date>{ISO(4)}</news:publication_date><news:title>{DUP[list(DUP)[0]][0]}</news:title></news:news></url></urlset>"""
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.cache = tempfile.mkdtemp()
        cls.orig = C.SOURCES
        C.SOURCES = [
            dict(id="baothu", name="Báo Thử", group="VN", tier=2, home=b + "/", sections=["/kinh-doanh"],
                 article_re=r"/[\w-]+-\d{6,}\.html$", page_tpl="{url}-p{n}", content_sel="article.fck_detail p"),
            dict(id="bao2", name="Báo Hai", group="VN-KT", tier=2, home=b + "/b2/", sitemap=True),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        C.SOURCES = cls.orig
        shutil.rmtree(cls.cache, ignore_errors=True)

    def test_pipeline(self):
        o = C.Opts()
        o.gnews = False
        o.verbose = True
        f = Fetcher(cache_dir=self.cache, delay=0)
        arts, reps = C.crawl_all(f, o)
        urls = {a["url"].replace(self.base, "") for a in arts}
        self.assertIn("/kinh-doanh/cang-cai-mep-mo-rong-2345678.html", urls, "phải đi được trang 2 của chuyên mục")
        self.assertIn("/the-gioi/bau-cu-giua-ky-my-4567890.html", urls, "phải lấy được bài từ RSS")
        self.assertIn(list(DUP)[0], urls, "phải lấy được bài từ sitemap")
        self.assertNotIn("/kinh-doanh/hpg-lai-quy-3-5678901.html", urls, "bài quá 24h phải bị loại")
        self.assertFalse(any("the-thao" in u for u in urls), "chuyên mục thể thao bị bỏ qua")

        now = time.time()
        items = build_items(arts, now)
        by_title = {i["title"]: i for i in items}
        cm = next(i for i in items if "Cái Mép" in i["title"])
        self.assertEqual(cm["topic"], "cai_mep")
        self.assertEqual(cm["n_sources"], 2, "2 báo cùng đưa tin Cái Mép phải gộp thành 1 sự kiện")
        self.assertGreaterEqual(cm["level"], 4)
        ls = by_title["Ngân hàng Nhà nước giữ nguyên lãi suất điều hành, lãi suất huy động tiếp tục giảm"]
        self.assertEqual(ls["topic"], "lai_suat")
        self.assertIn("14,2%", ls["bullets"][1], "bullet 2 phải là câu nhiều số liệu nhất")
        self.assertEqual(next(i for i in items if "Bộ Chính trị" in i["title"])["topic"], "tttc")
        self.assertEqual(next(i for i in items if "giữa kỳ" in i["title"])["topic"], "bau_cu_my")

        html = render(items, reps, o, now)
        self.assertIn("Tiêu điểm", html)
        self.assertIn("Cái Mép - Bình Giã - Châu Đức - Hồ Tràm", html)
        out = os.path.join(os.path.dirname(__file__), "..", "reports", "_offline_test.html")
        if os.environ.get("KEEP_HTML"):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(html)


class Units(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify("Khối ngoại bán ròng 1.200 tỷ đồng phiên thứ 5 liên tiếp", "")[0], "von_ngoai")
        self.assertEqual(classify("Giải ngân vốn đầu tư công 10 tháng đạt 60% kế hoạch", "")[0], "dau_tu_cong")
        self.assertEqual(classify("Xi Jinping tightens grip at Communist Party plenum", "")[0], "chinh_tri_tq")
        self.assertEqual(classify("Khởi công đoạn Vành đai 4 TP.HCM qua Bình Dương", "")[0], "ha_tang_hcm")
        self.assertEqual(classify("Dragon Capital: quỹ ngoại rót thêm vốn vào cổ phiếu ngân hàng", "")[0], "quy_dau_tu")
        self.assertEqual(classify("Vốn FDI đăng ký 10 tháng tăng 15%", "")[0], "fdi")
        self.assertNotEqual(classify("Bộ Chính trị Trung Quốc họp bàn kinh tế", "")[0], "bct_vn")
        self.assertEqual(classify("Ai sẽ thắng trận chung kết?", "")[0], "khac", "'ai' tiếng Việt không phải AI")

    def test_vn100(self):
        self.assertEqual(find_vn100("Cổ phiếu HPG và Vinamilk tăng mạnh"), ["HPG", "VNM"])
        self.assertEqual(find_vn100("Giá GAS hôm nay"), [])

    def test_dates(self):
        self.assertIsNotNone(X.parse_date("Thứ sáu, 31/10/2026, 08:30 (GMT+7)"))
        self.assertIsNotNone(X.parse_date("Fri, 31 Oct 2026 01:00:00 GMT"))
        self.assertIsNotNone(X.parse_date("2026-10-31T08:30:00+07:00"))

    def test_page_tpl(self):
        self.assertEqual(X.page_url("https://tuoitre.vn/kinh-doanh.htm", 2, "{stem}/trang-{n}{ext}"),
                         "https://tuoitre.vn/kinh-doanh/trang-2.htm")
        self.assertEqual(X.page_url("https://cafef.vn/vi-mo-dau-tu.chn", 3, "{stem}/trang-{n}{ext}"),
                         "https://cafef.vn/vi-mo-dau-tu/trang-3.chn")
        self.assertEqual(X.page_url("https://vnexpress.net/kinh-doanh", 2, "{url}-p{n}"),
                         "https://vnexpress.net/kinh-doanh-p2")
        self.assertEqual(X.page_url("https://thesaigontimes.vn/dia-oc/", 2, "{urls}page/{n}/"),
                         "https://thesaigontimes.vn/dia-oc/page/2/")

    def test_gnews_feed(self):
        xml = """<?xml version="1.0"?><rss><channel><item><title>Fed holds rates steady - Reuters</title>
<link>https://news.google.com/rss/articles/abc</link><pubDate>Fri, 31 Oct 2026 01:00:00 GMT</pubDate>
<source url="https://www.reuters.com">Reuters</source></item></channel></rss>"""
        it = X.parse_feed(xml)[0]
        self.assertEqual(it["source_name"], "Reuters")
        self.assertEqual(classify("Fed holds rates steady", "")[0], "lai_suat")

    def test_bullets_prefix(self):
        b = bullets("Tiêu đề", "(Dân trí) - Thủ tướng yêu cầu đẩy nhanh giải ngân vốn đầu tư công trong quý IV.", [],
                    "dau_tu_cong")
        self.assertTrue(b[0].startswith("Thủ tướng"))


if __name__ == "__main__":
    unittest.main()
