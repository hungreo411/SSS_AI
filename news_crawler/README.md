# Bản tin tổng hợp: crawler đa nguồn ra 1 file HTML tĩnh

Mỗi lần chạy, crawler đọc khoảng 45 nguồn báo trong nước và quốc tế. Với mỗi báo, nó đi qua **trang chủ, toàn bộ chuyên mục trên menu, từng trang phân trang, RSS và sitemap tin mới**, rồi mở từng bài để lấy tiêu đề và nội dung. Kết quả là **một file HTML tĩnh** gồm các cột:

| Topic | Tiêu đề báo | Nội dung chính (2 bullet) | Mức độ quan trọng (1–5) |
|---|---|---|---|

- **2 bullet** được trích nguyên văn từ bài, không viết lại: bullet 1 là sapo, bullet 2 là câu có nhiều dữ kiện và số liệu nhất trong thân bài.
- **Gộp tin trùng**: nhiều báo đưa cùng một sự kiện thì chỉ giữ một dòng, kèm link "cùng đưa tin" sang các báo còn lại. Càng nhiều báo đưa tin thì điểm càng cao.
- **Mức độ quan trọng** được chấm tự động theo topic, từ khoá tác động (Bộ Chính trị, nghị quyết, lãi suất, tỷ USD, khởi công…), quy mô số liệu, uy tín nguồn, số báo cùng đưa tin và độ mới.
- Đầu file có mục **Tiêu điểm** (30 tin quan trọng nhất). Cuối file có bảng **tình trạng quét từng nguồn**, cho biết báo nào lỗi hoặc bị chặn.

## Chạy

```bash
pip install -r requirements.txt
python -m news_crawler                       # 24h gần nhất, ra reports/ban-tin-YYYYMMDD-HHMM.html
python -m news_crawler --hours 48 --full     # quét sâu: 120 chuyên mục, 8 trang/chuyên mục, 800 bài/báo
python -m news_crawler --only vnexpress,cafef,baochinhphu -v
python -m news_crawler --min-level 3         # chỉ xuất tin từ mức "Trung bình" trở lên
python -m news_crawler --list                # xem danh sách nguồn
```

Cách khác là chạy trên GitHub: vào **Actions → "Ban tin tong hop" → Run workflow**, đợi chạy xong rồi tải file `ban-tin.html` trong phần Artifacts.

Lần chạy đầu mất vài phút. Bài đã đọc được cache vào `.cache/`, nên các lần sau nhanh hơn nhiều.

## Topic

Thứ tự hiển thị: Bầu cử giữa kỳ Mỹ · Bầu cử & nhân sự Trung Quốc · Bộ Chính trị Việt Nam · Chính trị, chính sách, Quốc hội VN · Trung tâm tài chính quốc tế · Doanh nghiệp VN100 · Chứng khoán VN · Kinh tế vĩ mô · Lãi suất, tiền tệ, ngân hàng · Tỷ giá, vàng, hàng hoá · Dòng vốn nước ngoài · Các quỹ đầu tư · FDI · Đầu tư công · Hạ tầng TP.HCM · Cái Mép, Bình Giã, Châu Đức, Hồ Tràm · Bất động sản · Thương mại & thuế quan · Kinh tế Trung Quốc · Chính trị, chính sách Mỹ · Địa chính trị & xung đột · Công nghệ, AI, bán dẫn · Thanh tra, pháp luật, chống tham nhũng · Kinh tế, doanh nghiệp (khác) · Thời sự khác.

Muốn thêm topic hoặc từ khoá thì sửa `topics.py`. Danh sách VN100 (mã và tên doanh nghiệp) cũng nằm trong file này.

## Nguồn

Sửa nguồn trong `sources.py`. Muốn thêm một báo, chỉ cần khai báo `id`, `name`, `home`; crawler sẽ tự dò menu chuyên mục, RSS và sitemap.

- **Chính phủ / Đảng / Quốc hội**: Báo Điện tử Chính phủ, Cổng TTĐT Chính phủ, Quốc hội, Đại biểu Nhân dân, Thanh tra Chính phủ, Báo Thanh tra, Nhân Dân, Tạp chí Cộng sản, VietnamPlus (TTXVN), NHNN.
- **Báo tổng hợp**: VnExpress, Tuổi Trẻ, Thanh Niên, Dân trí, VietNamNet, Người Lao Động, SGGP, Pháp Luật TP.HCM, ZNews, Báo Bà Rịa - Vũng Tàu.
- **Kinh tế, tài chính**: CafeF, VnEconomy (Thời báo Kinh tế VN), Thời báo Kinh tế Sài Gòn, Người Quan Sát, Báo Đầu tư, Đầu tư Chứng khoán, Vietstock, Tạp chí Tài chính, VnExpress International.
- **Quốc tế**: FT, Bloomberg, WSJ, Nikkei Asia, Reuters, The Economist, NYT, AP, CNBC, Politico, BBC, Guardian, SCMP, Caixin, Al Jazeera, The Diplomat.
- **Google News**: quét bổ sung theo từng topic (Cái Mép, Hồ Tràm, Bộ Chính trị, FDI…) và theo `site:` cho các báo trả phí.

**Báo trả phí** (FT, Bloomberg, WSJ, Nikkei, NYT, Economist…) chỉ cho đọc tiêu đề và sapo qua RSS. Crawler không vượt paywall, nên với các báo này bullet có thể chỉ gồm sapo hoặc chỉ có tiêu đề.

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Bộ test dựng một trang báo giả trên localhost (trang chủ, chuyên mục, phân trang, RSS, sitemap, bài viết) và chạy toàn bộ pipeline: crawl, phân topic, tóm tắt, gộp tin, xuất HTML.

## Lưu ý

- Crawler giới hạn 2 kết nối và 0,4 giây nghỉ giữa các request cho mỗi domain. Chỉ dùng cho mục đích cá nhân và tôn trọng điều khoản của từng báo.
- Cấu trúc HTML của báo thay đổi thì regex hoặc selector trong `sources.py` có thể lệch. Khi đó crawler tự chuyển sang heuristic chung, và bảng "tình trạng quét" cho biết nguồn nào cần chỉnh.
