# Quy Tắc & Hướng Dẫn Dự Án (Project Rules)
## 1. Đồng bộ với Giao Diện Web (`web_server_v3.py`)
- **Bắt buộc kiểm tra**: Mỗi khi có thay đổi ảnh hưởng đến tính năng, cấu hình, giao diện, nút bấm, ô chọn (combobox/option menu), ô tích (checkbox/switch) hay API điều khiển, **PHẢI luôn đồng bộ tương ứng sang `web_server_v3.py`** (cổng mặc định `8081` cho Tab 1, các Tab tiếp theo `8082`, `8083`... và Trang Tổng Quản Hub Gateway `8080`).
- **Thông báo rõ ràng**: Đối với các thay đổi thuần logic xử lý ngầm (như thời gian hoãn sleep, tọa độ click nội bộ, thuật toán...) không tác động đến giao diện/API Web, không cần sửa `web_server_v3.py`, nhưng **bắt buộc phải thông báo rõ cho người dùng**: *"Những thay đổi này thuộc logic nội bộ, không ảnh hưởng đến giao diện Web."*

## 2. Đồng bộ Thư mục Đóng Gói (`dist/`)
- Mọi thay đổi về file tài nguyên (hình ảnh trong `assets/`, cấu hình trong `config.json`, file khởi động `launch_app.vbs`, `Tao_Loi_Tat_Desktop.bat`) phải được sao chép/đồng bộ sang thư mục `dist/`.
- Khi có thay đổi mã nguồn cốt lõi (`main_v3.py`, `web_server_v3.py`), thực hiện build lại file chạy `dist/TS_Origin_Control_V3.exe` (qua `python build_v3.py`) để đảm bảo người dùng chạy file `.exe` luôn có bản cập nhật mới nhất.

## 3. Tuyệt Đối Không Can Thiệp Vào Bản Hoạt Động (`C:\LDPlayer\dist`)
- Khi đóng gói file `.exe` hoặc làm việc, **chỉ xuất và xử lý trong phạm vi thư mục của project (`dist/`)**. Thư mục đóng gói chia sẻ (`dist_share/`) **chỉ được tạo khi người dùng có yêu cầu cụ thể**, bình thường không tự ý tạo hay đóng gói vào thư mục này.
- **Tuyệt đối không tự ý sao chép, đồng bộ hay ghi đè** sang thư mục Bản hoạt động (ví dụ `C:\LDPlayer\dist` hoặc các thư mục bên ngoài). Việc cập nhật vào bản hoạt động người dùng sẽ tự mình thay thế vào sau khi kiểm tra xong.

## 4. Bảo Vệ File Khi Dọn Dẹp (Cleanup Protection)
- **Tuyệt đối không xóa**: Khi có yêu cầu dọn dẹp file rác, file tạm, file không sử dụng trong dự án, **KHÔNG ĐƯỢC XÓA** các file `test_dpad.py`, `test_swipe_team.py`, toàn bộ các thư mục dự án phụ `buff_train_ldplayer/`, `buff_train_bluestacks/` và các file/thư mục liên quan đến `screenshot` (bao gồm `screenshot.py` và các hình ảnh screenshot).

## 5. Dọn Dẹp File Rác Sau Khi Đóng Gói `buff_train_bluestacks`
- Sau khi thực hiện đóng gói trong thư mục `buff_train_bluestacks/` (qua `build_exe.py`), các file và thư mục tạm phát sinh từ quá trình build (bao gồm thư mục `build/`, file spec `TS_Buff_Train_BlueStacks.spec`, và cache `__pycache__/`) **bắt buộc phải được xóa bỏ sạch sẽ**, chỉ giữ lại file thực thi và tài nguyên cần thiết trong `buff_train_bluestacks/dist/`.

## 6. Không Tự Ý Chỉnh Sửa Công Cụ Thử Nghiệm
- **Ngưng chỉnh sửa**: Tuyệt đối **KHÔNG ĐƯỢC TỰ Ý CHỈNH SỬA**, can thiệp hay thay đổi mã nguồn các file công cụ thử nghiệm (như `test_swipe_team.py`, `test_dpad.py` hoặc các file test khác), **CHỈ chỉnh sửa KHI CÓ YÊU CẦU CỤ THỂ TỪ NGƯỜI DÙNG**.

