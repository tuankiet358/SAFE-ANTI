<div align="center">
<h1>SAFE-ANTI 2.0</h1>
<p><b>Giải pháp Bảo vệ và AutoMod Máy chủ Discord Toàn diện - Hiệu năng cao và Chuyên nghiệp</b></p>
Python
Discord.py
License
Support
<br />
<a href="[https://github.com/tuankiet358/SAFE-ANTI/archive/refs/heads/main.zip](https://github.com/tuankiet358/SAFE-ANTI/archive/refs/heads/main.zip)">
<img src="[https://img.shields.io/badge/TAI_VE_MA_NGUON_(.ZIP)-2ea44f?style=for-the-badge&logoColor=white](https://img.shields.io/badge/TAI_VE_MA_NGUON_(.ZIP)-2ea44f?style=for-the-badge&logoColor=white)" alt="Download ZIP" />
</a>
<a href="[https://github.com/tuankiet358/SAFE-ANTI/releases/latest](https://github.com/tuankiet358/SAFE-ANTI/releases/latest)">
<img src="[https://img.shields.io/badge/XEM_BAN_RELEASE_MOI_NHAT-0969da?style=for-the-badge&logoColor=white](https://img.shields.io/badge/XEM_BAN_RELEASE_MOI_NHAT-0969da?style=for-the-badge&logoColor=white)" alt="Latest Release" />
</a>
</div>

## Giới thiệu Dự án
SAFE-ANTI là hệ thống Discord Bot chuyên dụng cho công tác bảo mật và kiểm duyệt máy chủ, phát triển trên nền tảng Python (discord.py v2) với kiến trúc Modular/Cog hiện đại.
Hệ thống cung cấp lớp bảo vệ nhiều tầng giúp chống phá hoại (Anti-Nuke), kiểm soát thành viên quá khích, tích hợp Discord AutoMod API chuẩn xác và đi kèm giao diện tương tác trực quan bằng Buttons và Select Menus.

## Các Tính Năng Nổi Bật

| Tính năng | Mô tả chi tiết |
| :--- | :--- |
| Anti-Nuke / Anti-Raid | Phát hiện và ngăn chặn tức thì hành vi xóa kênh hàng loạt, ban/kick người dùng bất thường hoặc đổi cấu hình server trái phép. |
| Discord AutoMod Native | Tích hợp sâu vào API AutoMod của Discord để xử lý tin nhắn rác, link độc hại với tốc độ tính bằng mili-giây. |
| Giao diện UI/UX Tương tác | Bảng điều khiển (Dashboard) ngay trên Discord bằng Dropdown Menu và Button giúp quản trị viên dễ dàng cài đặt mà không cần gõ lệnh phức tạp. |
| Hệ thống Logging Chi tiết | Ghi nhận chi tiết mọi sự kiện nghi vấn dưới dạng tin nhắn nhúng (Embed) về kênh Log quản trị. |
| Global Rate Limiter | Cơ chế cooldown toàn cục tự động cô lập các đối tượng thực hiện hành vi spam / nuke liên tục. | <br> ## Cấu trúc Mã nguồn (Source Tree) <br> SAFE-ANTI/ <br> ├── .env.example              # Mẫu tệp cấu hình biến môi trường <br> ├── .gitignore                # Danh sách tệp loại trừ khỏi Git <br> ├── LICENSE                   # Giấy phép nguồn mở GPL-3.0 <br> ├── README.md                 # Tài liệu hướng dẫn dự án <br> ├── requirements.txt          # Danh sách thư viện Python phụ thuộc <br> └── src/ <br> ├── main.py               # File khởi chạy chính của Bot <br> ├── config.py             # Cấu hình toàn cục và thiết lập Token <br> ├── global_cooldown.py    # Bộ kiểm soát tần suất truy cập toàn cục <br> ├── database/ <br> │   ├── **init**.py       # Quản lý kết nối CSDL <br> │   └── anti_settings.db  # CSDL lưu thiết lập Anti riêng từng Server <br> ├── utils/ <br> │   ├── **init**.py <br> │   ├── embed.py          # Mẫu Embed giao diện chuẩn <br> │   └── logger.py         # Hệ thống ghi nhật ký hoạt động <br> └── cogs/ <br> └── anti/             # Module Anti chính <br> ├── **init**.py   # Khởi tạo Cog và đăng ký Event Listener <br> ├── constants.py  # Hằng số, hằng số cấu hình và màu sắc <br> ├── helpers.py    # Hàm bổ trợ định dạng UI/Log <br> ├── automod.py    # Xử lý quy tắc Discord AutoMod API <br> ├── ui.py         # Giao diện Button, Dropdown Menu <br> └── anti_cog.py   # Logic phát hiện và xử lý vi phạm <br> ## Hướng dẫn Cài đặt và Khởi chạy <br> ### 1. Yêu cầu Hệ thống <br> * Python 3.10 trở lên. <br> * Một Discord Bot Token tạo từ Discord Developer Portal (https://discord.com/developers/applications). <br> ### 2. Cài đặt Phụ thuộc <br> Tải mã nguồn về máy, mở Terminal / Command Prompt tại thư mục dự án và chạy: <br> pip install -r requirements.txt <br> ### 3. Cấu hình Môi trường <br> Tạo tệp .env dựa trên .env.example và điền Token của bạn: <br> DISCORD_TOKEN=ma_thong_bao_bot_cua_ban_o_day <br> BOT_PREFIX=! <br> ### 4. Khởi chạy Bot <br> python src/main.py <br> ## Cộng đồng và Hỗ trợ <br> Nếu bạn gặp bất kỳ lỗi nào hoặc muốn đóng góp ý kiến phát triển dự án, hãy tham gia máy chủ Discord của chúng tôi: <br> Tham gia ngay: TWIN CORE Discord Studio <br> <div align="center"> <br> <p>Được phát triển bởi tuankiet358 | Được tài trợ và phát triển bởi TWIN CORE Studio dành cho Cộng đồng Discord</p>

</div>
