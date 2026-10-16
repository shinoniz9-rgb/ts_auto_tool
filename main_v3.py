import customtkinter as ctk
import subprocess
import os
import threading
import time
import json
from datetime import datetime, timedelta
import cv2
import numpy as np
import unicodedata
import re
import sys
import tempfile
import multiprocessing
from tkinter import filedialog
import webbrowser
import web_server_v3 as web_server
import updater
from version import APP_VERSION

def get_app_dir():
    """Lấy đường dẫn thư mục thực tế chứa file .exe (hoặc script main.py)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir():
    """Lấy đường dẫn chứa tài nguyên nội bộ đóng gói bởi PyInstaller (_MEIPASS)"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

# Thử import pystray & PIL cho tính năng khay hệ thống (System Tray) và cắt ảnh
try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ==============================================================================
# HỆ THỐNG GIAO DIỆN CHUẨN (DESIGN SYSTEM ĐỒNG BỘ THEO APP_UI)
# ==============================================================================
FONT_FAMILY = "Segoe UI"

COLOR_BG_MAIN = "#121317"         # Nền chính cửa sổ
COLOR_CARD_BG = "#1a1c23"         # Nền các khung chính (Header, Tabview, Footer)
COLOR_CARD_INNER = "#14161c"      # Nền các card/khung con bên trong
COLOR_BTN_NAVY = "#2c3545"        # Màu nút chuẩn (Thoát, 📁, Tab Active)
COLOR_BTN_NAVY_HOVER = "#3a455a"  # Hiệu ứng hover nút chuẩn
COLOR_INPUT_BG = "#25272e"        # Nền ô chọn (Main, Tab Inactive)
COLOR_INPUT_BORDER = "#3d4049"    # Viền ô chọn
COLOR_COMBO_BG = "#374151"        # Nền thân ô menu drop (theo mẫu ảnh)
COLOR_COMBO_BTN = "#4b5563"       # Nền nút mũi tên menu drop (theo mẫu ảnh)
COLOR_COMBO_BTN_HOVER = "#6b7280" # Nền hover nút mũi tên menu drop
COLOR_COMBO_POPUP_BG = "#1f2937"  # Nền popup menu khi xổ xuống
COLOR_COMBO_POPUP_HOVER = "#374151" # Nền hover mục trong popup xổ xuống
COLOR_BTN_GAME = "#00875a"        # Nút Mở / Game (Xanh lục bảo)
COLOR_BTN_GAME_HOVER = "#00724c"
COLOR_BTN_STOP = "#d32f2f"        # Nút Stop (Đỏ tươi)
COLOR_BTN_STOP_HOVER = "#b71c1c"
COLOR_TEXT_MAIN = "#ffffff"       # Màu chữ chính (Trắng sắc nét)
COLOR_TEXT_MUTED = "#8c93a8"      # Màu chữ phụ / trạng thái
COLOR_TEXT_DIM = "#5c6378"        # Màu chữ mờ / tác giả
COLOR_ACCENT = "#38bdf8"          # Xanh dương / Electric Cyan điểm nhấn
COLOR_ORANGE = "#ea580c"          # Cam ấm cho công tắc & checkbox
COLOR_ORANGE_HOVER = "#c2410c"

class ToolLDPlayerGUI(ctk.CTk):
    # Danh sách 10 vị trí thành viên trong đội (ROI chuẩn 1280x720, w=20, h=11 gồm 6px HP đỏ + 5px SP xanh)
    # Thứ tự ưu tiên cứu: Hàng Sau (HS) 1->5 trước, sau đó Hàng Trước (HT) 1->5
    _TEAM_HP_MEMBERS = (
        {"key": "HS_1", "name": "HS_1", "file": "HS_1.png", "x": 702, "y": 497, "w": 20, "h": 11},
        {"key": "HS_2", "name": "HS_2", "file": "HS_2.png", "x": 782, "y": 449, "w": 20, "h": 11},
        {"key": "HS_3", "name": "HS_3", "file": "HS_3.png", "x": 863, "y": 427, "w": 20, "h": 11},
        {"key": "HS_4", "name": "HS_4", "file": "HS_4.png", "x": 943, "y": 371, "w": 20, "h": 11},
        {"key": "HS_5", "name": "HS_5", "file": "HS_5.png", "x": 1023, "y": 330, "w": 20, "h": 11},
        {"key": "HT_1", "name": "HT_1", "file": "HT_1.png", "x": 621, "y": 451, "w": 20, "h": 11},
        {"key": "HT_2", "name": "HT_2", "file": "HT_2.png", "x": 702, "y": 408, "w": 20, "h": 11},
        {"key": "HT_3", "name": "HT_3", "file": "HT_3.png", "x": 782, "y": 368, "w": 20, "h": 11},
        {"key": "HT_4", "name": "HT_4", "file": "HT_4.png", "x": 863, "y": 338, "w": 20, "h": 11},
        {"key": "HT_5", "name": "HT_5", "file": "HT_5.png", "x": 943, "y": 289, "w": 20, "h": 11},
    )

    def __init__(self):
        super().__init__()

        # --- CẤU HÌNH CỬA SỔ CHÍNH (CỐ ĐỊNH TOOL TỔNG) ---
        self.title(f"TS Origin-Control v{APP_VERSION}")
        self.geometry("610x665")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_MAIN)

        # Đăng ký sự kiện nút X (Thu nhỏ xuống khay hệ thống)
        self.tray_icon = None
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # --- BIẾN TRẠNG THÁI & CẤU HÌNH ---
        self.ld_path = r"C:\Program Files\LDPlayer\LDPlayer9"
        self.var_ld_path = ctk.StringVar(value=self.ld_path)
        self.dict_name_to_index = {}
        self.is_scanning = False
        self.game_icon_path = None
        self.get_app_dir = get_app_dir

        # Biến trạng thái Web Server & Cloudflare Tunnel (Truy cập từ xa)
        self.web_ip = "127.0.0.1"
        self.web_port = 8082
        self.cloudflared_proc = None
        self.public_web_url = ""
        self.current_web_url = ""

        # Biến trạng thái Công tắc tổng ON/OFF & Nút Dừng các Card
        self.var_switch_A = ctk.BooleanVar(value=False)  # Card A: BOSS THẾ GIỚI
        self.var_switch_B = ctk.BooleanVar(value=False)  # Card B: PHỤ BẢN ĐƠN / ĐỘI
        self.var_switch_C = ctk.BooleanVar(value=False)  # Card C: DỊ GIỚI ĐÊM
        self.var_switch_D = ctk.BooleanVar(value=False)  # Card D: 40 NPC / Nhị Kiều
        self.var_pause_D = ctk.BooleanVar(value=False)   # Nút Tạm Dừng ở Card D

        # Biến trạng thái các ô Checkbox Card A (BOSS THẾ GIỚI)
        self.var_A1 = ctk.BooleanVar(value=False)  # Boss

        # Biến trạng thái các ô Checkbox Card B (PHỤ BẢN ĐƠN / ĐỘI)
        self.var_B_don = ctk.BooleanVar(value=False)
        self.var_B_doi = ctk.BooleanVar(value=False)
        self.var_B1 = ctk.BooleanVar(value=False)  # PB 20
        self.var_B2 = ctk.BooleanVar(value=False)  # PB 50
        self.var_B3 = ctk.BooleanVar(value=False)  # PB 80
        self.var_B4 = ctk.BooleanVar(value=False)  # PB 110
        self.var_B5 = ctk.BooleanVar(value=False)  # PB 140

        # Biến trạng thái các ô Checkbox Card C (DỊ GIỚI ĐÊM)
        self.var_C1 = ctk.BooleanVar(value=False)  # Phúc Thần
        self.var_C2 = ctk.BooleanVar(value=False)  # Ký Lục
        self.var_C3 = ctk.BooleanVar(value=False)  # Rút Gọn

        # Biến trạng thái các ô Checkbox Card D (40 NPC / Nhị Kiều)
        self.var_D2 = ctk.BooleanVar(value=False)  # Tổ Đội
        self.var_D_nhan_doi = ctk.BooleanVar(value=False)  # Nhận Đội
        self.var_D3 = ctk.BooleanVar(value=False)  # 40 NPC
        self.var_D4 = ctk.BooleanVar(value=False)  # Nhị Kiều
        self.var_D_time = ctk.StringVar(value="20:00")  # Ô hẹn giờ chạy 40 NPC (mặc định 20:00)
        self.var_D_skill = ctk.StringVar(value="Buff HP / SP")  # Menu Kỹ Năng trong Card D

        # Biến trạng thái trong Card E (TỔ ĐỘI):
        self.var_E_quan_su = ctk.BooleanVar(value=False)
        self.selected_E_list_A_char = ""
        self.selected_E_list_B_char = ""
        self.list_E_B = []  # List tên nhân vật đã add sang Danh Sách B
        self.btn_E_list_A_dict = {}  # Các button bên Danh Sách A
        self.btn_E_list_B_dict = {}  # Các button bên Danh Sách B
        self._is_card_E_running = False  # Cờ bận Card E chống xung đột với Nhận Thư

        # Biến trạng thái Tab 3 CHIẾN ĐẤU:
        self.var_buff = ctk.BooleanVar(value=False)
        self.var_phong_thu = ctk.BooleanVar(value=False)
        # Biến tương thích ngược
        self.var_ket_gioi = self.var_phong_thu
        self.var_linh_kinh = self.var_phong_thu
        self.var_bang_tuong = self.var_phong_thu

        # Card Ngày: Quản lý tính năng Nhận Thư
        self.var_nhan_thu = ctk.BooleanVar(value=False)
        self._event_nhan_thu = threading.Event()
        self._stop_mail_sleep = threading.Event()  # Dùng để ngắt sleep sớm khi tắt ô tích Nhận Thư
        self._completed_mail_slots = set()

        # Quản lý tính năng Hẹn Giờ chạy các Card A, B, C, D
        self.var_hen_gio = ctk.BooleanVar(value=False)
        self.var_hen_gio_time = ctk.StringVar(value="05:00")
        self._event_hen_gio = threading.Event()
        self._stop_hen_gio_sleep = threading.Event()  # Dùng để ngắt sleep sớm khi tắt Hẹn Giờ tổng

        # Quản lý luồng tiến trình độc lập Tab Chiến Đấu (chống lag giật / nhân bản luồng)
        self._thread_buff = None
        self._thread_phong_thu = None

        # Quản lý hàng đợi tuần tự chống xung đột cho Card A (Boss Thế Giới) & Card B (Phụ Bản Đơn/Đội)
        self._card_AB_coordinator_running = False
        self._card_AB_lock = threading.Lock()

        # Biến trạng thái Dừng khẩn cấp & Thông báo khay Taskbar
        self.stop_requested = False
        self._stop_event = threading.Event()
        self.var_enable_notify = ctk.BooleanVar(value=True)
        self.var_enable_telegram = ctk.BooleanVar(value=True)
        self.telegram_bot_token = "8801452830:AAEmGuymSBhpsRB5HWM7kIShBaFcG4hpkMo"
        self.telegram_bot_token_2 = "8973239690:AAEgsy-M5vnXmNcU24hxt6e2lJzLFix53L0"
        self.telegram_chat_id = "6647756940"
        self.telegram_chat_id_2 = "-1004344257210"
        self.current_active_tab = None

        # --- TẠO HỆ THỐNG GIAO DIỆN ---
        self._setup_grid()
        self._create_ld_selection_card()
        self._create_unified_config_card()
        self._create_ld_path_card()

        # Nạp cấu hình đã lưu
        self.load_config()

        # Căn giữa cửa sổ ứng dụng trên màn hình Desktop (Kích thước cố định 610x665)
        self._center_window(610, 665)

        # Quét danh sách LDPlayer lần đầu tiên
        self.refresh_ld_tabs_async()

        # Khởi tạo bộ nhớ log thời gian thực & Kích hoạt Web Server điều khiển từ xa
        self.recent_logs = []
        self.update_info = None
        self.after(600, lambda: web_server.start_web_server(self, port=8082))
        self.after(1000, lambda: self.log_info(f"✨ TS Origin Control V3 (v{APP_VERSION}) - Đã sẵn sàng hoạt động!"))
        self.after(2500, lambda: updater.start_background_updater(self))

        # Dọn sạch ADB session bẩn từ lần chạy trước (chống xung đột ADB khi dev/debug)
        threading.Thread(target=self._cleanup_adb_sessions, daemon=True).start()

        # Luồng ngầm tự động nhận thư theo mốc giờ (tĩnh hoàn toàn khi tắt, kích hoạt qua _event_nhan_thu khi ô Nhận Thư được tích)
        threading.Thread(target=self._worker_auto_mail_daemon, daemon=True).start()

        # Luồng ngầm hẹn giờ thực thi các Card A, B, C, D
        threading.Thread(target=self._worker_hen_gio_daemon, daemon=True).start()

        # Định kỳ kiểm tra cập nhật nhãn hệ Boss (Card A) theo ngày hệ thống
        self.after(60000, self._update_boss_element_ui)

        # Định kỳ cập nhật đồng hồ hệ thống thời gian thực (realtime clock)
        self._update_realtime_clock()

    def _center_window(self, width: int = 610, height: int = 665):
        """Căn giữa cửa sổ ứng dụng trên màn hình Desktop (kích thước cố định)"""
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    # --- TÍNH NĂNG KHAY HỆ THỐNG (SYSTEM TRAY) ---
    def _create_tray_icon_image(self):
        """Tạo icon đại diện 64x64 cho khay hệ thống"""
        try:
            img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([2, 2, 62, 62], radius=12, fill='#1F2937', outline='#EA580C', width=3)
            draw.ellipse([18, 18, 46, 46], fill='#EA580C')
            draw.rectangle([28, 22, 36, 42], fill='#FFFFFF')
            draw.rectangle([22, 28, 42, 36], fill='#FFFFFF')
            return img
        except Exception:
            return None

    def _setup_system_tray(self):
        """Khởi tạo Icon và Menu ngữ cảnh ở khay hệ thống Windows (System Tray)"""
        if not HAS_PYSTRAY or self.tray_icon is not None:
            return

        try:
            icon_img = self._create_tray_icon_image()
            if not icon_img:
                return

            menu = pystray.Menu(
                pystray.MenuItem("Mở Tool TS Origin", self._show_window_from_tray, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Thoát Ứng Dụng", self._exit_app_from_tray)
            )
            self.tray_icon = pystray.Icon("TS_Origin_Control", icon_img, "TS Origin-Control", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Không thể khởi tạo khay hệ thống: {e}")

    def _on_close_window(self):
        """Sự kiện bấm nút X trên thanh tiêu đề: Thu nhỏ xuống khay hệ thống thay vì tắt hẳn"""
        if HAS_PYSTRAY:
            self.withdraw()  # Ẩn cửa sổ chính
            if self.tray_icon is None:
                self._setup_system_tray()
            self.log_info("📌 Tool đã được thu nhỏ xuống khay hệ thống (System Tray).")
        else:
            self.iconify()  # Thu nhỏ xuống Taskbar nếu không hỗ trợ khay hệ thống

    def _show_window_from_tray(self, icon=None, item=None):
        """Mở lại giao diện từ khay hệ thống"""
        self.after(0, self._restore_window_ui)

    def _restore_window_ui(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))
        self.log_info("📖 Đã mở lại giao diện Tool từ khay hệ thống.")

    def _exit_app_from_tray(self, icon=None, item=None):
        """Thoát hoàn toàn ứng dụng từ menu khay hệ thống"""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(0, self._destroy_app_completely)

    def _cleanup_adb_sessions(self):
        """Dọn sạch ADB session bẩn từ lần chạy trước: Kill rồi Start lại ADB server để đảm bảo session sạch.
        Chạy nền khi khởi động tool — ngăn chặn tình trạng xung đột ADB gây nhảy thao tác / mất kết nối giả lập."""
        try:
            adb_path = os.path.join(self.ld_path, "adb.exe")
            if not os.path.exists(adb_path):
                return
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            # Kill ADB server cũ (xóa mọi session bẩn từ lần chạy trước)
            subprocess.run(
                [adb_path, "kill-server"],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            time.sleep(0.5)
            # Start lại ADB server mới (session sạch hoàn toàn)
            subprocess.run(
                [adb_path, "start-server"],
                timeout=8,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            self.after(0, self.log_info, "🔌 [ADB] Đã reset ADB session — sẵn sàng kết nối giả lập.")
        except Exception:
            pass

    def _destroy_app_completely(self):
        # Kill ADB server trước khi thoát để không để lại session bẩn cho lần chạy tiếp theo
        try:
            adb_path = os.path.join(self.ld_path, "adb.exe")
            if os.path.exists(adb_path):
                subprocess.run(
                    [adb_path, "kill-server"],
                    timeout=4,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
        except Exception:
            pass
        try:
            web_server.stop_active_tunnel(self)
        except Exception:
            pass
        try:
            if hasattr(self, 'web_server') and self.web_server:
                self.web_server.shutdown()
        except Exception:
            pass
        try:
            self.save_config()
        except Exception:
            pass
        self.destroy()
        os._exit(0)


    def _get_character_options(self) -> list:
        """Danh sách các tùy chọn vị trí / chế độ xuất chiến trong menu thả xuống"""
        return ["Xuất Chiến", "Vị Trí 1", "Vị Trí 2", "Vị Trí 3", "Vị Trí 4"]

    @staticmethod
    def _get_boss_element_info() -> tuple:
        """Trả về (Thứ, Tên Hệ, Mã Màu) tương ứng ngày hiện tại của hệ thống"""
        days_map = {
            0: ("T2", "Địa", "#FDE047"),
            1: ("T3", "Thủy", "#38BDF8"),
            2: ("T4", "Hỏa", "#FF5252"),
            3: ("T5", "Phong", "#4ADE80"),
            4: ("T6", "Hỏa", "#FF5252"),
            5: ("T7", "Thủy", "#38BDF8"),
            6: ("CN", "Phong", "#4ADE80"),
        }
        weekday = datetime.now().weekday()
        return days_map.get(weekday, ("--", "Địa", "#FDE047"))

    def _update_boss_element_ui(self):
        """Cập nhật nhãn hệ Boss theo thứ hệ thống hiện tại"""
        try:
            day_str, elem_name, elem_color = self._get_boss_element_info()
            if hasattr(self, 'lbl_A_elem') and self.lbl_A_elem.winfo_exists():
                self.lbl_A_elem.configure(text=f" {elem_name} ", text_color=elem_color)
        except Exception:
            pass
        finally:
            try:
                self.after(60000, self._update_boss_element_ui)
            except Exception:
                pass

    def _update_realtime_clock(self):
        """Cập nhật đồng hồ hệ thống thời gian thực (HH:MM:SS) liên tục mỗi giây (chỉ vẽ lại UI khi số giây đổi)"""
        try:
            if hasattr(self, 'lbl_realtime_clock') and self.lbl_realtime_clock.winfo_exists():
                now_str = datetime.now().strftime("%H:%M:%S")
                if getattr(self, '_last_clock_str', None) != now_str:
                    self._last_clock_str = now_str
                    self.lbl_realtime_clock.configure(text=now_str)
        except Exception:
            pass
        finally:
            try:
                self.after(1000, self._update_realtime_clock)
            except Exception:
                pass

    def _get_nhanvat_options(self) -> list:
        """Danh sách tên nhân vật cho Danh Sách A: CHỈ quét file trực tiếp trong folder assets/card_e/nhanvat (KHÔNG quét thư mục con 40npc2k và pbdoi)"""
        names = []
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
        for base in [get_bundle_dir(), get_app_dir()]:
            assets_dir = os.path.join(base, "assets")
            nhanvat_dir = os.path.join(assets_dir, "card_e", "nhanvat")
            if os.path.exists(nhanvat_dir) and os.path.isdir(nhanvat_dir):
                try:
                    for f in sorted(os.listdir(nhanvat_dir)):
                        full_f = os.path.join(nhanvat_dir, f)
                        # CHỈ lấy file nằm trực tiếp tại thư mục cha, KHÔNG lấy thư mục con
                        if os.path.isfile(full_f) and f.lower().endswith(valid_exts):
                            char_name = os.path.splitext(f)[0]
                            if char_name and char_name not in names:
                                names.append(char_name)
                except Exception:
                    pass
        return sorted(names)

    def _select_E_list_A_item(self, char_name: str):
        """Chọn tên nhân vật bên [Danh Sách A] (đồng bộ folder ảnh)"""
        self.selected_E_list_A_char = char_name
        self._update_E_list_A_ui()

    def _render_E_list_A_ui(self):
        """Vẽ lại các phần tử trong [Danh Sách A] bên trái (Ẩn đi những nhân vật đã được thêm sang Danh Sách B)"""
        if not hasattr(self, 'scroll_E_list_A'):
            return

        for w in self.scroll_E_list_A.winfo_children():
            w.destroy()

        self.btn_E_list_A_dict = {}
        all_nhanvat = self._get_nhanvat_options()
        b_set = set(getattr(self, 'list_E_B', []))
        available_A = [name for name in all_nhanvat if name not in b_set]

        if not available_A:
            lbl_empty = ctk.CTkLabel(
                self.scroll_E_list_A,
                text="(Đã thêm hết)" if all_nhanvat else "(Chưa có ảnh)",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
                text_color=COLOR_TEXT_MUTED
            )
            lbl_empty.pack(pady=10)
            self.selected_E_list_A_char = ""
            return

        selected = getattr(self, 'selected_E_list_A_char', "")
        if not selected or selected not in available_A:
            selected = available_A[0]
            self.selected_E_list_A_char = selected

        for char_name in available_A:
            btn = ctk.CTkButton(
                self.scroll_E_list_A,
                text=char_name,
                height=27,
                corner_radius=6,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
                anchor="w",
                fg_color=COLOR_ORANGE if char_name == selected else COLOR_INPUT_BG,
                text_color="#FFFFFF" if char_name == selected else COLOR_TEXT_MAIN,
                hover_color=COLOR_ORANGE_HOVER if char_name == selected else COLOR_BTN_NAVY_HOVER,
                border_width=1,
                border_color=COLOR_ORANGE if char_name == selected else COLOR_INPUT_BORDER,
                command=lambda n=char_name: self._select_E_list_A_item(n)
            )
            btn.pack(fill="x", padx=1, pady=2)
            self.btn_E_list_A_dict[char_name] = btn

    def _update_E_list_A_ui(self):
        """Cập nhật màu sắc highlight tên được chọn trong [Danh Sách A] bên trái"""
        if not hasattr(self, 'btn_E_list_A_dict'):
            return
        selected = getattr(self, 'selected_E_list_A_char', "")
        for name, btn in self.btn_E_list_A_dict.items():
            if name == selected:
                btn.configure(fg_color=COLOR_ORANGE, text_color="#FFFFFF", hover_color=COLOR_ORANGE_HOVER, border_color=COLOR_ORANGE)
            else:
                btn.configure(fg_color=COLOR_INPUT_BG, text_color=COLOR_TEXT_MAIN, hover_color=COLOR_BTN_NAVY_HOVER, border_color=COLOR_INPUT_BORDER)

    def _add_A_to_B_E(self):
        """Thêm nhân vật đang chọn từ [Danh Sách A] sang [Danh Sách B] (Tự động ẩn khỏi Danh Sách A)"""
        if not hasattr(self, 'list_E_B'):
            self.list_E_B = []

        char_name = getattr(self, 'selected_E_list_A_char', "")
        if not char_name:
            all_opts = self._get_nhanvat_options()
            avail = [n for n in all_opts if n not in self.list_E_B]
            if avail:
                char_name = avail[0]
                self.selected_E_list_A_char = char_name

        if not char_name or char_name in self.list_E_B:
            return

        self.list_E_B.append(char_name)
        self._render_E_list_B_ui()
        self._render_E_list_A_ui()
        self.save_config()

    def _remove_B_item_E(self, char_name: str):
        """Xóa nhân vật khỏi [Danh Sách B] bên phải (Tự động hiện lại bên Danh Sách A)"""
        if hasattr(self, 'list_E_B') and char_name in self.list_E_B:
            self.list_E_B.remove(char_name)
            self._render_E_list_B_ui()
            self._render_E_list_A_ui()
            self.save_config()

    def _select_E_list_B_item(self, char_name: str):
        """Chọn tên nhân vật trong [Danh Sách B]"""
        self.selected_E_list_B_char = char_name
        self._update_E_list_B_ui()

    def _update_E_list_B_ui(self):
        """Cập nhật màu sắc highlight nút đại diện cho tên trong [Danh Sách B]"""
        if not hasattr(self, 'btn_E_list_B_dict'):
            return
        selected = getattr(self, 'selected_E_list_B_char', "")
        for name, btn in self.btn_E_list_B_dict.items():
            if name == selected:
                btn.configure(fg_color=COLOR_ORANGE, text_color="#FFFFFF", hover_color=COLOR_ORANGE_HOVER, border_color=COLOR_ORANGE)
            else:
                btn.configure(fg_color=COLOR_INPUT_BG, text_color=COLOR_TEXT_MAIN, hover_color=COLOR_BTN_NAVY_HOVER, border_color=COLOR_INPUT_BORDER)

    def _get_quan_su_options(self):
        """Lấy danh sách các nhân vật trong Danh Sách B để nạp vào Menu Quân Sư (Hàng 2)"""
        b_list = getattr(self, 'list_E_B', [])
        return ["(Trống)"] + list(b_list) if b_list else ["(Trống)"]

    def _update_E_quan_su_options(self):
        """Cập nhật lại danh sách lựa chọn trong Menu dropdown Quân Sư"""
        if not hasattr(self, 'combo_E_quan_su'):
            return
        opts = self._get_quan_su_options()
        self.combo_E_quan_su.configure(values=opts)
        current = self.combo_E_quan_su.get()
        if current not in opts:
            self.combo_E_quan_su.set(opts[0])
        if hasattr(self, 'var_E_quan_su'):
            self.var_E_quan_su.set(bool(self.combo_E_quan_su.get() and self.combo_E_quan_su.get() != "(Trống)"))

    def _render_E_list_B_ui(self):
        """Vẽ lại các phần tử trong [Danh Sách B] bên phải (giao diện CTkButton 100% y hệt chữ, nền, hình dáng của Danh Sách A)"""
        if not hasattr(self, 'scroll_E_list_B'):
            return

        for w in self.scroll_E_list_B.winfo_children():
            w.destroy()

        self.btn_E_list_B_dict = {}

        if not getattr(self, 'list_E_B', []):
            lbl_empty = ctk.CTkLabel(
                self.scroll_E_list_B,
                text="(Bấm ➔ để thêm)",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
                text_color=COLOR_TEXT_MUTED
            )
            lbl_empty.pack(pady=10)
            self._update_E_quan_su_options()
            return

        selected_B = getattr(self, 'selected_E_list_B_char', "")
        if not selected_B and self.list_E_B:
            selected_B = self.list_E_B[0]
            self.selected_E_list_B_char = selected_B

        for char_name in list(self.list_E_B):
            row_frame = ctk.CTkFrame(self.scroll_E_list_B, fg_color="transparent")
            row_frame.pack(fill="x", padx=1, pady=2)
            row_frame.grid_columnconfigure(0, weight=1)
            row_frame.grid_columnconfigure(1, weight=0)

            btn = ctk.CTkButton(
                row_frame,
                text=char_name,
                height=27,
                corner_radius=6,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
                anchor="w",
                fg_color=COLOR_ORANGE if char_name == selected_B else COLOR_INPUT_BG,
                text_color="#FFFFFF" if char_name == selected_B else COLOR_TEXT_MAIN,
                hover_color=COLOR_ORANGE_HOVER if char_name == selected_B else COLOR_BTN_NAVY_HOVER,
                border_width=1,
                border_color=COLOR_ORANGE if char_name == selected_B else COLOR_INPUT_BORDER,
                command=lambda n=char_name: self._select_E_list_B_item(n)
            )
            btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

            btn_del = ctk.CTkButton(
                row_frame,
                text="✕",
                width=24,
                height=27,
                corner_radius=6,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                fg_color=COLOR_INPUT_BG,
                text_color="#ef4444",
                hover_color="#374151",
                border_width=1,
                border_color=COLOR_INPUT_BORDER,
                command=lambda n=char_name: self._remove_B_item_E(n)
            )
            btn_del.grid(row=0, column=1, sticky="e")
            self.btn_E_list_B_dict[char_name] = btn

        self._update_E_quan_su_options()

    def _update_card_E_visibility(self):
        """Cập nhật trạng thái hiển thị của Card E (Tổ Đội) - Luôn mở sáng 100% 24/7 để cấu hình tự do"""
        if not hasattr(self, 'card_E'):
            return

        # SÁNG LÊN TOÀN DIỆN: Card E luôn mở sáng tự do, sẵn sàng tương tác
        if hasattr(self, 'lbl_E'): self.lbl_E.configure(text_color=COLOR_ACCENT)
        if hasattr(self, 'btn_E_add'): self.btn_E_add.configure(state="normal", fg_color=COLOR_ORANGE, text_color="#FFFFFF")
        if hasattr(self, 'btn_E_list_A_dict'):
            for name, btn in self.btn_E_list_A_dict.items():
                btn.configure(state="normal")
            self._update_E_list_A_ui()
        if hasattr(self, 'btn_E_list_B_dict'):
            for name, btn in self.btn_E_list_B_dict.items():
                btn.configure(state="normal")
            self._update_E_list_B_ui()
        self._render_E_list_B_ui()

        # Cấu hình trạng thái widget Quân Sư Card E (luôn mở sáng)
        if hasattr(self, 'combo_E_quan_su') and isinstance(self.combo_E_quan_su, ctk.CTkOptionMenu):
            self.combo_E_quan_su.configure(state="normal", text_color=COLOR_TEXT_MAIN, fg_color=COLOR_COMBO_BG, button_color=COLOR_COMBO_BTN, button_hover_color=COLOR_COMBO_BTN_HOVER)

    def _send_notification(self, title: str, message: str):
        """Phát thông báo nổi (Notification Toast) ở góc Taskbar hệ thống nếu tính năng đang BẬT"""
        if not hasattr(self, 'var_enable_notify') or not self.var_enable_notify.get():
            return

        def _notify_worker():
            # 1. Thử phát thông báo qua Pystray Icon nếu đang chạy khay hệ thống
            if hasattr(self, 'tray_icon') and self.tray_icon is not None and getattr(self, 'is_tray_running', False):
                try:
                    self.tray_icon.notify(message, title)
                    return
                except Exception:
                    pass

            # 2. Phát thông báo nổi Toast Notification chuẩn Windows 10/11 qua PowerShell
            try:
                safe_title = title.replace('"', "'")
                safe_msg = message.replace('"', "'")
                ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{safe_title}</text>
            <text>{safe_msg}</text>
        </binding>
    </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("TS Origin Control").Show($toast)
'''
                subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

        threading.Thread(target=_notify_worker, daemon=True).start()

    def send_telegram_alert(self, message: str, capture_screenshot: bool = True, tab_index: str = None, is_card_d: bool = False, delay_seconds: float = 0.0):
        """Gửi cảnh báo qua Telegram Bot kèm ảnh chụp màn hình giả lập (chạy luồng nền độc lập, không block game)
        Hỗ trợ delay_seconds để hoãn chụp ảnh trong luồng nền mà không làm chậm hay thay đổi luồng code game chính.
        Hỗ trợ gửi thêm Bot thứ 2 riêng biệt cho CARD D (40 NPC và Nhị Kiều)"""
        # 1. Kiểm tra cấu hình và cờ bật/tắt
        token = getattr(self, 'telegram_bot_token', '') or "8801452830:AAEmGuymSBhpsRB5HWM7kIShBaFcG4hpkMo"
        token_2 = getattr(self, 'telegram_bot_token_2', '') or "8973239690:AAEgsy-M5vnXmNcU24hxt6e2lJzLFix53L0"
        chat_id = getattr(self, 'telegram_chat_id', '') or "6647756940"
        chat_id_2 = getattr(self, 'telegram_chat_id_2', '') or "-1004344257210"
        enable_tg = getattr(self, 'var_enable_telegram', None)
        if enable_tg is not None and not enable_tg.get():
            return

        cfg_p = os.path.join(get_app_dir(), "config.json")
        if os.path.exists(cfg_p):
            try:
                with open(cfg_p, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    if "enable_telegram" in cfg_data and not cfg_data["enable_telegram"]:
                        return
                    if cfg_data.get("telegram_bot_token"):
                        token = cfg_data["telegram_bot_token"]
                    if cfg_data.get("telegram_bot_token_2"):
                        token_2 = cfg_data["telegram_bot_token_2"]
                    if cfg_data.get("telegram_chat_id"):
                        chat_id = cfg_data["telegram_chat_id"]
                    if cfg_data.get("telegram_chat_id_2"):
                        chat_id_2 = cfg_data["telegram_chat_id_2"]
            except Exception:
                pass

        # Xác định danh sách bot và chat_id nhận tin:
        # Bot 1 gửi về chat_id (cá nhân), Bot 2 gửi về chat_id_2 (nhóm)
        targets_to_send = []
        if token and chat_id:
            targets_to_send.append((token, str(chat_id)))

        is_d = (
            is_card_d
            or "[CARD D" in message
            or "[40 NPC]" in message
            or "[NHỊ KIỀU]" in message
            or "[2K & NHỊ KIỀU]" in message
        )
        if is_d and token_2:
            target_cid2 = str(chat_id_2) if chat_id_2 else str(chat_id)
            if target_cid2:
                targets_to_send.append((token_2, target_cid2))

        if not targets_to_send:
            return

        # Xác định tab index
        if tab_index is None:
            _, tid = self._get_selected_ld_info()
            tab_index = tid if tid is not None else "0"

        dnconsole_path = self._get_dnconsole_path()

        def _telegram_worker():
            try:
                import urllib.request
                import json as pyjson

                if delay_seconds > 0:
                    time.sleep(delay_seconds)

                img_bytes = None
                if capture_screenshot and dnconsole_path:
                    try:
                        screen = self._capture_screen_fast(dnconsole_path, str(tab_index), max_cache_age=0.0)
                        if screen is not None and getattr(screen, 'shape', None) and screen.shape[0] > 0 and screen.shape[1] > 0:
                            ret, buf = cv2.imencode('.jpg', screen, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                            if ret:
                                img_bytes = buf.tobytes()
                    except Exception:
                        img_bytes = None

                for current_bot_token, current_chat_id in targets_to_send:
                    sent_photo = False
                    # Gửi ảnh kèm chú thích nếu có ảnh
                    if img_bytes:
                        try:
                            boundary = '----WebKitFormBoundary' + os.urandom(16).hex()
                            body = bytearray()
                            body.extend(f'--{boundary}\r\n'.encode())
                            body.extend(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
                            body.extend(f'{current_chat_id}\r\n'.encode())

                            body.extend(f'--{boundary}\r\n'.encode())
                            body.extend(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
                            body.extend(message.encode('utf-8') + b'\r\n')

                            body.extend(f'--{boundary}\r\n'.encode())
                            body.extend(b'Content-Disposition: form-data; name="photo"; filename="screenshot.jpg"\r\n')
                            body.extend(b'Content-Type: image/jpeg\r\n\r\n')
                            body.extend(img_bytes)
                            body.extend(b'\r\n')
                            body.extend(f'--{boundary}--\r\n'.encode())

                            url = f'https://api.telegram.org/bot{current_bot_token}/sendPhoto'
                            req = urllib.request.Request(url, data=bytes(body), headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
                            with urllib.request.urlopen(req, timeout=15) as resp:
                                if resp.status == 200:
                                    sent_photo = True
                        except Exception:
                            sent_photo = False

                    # Fallback: Gửi tin nhắn text thường nếu không có ảnh hoặc gửi ảnh thất bại
                    if not sent_photo:
                        try:
                            url = f'https://api.telegram.org/bot{current_bot_token}/sendMessage'
                            payload = pyjson.dumps({'chat_id': current_chat_id, 'text': message}).encode('utf-8')
                            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
                            with urllib.request.urlopen(req, timeout=10):
                                pass
                        except Exception:
                            pass
            except Exception as ex:
                print(f"[Telegram Alert] Lỗi: {ex}")

        threading.Thread(target=_telegram_worker, daemon=True).start()

    def _get_current_tab_name(self) -> str:
        """Lấy tên tab LDPlayer hiện tại đang được chọn"""
        if hasattr(self, 'current_active_tab') and self.current_active_tab:
            if self.current_active_tab not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
                return self.current_active_tab
        if hasattr(self, 'combo_ld_tabs'):
            val = self.combo_ld_tabs.get().strip()
            if val and val not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
                return val
        if hasattr(self, 'saved_selected_tab') and self.saved_selected_tab:
            return self.saved_selected_tab
        return "default"

    def _extract_tab_config_from_ui(self) -> dict:
        """Trích xuất toàn bộ trạng thái cài đặt UI hiện tại thành dict cấu hình"""
        cfg = {}
        if hasattr(self, 'var_B_don'):
            cfg["B_don"] = self.var_B_don.get()
        if hasattr(self, 'var_B_doi'):
            cfg["B_doi"] = self.var_B_doi.get()

        if hasattr(self, 'combo_B_don_char'):
            cfg["B_don_char"] = self.combo_B_don_char.get()
        if hasattr(self, 'combo_B_team_char'):
            cfg["B_team_char"] = self.combo_B_team_char.get()
        if hasattr(self, 'combo_A_char'):
            cfg["A_char"] = self.combo_A_char.get()

        if hasattr(self, 'combo_D_team_char'):
            cfg["D_team_char"] = self.combo_D_team_char.get()
        if hasattr(self, 'combo_D_chien_dau'):
            cfg["D_chien_dau"] = self.combo_D_chien_dau.get()
        if hasattr(self, 'combo_D_tang'):
            cfg["D_tang"] = self.combo_D_tang.get()
        if hasattr(self, 'var_D_time'):
            cfg["D_time"] = self.var_D_time.get()
        if hasattr(self, 'var_D_nhan_doi'):
            cfg["D_nhan_doi"] = self.var_D_nhan_doi.get()
        if hasattr(self, 'var_D_skill'):
            cfg["D_skill"] = self.var_D_skill.get()
        if hasattr(self, 'var_pause_D'):
            cfg["pause_D"] = False

        for prefix in ["A", "B", "C", "D"]:
            switch_attr = f"var_switch_{prefix}"
            if hasattr(self, switch_attr):
                cfg[f"switch_{prefix}"] = False
            pause_attr = f"var_pause_{prefix}"
            if hasattr(self, pause_attr):
                cfg[f"pause_{prefix}"] = False

            for num in range(1, 6):
                key = f"{prefix}{num}"
                var_attr = f"var_{key}"
                if hasattr(self, var_attr):
                    cfg[key] = getattr(self, var_attr).get()

        if hasattr(self, 'list_E_B'):
            cfg["E_list_B"] = list(self.list_E_B)
        if hasattr(self, 'selected_E_list_A_char'):
            cfg["E_selected_left"] = self.selected_E_list_A_char
        if hasattr(self, 'var_E_quan_su'):
            cfg["E_quan_su"] = self.var_E_quan_su.get()
        if hasattr(self, 'combo_E_quan_su'):
            cfg["E_quan_su_char"] = self.combo_E_quan_su.get()

        # Card Chiến Đấu (luôn lưu False để khi mở lại tool mặc định ở trạng thái OFF)
        if hasattr(self, 'var_buff'):
            cfg["var_buff"] = False
        if hasattr(self, 'combo_buff'):
            cfg["combo_buff"] = self.combo_buff.get()
        if hasattr(self, 'var_phong_thu'):
            cfg["var_phong_thu"] = False
        if hasattr(self, 'combo_phong_thu_skill'):
            cfg["combo_phong_thu_skill"] = self.combo_phong_thu_skill.get()
        if hasattr(self, 'combo_phong_thu_target'):
            cfg["combo_phong_thu_target"] = self.combo_phong_thu_target.get()

        # Card Ngày (Nhận Thư)
        if hasattr(self, 'var_nhan_thu'):
            cfg["var_nhan_thu"] = self.var_nhan_thu.get()
        if hasattr(self, 'combo_nhan_thu_time'):
            cfg["combo_nhan_thu_time"] = self.combo_nhan_thu_time.get()

        # Quản lý Hẹn Giờ (luôn lưu False để khi mở lại tool luôn ở trạng thái tắt)
        if hasattr(self, 'var_hen_gio'):
            cfg["var_hen_gio"] = False
        if hasattr(self, 'var_hen_gio_time'):
            cfg["var_hen_gio_time"] = self.var_hen_gio_time.get()

        return cfg

    def _apply_tab_config_to_ui(self, cfg: dict):
        """Khôi phục toàn bộ trạng thái cài đặt UI từ dict cấu hình của tab"""
        # Phụ Bản Đơn / Đội (Card B - tương thích ngược key cũ E_don/E_doi)
        b_don_val = cfg.get("B_don", cfg.get("E_don"))
        if b_don_val is not None and hasattr(self, 'var_B_don'):
            self.var_B_don.set(bool(b_don_val))
        b_doi_val = cfg.get("B_doi", cfg.get("E_doi"))
        if b_doi_val is not None and hasattr(self, 'var_B_doi'):
            self.var_B_doi.set(bool(b_doi_val))

        opts = self._get_character_options()
        b_don_char = cfg.get("B_don_char", cfg.get("E_don_char"))
        if b_don_char and hasattr(self, 'combo_B_don_char'):
            self.combo_B_don_char.set(b_don_char if b_don_char in opts else "Xuất Chiến")
        b_team_char = cfg.get("B_team_char", cfg.get("E_team_char"))
        if b_team_char and hasattr(self, 'combo_B_team_char'):
            self.combo_B_team_char.set(b_team_char if b_team_char in opts else "Xuất Chiến")

        # Boss Thế Giới (Card A - tương thích ngược key cũ C_char/C_ve)
        a_char = cfg.get("A_char", cfg.get("C_char"))
        if a_char and hasattr(self, 'combo_A_char'):
            self.combo_A_char.set(a_char if a_char in opts else "Xuất Chiến")

        # 40 NPC / Nhị Kiều (Card D)
        if "D_team_char" in cfg and hasattr(self, 'combo_D_team_char'):
            val = cfg["D_team_char"]
            self.combo_D_team_char.set(val if val in opts else "Xuất Chiến")
        if "D_chien_dau" in cfg and hasattr(self, 'combo_D_chien_dau'):
            val = cfg["D_chien_dau"]
            self.combo_D_chien_dau.set("Auto")
        tang_D_opts = ["Auto"]
        if hasattr(self, 'combo_D_tang'):
            val = cfg.get("D_tang", "Auto")
            self.combo_D_tang.set(val if val in tang_D_opts else "Auto")
        if "D_time" in cfg and hasattr(self, 'var_D_time'):
            self.var_D_time.set(cfg["D_time"])
        if "D_skill" in cfg and hasattr(self, 'var_D_skill'):
            sk_val = cfg["D_skill"]
            if sk_val in ["Buff HP / SP", "Linh Kính", "Kết Giới", "Đánh Tay"]:
                self.var_D_skill.set(sk_val)
                if hasattr(self, 'combo_D_skill'):
                    self.combo_D_skill.set(sk_val)
        if "D_nhan_doi" in cfg and hasattr(self, 'var_D_nhan_doi'):
            self.var_D_nhan_doi.set(bool(cfg["D_nhan_doi"]))
        if hasattr(self, 'var_pause_D'):
            self.var_pause_D.set(False)

        for prefix in ["A", "B", "C", "D"]:
            switch_attr = f"var_switch_{prefix}"
            if hasattr(self, switch_attr):
                getattr(self, switch_attr).set(False)  # Luôn công tắc OFF khi nạp
            pause_attr = f"var_pause_{prefix}"
            if hasattr(self, pause_attr):
                getattr(self, pause_attr).set(False)  # Luôn nút Tạm Dừng OFF khi nạp

            for num in range(1, 6):
                key = f"{prefix}{num}"
                var_attr = f"var_{key}"
                old_key = key
                if prefix == "A": old_key = f"C{num}"
                elif prefix == "B": old_key = f"E{num}"
                elif prefix == "C": old_key = f"B{num}"
                val = cfg.get(key, cfg.get(old_key))
                if val is not None and hasattr(self, var_attr):
                    getattr(self, var_attr).set(bool(val))

        # Tổ Đội (Card E - tương thích ngược key cũ G)
        sel_left = cfg.get("E_selected_left", cfg.get("G_selected_left"))
        if sel_left:
            self.selected_E_list_A_char = sel_left

        list_b = cfg.get("E_list_B", cfg.get("G_list_B"))
        if list_b and isinstance(list_b, list):
            self.list_E_B = list(list_b)
        else:
            self.list_E_B = []
        self._render_E_list_A_ui()
        self._render_E_list_B_ui()

        e_qs_char = cfg.get("E_quan_su_char", cfg.get("G_quan_su_char"))
        if e_qs_char and hasattr(self, 'combo_E_quan_su'):
            if e_qs_char in self._get_quan_su_options():
                self.combo_E_quan_su.set(e_qs_char)

        # Đồng bộ cờ var_E_quan_su chuẩn xác theo giá trị đang chọn trong combo_E_quan_su
        if hasattr(self, 'var_E_quan_su'):
            qs_val = self.combo_E_quan_su.get() if hasattr(self, 'combo_E_quan_su') else ""
            self.var_E_quan_su.set(bool(qs_val and qs_val != "(Trống)"))

        # Tab 3: Chiến Đấu (Buff / HP / SP & Phòng Thủ: Luôn mặc định OFF khi nạp cấu hình / mở tool)
        if hasattr(self, 'var_buff'):
            self.var_buff.set(False)
        buff_opts = ["Buff HP", "Buff SP", "Buff HP / SP"]
        if "combo_buff" in cfg and hasattr(self, 'combo_buff'):
            val = cfg["combo_buff"]
            if val in ["Buff 3HP / SP", "Buff 3HP / 1SP", "HP / SP / HS", "Buff HP / SP"]:
                val = "Buff HP / SP"
            self.combo_buff.set(val if val in buff_opts else "Buff HP")

        # Cấu hình Kỹ Năng Phòng Thủ (Gộp Kết Giới / Linh Kính / Băng Tường)
        skill_opts = ["Kết Giới", "Linh Kính", "Băng Tường"]
        target_opts = ["Chart", "Chart / Pet", "Team"]

        if hasattr(self, 'var_phong_thu'):
            self.var_phong_thu.set(False)

        if "combo_phong_thu_skill" in cfg and hasattr(self, 'combo_phong_thu_skill'):
            val_sk = cfg["combo_phong_thu_skill"]
            self.combo_phong_thu_skill.set(val_sk if val_sk in skill_opts else "Kết Giới")
        if "combo_phong_thu_target" in cfg and hasattr(self, 'combo_phong_thu_target'):
            val_tg = cfg["combo_phong_thu_target"]
            self.combo_phong_thu_target.set(val_tg if val_tg in target_opts else "Chart")

        # Đảm bảo nguyên tắc loại trừ lẫn nhau cho ô chiến đấu khi nạp cấu hình
        if hasattr(self, 'var_buff') and self.var_buff.get():
            if hasattr(self, 'var_phong_thu'): self.var_phong_thu.set(False)

        # Card Ngày (Nhận Thư)
        nhan_thu_opts = ["Tất Cả", "12H01", "18H01", "22H01"]
        if "combo_nhan_thu_time" in cfg and hasattr(self, 'combo_nhan_thu_time'):
            val_nt_time = cfg["combo_nhan_thu_time"]
            if val_nt_time in ["Tất Cả (12H01 - 18H01 - 22H01)", "Tất Cả"]:
                val_nt_time = "Tất Cả"
            self.combo_nhan_thu_time.set(val_nt_time if val_nt_time in nhan_thu_opts else "Tất Cả")

        # Card Ngày (Nhận Thư) - Mặc định khi mở tool luôn nhả ô tích (False)
        if hasattr(self, 'var_nhan_thu'):
            self.var_nhan_thu.set(False)
            if hasattr(self, '_event_nhan_thu'):
                self._event_nhan_thu.clear()

        # Hẹn Giờ: Giữ mốc giờ cài đặt, nhưng ô tích luôn mặc định tắt (False) khi mở lại tool
        if "var_hen_gio_time" in cfg and hasattr(self, 'var_hen_gio_time'):
            val_hg_time = cfg["var_hen_gio_time"]
            self.var_hen_gio_time.set(val_hg_time)
        if hasattr(self, 'var_hen_gio'):
            self.var_hen_gio.set(False)
            if hasattr(self, '_event_hen_gio'):
                self._event_hen_gio.clear()
            self._update_hen_gio_ui()

        self._update_card_E_visibility()
        self._update_event_cards_state()
        self._update_buff_state()
        self._update_phong_thu_state()

    def save_config(self, target_tab: str = None):
        """Lưu cấu hình máy chủ & checkbox theo từng tab LDPlayer vào config.json"""
        try:
            config_path = os.path.join(get_app_dir(), "config.json")
            config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    config = {}

            if "tab_configs" not in config or not isinstance(config["tab_configs"], dict):
                config["tab_configs"] = {}

            current_tab = target_tab or self._get_current_tab_name()
            tab_cfg = self._extract_tab_config_from_ui()
            config["tab_configs"][current_tab] = tab_cfg

            if hasattr(self, 'var_enable_notify'):
                config["enable_notify"] = self.var_enable_notify.get()
            if hasattr(self, 'var_enable_telegram'):
                config["enable_telegram"] = self.var_enable_telegram.get()
            if hasattr(self, 'telegram_bot_token') and self.telegram_bot_token:
                config["telegram_bot_token"] = self.telegram_bot_token
            if hasattr(self, 'telegram_bot_token_2') and self.telegram_bot_token_2:
                config["telegram_bot_token_2"] = self.telegram_bot_token_2
            if hasattr(self, 'telegram_chat_id') and self.telegram_chat_id:
                config["telegram_chat_id"] = self.telegram_chat_id
            if hasattr(self, 'telegram_chat_id_2') and self.telegram_chat_id_2:
                config["telegram_chat_id_2"] = self.telegram_chat_id_2
            if hasattr(self, 'combo_ld_tabs'):
                val_tab = self.combo_ld_tabs.get()
                if val_tab and val_tab not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
                    config["selected_tab"] = val_tab
            if hasattr(self, 'var_ld_path'):
                config["ld_path"] = self.var_ld_path.get().strip()

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def load_config(self, target_tab: str = None):
        """Khôi phục cấu hình riêng của tab LDPlayer được chọn từ config.json"""
        config_path = os.path.join(get_app_dir(), "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                if "enable_notify" in config and hasattr(self, 'var_enable_notify'):
                    self.var_enable_notify.set(bool(config["enable_notify"]))

                if "enable_telegram" in config and hasattr(self, 'var_enable_telegram'):
                    self.var_enable_telegram.set(bool(config["enable_telegram"]))
                if "telegram_bot_token" in config:
                    self.telegram_bot_token = str(config["telegram_bot_token"]).strip()
                if "telegram_bot_token_2" in config:
                    self.telegram_bot_token_2 = str(config["telegram_bot_token_2"]).strip()
                if "telegram_chat_id" in config:
                    self.telegram_chat_id = str(config["telegram_chat_id"]).strip()
                if "telegram_chat_id_2" in config:
                    self.telegram_chat_id_2 = str(config["telegram_chat_id_2"]).strip()

                if "ld_path" in config:
                    saved_path = config["ld_path"]
                    if os.path.exists(saved_path):
                        self.ld_path = saved_path
                        if hasattr(self, 'var_ld_path'):
                            self.var_ld_path.set(self.ld_path)

                if "selected_tab" in config and hasattr(self, 'combo_ld_tabs'):
                    self.saved_selected_tab = config["selected_tab"]

                tab_to_load = target_tab or self._get_current_tab_name()
                if tab_to_load and tab_to_load not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
                    self.current_active_tab = tab_to_load

                tab_configs = config.get("tab_configs", {})

                if tab_to_load in tab_configs and isinstance(tab_configs[tab_to_load], dict):
                    tab_cfg = tab_configs[tab_to_load]
                else:
                    # Fallback cho config cũ chưa phân tách tab_configs
                    tab_cfg = config

                self._apply_tab_config_to_ui(tab_cfg)
            except Exception:
                pass

    def _setup_grid(self):
        """Thiết lập Grid Layout 1 cột"""
        self.grid_rowconfigure(0, weight=0)  # Card gộp Tab LDPlayer, Nút điều khiển & Hẹn Giờ
        self.grid_rowconfigure(1, weight=1)  # Khung chứa 5 Card Cấu hình co giãn
        self.grid_rowconfigure(2, weight=0)  # Card Web Server điều khiển từ xa bên dưới

        self.grid_columnconfigure(0, weight=1)  # Cột duy nhất chứa toàn bộ các Card

    def _create_ld_selection_card(self):
        """Khung Card Top:
        - Hàng 1: Nút Folder 📁, Bộ Chọn Tab LDPlayer, Game, Exit, Stop
        - Hàng 2: Nút Hẹn Giờ (tap để bật/tắt, không ô tích), Ô nhập giờ hẹn, Đồng hồ hệ thống realtime
        """
        self.card_ld = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=12)
        self.card_ld.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="nsew")
        self.card_ld.grid_columnconfigure(0, weight=0)                          # Nút Folder (bên trái)
        self.card_ld.grid_columnconfigure(1, weight=1)                          # Tab LDPlayer (rộng rãi co giãn)
        self.card_ld.grid_columnconfigure(2, weight=0)                          # Game
        self.card_ld.grid_columnconfigure(3, weight=0)                          # Exit
        self.card_ld.grid_columnconfigure(4, weight=0)                          # Stop
        self.card_ld.grid_rowconfigure(0, weight=0)
        self.card_ld.grid_rowconfigure(1, weight=0)

        # Kích thước nút: Nút lớn Game/Exit/Stop tăng 5% chiều X (112px -> 118px); Nút Folder tăng 5% trục X (~35px, tức 30% nút Game)
        GAME_BTN_WIDTH = 118
        FOLDER_BTN_WIDTH = 35

        # 1. Nút Chọn Thư Mục LDPlayer ("📁" - Đặt bên trái menu chọn LDPlayer)
        self.btn_browse_ld = ctk.CTkButton(
            self.card_ld,
            text="📁",
            width=FOLDER_BTN_WIDTH,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLOR_TEXT_MAIN,
            height=38,
            corner_radius=8,
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            command=self._browse_ld_path
        )
        self.btn_browse_ld.grid(row=0, column=0, padx=(8, 4), pady=(7, 3))

        # 2. Menu Tab LDPlayer (Kích thước nút 38px theo app_ui)
        self.combo_ld_tabs = ctk.CTkComboBox(
            self.card_ld,
            values=["Đang quét tab..."],
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            fg_color=COLOR_COMBO_BG,
            border_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=8,
            height=38,
            command=self._on_ld_tab_selected
        )
        self.combo_ld_tabs.grid(row=0, column=1, padx=(4, 6), pady=(7, 3), sticky="ew")

        # 3. Nút "Game" (Kích thước nút 38px - Màu xanh lục bảo #00875a)
        self.btn_enter_game = ctk.CTkButton(
            self.card_ld,
            text="Game",
            width=GAME_BTN_WIDTH,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            height=38,
            corner_radius=8,
            fg_color=COLOR_BTN_GAME,
            hover_color=COLOR_BTN_GAME_HOVER,
            command=self.xu_ly_ts_origin
        )
        self.btn_enter_game.grid(row=0, column=2, padx=4, pady=(7, 3))

        # 4. Nút "Exit" đặt kế bên nút Game (Kích thước nút 38px - Màu navy #2c3545)
        self.btn_exit_game = ctk.CTkButton(
            self.card_ld,
            text="Exit",
            width=GAME_BTN_WIDTH,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            height=38,
            corner_radius=8,
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            command=self.xu_ly_exit_game
        )
        self.btn_exit_game.grid(row=0, column=3, padx=4, pady=(7, 3))

        # 5. Nút "Stop" ở cuối cùng (Kích thước nút 38px - Màu đỏ #d32f2f)
        self.btn_stop = ctk.CTkButton(
            self.card_ld,
            text="Stop",
            width=GAME_BTN_WIDTH,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            height=38,
            corner_radius=8,
            fg_color=COLOR_BTN_STOP,
            hover_color=COLOR_BTN_STOP_HOVER,
            command=self.dung_tat_ca_hoat_dong
        )
        self.btn_stop.grid(row=0, column=4, padx=(4, 8), pady=(7, 3))

        # =========================================================================
        # HÀNG 2: HẸN GIỜ, Ô GHI GIỜ HẸN & ĐỒNG HỒ REALTIME (CÂN ĐỐI THEO LƯỚI CARD TOP)
        # =========================================================================
        # 1. Nút Hẹn Giờ: Kéo dài từ lề trái đến điểm cuối nút Game (Column 0-2)
        self.btn_hen_gio = ctk.CTkButton(
            self.card_ld,
            text="Hẹn Giờ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            height=38,
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            corner_radius=8,
            anchor="center",
            command=self._on_btn_hen_gio_clicked
        )
        self.btn_hen_gio.grid(row=1, column=0, columnspan=3, padx=(8, 4), pady=(3, 7), sticky="ew")

        # 2. Ô ghi giờ hẹn (mặc định 05:00): Đặt dưới nút Exit, chiều rộng bằng nút Exit (Column 3)
        self.entry_hen_gio_time = ctk.CTkEntry(
            self.card_ld,
            textvariable=self.var_hen_gio_time,
            width=GAME_BTN_WIDTH,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            fg_color=COLOR_INPUT_BG,
            border_width=1,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=8,
            justify="center",
            placeholder_text="05:00"
        )
        self.entry_hen_gio_time.grid(row=1, column=3, padx=4, pady=(3, 7))
        self.entry_hen_gio_time.bind("<FocusOut>", lambda e: self._on_hen_gio_time_changed())
        self.entry_hen_gio_time.bind("<Return>", lambda e: self._on_hen_gio_time_changed())

        # 3. Đồng hồ thời gian thực: Đặt cân đối bên dưới, chiều rộng bằng nút Stop (Column 4)
        self.lbl_realtime_clock = ctk.CTkLabel(
            self.card_ld,
            text=datetime.now().strftime("%H:%M:%S"),
            width=GAME_BTN_WIDTH,
            height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_ACCENT,
            fg_color=COLOR_CARD_INNER,
            border_width=1,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=8
        )
        self.lbl_realtime_clock.grid(row=1, column=4, padx=(4, 8), pady=(3, 7))

    def _on_btn_hen_gio_clicked(self):
        """Xử lý khi người dùng bấm trực tiếp vào nút Hẹn Giờ (Toggle Bật / Tắt)"""
        new_state = not self.var_hen_gio.get()
        self.var_hen_gio.set(new_state)
        self._on_hen_gio_toggled()

    def _update_hen_gio_ui(self):
        """Cập nhật trạng thái sáng/tối của nút Hẹn Giờ trên Card Top (Sáng khi Bật, Tối khi Tắt hoặc chạy xong)"""
        if not hasattr(self, 'btn_hen_gio') or not self.btn_hen_gio.winfo_exists():
            return
        is_enabled = bool(self.var_hen_gio.get()) if hasattr(self, 'var_hen_gio') else False
        if is_enabled:
            self.btn_hen_gio.configure(
                fg_color=COLOR_ORANGE,
                hover_color=COLOR_ORANGE_HOVER,
                text="Hẹn Giờ (Bật)"
            )
        else:
            self.btn_hen_gio.configure(
                fg_color=COLOR_BTN_NAVY,
                hover_color=COLOR_BTN_NAVY_HOVER,
                text="Hẹn Giờ"
            )

    def _on_ld_tab_selected(self, choice: str):
        """Tự động chuyển đổi cấu hình riêng khi người dùng chọn tab LDPlayer khác"""
        if not choice or choice in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
            return

        prev_tab = getattr(self, 'current_active_tab', None)
        if prev_tab and prev_tab != choice:
            self.save_config(target_tab=prev_tab)

        self.current_active_tab = choice
        self.saved_selected_tab = choice

        self.load_config(target_tab=choice)
        self.log_info(f"🔄 Đã nạp cấu hình riêng của tab LDPlayer: '{choice}'")

    def _create_ld_path_card(self):
        """Card hiển thị Khung Đường Link Web Server Điều Khiển Từ Xa bên dưới cùng theo style app_ui"""
        self.card_path = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=12)
        self.card_path.grid(row=2, column=0, padx=12, pady=(4, 8), sticky="nsew")
        self.card_path.grid_columnconfigure(0, weight=1)

        # Khung Đường Link Web Server Điều Khiển Từ Xa (Tạo Link 4G)
        self.frame_web_bar = ctk.CTkFrame(self.card_path, fg_color=COLOR_CARD_INNER, corner_radius=8, border_width=1, border_color=COLOR_INPUT_BORDER)
        self.frame_web_bar.grid(row=0, column=0, padx=10, pady=(6, 6), sticky="ew")
        self.frame_web_bar.grid_columnconfigure(0, weight=1)
        self.frame_web_bar.grid_columnconfigure(1, weight=0)

        self.current_web_url = f"http://{getattr(self, 'web_ip', '127.0.0.1')}:{getattr(self, 'web_port', 8082)}"

        self.lbl_web_url = ctk.CTkLabel(
            self.frame_web_bar,
            text=f"🌐 Web: {self.current_web_url}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_ACCENT,
            anchor="w"
        )
        self.lbl_web_url.grid(row=0, column=0, padx=(10, 4), pady=5, sticky="w")

        # Frame chứa các nút bấm bên phải (Sao Chép, Mở Web, 4G, Thông Báo) ép sát lề phải
        self.frame_right_btns = ctk.CTkFrame(self.frame_web_bar, fg_color="transparent")
        self.frame_right_btns.grid(row=0, column=1, padx=(2, 8), pady=3, sticky="e")

        self.btn_copy_url = ctk.CTkButton(
            self.frame_right_btns,
            text="Copy",
            width=54,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            corner_radius=6,
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            command=self._copy_web_url
        )
        self.btn_copy_url.pack(side="left", padx=2)

        self.btn_open_web = ctk.CTkButton(
            self.frame_right_btns,
            text="Open",
            width=54,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            corner_radius=6,
            fg_color=COLOR_BTN_GAME,
            hover_color=COLOR_BTN_GAME_HOVER,
            command=self._open_web_in_browser
        )
        self.btn_open_web.pack(side="left", padx=2)

        self.btn_online_tunnel = ctk.CTkButton(
            self.frame_right_btns,
            text="Create Online",
            width=110,
            height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            corner_radius=6,
            fg_color=COLOR_ORANGE,
            hover_color=COLOR_ORANGE_HOVER,
            command=self._start_online_tunnel
        )
        self.btn_online_tunnel.pack(side="left", padx=(2, 0))

    def _copy_web_url(self):
        """Sao chép đường dẫn Web Server vào Clipboard"""
        url = getattr(self, 'current_web_url', '')
        if url:
            self.clipboard_clear()
            self.clipboard_append(url)
            self.log_info(f"📋 Đã sao chép đường link Web: {url}")

    def _open_web_in_browser(self):
        """Mở đường link Web trên trình duyệt mặc định của máy tính"""
        url = getattr(self, 'current_web_url', '')
        if url:
            webbrowser.open(url)
            self.log_info(f"🌐 Đang mở Web Dashboard trên trình duyệt: {url}")

    def _start_online_tunnel(self):
        """Khởi động Cloudflare Tunnel để tạo link truy cập từ xa (4G/Internet)"""
        self.btn_online_tunnel.configure(text="Đang kết nối...", state="disabled")
        web_server.start_cloudflare_tunnel(self)

    def _update_web_url_ui(self, url: str, is_public_4g: bool = False):
        """Cập nhật đường link Web lên thanh hiển thị trên GUI"""
        self.current_web_url = url
        is_4g = is_public_4g or url.startswith("https://")
        if hasattr(self, 'lbl_web_url'):
            prefix = "4G" if is_4g else "Wifi"
            self.lbl_web_url.configure(text=f"🌐 {prefix}: {url}")
        if hasattr(self, 'btn_online_tunnel'):
            if is_4g:
                self.btn_online_tunnel.configure(text="Online Ready", state="disabled", fg_color="#059669")
                try:
                    self.clipboard_clear()
                    self.clipboard_append(url)
                    self.log_info(f"📋 Đã tự động sao chép đường link 4G vào Clipboard: {url}")
                except Exception:
                    pass
            else:
                self.btn_online_tunnel.configure(text="Create Online", state="normal", fg_color="#EA580C")

    def _on_tunnel_failed(self):
        """Xử lý khi đường truyền 4G bị ngắt hoặc không thể tạo tunnel"""
        if hasattr(self, 'btn_online_tunnel'):
            self.btn_online_tunnel.configure(text="Retry Online", state="normal", fg_color="#EA580C")
        if hasattr(self, 'lbl_web_url'):
            local_url = f"http://{getattr(self, 'web_ip', '127.0.0.1')}:{getattr(self, 'web_port', 8082)}"
            self.lbl_web_url.configure(text=f"🌐 Wifi: {local_url}")
            self.current_web_url = local_url
        self.log_warning("⚠️ Đường truyền 4G đã dừng. Bấm 'Retry Online' nếu muốn kết nối lại.")

    def _on_hen_gio_toggled(self):
        """Xử lý khi người dùng bật / tắt Hẹn Giờ"""
        is_enabled = bool(self.var_hen_gio.get()) if hasattr(self, 'var_hen_gio') else False
        t = self.var_hen_gio_time.get() if hasattr(self, 'var_hen_gio_time') else "05:00"
        if is_enabled:
            if hasattr(self, '_event_hen_gio'):
                self._event_hen_gio.set()
            self.after(0, self.log_info, f"⏰ [HẸN GIỜ] Đã bật chế độ Hẹn Giờ (Mốc: {t}). Các Card (A, B, C, D) khi gạt ON sẽ chờ đến đúng {t} mới bắt đầu chạy!")
        else:
            if hasattr(self, '_event_hen_gio'):
                self._event_hen_gio.clear()
            if hasattr(self, '_stop_hen_gio_sleep'):
                self._stop_hen_gio_sleep.set()
            # Theo yêu cầu người dùng: Khi tắt Hẹn Giờ -> Hủy hẹn giờ và nhả công tắc các Card về OFF
            for prefix in ["A", "B", "C", "D"]:
                switch_attr = f"var_switch_{prefix}"
                if hasattr(self, switch_attr):
                    getattr(self, switch_attr).set(False)
            if hasattr(self, 'var_pause_D'):
                self.var_pause_D.set(False)
            self._update_card_E_visibility()
            self.after(0, self.log_info, "🛑 [HẸN GIỜ] Đã tắt Hẹn Giờ ➔ Đã hủy hẹn giờ và nhả tất cả công tắc Card A, B, C, D về OFF!")
        self._update_hen_gio_ui()
        self.save_config()

    def _on_hen_gio_time_changed(self, choice=None):
        """Xử lý khi thay đổi mốc giờ hẹn (gõ trực tiếp định dạng HH:MM)"""
        val = self.var_hen_gio_time.get().strip() if hasattr(self, 'var_hen_gio_time') else "05:00"
        if len(val) == 4 and val[1] == ':':
            val = f"0{val}"
            self.var_hen_gio_time.set(val)
        self.save_config()
        if hasattr(self, 'var_hen_gio') and self.var_hen_gio.get():
            self.after(0, self.log_info, f"⏰ [HẸN GIỜ] Đã cập nhật mốc hẹn giờ mới: {val}")

    def _on_D_time_changed(self, choice=None):
        """Xử lý khi thay đổi mốc giờ hẹn Card D (định dạng HH:MM)"""
        val = self.var_D_time.get().strip() if hasattr(self, 'var_D_time') else "20:00"
        if len(val) == 4 and val[1] == ':':
            val = f"0{val}"
            self.var_D_time.set(val)
        self.save_config()
        self.after(0, self.log_info, f"⏰ [CARD D] Đã cập nhật mốc hẹn giờ 40 NPC: {val}")

    def _browse_ld_path(self):
        """Mở hộp thoại chọn thư mục LDPlayer9"""
        curr_path = self.var_ld_path.get().strip()
        init_dir = curr_path if os.path.exists(curr_path) else r"C:\Program Files\LDPlayer"
        selected_dir = filedialog.askdirectory(initialdir=init_dir, title="Chọn thư mục cài đặt LDPlayer9")
        if selected_dir:
            self.ld_path = os.path.normpath(selected_dir)
            self.var_ld_path.set(self.ld_path)
            self.save_config()
            self.refresh_ld_tabs_async()

    def _get_selected_ld_info(self):
        """Lấy tên tab và index tab LDPlayer đang chọn"""
        tab_name = self.combo_ld_tabs.get()
        if tab_name in ["Đang quét tab...", "Không tìm thấy tab LD nào", "Sai đường dẫn LDPlayer", "Lỗi quét dữ liệu"]:
            return None, None
        dict_map = getattr(self, "dict_name_to_index", {})
        index_tab = dict_map.get(tab_name)
        if index_tab is None:
            # Dò tìm con số trong tên tab (VD: "LDPlayer-1" -> "1")
            nums = re.findall(r'\d+', tab_name)
            index_tab = nums[0] if nums else "0"
        return tab_name, index_tab

    def _on_checkbox_toggled(self):
        """Callback khi bất kỳ ô checkbox nào được tích chọn/bỏ chọn"""
        self._update_card_E_visibility()
        self._update_event_cards_state()
        self._update_buff_state()
        self._update_phong_thu_state()
        self.save_config()

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: CARD F (CẤU HÌNH CHIẾN ĐẤU / HP / SP BUFF)
    # =========================================================================
    def _update_buff_state(self):
        """Cập nhật trạng thái ô dropdown HP / SP (luôn luôn mở sáng để chọn trước chế độ)"""
        if not hasattr(self, 'combo_buff'):
            return
        self.combo_buff.configure(state="normal", fg_color="#374151", button_color="#4B5563", button_hover_color="#6B7280", text_color="#FFFFFF")

    def _on_buff_toggled(self):
        """Callback riêng cho ô Buff (HP / SP) (Tab Chiến Đấu): Bật/tắt menu dropdown Buff và kích hoạt chạy song song độc lập (Chỉ phụ thuộc nút Dừng tổng)"""
        self._update_buff_state()
        self.save_config()

        if self.var_buff.get():
            # Chống xung đột Card Chiến Đấu: Tự động nhả ô Kỹ Năng Phòng Thủ
            if hasattr(self, 'var_phong_thu') and self.var_phong_thu.get():
                self.var_phong_thu.set(False)
                self.log_info("ℹ️ [Chiến Đấu] Đã tự động tắt Kỹ Năng Phòng Thủ để chạy 'Buff (HP / SP)'.")
            self.save_config()

            self._reset_stop_flags()
            tab_name, tab_index = self._get_selected_ld_info()
            if tab_index is None:
                self.log_error("Vui lòng chọn một Tab LDPlayer trước khi kích hoạt ô Buff!")
                self.var_buff.set(False)
                self.save_config()
                return

            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.log_error(f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                self.var_buff.set(False)
                self.save_config()
                return

            choice = self.combo_buff.get() if hasattr(self, 'combo_buff') else "Buff HP"
            self.log_info(f"⚡ [Buff] Ô Buff vừa tích BẬT ➔ Kích hoạt tiến trình Buff song song (Chế độ: {choice}) trên Tab: {tab_name} (Index: {tab_index})...")
            if hasattr(self, '_thread_buff') and self._thread_buff and self._thread_buff.is_alive():
                return
            self._thread_buff = threading.Thread(target=self._run_buff_standalone, args=(dnconsole_path, tab_name, tab_index), daemon=True)
            self._thread_buff.start()
        else:
            self.log_info("🛑 [Buff] Ô Buff vừa bỏ tích ➔ Đã ngắt tiến trình Buff song song!")

    def _run_buff_standalone(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Worker thread thực thi độc lập/song song cho ô Buff mà không ảnh hưởng tới các Card khác"""
        try:
            while self.var_buff.get() and not self.stop_requested:
                choice = self.combo_buff.get() if hasattr(self, 'combo_buff') else "Buff HP"
                if choice == "Buff HP":
                    self._handle_buff_hp(dnconsole_path, tab_name, tab_index)
                elif choice == "Buff SP":
                    self._handle_buff_sp(dnconsole_path, tab_name, tab_index)
                elif choice == "Buff HP / SP":
                    self._handle_buff_cycle(dnconsole_path, tab_name, tab_index)
                else:
                    self._handle_buff_hp(dnconsole_path, tab_name, tab_index)

                if self._sleep_with_stop_check(0.1, check_active=self.var_buff.get):
                    break

            if not self.stop_requested and not self.var_buff.get():
                self.after(0, self.log_info, "🛑 [Buff] Đã dừng tiến trình Buff theo yêu cầu bỏ tích ô.")
        except Exception as e:
            self.after(0, self.log_error, f"❌ Lỗi luồng thực thi Buff song song: {str(e)}")
        finally:
            self._thread_buff = None

    def _tap_login_auto_twice(self, dnconsole_path: str, tab_index: str):
        """Tap 2 lần cách nhau 0.3s vào tọa độ nút Auto (190, 140)"""
        for tap_idx in range(1, 3):
            is_f_buff = hasattr(self, 'var_buff') and self.var_buff.get()
            is_d_active = hasattr(self, 'var_switch_D') and self.var_switch_D.get() and not (hasattr(self, '_should_stop_card_D') and self._should_stop_card_D())
            is_defense = (hasattr(self, 'var_phong_thu') and self.var_phong_thu.get()) or (hasattr(self, 'var_ket_gioi') and self.var_ket_gioi.get()) or (hasattr(self, 'var_linh_kinh') and self.var_linh_kinh.get()) or (hasattr(self, 'var_bang_tuong') and self.var_bang_tuong.get())

            if self.stop_requested or not (is_f_buff or is_d_active or is_defense):
                break
            log_tag = "Card D" if is_d_active else ("Phòng Thủ" if is_defense else "HP / SP")
            self.after(0, self.log_info, f"👉 [{log_tag}] Tap nút Auto (190, 140) lần {tap_idx}/2...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 190 140"])
            time.sleep(0.3)

    def _check_and_tap_f_tieptheo(self, dnconsole_path: str, tab_index: str, log_tag: str = "HP / SP", stop_check=None):
        """
        Ngay khi thấy card_f/f_dung.png:
        Quét tìm ảnh card_f/f_tieptheo.png (80%, ROI 1050, 530, 1165, 680) nghỉ 0.25s/lần trong 0.5s.
        Nếu thấy: tap vào ảnh card_f/f_tieptheo.png, hoãn 0.3s.
        Nếu không thấy: bỏ qua, chuyển sang Bước tiếp theo.
        """
        is_stop = stop_check if callable(stop_check) else (lambda: not self.var_buff.get() or self.stop_requested)
        if is_stop(): return
        self.after(0, self.log_info, f"👁️ [{log_tag}] Quét tìm 'card_f/f_tieptheo.png' (80%, ROI 1050,530,1165,680) nghỉ 0.25s/lần trong 0.5s...")
        start_tt = time.time()
        while time.time() - start_tt < 0.5:
            if is_stop(): return
            tt_x, tt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_tieptheo.png", threshold=0.80, region=(1050, 530, 1165, 680))
            if tt_x is not None and tt_y is not None:
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tt_x} {tt_y}"])
                time.sleep(0.3)
                break
            time.sleep(0.25)

    def _handle_buff_hp(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Hành động 1 - Buff HP: Lượt buff HP tiêu chuẩn kèm kiểm tra ưu tiên Hồi Sinh"""
        self._handle_buff_turn(dnconsole_path, tab_name, tab_index, action_type="HP", check_priority=True)

    def _handle_buff_sp(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Hành động 2 - Buff SP: Lượt buff SP tiêu chuẩn (thuần buff SP)"""
        self._handle_buff_turn(dnconsole_path, tab_name, tab_index, action_type="SP", check_priority=False)

    def _detect_dead_members(self, dnconsole_path: str, tab_index: str):
        """
        Mắt thần quét toàn bộ 10 thành viên trong assets/team_hp theo từng slot (Thuật toán tối ưu tập trung nhánh gục ngã).
        Danh sách trả về gồm tất cả các thành viên bị đánh chết, sắp xếp theo thứ tự: Hàng Sau trước, Hàng Trước sau.
        Cơ chế nhận diện chuẩn xác 100%:
        - Tầng 1: Kiểm tra máu đỏ HP tại vị trí đứng chuẩn (x+2 đến x+35, y đến y+5).
                  Nếu còn dải đỏ (red >= 8px) ➔ Thành viên còn sống 100% ➔ Bỏ qua ngay lập tức.
        - Tầng 2: Nếu mất máu đỏ khi đứng ➔ Quét tìm thanh SP xanh Cyan gục ngã bằng bộ lọc hình thái học ngang (kernel 8x1).
                  Khi tìm thấy thanh SP (bw >= 8, bh <= 6):
                  + Kiểm tra vị trí tụt thấp (dy_offset >= 11): Nhân vật ngã gục xuống sàn nên thanh SP thụt sâu xuống.
                  + Quét ngược lên trên 1..6px: Kiểm tra phía trên không còn máu đỏ HP (red_above <= 3).
                  ➔ Khẳng định 100% THÀNH VIÊN ĐÃ GỤC NGÃ (Tập trung tuyệt đối vào nhánh gục ngã, loại bỏ hoàn toàn nhận diện nhầm).
        """
        screen = self._capture_screen_fast(dnconsole_path, tab_index, max_cache_age=0.0)
        if screen is None or screen.size == 0:
            return []

        # Đảm bảo chuẩn kích thước 1280x720
        if screen.shape[0] != 720 or screen.shape[1] != 1280:
            screen = cv2.resize(screen, (1280, 720), interpolation=cv2.INTER_LINEAR)

        dead_list = []
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 1))

        for m in self._TEAM_HP_MEMBERS:
            x, y = m["x"], m["y"]

            # --- TẦNG 1: KIỂM TRA MÁU ĐỎ HP TẠI VỊ TRÍ ĐỨNG CHUẨN (TỐI ƯU CHỐNG NHIỄU) ---
            roi_standing_hp = screen[max(0, y):min(screen.shape[0], y + 5), max(0, x + 2):min(screen.shape[1], x + 35)]
            if roi_standing_hp.size > 0:
                b_s, g_s, r_s = cv2.split(roi_standing_hp)
                red_standing = int(np.sum((r_s >= 160) & (g_s <= 65) & (b_s <= 65)))
                # Phải có ít nhất 8px đỏ trở lên mới tính là còn sống (loại bỏ số damage và hiệu ứng skill rác)
                if red_standing >= 8:
                    continue
            else:
                red_standing = 0

            # --- TẦNG 2: MÁU ĐỎ THẤP / MẤT MÁU ➔ XÁC MINH CHẮC CHẮN ĐÃ GỤC XUỐNG SÀN ---
            # Vùng quét SP bao quát từ vị trí đứng đến vị trí thụt xuống khi ngã gục (y+4 đến y+28, x+2 đến x+35)
            roi_sp = screen[max(0, y + 4):min(screen.shape[0], y + 28), max(0, x + 2):min(screen.shape[1], x + 35)]
            if roi_sp.size == 0:
                continue

            b_sp, g_sp, r_sp = cv2.split(roi_sp)
            cyan_mask = ((b_sp >= 160) & (g_sp >= 100) & (r_sp <= 75)).astype(np.uint8) * 255

            # Lọc ngang dải SP: Loại bỏ sạch sẽ ngọc tròn và mảng áo to (kernel 8x1 bắt cả khi SP cạn)
            cyan_bars = cv2.morphologyEx(cyan_mask, cv2.MORPH_OPEN, kernel_h)
            num_c, _, stats_c, _ = cv2.connectedComponentsWithStats(cyan_bars)

            is_confirmed_dead = False
            sp_px = 0

            for i in range(1, num_c):
                bx, by, bw, bh, area = stats_c[i]
                if bw >= 8 and bh <= 6:
                    # Tọa độ tuyệt đối của dải SP này trên màn hình
                    abs_sp_x = x + 2 + bx
                    abs_sp_y = y + 4 + by
                    dy_offset = abs_sp_y - y

                    # CHỈ XÉT TRƯỜNG HỢP DUY NHẤT: ĐÃ NGÃ GỤC XUỐNG SÀN (dy_offset >= 11)
                    # (Nhân vật còn đứng = còn sống 100%, chỉ gục ngã xuống sàn mới xác nhận đã chết)
                    if dy_offset >= 11:
                        # Quét ngược lên trên 1..6px kiểm tra không còn máu đỏ HP
                        roi_above = screen[max(0, abs_sp_y - 6):abs_sp_y, abs_sp_x:min(screen.shape[1], abs_sp_x + bw)]
                        if roi_above.size > 0:
                            b_a, g_a, r_a = cv2.split(roi_above)
                            red_above = int(np.sum((r_a >= 160) & (g_a <= 65) & (b_a <= 65)))
                        else:
                            red_above = 0

                        # Phía trên không còn đỏ (red_above <= 3) ➔ 100% ĐÃ GỤC NGÃ!
                        if red_above <= 3:
                            is_confirmed_dead = True
                            sp_px = area
                            break

            # Có dải SP thỏa mãn điều kiện gục ngã ➔ Xác nhận thành viên đã chết!
            if is_confirmed_dead:
                dead_list.append({**m, "red_pixels": red_standing, "cyan_sp": sp_px})

        return dead_list

    def _handle_priority_hs(self, dnconsole_path: str, tab_name: str, tab_index: str, log_tag: str = "Buff HP / SP", is_card_d: bool = False, is_ket_gioi: bool = False, is_linh_kinh: bool = False, is_bang_tuong: bool = False, min_dead: int = 2, reverse_priority: bool = False) -> bool:
        """
        Bước 2: THAO TÁC ƯU TIÊN (_handle_priority_hs)
        QUY TẮC: CHỈ KÍCH HOẠT HỒI SINH KHI CÓ ĐỦ SỐ THÀNH VIÊN BỊ CHẾT (>= min_dead, mặc định 2; Mốc Chart/Chart-Pet là >= 1; Mốc Team là >= 3).
        - Nếu có 0 người chết: Chuyển tiếp sang Bước 3 (Buff chiêu bình thường).
        - Nếu số người chết < min_dead: Bỏ qua thao tác hồi sinh ➔ Chuyển tiếp sang Bước 3 (Buff chiêu bình thường).
        - Nếu có đủ từ min_dead người chết trở lên:
          + Lấy thành viên chết có độ ưu tiên cao nhất:
            * Chuẩn (reverse_priority=False): Hàng Sau trước, Hàng Trước sau (HS_1 -> HS_5 -> HT_1 -> HT_5).
            * Đảo ngược (reverse_priority=True): Đảo ngược hoàn toàn từ cuối lên (HT_5 ngược về HT_1 rồi đến HS_5 ngược về HS_1).
          + Quét tìm ảnh kỹ năng card_f/skill/f_hs.png (85%, ROI: 640, 0, 1280, 145).
          + Nếu KHÔNG thấy chiêu: Chuyển tiếp sang Bước 3 ➔ Hoãn 0.1s.
          + Nếu CÓ thấy chiêu:
            * Tap vào chiêu f_hs.png ➔ Hoãn 0.2s.
            * Tap skill vào tọa độ offset cơ thể người chết ưu tiên (X + 35, Y + 95) ➔ Hoãn 0.2s.
            * Tap 2 lần nút Auto (190, 140) cách nhau 0.3s ➔ Hoãn chờ 5s ➔ Kết thúc lượt quay lại vòng lặp.
        """
        def _is_stopped():
            if is_card_d:
                return self._should_stop_card_D()
            if is_ket_gioi or is_linh_kinh or is_bang_tuong:
                return not self.var_phong_thu.get() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set())
            return not self.var_buff.get() or self.stop_requested

        if _is_stopped():
            return False

        # Quét danh sách tất cả thành viên bị chết trong 10 slot
        dead_members = self._detect_dead_members(dnconsole_path, tab_index)
        total_dead = len(dead_members)

        # Trường hợp 1: Không có ai chết
        if total_dead == 0:
            self.after(0, self.log_info, f"💚 [{log_tag}] Không có thành viên nào bị chết ➔ Chuyển tiếp sang bước ra chiêu bình thường.")
            return False

        # Trường hợp 2: Số người chết không đủ điều kiện (< min_dead)
        if total_dead < min_dead:
            dead_names = ", ".join([m.get("name", m.get("key", "Unknown")) for m in dead_members])
            self.after(0, self.log_info, f"ℹ️ [{log_tag}] Phát hiện {total_dead} thành viên bị chết [{dead_names}] (< {min_dead} người) ➔ Bỏ qua Hồi Sinh, chuyển tiếp sang bước ra chiêu bình thường.")
            return False

        # Trường hợp 3: Đạt số người chết tối thiểu (>= min_dead) -> KÍCH HOẠT HỒI SINH
        dead_names = ", ".join([m.get("name", m.get("key", "Unknown")) for m in dead_members])
        if reverse_priority:
            priority_member = dead_members[-1]
            prio_desc = "Đảo ngược (từ cuối lên)"
        else:
            priority_member = dead_members[0]
            prio_desc = "Chuẩn (HS->HT)"

        key_name = priority_member.get("name", priority_member.get("key", "Unknown"))
        d_x = priority_member.get("x", 0)
        d_y = priority_member.get("y", 0)
        red_px = priority_member.get("red_pixels", 0)
        cyan_px = priority_member.get("cyan_sp", 0)

        self.after(0, self.log_info, f"💀 [{log_tag}] Phát hiện {total_dead} thành viên BỊ CHẾT [{dead_names}] (>= {min_dead} người) ➔ Kích hoạt Hồi Sinh [{prio_desc}] cho mục tiêu ưu tiên '{key_name}' (Đỏ: {red_px}px, SP: {cyan_px}px)")
        time.sleep(0.1)

        if _is_stopped():
            return False

        # Quét tìm ảnh kỹ năng card_f/skill/f_hs.png (85%, ROI: 640, 0, 1280, 145)
        self.after(0, self.log_info, f"👁️ [{log_tag}] Quét tìm chiêu hồi sinh 'card_f/skill/f_hs.png' (85%, ROI 640,0,1280,145)...")
        hs_x, hs_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/skill/f_hs.png", threshold=0.85, region=(640, 0, 1280, 145))

        # Nếu KHÔNG thấy chiêu: chuyển tiếp sang Bước 3 ➔ Hoãn 0.1s
        if hs_x is None or hs_y is None:
            self.after(0, self.log_info, f"⚠️ [{log_tag}] KHÔNG thấy chiêu 'card_f/skill/f_hs.png' ➔ Chuyển tiếp sang Bước 3 ➔ Hoãn 0.1s.")
            time.sleep(0.1)
            return False

        # Nếu CÓ thấy chiêu:
        self.after(0, self.log_info, f"🎯 [{log_tag}] Đã thấy chiêu hồi sinh 'card_f/skill/f_hs.png' tại ({hs_x}, {hs_y}) ➔ Tap chọn chiêu")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {hs_x} {hs_y}"])
        time.sleep(0.2)

        if _is_stopped():
            return True

        # Tính từ ảnh thành viên bị chết: X_offset + 35 , Y_offset + 95 , tap skill vào tọa độ offset , hoãn 0.2s
        target_x = d_x + 35
        target_y = d_y + 95
        self.after(0, self.log_info, f"👉 [{log_tag}] Tap mục tiêu hồi sinh '{key_name}' tại tọa độ ({target_x}, {target_y}) (offset +35, +95)")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {target_x} {target_y}"])
        time.sleep(0.2)

        if _is_stopped():
            return True

        # Tap 2 lần nút Auto (190, 140) cách nhau 0.3s ➔ Hoãn chờ 5s ➔ Kết thúc lượt quay lại vòng lặp
        self.after(0, self.log_info, f"🎯 [{log_tag}] Tap 2 lần nút Auto (190, 140) ➔ Hoãn 5s ➔ Kết thúc lượt hồi sinh...")
        self._tap_login_auto_twice(dnconsole_path, tab_index)
        if self._sleep_with_stop_check(5.0, check_active=lambda: not _is_stopped()):
            return True

        return True

    def _handle_buff_turn(self, dnconsole_path: str, tab_name: str, tab_index: str, action_type: str = "HP", check_priority: bool = True):
        """
        Xử lý 1 lượt đánh hoàn chỉnh cho Mốc Buff (HP, SP hoặc Chu kỳ HP / SP):
        1. Quét chờ xuất hiện card_f/f_dung.png (80%, ROI 640,0,1280,145) (0.5s/lần) (CHỈ QUÉT KHÔNG TAP).
           - Ngay khi thấy: quét tìm f_tieptheo.png (80%, ROI 1050,530,1165,680) nghỉ 0.25s/lần trong 0.5s. Nếu thấy thì tap, hoãn 0.3s.
        2. THAO TÁC ƯU TIÊN (Nếu check_priority=True): Gọi _handle_priority_hs(...)
           - Nếu trả về True: Đã hoàn tất hành động ưu tiên trong lượt ➔ Kết thúc lượt.
           - Nếu trả về False: Chuyển sang thực hiện kỹ năng theo chu kỳ (HP hoặc SP).
        3. Thực hiện kỹ năng Buff:
           - Nếu action_type == "HP": Quét tìm card_f/skill/f_hp.png (85%, ROI 640,0,1280,145).
             + Không thấy: Tap 2 lần nút Auto (190, 140) hoãn 5s.
             + Có thấy: Tap f_hp.png hoãn 0.2s ➔ Tap đồng đội (905, 515) hoãn 0.2s ➔ Tap 2 lần nút Auto (190, 140) hoãn 5s.
           - Nếu action_type == "SP": Quét tìm card_f/skill/f_sp.png (85%, ROI 640,0,1280,145).
             + Không thấy: Tap 2 lần nút Auto (190, 140) hoãn 5s.
             + Có thấy: Tap f_sp.png hoãn 0.2s ➔ Tap đồng đội (905, 515) hoãn 0.2s ➔ Tap 2 lần nút Auto (190, 140) hoãn 5s.
        """
        if not self.var_buff.get() or self.stop_requested: return

        # 1. Quét chờ xuất hiện: Quét tìm ảnh card_f/f_dung.png (80%, ROI 640,0,1280,145) (0.5s/lần) cho tới khi xuất hiện (CHỈ QUÉT KHÔNG TAP)
        self.after(0, self.log_info, f"👁️ [Buff {action_type}] Quét chờ xuất hiện 'card_f/f_dung.png' (80%, ROI 640,0,1280,145) (0.5s/lần)...")
        d_x, d_y = None, None
        while not self.stop_requested and self.var_buff.get():
            d_x, d_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
            if d_x is not None and d_y is not None:
                break
            if self._sleep_with_stop_check(0.5, check_active=self.var_buff.get): return

        if not self.var_buff.get() or self.stop_requested: return
        self.after(0, self.log_info, f"🎯 [Buff {action_type}] Đã thấy 'card_f/f_dung.png' tại ({d_x}, {d_y}) (CHỈ QUÉT KHÔNG TAP)...")

        # Quét tìm f_tieptheo.png trong 0.5s
        self._check_and_tap_f_tieptheo(dnconsole_path, tab_index, log_tag=f"Buff {action_type}")

        if not self.var_buff.get() or self.stop_requested: return

        # 2. KIỂM TRA THAO TÁC ƯU TIÊN TRƯỚC TIÊN (NẾU ĐƯỢC BẬT)
        if check_priority:
            self.after(0, self.log_info, f"🔍 [Buff {action_type}] Kiểm tra Thao Tác Ưu Tiên (Hồi Sinh)...")
            handled_priority = self._handle_priority_hs(dnconsole_path, tab_name, tab_index, log_tag=f"Buff {action_type} - HS")
            if handled_priority:
                self.after(0, self.log_info, f"⭐ [Buff {action_type}] Đã hoàn tất Thao Tác Ưu Tiên trong lượt này!")
                return

        if not self.var_buff.get() or self.stop_requested: return

        # 3. THỰC HIỆN KỸ NĂNG BUFF THEO LOẠI (HP hoặc SP)
        skill_img = "card_f/skill/f_hp.png" if action_type == "HP" else "card_f/skill/f_sp.png"
        self.after(0, self.log_info, f"👉 [Buff {action_type}] Chuyển sang Buff {action_type} ➔ Quét tìm '{skill_img}' (85%, ROI 640,0,1280,145)...")

        s_x, s_y = self._find_template_on_screen(dnconsole_path, tab_index, skill_img, threshold=0.85, region=(640, 0, 1280, 145))
        if s_x is None or s_y is None:
            self.after(0, self.log_info, f"⚠️ [Buff {action_type}] KHÔNG thấy '{skill_img}' (85%) ➔ Tap 2 lần nút Auto (190, 140) hoãn 5s...")
            self._tap_login_auto_twice(dnconsole_path, tab_index)
            if self._sleep_with_stop_check(5.0, check_active=self.var_buff.get): return
        else:
            self.after(0, self.log_info, f"🎯 [Buff {action_type}] Đã thấy '{skill_img}' tại ({s_x}, {s_y}) ➔ Tap")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {s_x} {s_y}"])
            time.sleep(0.2)

            if not self.var_buff.get() or self.stop_requested: return
            self.after(0, self.log_info, f"🎯 [Buff {action_type}] Tap tọa độ cố định (905, 515)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 905 515"])
            time.sleep(0.2)

            if not self.var_buff.get() or self.stop_requested: return
            self.after(0, self.log_info, f"🎯 [Buff {action_type}] Tap 2 lần nút Auto (190, 140)")
            self._tap_login_auto_twice(dnconsole_path, tab_index)
            if self._sleep_with_stop_check(5.0, check_active=self.var_buff.get): return

    def _handle_buff_cycle(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """
        Mốc Buff HP / SP:
        - Vận hành theo chu kỳ: 5 lượt đầu buff HP ➔ lượt thứ 6 buff SP.
        - Có tích hợp sẵn Thao Tác Ưu Tiên (_handle_priority_hs) kiểm tra ở mỗi lượt trước khi ra chiêu.
        """
        if not self.var_buff.get() or self.stop_requested: return

        # 5 Lượt đầu: Buff HP (kèm kiểm tra ưu tiên mỗi lượt)
        for hp_round in range(1, 6):
            if not self.var_buff.get() or self.stop_requested: return
            if hasattr(self, 'combo_buff') and self.combo_buff.get() != "Buff HP / SP": return
            self.after(0, self.log_info, f"🔄 [Buff HP / SP] ➔ [Chu kỳ HP - Lần {hp_round}/5] Bắt đầu lượt...")
            self._handle_buff_turn(dnconsole_path, tab_name, tab_index, action_type="HP")

        if not self.var_buff.get() or self.stop_requested: return
        if hasattr(self, 'combo_buff') and self.combo_buff.get() != "Buff HP / SP": return

        # Lượt 6: Buff SP (kèm kiểm tra ưu tiên)
        self.after(0, self.log_info, "🔄 [Buff HP / SP] ➔ [Chu kỳ SP - Lần 1/1 (Lượt 6)] Bắt đầu lượt...")
        self._handle_buff_turn(dnconsole_path, tab_name, tab_index, action_type="SP")

    # -------------------------------------------------------------------------
    # Ô KẾT GIỚI (MENU: Chart / Chart / Pet / Team)
    # -------------------------------------------------------------------------
    def _update_phong_thu_state(self):
        """Cập nhật trạng thái các ô dropdown Kỹ Năng Phòng Thủ (luôn mở sáng để chọn trước chế độ)"""
        if hasattr(self, 'combo_phong_thu_skill'):
            self.combo_phong_thu_skill.configure(state="normal", fg_color="#374151", button_color="#4B5563", button_hover_color="#6B7280", text_color="#FFFFFF")
        if hasattr(self, 'combo_phong_thu_target'):
            self.combo_phong_thu_target.configure(state="normal", fg_color="#374151", button_color="#4B5563", button_hover_color="#6B7280", text_color="#FFFFFF")


    def _on_phong_thu_toggled(self):
        """Callback cho ô Kỹ Năng Phòng Thủ (Tab Chiến Đấu): Khởi chạy luồng chạy song song độc lập"""
        self._update_phong_thu_state()
        self.save_config()

        if self.var_phong_thu.get():
            # Chống xung đột Card Chiến Đấu: Tự động nhả ô HP / SP
            if hasattr(self, 'var_buff') and self.var_buff.get():
                self.var_buff.set(False)
                self.log_info("ℹ️ [Chiến Đấu] Đã tự động tắt 'HP / SP' để chạy Kỹ Năng Phòng Thủ.")
            self.save_config()

            self._reset_stop_flags()
            tab_name, tab_index = self._get_selected_ld_info()
            if tab_index is None:
                self.log_error("Vui lòng chọn một Tab LDPlayer trước khi kích hoạt Kỹ Năng Phòng Thủ!")
                self.var_phong_thu.set(False)
                self.save_config()
                return

            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.log_error(f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                self.var_phong_thu.set(False)
                self.save_config()
                return

            skill_name = self.combo_phong_thu_skill.get() if hasattr(self, 'combo_phong_thu_skill') else "Kết Giới"
            choice = self.combo_phong_thu_target.get() if hasattr(self, 'combo_phong_thu_target') else "Chart"
            self.log_info(f"🛡️ [PHÒNG THỦ] Ô Kỹ Năng vừa tích BẬT ➔ Kích hoạt tiến trình [{skill_name}] (Chế độ: {choice}) trên Tab: {tab_name} (Index: {tab_index})...")

            if hasattr(self, '_thread_phong_thu') and self._thread_phong_thu and self._thread_phong_thu.is_alive():
                return
            self._thread_phong_thu = threading.Thread(target=self._run_phong_thu_standalone, args=(dnconsole_path, tab_name, tab_index), daemon=True)
            self._thread_phong_thu.start()
        else:
            self.log_info("🛑 [PHÒNG THỦ] Ô Kỹ Năng vừa bỏ tích ➔ Đã ngắt tiến trình song song!")


    # =========================================================================
    # 🛡️ UNIFIED COMBAT DEFENSE ENGINE (KẾT GIỚI / LINH KÍNH / BĂNG TƯỜNG)
    # =========================================================================
    _COMBAT_DEFENSE_CONFIGS = {
        "Kết Giới": {
            "key": "ket_gioi",
            "name": "KẾT GIỚI",
            "icon": "🛡️",
            "template": "card_f/skill/f_kg.png",
            "var_name": "var_phong_thu",
            "combo_name": "combo_phong_thu_target",
            "max_turns": 5,
        },
        "Linh Kính": {
            "key": "linh_kinh",
            "name": "LINH KÍNH",
            "icon": "🪞",
            "template": "card_f/skill/f_lk.png",
            "var_name": "var_phong_thu",
            "combo_name": "combo_phong_thu_target",
            "max_turns": 4,
        },
        "Băng Tường": {
            "key": "bang_tuong",
            "name": "BĂNG TƯỜNG",
            "icon": "🧊",
            "template": "card_f/skill/f_bt.png",
            "var_name": "var_phong_thu",
            "combo_name": "combo_phong_thu_target",
            "max_turns": 3,
        }
    }
    # Hỗ trợ cả key tiếng Anh và tiếng Việt
    _COMBAT_DEFENSE_CONFIGS["ket_gioi"] = _COMBAT_DEFENSE_CONFIGS["Kết Giới"]
    _COMBAT_DEFENSE_CONFIGS["linh_kinh"] = _COMBAT_DEFENSE_CONFIGS["Linh Kính"]
    _COMBAT_DEFENSE_CONFIGS["bang_tuong"] = _COMBAT_DEFENSE_CONFIGS["Băng Tường"]

    def _combat_skill_buoc_1(self, dnconsole_path: str, tab_index: str, skill_cfg: dict) -> bool:
        """
        BƯỚC 1: Quét Nhận Diện Bắt Đầu Lượt Đánh (Dùng chung cho cả Kết Giới / Linh Kính / Băng Tường)
        1. Quét f_dung.png trong ROI: (640, 0, 1280, 145) với độ khớp 80%, lặp lại mỗi 0.5s.
           Quy tắc: CHỈ QUÉT, KHÔNG TAP vào f_dung.png.
        2. Ngay khi thấy f_dung.png, quét phụ f_tieptheo.png trong ROI: (1050, 530, 1165, 680) với độ khớp 80%,
           nghỉ 0.25s/lần trong tối đa 0.5s.
           - Nếu tìm thấy: Tap click trực tiếp vào tọa độ ảnh f_tieptheo.png, sau đó hoãn 0.3s rồi sang Bước 2.
           - Nếu không thấy trong 0.5s: Bỏ qua và chuyển thẳng sang Bước 2.
        """
        var_skill = getattr(self, skill_cfg["var_name"])
        check_active = var_skill.get
        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return False

        skill_tag = skill_cfg["name"]
        self.after(0, self.log_info, f"👁️ [{skill_tag} - BƯỚC 1] Quét chờ lượt đánh 'card_f/f_dung.png' (80%, ROI 640,0,1280,145) mỗi 0.5s...")
        d_x, d_y = None, None
        while not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()) and check_active():
            d_x, d_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
            if d_x is not None and d_y is not None:
                break
            if self._sleep_with_stop_check(0.5, check_active=check_active):
                return False

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return False

        self.after(0, self.log_info, f"🎯 [{skill_tag} - BƯỚC 1] Đã phát hiện 'card_f/f_dung.png' tại ({d_x}, {d_y}) (CHỈ QUÉT, KHÔNG TAP) ➔ Đã đến lượt ra chiêu!")

        # 2. Quét phụ nút Tiếp Theo (f_tieptheo.png) trong tối đa 0.5s (nghỉ 0.25s/lần)
        self._check_and_tap_f_tieptheo(
            dnconsole_path, tab_index,
            log_tag=f"{skill_tag} - BƯỚC 1",
            stop_check=lambda: not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set())
        )

        return not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()) and check_active()

    def _combat_skill_tap_auto_twice_and_wait(self, dnconsole_path: str, tab_index: str, skill_cfg: dict, wait_seconds: float = 5.0):
        """Tap 2 lần liên tiếp vào nút Auto (190, 140) cách nhau 0.3s, sau đó hoãn chờ wait_seconds (mặc định 5.0s)"""
        var_skill = getattr(self, skill_cfg["var_name"])
        check_active = var_skill.get
        skill_tag = skill_cfg["name"]

        for tap_idx in range(1, 3):
            if self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()) or not check_active():
                break
            self.after(0, self.log_info, f"👉 [{skill_tag}] Tap nút Auto (190, 140) lần {tap_idx}/2...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 190 140"])
            time.sleep(0.3)

        if not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()) and check_active():
            self.after(0, self.log_info, f"⏳ [{skill_tag}] Hoãn chờ cố định {wait_seconds}s (chờ thi triển skill & hồi lượt đánh)...")
            self._sleep_with_stop_check(wait_seconds, check_active=check_active)

    def _check_defense_priority_hs(self, dnconsole_path: str, tab_name: str, tab_index: str,
                                   skill_cfg: dict, mode_tag: str, min_dead: int = 1,
                                   reverse_priority: bool = False, turn_label: str = "") -> bool:
        """
        Helper kiểm tra và thực hiện Thao Tác Ưu Tiên Hồi Sinh trong kỹ năng phòng thủ.
        Trả về True nếu đã xử lý hồi sinh (để hàm gọi return luôn), False nếu không có ai cần HS.
        """
        skill_tag = skill_cfg["name"]
        prefix = f"[{skill_tag} - {mode_tag}]"
        turn_str = f" [{turn_label}]" if turn_label else ""
        dead_str = f">= {min_dead} người chết" + (", đảo ngược" if reverse_priority else "")

        self.after(0, self.log_info, f"🔍 {prefix}{turn_str} Kiểm tra Thao Tác Ưu Tiên (Hồi Sinh {dead_str})...")

        hs_kwargs = {
            "log_tag": f"{skill_tag} - {mode_tag} - HS",
            "min_dead": min_dead,
            "reverse_priority": reverse_priority
        }
        if skill_cfg["key"] == "ket_gioi":
            hs_kwargs["is_ket_gioi"] = True
        elif skill_cfg["key"] == "linh_kinh":
            hs_kwargs["is_linh_kinh"] = True
        elif skill_cfg["key"] == "bang_tuong":
            hs_kwargs["is_bang_tuong"] = True

        handled_priority = self._handle_priority_hs(dnconsole_path, tab_name, tab_index, **hs_kwargs)
        if handled_priority:
            finish_str = f" trong {turn_label}" if turn_label else " trong lượt này"
            self.after(0, self.log_info, f"⭐ {prefix} Đã hoàn tất Thao Tác Ưu Tiên (Hồi Sinh){finish_str}!")
            return True
        return False

    def _cast_defense_skill_to_target(self, dnconsole_path: str, tab_index: str, skill_cfg: dict,
                                      target_x: int, target_y: int, target_label: str,
                                      step_tag: str, check_active) -> bool:
        """
        Helper ra chiêu kỹ năng phòng thủ:
        - Quét template skill (85%, ROI 640,0,1280,145)
        - Nếu không thấy: Tap 2 lần Auto (190, 140) -> Chờ 5.0s -> Trả về False
        - Nếu thấy: Tap skill -> Chờ 0.2s -> Tap mục tiêu (target_x, target_y) -> Chờ 0.2s -> Tap 2 lần Auto -> Chờ 5.0s -> Trả về True
        """
        skill_tag = skill_cfg["name"]
        skill_template = skill_cfg["template"]

        self.after(0, self.log_info, f"👉 [{skill_tag} - {step_tag}] BƯỚC 2: Quét tìm skill '{skill_template}' (85%, ROI 640,0,1280,145)...")
        s_x, s_y = self._find_template_on_screen(dnconsole_path, tab_index, skill_template, threshold=0.85, region=(640, 0, 1280, 145))

        if s_x is None or s_y is None:
            self.after(0, self.log_info, f"⚠️ [{skill_tag} - {step_tag}] KHÔNG thấy '{skill_template}' ➔ Tap 2 lần Auto (190, 140)")
            self._combat_skill_tap_auto_twice_and_wait(dnconsole_path, tab_index, skill_cfg, wait_seconds=5.0)
            return False

        self.after(0, self.log_info, f"🎯 [{skill_tag} - {step_tag}] Đã thấy '{skill_template}' tại ({s_x}, {s_y}) ➔ Tap")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {s_x} {s_y}"])
        time.sleep(0.2)

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return False

        self.after(0, self.log_info, f"🎯 [{skill_tag} - {step_tag}] Tap {target_label} nhận buff tại ({target_x}, {target_y})")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {target_x} {target_y}"])
        time.sleep(0.2)

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return False

        self.after(0, self.log_info, f"🎯 [{skill_tag} - {step_tag}] Tap 2 lần nút Auto (190, 140) kết thúc lượt buff")
        self._combat_skill_tap_auto_twice_and_wait(dnconsole_path, tab_index, skill_cfg, wait_seconds=5.0)
        return True

    def _handle_combat_defense_cycle(self, dnconsole_path: str, tab_name: str, tab_index: str,
                                     turn: int, skill_cfg: dict,
                                     target_map: dict, mode_tag: str) -> int:
        """
        Xử lý chu kỳ buff theo lượt (Dùng chung cho Chế Độ Chart và Chế Độ Chart / Pet):
        - target_map: dict dạng {turn_num: (tx, ty, label, next_info)}
        - Nếu turn có trong target_map: Tìm skill -> buff mục tiêu -> sang turn + 1
        - Nếu turn không có trong target_map (các lượt còn lại): Auto 2 lần -> sang turn + 1 (vòng lặp về 1 nếu > max_turns)
        """
        var_skill = getattr(self, skill_cfg["var_name"])
        check_active = var_skill.get
        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return turn

        skill_tag = skill_cfg["name"]
        max_turns = skill_cfg["max_turns"]

        # BƯỚC 1: Quét nhận diện bắt đầu lượt đánh
        self.after(0, self.log_info, f"⚔️ [{skill_tag} - {mode_tag}] [LƯỢT {turn}/{max_turns}] Bắt đầu Bước 1: Quét nhận diện lượt đánh...")
        if not self._combat_skill_buoc_1(dnconsole_path, tab_index, skill_cfg):
            return turn

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return turn

        # KIỂM TRA THAO TÁC ƯU TIÊN (HỒI SINH >= 1 NGƯỜI CHẾT)
        if self._check_defense_priority_hs(dnconsole_path, tab_name, tab_index, skill_cfg,
                                           mode_tag=mode_tag, min_dead=1, reverse_priority=False,
                                           turn_label=f"LƯỢT {turn}/{max_turns}"):
            return turn

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return turn

        if turn in target_map:
            tx, ty, target_label, next_info = target_map[turn]
            step_tag = f"{mode_tag}] [LƯỢT {turn}"
            cast_success = self._cast_defense_skill_to_target(
                dnconsole_path, tab_index, skill_cfg,
                target_x=tx, target_y=ty, target_label=target_label,
                step_tag=step_tag, check_active=check_active
            )
            if not cast_success:
                return 1

            self.after(0, self.log_info, f"✅ [{skill_tag} - {mode_tag}] Đã hoàn tất buff {target_label} Lượt {turn}! Chuyển sang {next_info}...")
            return turn + 1
        else:
            # Các lượt còn lại (Lượt 2..max_turns hoặc 3..max_turns): Bỏ qua Bước 2
            self.after(0, self.log_info, f"ℹ️ [{skill_tag} - {mode_tag}] [LƯỢT {turn}/{max_turns}] Đã xong Bước 1 ➔ Bỏ qua Bước 2. Tap 2 lần nút Auto (190, 140) xác nhận kết thúc lượt")
            self._combat_skill_tap_auto_twice_and_wait(dnconsole_path, tab_index, skill_cfg, wait_seconds=5.0)

            next_turn = turn + 1
            if next_turn > max_turns:
                self.after(0, self.log_info, f"🔄 [{skill_tag} - {mode_tag}] Đã hoàn tất chu kỳ {max_turns} lượt! Bắt đầu lại Lượt {max_turns+1} (tương ứng Lượt 1 mới để buff lại)...")
                next_turn = 1
            else:
                self.after(0, self.log_info, f"➡️ [{skill_tag} - {mode_tag}] Chuẩn bị sang Lượt {next_turn}/{max_turns}...")
            return next_turn

    def _handle_combat_defense_chart(self, dnconsole_path: str, tab_name: str, tab_index: str, turn: int, skill_cfg: dict) -> int:
        """
        Xử lý Chế Độ 1: Mốc Chart (Dùng chung cho Kết Giới / Linh Kính / Băng Tường)
        - Lượt 1: Buff Chart (905, 515) -> Chuyển sang Lượt 2
        - Lượt 2..max_turns: Auto 2 lần -> next_turn
        """
        target_map = {
            1: (905, 515, "mục tiêu đồng đội", "Lượt 2")
        }
        return self._handle_combat_defense_cycle(dnconsole_path, tab_name, tab_index, turn, skill_cfg, target_map, "CHART")

    def _handle_combat_defense_chart_pet(self, dnconsole_path: str, tab_name: str, tab_index: str, turn: int, skill_cfg: dict) -> int:
        """
        Xử lý Chế Độ 2: Mốc Chart / Pet (Dùng chung cho Kết Giới / Linh Kính / Băng Tường)
        - Lượt 1: Buff Chart (905, 515) -> Chuyển sang Lượt 2
        - Lượt 2: Buff Pet (825, 470) -> Chuyển sang Lượt 3
        - Lượt 3..max_turns: Auto 2 lần -> next_turn
        """
        target_map = {
            1: (905, 515, "mục tiêu Chart", "Lượt 2 (Buff Pet)"),
            2: (825, 470, "mục tiêu Pet", "Lượt 3 (Đánh thường / Auto)")
        }
        return self._handle_combat_defense_cycle(dnconsole_path, tab_name, tab_index, turn, skill_cfg, target_map, "CHART / PET")

    def _handle_combat_defense_team(self, dnconsole_path: str, tab_name: str, tab_index: str, target_idx: int, skill_cfg: dict) -> int:
        """
        Xử lý Chế Độ 3: Mốc Team (Dùng chung cho Kết Giới / Linh Kính / Băng Tường)
        - Danh sách thứ tự mục tiêu (Mục tiêu 3 đầu tiên khi vào trận, sau đó lần lượt 1 - 2 - 4 - 5):
            Index 0: Mục tiêu 3 -> (905, 515) (Ưu tiên đầu trận)
            Index 1: Mục tiêu 1 -> (1065, 435)
            Index 2: Mục tiêu 2 -> (985, 475)
            Index 3: Mục tiêu 4 -> (825, 555)
            Index 4: Mục tiêu 5 -> (745, 595)
        - Tự động reset target_idx = 0 khi hết trận (phát hiện f_vaotran.png).
        """
        var_skill = getattr(self, skill_cfg["var_name"])
        check_active = var_skill.get
        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return target_idx

        skill_tag = skill_cfg["name"]

        target_list = [
            {"num": 3, "name": "Mục tiêu 3 (Đầu trận)", "coord": (905, 515)},
            {"num": 1, "name": "Mục tiêu 1", "coord": (1065, 435)},
            {"num": 2, "name": "Mục tiêu 2", "coord": (985, 475)},
            {"num": 4, "name": "Mục tiêu 4", "coord": (825, 555)},
            {"num": 5, "name": "Mục tiêu 5", "coord": (745, 595)},
        ]
        curr_idx = target_idx % len(target_list)
        target_info = target_list[curr_idx]
        tx, ty = target_info["coord"]
        target_label = target_info["name"]

        # BƯỚC 1: Quét nhận diện bắt đầu lượt đánh (Đã hoàn thành hoãn 5s trước đó -> Kích hoạt quét f_vaotran & f_dung)
        self.after(0, self.log_info, f"⚔️ [{skill_tag} - TEAM] [{target_label} ({tx}, {ty})] Chờ lượt đánh 'f_dung' hoặc hết trận 'f_vaotran'...")

        found_turn = False
        while not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()) and check_active():
            # 1. Quét f_vaotran.png (ROI 1215, 0, 1280, 45, 80%) kiểm tra hết trận / ngoài trận
            vt_x, vt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
            if vt_x is not None and vt_y is not None:
                self.after(0, self.log_info, f"🎯 [{skill_tag} - TEAM] Phát hiện 'card_f/f_vaotran.png' tại ({vt_x}, {vt_y}) ➔ Trận đấu đã kết thúc / Đang ngoài trận!")
                self.after(0, self.log_info, f"🔄 [{skill_tag} - TEAM] Tự động reset chu kỳ buff về Mục tiêu 3 (905, 515). Chờ vào trận đấu mới...")
                while not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()) and check_active():
                    if self._sleep_with_stop_check(0.5, check_active=check_active):
                        return 0
                    # Kiểm tra nếu f_dung.png xuất hiện đột ngột (đã vào trận và đến lượt)
                    d_chk_x, d_chk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
                    if d_chk_x is not None and d_chk_y is not None:
                        self.after(0, self.log_info, f"🎯 [{skill_tag} - TEAM] Phát hiện 'card_f/f_dung.png' ➔ Đã chính thức vào trận đấu mới!")
                        found_turn = True
                        break
                    # Kiểm tra f_vaotran.png đã biến mất chưa
                    vt_chk_x, vt_chk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                    if vt_chk_x is None or vt_chk_y is None:
                        self.after(0, self.log_info, f"🎯 [{skill_tag} - TEAM] 'card_f/f_vaotran.png' đã biến mất ➔ Đã vào trận đấu mới! Bắt đầu chu kỳ từ Mục tiêu 3 (905, 515)...")
                        break

                if found_turn:
                    curr_idx = 0
                    target_info = target_list[0]
                    tx, ty = target_info["coord"]
                    target_label = target_info["name"]
                    break

            # 2. Quét f_dung.png (ROI 640, 0, 1280, 145, 80%) kiểm tra đến lượt ra chiêu
            d_x, d_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
            if d_x is not None and d_y is not None:
                self.after(0, self.log_info, f"🎯 [{skill_tag} - TEAM] Đã phát hiện 'card_f/f_dung.png' tại ({d_x}, {d_y}) (CHỈ QUÉT, KHÔNG TAP) ➔ Đã đến lượt ra chiêu! NGỪNG QUÉT f_vaotran!")
                found_turn = True
                break

            if self._sleep_with_stop_check(0.5, check_active=check_active):
                return curr_idx

        if not found_turn or not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return curr_idx

        # Quét phụ nút Tiếp Theo (f_tieptheo.png) trong tối đa 0.5s (nghỉ 0.25s/lần)
        self._check_and_tap_f_tieptheo(
            dnconsole_path, tab_index,
            log_tag=f"{skill_tag} - TEAM",
            stop_check=lambda: not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set())
        )

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return curr_idx

        # KIỂM TRA THAO TÁC ƯU TIÊN (HỒI SINH >= 3 NGƯỜI CHẾT, ƯU TIÊN ĐẢO NGƯỢC)
        if self._check_defense_priority_hs(dnconsole_path, tab_name, tab_index, skill_cfg,
                                           mode_tag="TEAM", min_dead=3, reverse_priority=True,
                                           turn_label=target_label):
            return curr_idx

        if not check_active() or self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
            return curr_idx

        # BƯỚC 2: Nhận diện Skill & Ra Chiêu
        step_tag = f"TEAM] [{target_label}"
        cast_success = self._cast_defense_skill_to_target(
            dnconsole_path, tab_index, skill_cfg,
            target_x=tx, target_y=ty, target_label=target_label,
            step_tag=step_tag, check_active=check_active
        )
        if not cast_success:
            return curr_idx

        next_idx = (curr_idx + 1) % len(target_list)
        next_target_info = target_list[next_idx]
        self.after(0, self.log_info, f"✅ [{skill_tag} - TEAM] Đã buff xong {target_label}! Mục tiêu tiếp theo: {next_target_info['name']} ({next_target_info['coord'][0]}, {next_target_info['coord'][1]})...")
        return next_idx

    def _run_phong_thu_standalone(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Worker thread thực thi Kỹ Năng Phòng Thủ (Kết Giới / Linh Kính / Băng Tường)"""
        try:
            turn_mode = 1
            team_target_idx = 0
            last_skill = None
            last_choice = None

            while self.var_phong_thu.get() and not self.stop_requested and not (hasattr(self, '_stop_event') and self._stop_event.is_set()):
                skill_name = self.combo_phong_thu_skill.get() if hasattr(self, 'combo_phong_thu_skill') else "Kết Giới"
                skill_cfg = self._COMBAT_DEFENSE_CONFIGS.get(skill_name, self._COMBAT_DEFENSE_CONFIGS.get("Kết Giới"))
                choice = self.combo_phong_thu_target.get() if hasattr(self, 'combo_phong_thu_target') else "Chart"

                if skill_name != last_skill or choice != last_choice:
                    last_skill = skill_name
                    last_choice = choice
                    turn_mode = 1
                    team_target_idx = 0
                    self.after(0, self.log_info, f"ℹ️ [{skill_cfg['name']}] Kỹ năng: {skill_name} | Chế độ: {choice} (Tab: {tab_name})")

                if choice == "Chart":
                    turn_mode = self._handle_combat_defense_chart(dnconsole_path, tab_name, tab_index, turn_mode, skill_cfg)
                elif choice == "Chart / Pet":
                    turn_mode = self._handle_combat_defense_chart_pet(dnconsole_path, tab_name, tab_index, turn_mode, skill_cfg)
                elif choice == "Team":
                    team_target_idx = self._handle_combat_defense_team(dnconsole_path, tab_name, tab_index, team_target_idx, skill_cfg)
                else:
                    self._sleep_with_stop_check(0.5, check_active=self.var_phong_thu.get)

            if not self.stop_requested and not self.var_phong_thu.get():
                self.after(0, self.log_info, "🛑 [Phòng Thủ] Đã dừng tiến trình Phòng Thủ theo yêu cầu bỏ tích ô.")
        except Exception as e:
            self.after(0, self.log_error, f"❌ Lỗi luồng thực thi Phòng Thủ song song: {str(e)}")
        finally:
            self._thread_phong_thu = None

    def _on_switch_C_toggled(self):
        """Callback công tắc Card DỊ GIỚI ĐÊM (C): Gạt ON ➔ Chạy hoặc xếp hàng tuần tự; Gạt OFF ➔ Dừng tiến trình card này"""
        self._on_checkbox_toggled()
        if not self.var_switch_C.get():
            self.save_config()
            self.log_info("🛑 [CARD C: DỊ GIỚI ĐÊM] Công tắc gạt về OFF ➔ Đã ngắt tiến trình Card Dị Giới!")
        else:
            self._reset_stop_flags()
            tab_name, tab_index = self._get_selected_ld_info()
            if tab_index is None:
                self.log_error("Vui lòng chọn một Tab LDPlayer trước khi bật công tắc Dị Giới!")
                self.var_switch_C.set(False)
                self.save_config()
                return

            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.log_error(f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                self.var_switch_C.set(False)
                self.save_config()
                return

            self.save_config()
            if hasattr(self, 'var_hen_gio') and self.var_hen_gio.get():
                t = self.var_hen_gio_time.get() if hasattr(self, 'var_hen_gio_time') else "05:00"
                self.log_info(f"⏰ [HẸN GIỜ] Card Dị Giới (C) đã bật ON và được lên lịch chờ đến mốc {t}!")
                return

            self._trigger_card_AB_workflow("Dị Giới")

    def _on_switch_B_toggled(self):
        """Callback công tắc Card PHỤ BẢN ĐƠN / ĐỘI (B): Gạt ON ➔ Tự chạy hoặc xếp hàng; Gạt OFF ➔ Dừng card này"""
        self._on_checkbox_toggled()
        if not self.var_switch_B.get():
            self._update_card_E_visibility()
            self.save_config()
            self.log_info("🛑 [CARD B: PHỤ BẢN ĐƠN / ĐỘI] Công tắc gạt về OFF ➔ Đã dừng tiến trình Card Phụ Bản!")
        else:
            self._update_card_E_visibility()
            self.save_config()
            if hasattr(self, 'var_hen_gio') and self.var_hen_gio.get():
                t = self.var_hen_gio_time.get() if hasattr(self, 'var_hen_gio_time') else "05:00"
                self.log_info(f"⏰ [HẸN GIỜ] Card Phụ Bản Đơn / Đội (B) đã bật ON và được lên lịch chờ đến mốc {t}!")
                return
            self._trigger_card_AB_workflow("Phụ Bản Đơn / Đội")

    def _on_switch_A_toggled(self):
        """Callback công tắc Card BOSS THẾ GIỚI (A): Gạt ON ➔ Tự chạy hoặc xếp hàng; Gạt OFF ➔ Dừng card này"""
        self._on_checkbox_toggled()
        if not self.var_switch_A.get():
            self.save_config()
            self.log_info("🛑 [CARD A: BOSS THẾ GIỚI] Công tắc gạt về OFF ➔ Đã dừng tiến trình Boss Thế Giới!")
        else:
            self.save_config()
            if hasattr(self, 'var_hen_gio') and self.var_hen_gio.get():
                t = self.var_hen_gio_time.get() if hasattr(self, 'var_hen_gio_time') else "05:00"
                self.log_info(f"⏰ [HẸN GIỜ] Card Boss Thế Giới (A) đã bật ON và được lên lịch chờ đến mốc {t}!")
                return
            self._trigger_card_AB_workflow("Boss Thế Giới")

    def _on_switch_D_toggled(self):
        """Callback riêng cho công tắc Tab Sự Kiện (Card D): Khi gạt ON ➔ Chạy hoặc xếp hàng tuần tự; Gạt OFF ➔ Ngắt tiến trình"""
        self._on_checkbox_toggled()
        if not self.var_switch_D.get():
            if hasattr(self, 'var_pause_D'):
                self.var_pause_D.set(False)
            self.save_config()
            self.log_info("🛑 [SỰ KIỆN - CARD D] Công tắc gạt về OFF ➔ Đã ngắt tiến trình & nhả ô Tạm Dừng!")
        else:
            self._reset_stop_flags()
            tab_name, tab_index = self._get_selected_ld_info()
            if tab_index is None:
                self.log_error("Vui lòng chọn một Tab LDPlayer trước khi bật công tắc Sự Kiện (Card D)!")
                self.var_switch_D.set(False)
                if hasattr(self, 'var_pause_D'):
                    self.var_pause_D.set(False)
                self.save_config()
                return

            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.log_error(f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                self.var_switch_D.set(False)
                if hasattr(self, 'var_pause_D'):
                    self.var_pause_D.set(False)
                self.save_config()
                return

            self.save_config()
            if hasattr(self, 'var_hen_gio') and self.var_hen_gio.get():
                t = self.var_hen_gio_time.get() if hasattr(self, 'var_hen_gio_time') else "05:00"
                self.log_info(f"⏰ [HẸN GIỜ] Tab Sự Kiện (Card D) đã bật ON và được lên lịch chờ đến mốc {t}!")
                return

            self._trigger_card_AB_workflow("40 NPC / Nhị Kiều")

    def _on_pause_D_toggled(self):
        """Callback nút Dừng ở Tab Sự Kiện: Tích vào thì tạm dừng, nhả ra chạy tiếp"""
        self._on_checkbox_toggled()
        if self.var_pause_D.get():
            self.log_info("⏸️ [Sự Kiện - Card D] Tích ô Dừng ➔ Tạm dừng hoạt động (nhả ô Dừng sẽ chạy tiếp)!")
        else:
            self.log_info("▶️ [Sự Kiện - Card D] Nhả ô Dừng ➔ Khôi phục chạy tiếp!")
        self.save_config()

    def _refresh_desktop_logs(self):
        """Làm mới danh sách nhật ký hiển thị trên Tab Nhật Ký của Desktop GUI"""
        if hasattr(self, 'txt_log') and hasattr(self, 'recent_logs'):
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            for line in self.recent_logs:
                self.txt_log.insert("end", f"{line}\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")

    def _create_unified_config_card(self):
        """Tạo hệ thống phân Tab giao diện Desktop theo phong cách app_ui (Tab 1: Cards A-D, Tab 2: Tổ Đội, Tab 3: Ngày, Tab 4: Chiến Đấu, Tab 5: Log)"""
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=10,
            fg_color=COLOR_CARD_BG,
            segmented_button_fg_color="#14161c",
            segmented_button_selected_color=COLOR_BTN_NAVY,
            segmented_button_selected_hover_color=COLOR_BTN_NAVY_HOVER,
            segmented_button_unselected_color=COLOR_INPUT_BG,
            segmented_button_unselected_hover_color=COLOR_BTN_NAVY,
            text_color=COLOR_TEXT_MAIN
        )
        self.tabview.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="nsew")

        # Khởi tạo 5 Tab chính theo đúng thứ tự (không dùng biểu tượng)
        tab_ctrl = self.tabview.add("Hoạt Động")
        tab_team = self.tabview.add("Tổ Đội")
        tab_daily = self.tabview.add("Sự Kiện")
        tab_combat = self.tabview.add("Chiến Đấu")
        tab_logs = self.tabview.add("Nhật Ký")

        # Cấu hình thanh tiêu đề Tab: cỡ 15 đậm, cao 38px rõ nét trải đều 5 cột
        if hasattr(self.tabview, "_segmented_button"):
            self.tabview._segmented_button.configure(
                font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
                height=38
            )
            self.tabview._segmented_button.grid(sticky="ew", padx=6)
            self.tabview._segmented_button.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="equal_tabs")

        # ------------------- TAB 1: 🎮 HOẠT ĐỘNG (CARDS A, NGÀY, C, B) -------------------
        # Cột Trái: Hàng 1: Card A (Boss TG) | Hàng 2: Card Ngày | Hàng 3: Card C (Dị Giới Đêm)
        # Cột Phải: Card B (Phụ Bản Đơn / Đội) - Chiều cao Y bằng 3 card bên trái
        self.container_cfg = ctk.CTkFrame(tab_ctrl, fg_color="transparent")
        self.container_cfg.pack(fill="both", expand=True, padx=4, pady=4)
        self.container_cfg.grid_columnconfigure(0, weight=1, uniform="card_cols")
        self.container_cfg.grid_columnconfigure(1, weight=1, uniform="card_cols")
        self.container_cfg.grid_rowconfigure(0, weight=1)

        # Cột trái: 3 Card (Hàng 1: Boss TG, Hàng 2: Ngày, Hàng 3: Dị Giới Đêm)
        self.col_left_cfg = ctk.CTkFrame(self.container_cfg, fg_color="transparent")
        self.col_left_cfg.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=0)
        self.col_left_cfg.grid_columnconfigure(0, weight=1)
        self.col_left_cfg.grid_rowconfigure(0, weight=80, uniform="left_card_rows")   # Hàng 1: Card A (Boss TG)
        self.col_left_cfg.grid_rowconfigure(1, weight=80, uniform="left_card_rows")   # Hàng 2: Card Ngày
        self.col_left_cfg.grid_rowconfigure(2, weight=160, uniform="left_card_rows")  # Hàng 3: Card C (Dị Giới Đêm)

        # Cột phải: 1 Card (Card B: Phụ Bản Đơn / Đội) - Chiều cao Y bằng 3 card bên trái
        self.col_right_cfg = ctk.CTkFrame(self.container_cfg, fg_color="transparent")
        self.col_right_cfg.grid(row=0, column=1, sticky="nsew", padx=(2, 0), pady=0)
        self.col_right_cfg.grid_columnconfigure(0, weight=1)
        self.col_right_cfg.grid_rowconfigure(0, weight=1)

        # ------------------- TAB 5: 📜 NHẬT KÝ HOẠT ĐỘNG -------------------
        hdr_log = ctk.CTkFrame(tab_logs, fg_color="transparent")
        hdr_log.pack(fill="x", padx=6, pady=(4, 6))
        lbl_log = ctk.CTkLabel(
            hdr_log,
            text="📜 Nhật Ký Hoạt Động Thời Gian Thực",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_ACCENT
        )
        lbl_log.pack(side="left")

        btn_ref_log = ctk.CTkButton(
            hdr_log,
            text="🔄 Làm Mới",
            width=90,
            height=29,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            text_color=COLOR_TEXT_MAIN,
            corner_radius=6,
            command=self._refresh_desktop_logs
        )
        btn_ref_log.pack(side="right")

        self.txt_log = ctk.CTkTextbox(
            tab_logs,
            font=ctk.CTkFont(family="Consolas", size=14),
            fg_color="#0e1015",
            text_color="#CBD5E1",
            corner_radius=8
        )
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # ------------------- CARD A: BOSS THẾ GIỚI (Cột Trái, Hàng 0) -------------------
        self.card_A = ctk.CTkFrame(self.col_left_cfg, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_A.grid(row=0, column=0, padx=4, pady=3, sticky="nsew")
        self.card_A.grid_columnconfigure(0, weight=1)
        self.card_A.grid_rowconfigure(0, weight=0)
        self.card_A.grid_rowconfigure(1, weight=1)

        hdr_A = ctk.CTkFrame(self.card_A, fg_color="transparent")
        hdr_A.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_A.grid_columnconfigure(0, weight=1)
        hdr_A.grid_columnconfigure(1, weight=0)

        lbl_A = ctk.CTkLabel(hdr_A, text="BOSS THẾ GIỚI", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_A.grid(row=0, column=0, sticky="w")

        self.switch_A = ctk.CTkSwitch(
            hdr_A, text="", variable=self.var_switch_A, command=self._on_switch_A_toggled,
            width=36, height=18, switch_width=34, switch_height=18, corner_radius=9,
            border_width=1, border_color=COLOR_INPUT_BORDER, fg_color=COLOR_INPUT_BG, progress_color=COLOR_ORANGE,
            button_color="#FFFFFF", button_hover_color="#E2E8F0"
        )
        self.switch_A.grid(row=0, column=1, sticky="e")

        char_options = self._get_character_options()

        # Row 1: Boss + Badge Hệ (tự động theo thứ hệ thống) + Menu Vị trí xuất chiến
        row_A1 = ctk.CTkFrame(self.card_A, fg_color="transparent")
        row_A1.grid(row=1, column=0, padx=8, pady=(2, 6), sticky="ew")

        # Cụm bên trái: [x] Boss + Badge Hệ
        left_box_A = ctk.CTkFrame(row_A1, fg_color="transparent")
        left_box_A.pack(side="left")

        self.chk_A1 = ctk.CTkCheckBox(
            left_box_A, text="Boss", variable=self.var_A1, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5, width=0
        )
        self.chk_A1.pack(side="left")

        # Badge Hệ Boss tự động cập nhật theo thứ hệ thống
        day_str, elem_name, elem_color = self._get_boss_element_info()
        self.lbl_A_elem = ctk.CTkLabel(
            left_box_A,
            text=f" {elem_name} ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=elem_color,
            fg_color=COLOR_INPUT_BG,
            corner_radius=6,
            height=22
        )
        self.lbl_A_elem.pack(side="left", padx=(6, 0))

        # Menu Vị trí xuất chiến
        self.combo_A_char = ctk.CTkOptionMenu(
            row_A1,
            values=char_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=120,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_A_char.set(char_options[0] if char_options else "Xuất Chiến")
        self.combo_A_char.pack(side="right", padx=(0, 2))


        # =========================================================================
        # 🔓 GIAO DIỆN CARD C (DỊ GIỚI ĐÊM - Cột Trái, Hàng 2)
        # =========================================================================
        self.card_C = ctk.CTkFrame(self.col_left_cfg, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_C.grid(row=2, column=0, padx=4, pady=3, sticky="nsew")
        self.card_C.grid_columnconfigure(0, weight=1)
        self.card_C.grid_rowconfigure(0, weight=0)
        self.card_C.grid_rowconfigure((1, 2, 3), weight=1)

        hdr_C = ctk.CTkFrame(self.card_C, fg_color="transparent")
        hdr_C.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_C.grid_columnconfigure(0, weight=1)
        hdr_C.grid_columnconfigure(1, weight=0)

        lbl_C = ctk.CTkLabel(hdr_C, text="DỊ GIỚI ĐÊM", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_C.grid(row=0, column=0, sticky="w")

        self.switch_C = ctk.CTkSwitch(
            hdr_C, text="", variable=self.var_switch_C, command=self._on_switch_C_toggled,
            width=36, height=18, switch_width=34, switch_height=18, corner_radius=9,
            border_width=1, border_color=COLOR_INPUT_BORDER, fg_color=COLOR_INPUT_BG, progress_color=COLOR_ORANGE,
            button_color="#FFFFFF", button_hover_color="#E2E8F0"
        )
        self.switch_C.grid(row=0, column=1, sticky="e")

        # Row 1: Phúc Thần + ( OFF / ON )
        row_C1 = ctk.CTkFrame(self.card_C, fg_color="transparent")
        row_C1.grid(row=1, column=0, padx=8, pady=1, sticky="ew")

        self.chk_C1 = ctk.CTkCheckBox(
            row_C1, text="Phúc Thần", variable=self.var_C1, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_C1.pack(side="left")

        lbl_C1_tag = ctk.CTkLabel(row_C1, text="( OFF / ON )", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MUTED)
        lbl_C1_tag.pack(side="right", padx=(0, 8))

        # Row 2: Ký Lục + ( OFF / ON )
        row_C2 = ctk.CTkFrame(self.card_C, fg_color="transparent")
        row_C2.grid(row=2, column=0, padx=8, pady=1, sticky="ew")

        self.chk_C2 = ctk.CTkCheckBox(
            row_C2, text="Ký Lục", variable=self.var_C2, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_C2.pack(side="left")

        lbl_C2_tag = ctk.CTkLabel(row_C2, text="( OFF / ON )", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MUTED)
        lbl_C2_tag.pack(side="right", padx=(0, 8))

        # Row 3: Rút Gọn + ( OFF / ON )
        row_C3 = ctk.CTkFrame(self.card_C, fg_color="transparent")
        row_C3.grid(row=3, column=0, padx=8, pady=(1, 4), sticky="ew")

        self.chk_C3 = ctk.CTkCheckBox(
            row_C3, text="Rút Gọn", variable=self.var_C3, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_C3.pack(side="left")

        lbl_C3_tag = ctk.CTkLabel(row_C3, text="( OFF / ON )", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MUTED)
        lbl_C3_tag.pack(side="right", padx=(0, 8))

        # =========================================================================
        # 🔓 GIAO DIỆN CARD B (PHỤ BẢN ĐƠN / ĐỘI - Cột Phải, Hàng 0 - Chiều cao bao quát)
        # =========================================================================
        self.card_B = ctk.CTkFrame(self.col_right_cfg, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_B.grid(row=0, column=0, padx=4, pady=3, sticky="nsew")
        self.card_B.grid_columnconfigure(0, weight=1)
        self.card_B.grid_rowconfigure(0, weight=0)
        self.card_B.grid_rowconfigure(1, weight=1)

        hdr_B = ctk.CTkFrame(self.card_B, fg_color="transparent")
        hdr_B.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_B.grid_columnconfigure(0, weight=1)
        hdr_B.grid_columnconfigure(1, weight=0)

        lbl_B = ctk.CTkLabel(hdr_B, text="PHỤ BẢN ĐƠN / ĐỘI", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_B.grid(row=0, column=0, sticky="w")

        self.switch_B = ctk.CTkSwitch(
            hdr_B, text="", variable=self.var_switch_B, command=self._on_switch_B_toggled,
            width=36, height=18, switch_width=34, switch_height=18, corner_radius=9,
            border_width=1, border_color=COLOR_INPUT_BORDER, fg_color=COLOR_INPUT_BG, progress_color=COLOR_ORANGE,
            button_color="#FFFFFF", button_hover_color="#E2E8F0"
        )
        self.switch_B.grid(row=0, column=1, sticky="e")

        # Thùng chứa thân Card B (gồm 4 Hàng nội dung đồng nhất + 1 đường gạch ngang)
        body_B = ctk.CTkFrame(self.card_B, fg_color="transparent")
        body_B.grid(row=1, column=0, padx=8, pady=(2, 6), sticky="nsew")
        body_B.grid_columnconfigure(0, weight=1)
        body_B.grid_rowconfigure((0, 2, 3, 4), weight=1, uniform="pb_row")
        body_B.grid_rowconfigure(1, weight=0)

        # HẰNG 1 (Phụ Bản Đơn): [ ] Đơn | [ Menu NV Đơn ]
        row1_frame = ctk.CTkFrame(body_B, fg_color="transparent")
        row1_frame.grid(row=0, column=0, sticky="ew")

        self.chk_B_don = ctk.CTkCheckBox(
            row1_frame, text="Đơn", variable=self.var_B_don, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_B_don.pack(side="left")

        self.combo_B_don_char = ctk.CTkOptionMenu(
            row1_frame,
            values=char_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=120,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_B_don_char.set(char_options[0] if char_options else "Xuất Chiến")
        self.combo_B_don_char.pack(side="right", padx=(0, 2))

        # Đường gạch ngang phân cách ở Row 1 (Nằm giữa Hàng 1 và Hàng 2)
        divider_horiz_B = ctk.CTkFrame(body_B, height=2, corner_radius=0, fg_color=COLOR_ORANGE, border_width=0)
        divider_horiz_B.grid(row=1, column=0, sticky="ew", padx=2, pady=(2, 4))

        # HẰNG 2 (Phụ Bản Đội): [ ] Đội | [ Menu NV Team ]
        row2_frame = ctk.CTkFrame(body_B, fg_color="transparent")
        row2_frame.grid(row=2, column=0, sticky="ew")

        self.chk_B_doi = ctk.CTkCheckBox(
            row2_frame, text="Đội", variable=self.var_B_doi, command=self._on_checkbox_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_B_doi.pack(side="left")

        self.combo_B_team_char = ctk.CTkOptionMenu(
            row2_frame,
            values=char_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=120,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_B_team_char.set(char_options[0] if char_options else "Xuất Chiến")
        self.combo_B_team_char.pack(side="right", padx=(0, 2))

        # HẰNG 3 (PB 20, PB 50, PB 80)
        row3_frame = ctk.CTkFrame(body_B, fg_color="transparent")
        row3_frame.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        row3_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="pb_cols")

        self.chk_B1 = ctk.CTkCheckBox(row3_frame, text="PB 20", variable=self.var_B1, command=self._on_checkbox_toggled, font=ctk.CTkFont(family=FONT_FAMILY, size=13), fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN, checkbox_width=16, checkbox_height=16, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5)
        self.chk_B1.grid(row=0, column=0, sticky="w")

        self.chk_B2 = ctk.CTkCheckBox(row3_frame, text="PB 50", variable=self.var_B2, command=self._on_checkbox_toggled, font=ctk.CTkFont(family=FONT_FAMILY, size=13), fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN, checkbox_width=16, checkbox_height=16, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5)
        self.chk_B2.grid(row=0, column=1, sticky="w")

        self.chk_B3 = ctk.CTkCheckBox(row3_frame, text="PB 80", variable=self.var_B3, command=self._on_checkbox_toggled, font=ctk.CTkFont(family=FONT_FAMILY, size=13), fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN, checkbox_width=16, checkbox_height=16, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5)
        self.chk_B3.grid(row=0, column=2, sticky="w")

        # HẰNG 4 (PB 110, PB 140)
        row4_frame = ctk.CTkFrame(body_B, fg_color="transparent")
        row4_frame.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        row4_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="pb_cols")

        self.chk_B4 = ctk.CTkCheckBox(row4_frame, text="PB 110", variable=self.var_B4, command=self._on_checkbox_toggled, font=ctk.CTkFont(family=FONT_FAMILY, size=13), fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN, checkbox_width=16, checkbox_height=16, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5)
        self.chk_B4.grid(row=0, column=0, sticky="w")

        self.chk_B5 = ctk.CTkCheckBox(row4_frame, text="PB 140", variable=self.var_B5, command=self._on_checkbox_toggled, font=ctk.CTkFont(family=FONT_FAMILY, size=13), fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN, checkbox_width=16, checkbox_height=16, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5)
        self.chk_B5.grid(row=0, column=1, sticky="w")

        # Placeholder col 2 để cân đối độ rộng tuyệt đối 3 cột với Hàng 3
        ctk.CTkFrame(row4_frame, fg_color="transparent", width=1, height=1).grid(row=0, column=2, sticky="nsew")

        # =========================================================================
        # 📅 GIAO DIỆN CARD NGÀY (TAB HOẠT ĐỘNG - Cột Trái, Hàng 1)
        # =========================================================================
        self.card_daily = ctk.CTkFrame(self.col_left_cfg, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_daily.grid(row=1, column=0, padx=4, pady=3, sticky="nsew")
        self.card_daily.grid_columnconfigure(0, weight=1)
        self.card_daily.grid_rowconfigure(0, weight=0)
        self.card_daily.grid_rowconfigure(1, weight=1)

        hdr_daily = ctk.CTkFrame(self.card_daily, fg_color="transparent")
        hdr_daily.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_daily.grid_columnconfigure(0, weight=1)

        lbl_daily = ctk.CTkLabel(hdr_daily, text="NGÀY", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_daily.grid(row=0, column=0, sticky="w")

        # Hàng 1: [ ] Nhận Thư | Menu Mốc Giờ (12H01 / 18H01 / 22H01 / Tất Cả)
        row_daily1 = ctk.CTkFrame(self.card_daily, fg_color="transparent")
        row_daily1.grid(row=1, column=0, padx=8, pady=(2, 6), sticky="ew")

        self.chk_nhan_thu = ctk.CTkCheckBox(
            row_daily1,
            text="Nhận Thư",
            variable=self.var_nhan_thu,
            command=self._on_nhan_thu_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE,
            hover_color=COLOR_ORANGE_HOVER,
            checkmark_color="#FFFFFF",
            text_color=COLOR_TEXT_MAIN,
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=5
        )
        self.chk_nhan_thu.pack(side="left")

        nhan_thu_time_options = ["Tất Cả", "12H01", "18H01", "22H01"]
        self.combo_nhan_thu_time = ctk.CTkOptionMenu(
            row_daily1,
            values=nhan_thu_time_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=120,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_nhan_thu_combo_changed(choice)
        )
        self.combo_nhan_thu_time.set("Tất Cả")
        self.combo_nhan_thu_time.pack(side="right", padx=(0, 2))

        # =========================================================================
        # 🔓 GIAO DIỆN CARD E (QUẢN LÝ TỔ ĐỘI)
        # =========================================================================
        self.card_E = ctk.CTkFrame(tab_team, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_E.pack(fill="both", expand=True, padx=8, pady=8)
        self.card_E.grid_columnconfigure(0, weight=1)
        self.card_E.grid_rowconfigure((0, 1), weight=0)
        self.card_E.grid_rowconfigure(2, weight=1)

        hdr_E = ctk.CTkFrame(self.card_E, fg_color="transparent")
        hdr_E.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_E.grid_columnconfigure(0, weight=1)

        self.lbl_E = ctk.CTkLabel(hdr_E, text="QUẢN LÝ TỔ ĐỘI", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        self.lbl_E.grid(row=0, column=0, sticky="w")

        # KHUNG ĐIỀU KHIỂN HÀNG QUÂN SƯ
        panel_E = ctk.CTkFrame(self.card_E, fg_color="transparent")
        panel_E.grid(row=1, column=0, padx=8, pady=(2, 4), sticky="ew")
        panel_E.grid_columnconfigure(0, weight=0)
        panel_E.grid_columnconfigure(1, weight=1)

        # Quân Sư
        self.lbl_E_quan_su = ctk.CTkLabel(
            panel_E,
            text="Quân Sư:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color="#F59E0B"
        )
        self.lbl_E_quan_su.grid(row=0, column=0, padx=(2, 6), pady=(2, 2), sticky="w")

        qs_opts = self._get_quan_su_options()
        self.combo_E_quan_su = ctk.CTkOptionMenu(
            panel_E,
            values=qs_opts,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=30,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_combo_quan_su_changed(choice)
        )
        self.combo_E_quan_su.set(qs_opts[0] if qs_opts else "(Trống)")
        self.combo_E_quan_su.grid(row=0, column=1, padx=(2, 2), pady=(2, 2), sticky="ew")

        # HÀNG 2: Khung chứa 2 Bảng danh sách A - B và Nút Mũi Tên ➔ ở giữa
        body_E = ctk.CTkFrame(self.card_E, fg_color="transparent")
        body_E.grid(row=2, column=0, padx=8, pady=(4, 8), sticky="nsew")
        body_E.grid_columnconfigure((0, 2), weight=1, uniform="equal_list_E")
        body_E.grid_columnconfigure(1, weight=0)
        body_E.grid_rowconfigure(0, weight=1)

        # 1. Bảng [Danh Sách A] bên trái (Tướng Có Sẵn)
        self.scroll_E_list_A = ctk.CTkScrollableFrame(
            body_E,
            fg_color=COLOR_INPUT_BG,
            corner_radius=8,
            scrollbar_button_color="#3a455a",
            scrollbar_button_hover_color="#4b5563"
        )
        self.scroll_E_list_A.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.scroll_E_list_A.grid_columnconfigure(0, weight=1)

        # 2. Khung ở giữa chứa Nút Mũi Tên ➔
        frame_mid_E = ctk.CTkFrame(body_E, fg_color="transparent")
        frame_mid_E.grid(row=0, column=1, sticky="ns", padx=4)

        self.btn_E_add = ctk.CTkButton(
            frame_mid_E,
            text="➔",
            width=38,
            height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
            text_color="#FFFFFF",
            fg_color=COLOR_ORANGE,
            hover_color=COLOR_ORANGE_HOVER,
            corner_radius=6,
            command=self._add_A_to_B_E
        )
        self.btn_E_add.pack(expand=True)

        # 3. Bảng [Danh Sách B] bên phải (Đội Hình)
        self.scroll_E_list_B = ctk.CTkScrollableFrame(
            body_E,
            fg_color=COLOR_INPUT_BG,
            corner_radius=8,
            scrollbar_button_color="#3a455a",
            scrollbar_button_hover_color="#4b5563"
        )
        self.scroll_E_list_B.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self.scroll_E_list_B.grid_columnconfigure(0, weight=1)

        # Nạp dữ liệu ban đầu cho Danh Sách A và Danh Sách B
        self._render_E_list_A_ui()
        self._render_E_list_B_ui()

        # =========================================================================
        # 🔓 GIAO DIỆN TAB SỰ KIỆN (LƯỚI CÂN ĐỐI 5 CARD HOÀN CHỈNH)
        # =========================================================================
        self.container_daily = ctk.CTkFrame(tab_daily, fg_color="transparent")
        self.container_daily.pack(fill="both", expand=True, padx=4, pady=4)
        self.container_daily.grid_columnconfigure((0, 1), weight=1, uniform="daily_cols")
        self.container_daily.grid_rowconfigure(0, weight=110)
        self.container_daily.grid_rowconfigure(1, weight=52, uniform="daily_mid_row")
        self.container_daily.grid_rowconfigure(2, weight=108, uniform="daily_bot_row")

        # =========================================================================
        # 1. HÀNG 1 (CỘT 0-1): CARD TỔ ĐỘI / KỸ NĂNG (TRÊN CÙNG, FULL 2 CỘT)
        # =========================================================================
        self.card_team_skill = ctk.CTkFrame(self.container_daily, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_team_skill.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=4, pady=(2, 3))
        self.card_team_skill.grid_columnconfigure(0, weight=1)
        self.card_team_skill.grid_rowconfigure(0, weight=0)
        self.card_team_skill.grid_rowconfigure(1, weight=1)

        hdr_team_skill = ctk.CTkFrame(self.card_team_skill, fg_color="transparent")
        hdr_team_skill.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_team_skill.grid_columnconfigure(0, weight=1)
        hdr_team_skill.grid_columnconfigure(1, weight=0)
        hdr_team_skill.grid_columnconfigure(2, weight=0)

        lbl_team_skill = ctk.CTkLabel(hdr_team_skill, text="TỔ ĐỘI / KỸ NĂNG", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_team_skill.grid(row=0, column=0, sticky="w")

        self.chk_pause_D = ctk.CTkCheckBox(
            hdr_team_skill, text="", variable=self.var_pause_D, command=self._on_pause_D_toggled,
            width=18, height=18,
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF",
            checkbox_width=18, checkbox_height=18, border_width=2, corner_radius=5, border_color=COLOR_INPUT_BORDER
        )
        self.chk_pause_D.grid(row=0, column=1, sticky="e", padx=(0, 6))

        self.switch_D = ctk.CTkSwitch(
            hdr_team_skill, text="", variable=self.var_switch_D, command=self._on_switch_D_toggled,
            width=36, height=18, switch_width=34, switch_height=18, corner_radius=9,
            border_width=1, border_color=COLOR_INPUT_BORDER, fg_color=COLOR_INPUT_BG, progress_color=COLOR_ORANGE,
            button_color="#FFFFFF", button_hover_color="#E2E8F0"
        )
        self.switch_D.grid(row=0, column=2, sticky="e")

        # Thân Card Tổ Đội / Kỹ Năng (Lưới cân đối 2 hàng x 2 cột)
        body_team_skill = ctk.CTkFrame(self.card_team_skill, fg_color="transparent")
        body_team_skill.grid(row=1, column=0, padx=10, pady=(2, 8), sticky="nsew")
        body_team_skill.grid_columnconfigure(0, weight=1)
        body_team_skill.grid_columnconfigure(1, weight=1)
        body_team_skill.grid_rowconfigure((0, 1), weight=1)

        # Hàng 1: [ ] Tổ Đội (Trái) + Menu Vị trí xuất chiến (Phải)
        self.chk_D2 = ctk.CTkCheckBox(
            body_team_skill, text="Tổ Đội", variable=self.var_D2, command=self._on_D2_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_D2.grid(row=0, column=0, sticky="w", padx=(2, 0), pady=4)

        self.combo_D_team_char = ctk.CTkOptionMenu(
            body_team_skill,
            values=char_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=150,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_D_team_char.set(char_options[0] if char_options else "Xuất Chiến")
        self.combo_D_team_char.grid(row=0, column=1, sticky="e", padx=(0, 2), pady=4)

        # Hàng 2: [ ] Nhận Đội (Trái) + Menu Kỹ Năng (Phải - đồng bộ width 150 cân đối)
        self.chk_D_nhan_doi = ctk.CTkCheckBox(
            body_team_skill, text="Nhận Đội", variable=self.var_D_nhan_doi, command=self._on_D_nhan_doi_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN,
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5
        )
        self.chk_D_nhan_doi.grid(row=1, column=0, sticky="w", padx=(2, 0), pady=4)

        self.combo_D_skill = ctk.CTkOptionMenu(
            body_team_skill,
            values=["Buff HP / SP", "Linh Kính", "Kết Giới", "Đánh Tay"],
            variable=self.var_D_skill,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=150,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self.save_config()
        )
        self.combo_D_skill.set("Buff HP / SP")
        self.combo_D_skill.grid(row=1, column=1, sticky="e", padx=(0, 2), pady=4)

        # =========================================================================
        # 2. HÀNG 2: CARD 40 NPC (CỘT 0) & CARD NHỊ KIỀU (CỘT 1) - THU GỌN TRỤC Y (THEO CARD BOSS TG)
        # =========================================================================
        # --- HÀNG 2, CỘT 0: CARD 40 NPC ---
        self.card_40npc = ctk.CTkFrame(self.container_daily, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_40npc.grid(row=1, column=0, sticky="nsew", padx=(4, 2), pady=(2, 2))
        self.card_40npc.grid_columnconfigure(0, weight=1)
        self.card_40npc.grid_rowconfigure(0, weight=0)
        self.card_40npc.grid_rowconfigure(1, weight=1)

        hdr_40npc = ctk.CTkFrame(self.card_40npc, fg_color="transparent")
        hdr_40npc.grid(row=0, column=0, padx=8, pady=(4, 2), sticky="ew")
        lbl_40npc = ctk.CTkLabel(hdr_40npc, text="40 NPC", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_40npc.pack(side="left")

        self.entry_D_time = ctk.CTkEntry(
            hdr_40npc,
            textvariable=self.var_D_time,
            width=80,
            height=25,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            fg_color=COLOR_INPUT_BG,
            border_width=1,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=6,
            justify="center",
            placeholder_text="20:00"
        )
        self.entry_D_time.pack(side="right")
        self.entry_D_time.bind("<FocusOut>", lambda e: self._on_D_time_changed())
        self.entry_D_time.bind("<Return>", lambda e: self._on_D_time_changed())

        body_40npc = ctk.CTkFrame(self.card_40npc, fg_color="transparent")
        body_40npc.grid(row=1, column=0, padx=8, pady=(2, 4), sticky="nsew")
        body_40npc.grid_columnconfigure(0, weight=1)
        body_40npc.grid_columnconfigure(1, weight=1)
        body_40npc.grid_rowconfigure(0, weight=1)

        # Hàng 1 (40 NPC): Ô tích 40 NPC (Trái) - Menu Mốc (Phải)
        self.chk_D3 = ctk.CTkCheckBox(
            body_40npc, text="40 NPC", variable=self.var_D3, command=self._on_D3_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5,
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN
        )
        self.chk_D3.grid(row=0, column=0, sticky="w", padx=(2, 0), pady=1)

        self.combo_D_chien_dau = ctk.CTkOptionMenu(
            body_40npc,
            values=["Auto"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=105,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_D_chien_dau.set("Auto")
        self.combo_D_chien_dau.grid(row=0, column=1, sticky="e", padx=(0, 2), pady=1)

        # --- HÀNG 2, CỘT 1: CARD NHỊ KIỀU ---
        self.card_nhikieu = ctk.CTkFrame(self.container_daily, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_nhikieu.grid(row=1, column=1, sticky="nsew", padx=(2, 4), pady=(2, 2))
        self.card_nhikieu.grid_columnconfigure(0, weight=1)
        self.card_nhikieu.grid_rowconfigure(0, weight=0)
        self.card_nhikieu.grid_rowconfigure(1, weight=1)

        hdr_nhikieu = ctk.CTkFrame(self.card_nhikieu, fg_color="transparent")
        hdr_nhikieu.grid(row=0, column=0, padx=8, pady=(4, 2), sticky="ew")
        lbl_nhikieu = ctk.CTkLabel(hdr_nhikieu, text="NHỊ KIỀU", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT, height=25)
        lbl_nhikieu.pack(side="left")

        body_nhikieu = ctk.CTkFrame(self.card_nhikieu, fg_color="transparent")
        body_nhikieu.grid(row=1, column=0, padx=8, pady=(2, 4), sticky="nsew")
        body_nhikieu.grid_columnconfigure(0, weight=1)
        body_nhikieu.grid_columnconfigure(1, weight=1)
        body_nhikieu.grid_rowconfigure(0, weight=1)

        # Hàng 1 (Nhị Kiều): Ô tích Nhị Kiều (Trái) - Menu Mốc (Phải)
        self.chk_D4 = ctk.CTkCheckBox(
            body_nhikieu, text="Nhị Kiều", variable=self.var_D4, command=self._on_D4_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            checkbox_width=18, checkbox_height=18, border_width=2, border_color=COLOR_INPUT_BORDER, corner_radius=5,
            fg_color=COLOR_ORANGE, hover_color=COLOR_ORANGE_HOVER, checkmark_color="#FFFFFF", text_color=COLOR_TEXT_MAIN
        )
        self.chk_D4.grid(row=0, column=0, sticky="w", padx=(2, 0), pady=1)

        tang_options = ["Auto"]
        self.combo_D_tang = ctk.CTkOptionMenu(
            body_nhikieu,
            values=tang_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=28,
            width=105,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_D_tang.set("Auto")
        self.combo_D_tang.grid(row=0, column=1, sticky="e", padx=(0, 2), pady=1)

        # =========================================================================
        # 3. HÀNG 3: CARD HOẠT ĐỘNG 1 (CỘT 0) & CARD HOẠT ĐỘNG 2 (CỘT 1) - TĂNG TRỤC Y BÙ LẠI
        # =========================================================================
        # --- HÀNG 3, CỘT 0: CARD HOẠT ĐỘNG 1 (DƯỚI 40 NPC) ---
        self.card_extra1 = ctk.CTkFrame(self.container_daily, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_extra1.grid(row=2, column=0, sticky="nsew", padx=(4, 2), pady=(3, 3))
        self.card_extra1.grid_columnconfigure(0, weight=1)
        self.card_extra1.grid_rowconfigure(0, weight=0)
        self.card_extra1.grid_rowconfigure(1, weight=1)

        hdr_extra1 = ctk.CTkFrame(self.card_extra1, fg_color="transparent")
        hdr_extra1.grid(row=0, column=0, padx=8, pady=(6, 2), sticky="ew")
        lbl_extra1 = ctk.CTkLabel(hdr_extra1, text="HOẠT ĐỘNG 1", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_extra1.pack(side="left")

        body_extra1 = ctk.CTkFrame(self.card_extra1, fg_color="transparent")
        body_extra1.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")
        body_extra1.grid_columnconfigure(0, weight=1)
        body_extra1.grid_rowconfigure(0, weight=1)
        lbl_extra1_ph = ctk.CTkLabel(body_extra1, text="(Chờ cấu hình)", font=ctk.CTkFont(family=FONT_FAMILY, size=13, slant="italic"), text_color="#64748b")
        lbl_extra1_ph.grid(row=0, column=0, sticky="nsew")

        # --- HÀNG 3, CỘT 1: CARD HOẠT ĐỘNG 2 (DƯỚI NHỊ KIỀU) ---
        self.card_extra2 = ctk.CTkFrame(self.container_daily, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_extra2.grid(row=2, column=1, sticky="nsew", padx=(2, 4), pady=(3, 3))
        self.card_extra2.grid_columnconfigure(0, weight=1)
        self.card_extra2.grid_rowconfigure(0, weight=0)
        self.card_extra2.grid_rowconfigure(1, weight=1)

        hdr_extra2 = ctk.CTkFrame(self.card_extra2, fg_color="transparent")
        hdr_extra2.grid(row=0, column=0, padx=8, pady=(6, 2), sticky="ew")
        lbl_extra2 = ctk.CTkLabel(hdr_extra2, text="HOẠT ĐỘNG 2", font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"), text_color=COLOR_ACCENT)
        lbl_extra2.pack(side="left")

        body_extra2 = ctk.CTkFrame(self.card_extra2, fg_color="transparent")
        body_extra2.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")
        body_extra2.grid_columnconfigure(0, weight=1)
        body_extra2.grid_rowconfigure(0, weight=1)
        lbl_extra2_ph = ctk.CTkLabel(body_extra2, text="(Chờ cấu hình)", font=ctk.CTkFont(family=FONT_FAMILY, size=13, slant="italic"), text_color="#64748b")
        lbl_extra2_ph.grid(row=0, column=0, sticky="nsew")

        # =========================================================================
        # 🔓 GIAO DIỆN CARD F (CẤU HÌNH CHIẾN ĐẤU)
        # =========================================================================
        self.card_combat = ctk.CTkFrame(tab_combat, fg_color=COLOR_CARD_INNER, corner_radius=10)
        self.card_combat.pack(fill="both", expand=True, padx=8, pady=8)
        self.card_combat.grid_columnconfigure(0, weight=1)
        self.card_combat.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=0)

        hdr_combat = ctk.CTkFrame(self.card_combat, fg_color="transparent")
        hdr_combat.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        hdr_combat.grid_columnconfigure(0, weight=1)

        lbl_combat = ctk.CTkLabel(
            hdr_combat,
            text="CẤU HÌNH CHIẾN ĐẤU",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_ACCENT
        )
        lbl_combat.grid(row=0, column=0, sticky="w")

        # Hàng 1: [ ] Buff | [ Menu Dropdown: Buff HP / Buff SP / Buff HP / SP ]
        row_combat1 = ctk.CTkFrame(self.card_combat, fg_color="transparent")
        row_combat1.grid(row=1, column=0, padx=8, pady=6, sticky="ew")

        col_left1 = ctk.CTkFrame(row_combat1, fg_color="transparent", width=180, height=32)
        col_left1.pack(side="left")
        col_left1.pack_propagate(False)

        self.chk_buff = ctk.CTkCheckBox(
            col_left1,
            text="",
            variable=self.var_buff,
            command=self._on_buff_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE,
            hover_color=COLOR_ORANGE_HOVER,
            checkmark_color="#FFFFFF",
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=5,
            width=18
        )
        self.chk_buff.pack(side="left", padx=(2, 4))

        self.btn_lbl_buff = ctk.CTkButton(
            col_left1,
            text="HP / SP",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
            height=30,
            width=145,
            fg_color=COLOR_BTN_NAVY,
            hover_color=COLOR_BTN_NAVY_HOVER,
            corner_radius=6,
            anchor="w",
            command=lambda: [self.var_buff.set(not self.var_buff.get()), self._on_buff_toggled()]
        )
        self.btn_lbl_buff.pack(side="left", padx=(0, 0))

        lbl_sub_buff = ctk.CTkLabel(
            row_combat1,
            text="( Tắt Auto )",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_sub_buff.pack(side="left", padx=(8, 0))

        buff_options = ["Buff HP", "Buff SP", "Buff HP / SP"]
        self.combo_buff = ctk.CTkOptionMenu(
            row_combat1,
            values=buff_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=30,
            width=145,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_buff.set(buff_options[0])
        self.combo_buff.pack(side="right", padx=(0, 4))

        # Hàng 2: [ ] [ Kỹ Năng ▼ ] ( Tắt Auto ) | [ Mục Tiêu ▼ ]
        row_combat2 = ctk.CTkFrame(self.card_combat, fg_color="transparent")
        row_combat2.grid(row=2, column=0, padx=8, pady=(0, 6), sticky="ew")

        col_left2 = ctk.CTkFrame(row_combat2, fg_color="transparent", width=180, height=32)
        col_left2.pack(side="left")
        col_left2.pack_propagate(False)

        self.chk_phong_thu = ctk.CTkCheckBox(
            col_left2,
            text="",
            variable=self.var_phong_thu,
            command=self._on_phong_thu_toggled,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="normal"),
            fg_color=COLOR_ORANGE,
            hover_color=COLOR_ORANGE_HOVER,
            checkmark_color="#FFFFFF",
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            border_color=COLOR_INPUT_BORDER,
            corner_radius=5,
            width=18
        )
        self.chk_phong_thu.pack(side="left", padx=(2, 4))

        defense_skills = ["Kết Giới", "Linh Kính", "Băng Tường"]
        self.combo_phong_thu_skill = ctk.CTkOptionMenu(
            col_left2,
            values=defense_skills,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=30,
            width=145,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_phong_thu_skill.set(defense_skills[0])
        self.combo_phong_thu_skill.pack(side="left", padx=(0, 0))

        lbl_sub_defense = ctk.CTkLabel(
            row_combat2,
            text="( Tắt Auto )",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal"),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_sub_defense.pack(side="left", padx=(8, 0))

        target_options = ["Chart", "Chart / Pet", "Team"]
        self.combo_phong_thu_target = ctk.CTkOptionMenu(
            row_combat2,
            values=target_options,
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLOR_TEXT_MAIN,
            dropdown_text_color=COLOR_TEXT_MAIN,
            height=30,
            width=145,
            dynamic_resizing=False,
            fg_color=COLOR_COMBO_BG,
            button_color=COLOR_COMBO_BTN,
            button_hover_color=COLOR_COMBO_BTN_HOVER,
            dropdown_fg_color=COLOR_COMBO_POPUP_BG,
            dropdown_hover_color=COLOR_COMBO_POPUP_HOVER,
            corner_radius=6,
            command=lambda choice: self._on_checkbox_toggled()
        )
        self.combo_phong_thu_target.set(target_options[0])
        self.combo_phong_thu_target.pack(side="right", padx=(0, 4))

        self._update_phong_thu_state()

    def _on_D_nhan_doi_toggled(self):
        """Khi tích ô Nhận Đội -> Loại trừ Tổ Đội (D2) và các card bên dưới (40 NPC, Nhị Kiều)"""
        if hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get():
            if hasattr(self, 'var_D2'):
                self.var_D2.set(False)
            if hasattr(self, 'var_D3'):
                self.var_D3.set(False)
            if hasattr(self, 'var_D4'):
                self.var_D4.set(False)
        self._update_event_cards_state()
        self._on_checkbox_toggled()

    def _on_D2_toggled(self):
        """Khi tích ô Tổ Đội -> Loại trừ ô Nhận Đội"""
        if hasattr(self, 'var_D2') and self.var_D2.get():
            if hasattr(self, 'var_D_nhan_doi'):
                self.var_D_nhan_doi.set(False)
        self._on_checkbox_toggled()

    def _on_D3_toggled(self):
        """Khi tích sự kiện 40 NPC -> Bỏ chọn sự kiện Nhị Kiều và Nhận Đội (loại trừ nhau)."""
        if self.var_D3.get():
            self.var_D4.set(False)
            if hasattr(self, 'var_D_nhan_doi'):
                self.var_D_nhan_doi.set(False)
        self._update_event_cards_state()
        self._on_checkbox_toggled()

    def _on_D4_toggled(self):
        """Khi tích sự kiện Nhị Kiều -> Bỏ chọn sự kiện 40 NPC và ô Nhận Đội (loại trừ nhau)"""
        if self.var_D4.get():
            self.var_D3.set(False)
            if hasattr(self, 'var_D_nhan_doi'):
                self.var_D_nhan_doi.set(False)
        self._update_event_cards_state()
        self._on_checkbox_toggled()

    def _update_event_cards_state(self):
        """
        Cập nhật trạng thái quản lý giữa Card 40 NPC và Card Nhị Kiều:
        - Ô menu Auto và ô ghi giờ: thuộc quản lý trực tiếp của ô sự kiện 40 NPC (var_D3).
        - Ô menu Tầng: thuộc quản lý trực tiếp của ô sự kiện Nhị Kiều (var_D4).
        """
        if not hasattr(self, 'chk_D3') or not hasattr(self, 'chk_D4'):
            return

        is_40npc = self.var_D3.get()
        is_nhi_kieu = self.var_D4.get()

        if is_40npc:
            # 40 NPC được chọn: Mở menu Auto và ô ghi giờ, khóa mờ menu Tầng Nhị Kiều
            self.chk_D3.configure(state="normal", text_color="#FFFFFF")
            self.chk_D4.configure(state="normal", text_color="#FFFFFF")
            if hasattr(self, 'entry_D_time'):
                self.entry_D_time.configure(state="normal", text_color="#FFFFFF", fg_color=COLOR_INPUT_BG)
            if hasattr(self, 'combo_D_chien_dau'):
                self.combo_D_chien_dau.configure(
                    state="normal", text_color="#FFFFFF", fg_color=COLOR_COMBO_BG,
                    button_color=COLOR_COMBO_BTN, button_hover_color=COLOR_COMBO_BTN_HOVER
                )
            if hasattr(self, 'combo_D_tang'):
                self.combo_D_tang.configure(
                    state="disabled", text_color="#4B5563", fg_color="#18181B",
                    button_color="#18181B", button_hover_color="#18181B"
                )
        elif is_nhi_kieu:
            # Nhị Kiều được chọn: Mở menu Tầng, khóa mờ menu 40 NPC và ô ghi giờ
            self.chk_D4.configure(state="normal", text_color="#FFFFFF")
            self.chk_D3.configure(state="normal", text_color="#FFFFFF")
            if hasattr(self, 'entry_D_time'):
                self.entry_D_time.configure(state="disabled", text_color="#4B5563", fg_color="#18181B")
            if hasattr(self, 'combo_D_tang'):
                self.combo_D_tang.configure(
                    state="normal", text_color="#FFFFFF", fg_color=COLOR_COMBO_BG,
                    button_color=COLOR_COMBO_BTN, button_hover_color=COLOR_COMBO_BTN_HOVER
                )
            if hasattr(self, 'combo_D_chien_dau'):
                self.combo_D_chien_dau.configure(
                    state="disabled", text_color="#4B5563", fg_color="#18181B",
                    button_color="#18181B", button_hover_color="#18181B"
                )
        else:
            # Cả 40 NPC và Nhị Kiều chưa được chọn: Khóa cả 2 menu dropdown và ô ghi giờ
            self.chk_D3.configure(state="normal", text_color="#FFFFFF")
            self.chk_D4.configure(state="normal", text_color="#FFFFFF")
            if hasattr(self, 'entry_D_time'):
                self.entry_D_time.configure(state="disabled", text_color="#4B5563", fg_color="#18181B")
            if hasattr(self, 'combo_D_chien_dau'):
                self.combo_D_chien_dau.configure(
                    state="disabled", text_color="#4B5563", fg_color="#18181B",
                    button_color="#18181B", button_hover_color="#18181B"
                )
            if hasattr(self, 'combo_D_tang'):
                self.combo_D_tang.configure(
                    state="disabled", text_color="#4B5563", fg_color="#18181B",
                    button_color="#18181B", button_hover_color="#18181B"
                )

    # --- HÀM CẬP NHẬT TRẠNG THÁI & XUẤT LOG ---
    _LOG_LEVELS = {
        "info": ("ℹ️ ", "Thông báo"),
        "warning": ("⚠️ ", "Cảnh báo"),
        "error": ("❌ ", "Lỗi"),
    }

    def _append_ui_log(self, log_line: str):
        """Chèn log vào widget txt_log và tự động cắt bớt log cũ khi vượt quá 500 dòng để chống tràn bộ nhớ và lag giật"""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._append_ui_log, log_line)
            return
        if hasattr(self, 'txt_log'):
            try:
                self.txt_log.configure(state="normal")
                self.txt_log.insert("end", f"{log_line}\n")
                # Tinh gọn: Chỉ kiểm tra tỉa bớt log mỗi 30 dòng để tránh gọi index và parse chuỗi liên tục
                self._log_trim_counter = getattr(self, '_log_trim_counter', 0) + 1
                if self._log_trim_counter >= 30:
                    self._log_trim_counter = 0
                    line_idx = self.txt_log.index("end-1c")
                    total_lines = int(line_idx.split('.')[0])
                    if total_lines > 500:
                        self.txt_log.delete("1.0", f"{total_lines - 450}.0")
                self.txt_log.see("end")
                self.txt_log.configure(state="disabled")
            except Exception:
                pass

    def _log(self, level: str, message: str):
        """Hàm log dùng chung: cập nhật thanh trạng thái & ô ghi Log trên GUI & Web UI (luôn chạy trên main thread)"""
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._log, level, message)
            return

        # Chống spam: Lọc bỏ thông báo info giống hệt nhau liên tiếp trong vòng 1.2s
        if level == "info":
            now_ts = time.time()
            if getattr(self, '_last_info_msg', None) == message and (now_ts - getattr(self, '_last_info_time', 0)) < 1.2:
                return
            self._last_info_msg = message
            self._last_info_time = now_ts

        icon, status_label = self._LOG_LEVELS[level]
        prefix = "" if (message and ord(message[0]) > 127) else icon
        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {prefix}{message}"
        if not hasattr(self, 'recent_logs'):
            self.recent_logs = []
        self.recent_logs.append(log_line)
        if len(self.recent_logs) > 300:
            del self.recent_logs[:len(self.recent_logs) - 300]

        if hasattr(self, 'lbl_status'):
            self.lbl_status.configure(text=f"{status_label}: {message}")
        self._append_ui_log(log_line)

    def log_info(self, message: str):
        """Ghi log thông tin lên GUI & Web UI"""
        self._log("info", message)

    def log_warning(self, message: str):
        """Ghi log cảnh báo lên GUI & Web UI"""
        self._log("warning", message)

    def log_error(self, message: str):
        """Ghi log lỗi lên GUI & Web UI"""
        self._log("error", message)

    def _get_dnconsole_path(self) -> str | None:
        """Lấy đường dẫn thực thi chuẩn ldconsole.exe / dnconsole.exe của LDPlayer"""
        if not hasattr(self, 'ld_path') or not self.ld_path:
            return None
        for name in ["ldconsole.exe", "dnconsole.exe"]:
            p = os.path.join(self.ld_path, name)
            if os.path.exists(p):
                return p
        return None

    def _exec_cmd(self, cmd_list, text=False):
        """Thực thi lệnh ADB/LDConsole an toàn và chính xác 100% trên mọi Tab LDPlayer"""
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "creationflags": creation_flags
        }
        if text:
            kwargs["text"] = True
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "ignore"

        # 1. Thử chạy trực tiếp lệnh dnconsole/ldconsole (Cơ chế chuẩn native 100% của LDPlayer)
        try:
            res = subprocess.run(cmd_list, timeout=15, **kwargs)
            if res is not None and res.returncode == 0:
                return res
            elif res is not None:
                # Nếu lệnh dnconsole chính chủ chạy xong (kể cả returncode != 0), vẫn ưu tiên kết quả chính chủ
                pass
        except OSError as e:
            if getattr(e, 'winerror', None) == 740 or "740" in str(e):
                try:
                    cmd_str = " ".join([f'"{arg}"' if " " in str(arg) else str(arg) for arg in cmd_list])
                    res_cmd = subprocess.run(f'cmd /c {cmd_str}', shell=True, timeout=15, **kwargs)
                    if res_cmd is not None:
                        return res_cmd
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Nếu là lệnh ADB gọi qua dnconsole và gặp sự cố, mới chuyển hướng dự phòng qua adb.exe
        if len(cmd_list) >= 6 and cmd_list[1] == "adb" and "--index" in cmd_list and "--command" in cmd_list:
            try:
                idx_pos = cmd_list.index("--index") + 1
                cmd_pos = cmd_list.index("--command") + 1
                tab_idx = int(cmd_list[idx_pos])
                raw_subcmd = str(cmd_list[cmd_pos]).strip()

                adb_path = os.path.join(self.ld_path, "adb.exe")

                if os.path.exists(adb_path):
                    port_5555 = 5555 + (tab_idx * 2)
                    port_5554 = 5554 + (tab_idx * 2)
                    
                    # Kết nối tự động lại cổng ADB nếu bị rớt
                    try:
                        subprocess.run([adb_path, "connect", f"127.0.0.1:{port_5555}"], timeout=3, **kwargs)
                    except Exception:
                        pass

                    candidate_devices = [
                        f"127.0.0.1:{port_5555}",
                        f"emulator-{port_5554}"
                    ]

                    for device_id in candidate_devices:
                        if raw_subcmd.lower().startswith("pull "):
                            parts = raw_subcmd.split(maxsplit=2)
                            if len(parts) >= 3:
                                remote_p = parts[1].strip('"')
                                local_p = parts[2].strip('"')
                                direct_adb_cmd = [adb_path, "-s", device_id, "pull", remote_p, local_p]
                            else:
                                direct_adb_cmd = [adb_path, "-s", device_id] + raw_subcmd.split()
                        else:
                            subcmd_parts = raw_subcmd.split()
                            if subcmd_parts and subcmd_parts[0].lower() == "shell":
                                subcmd_parts = subcmd_parts[1:]
                            direct_adb_cmd = [adb_path, "-s", device_id, "shell"] + subcmd_parts

                        res = subprocess.run(direct_adb_cmd, timeout=15, **kwargs)
                        if res.returncode == 0:
                            return res
            except Exception:
                pass

        # Fallback chạy lại lệnh gốc
        try:
            return subprocess.run(cmd_list, timeout=15, **kwargs)
        except Exception:
            return None

    def _is_ld_loaded_100(self, dnconsole_path: str, tab_index: str) -> bool:
        """Kiểm tra nhanh trạng thái nạp 100% của giả lập LDPlayer qua list2 (không bị đứng/treo ADB)"""
        try:
            res = self._exec_cmd([dnconsole_path, "list2"], text=True)
            if res and res.stdout:
                for line in res.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 5 and parts[0] == str(tab_index):
                        # Cột 4 (phần tử thứ 5) chính là android_started (1 = Đã nạp xong 100%, 0 = Đang nạp/Tắt)
                        if parts[4] == "1":
                            return True
        except Exception:
            pass
        return False

    # --- QUÉT VÀ CẬP NHẬT DỮ LIỆU LDPLAYER (ASYNC) ---
    def refresh_ld_tabs_async(self):
        """Kích hoạt quét LDPlayer trong Thread riêng biệt tránh đơ UI"""
        if self.is_scanning:
            return

        self.is_scanning = True
        threading.Thread(target=self._worker_scan_ld, daemon=True).start()

    def _worker_scan_ld(self):
        """Worker thread chạy quét danh sách giả lập LDPlayer qua dnconsole list2"""
        try:
            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.after(0, self._update_ui_ld_scan_result, [], f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                return

            result = self._exec_cmd([dnconsole_path, "list2"], text=True)
            if not result or not result.stdout:
                self.after(0, self._update_ui_ld_scan_result, [], "Không nhận được phản hồi từ dnconsole list2")
                return

            lines = result.stdout.strip().split('\n')
            new_tabs = []
            dict_temp = {}

            for line in lines:
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 2:
                        idx = parts[0].strip()
                        name = parts[1].strip()
                        new_tabs.append(name)
                        dict_temp[name] = idx

            self.after(0, self._update_ui_ld_scan_result, new_tabs, None, dict_temp)

        except Exception as e:
            try:
                self.after(0, self._update_ui_ld_scan_result, [], str(e))
            except Exception:
                # Cửa sổ đã hủy / after thất bại: vẫn phải nhả cờ để lần quét sau không bị kẹt
                self.is_scanning = False

    def _update_ui_ld_scan_result(self, tab_names: list, error_msg: str = None, dict_map: dict = None):
        """Cập nhật giao diện sau khi kết thúc quét"""
        self.is_scanning = False

        if error_msg:
            self.combo_ld_tabs.configure(values=["Lỗi quét dữ liệu"])
            self.combo_ld_tabs.set("Lỗi quét dữ liệu")
            self.log_error(f"Quét tab thất bại: {error_msg}")
            return

        if dict_map is not None:
            self.dict_name_to_index = dict_map

        if tab_names:
            current_selection = self.combo_ld_tabs.get()
            self.combo_ld_tabs.configure(values=tab_names)

            saved_tab = getattr(self, 'saved_selected_tab', None)
            if current_selection in tab_names and current_selection not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]:
                target_sel = current_selection
            elif saved_tab and saved_tab in tab_names:
                target_sel = saved_tab
            else:
                target_sel = tab_names[0]

            self.combo_ld_tabs.set(target_sel)
            self._on_ld_tab_selected(target_sel)

            count = len(tab_names)
            self.log_info(f"Đã phát hiện {count} tab LDPlayer: {', '.join(tab_names)}")
        else:
            self.combo_ld_tabs.configure(values=["Không tìm thấy tab LD nào"])
            self.combo_ld_tabs.set("Không tìm thấy tab LD nào")
            self.log_info("Không tìm thấy tab LDPlayer nào.")

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: BỘ NÚT TOP (GAME, EXIT, STOP)
    # =========================================================================
    def xu_ly_exit_game(self):
        """Thoát ứng dụng game TS Origin về màn hình chính giả lập LDPlayer"""
        if getattr(self, '_is_exiting_game', False):
            self.log_warning("Tiến trình đóng game đang thực thi...")
            return

        tab, idx = self._get_selected_ld_info()
        if idx is None:
            self.log_error("Vui lòng chọn một Tab LDPlayer trước khi bấm Exit!")
            return

        self._is_exiting_game = True
        self.btn_exit_game.configure(state="disabled", text="Đang thoát...")
        self.log_info(f"🚪 [Exit] Đang đóng game và về màn hình chính giả lập LDPlayer (Tab {tab})...")
        threading.Thread(target=self._worker_exit_game, args=(tab, idx), daemon=True).start()

    def _worker_exit_game(self, tab_name: str, tab_index: str):
        try:
            dnconsole_path = self._get_dnconsole_path()

            target_pkg = "com.vtcmobile.gz06"
            if dnconsole_path:
                # 1. Quét đóng ứng dụng game qua killapp
                self._exec_cmd([dnconsole_path, "killapp", "--index", str(tab_index), "--packagename", target_pkg])
                # 2. Gộp force-stop và phím Home (keyevent 3) vào 1 lệnh ADB duy nhất
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell am force-stop {target_pkg} && input keyevent 3"])

            self.after(0, self.log_info, f"✅ [Exit] Đã thoát game trên Tab {tab_name} thành công! (Về màn hình chính giả lập)")
        except Exception as e:
            self.after(0, self.log_error, f"❌ Lỗi khi đóng game trên Tab {tab_name}: {e}")
        finally:
            self._is_exiting_game = False
            self.after(0, lambda: self.btn_exit_game.configure(state="normal", text="Exit"))

    # ---- HÀM XỬ LÝ SỰ KIỆN TS ORIGIN (TỰ ĐỘNG BẤM ICON MỞ GAME) ----
    def xu_ly_ts_origin(self):
        if getattr(self, '_is_launching_game', False):
            self.log_warning("Tiến trình mở game đang chạy, vui lòng chờ trong giây lát...")
            return

        self._reset_stop_flags()
        tab, idx = self._get_selected_ld_info()
        if idx is None:
            self.log_error("Vui lòng chọn một Tab LDPlayer trước khi bấm mở game!")
            return

        self._is_launching_game = True
        self.log_info(f"🚀 [Mở Game] Khởi động Giả lập LDPlayer (Tab {tab}) ➔ Chờ Load 100% ➔ Mở App Game...")
        self.btn_enter_game.configure(state="disabled", text="Đang mở Game...")

        # Chạy lệnh mở app trong Thread riêng để không làm treo giao diện
        threading.Thread(target=self._worker_launch_ts_origin, args=(tab, idx), daemon=True).start()

    def _worker_launch_ts_origin(self, tab_name: str, tab_index: str):
        """Worker thread khởi chạy LDPlayer và khởi chạy game TS Origin"""
        try:
            dnconsole_path = self._get_dnconsole_path()
            if not dnconsole_path:
                self.after(0, self._finish_launch_ts_origin, False, f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                return

            # Bước 1: Khởi chạy Giả lập LDPlayer nếu chưa mở
            if not self._is_ld_loaded_100(dnconsole_path, tab_index):
                self.after(0, self.log_info, f"🖥️ [Bước 1/3] Khởi động Giả lập LDPlayer Tab: {tab_name}...")
                self._exec_cmd([dnconsole_path, "launch", "--index", str(tab_index)])
            else:
                self.after(0, self.log_info, f"🖥️ Tab LDPlayer {tab_name} (Index: {tab_index}) đã mở sẵn...")

            # Bước 2: Theo dõi tiến trình chờ nạp 100% qua console list2
            self.after(0, self.log_info, f"⏳ [Bước 2/3] Đang chờ giả lập LDPlayer Tab: {tab_name} (Index: {tab_index}) load 100%...")
            boot_start = time.time()
            emulator_ready = False

            for check_idx in range(90):
                if self.stop_requested:
                    self.after(0, self._finish_launch_ts_origin, False, "🛑 Tiến trình mở game đã dừng theo yêu cầu!")
                    return

                if self._is_ld_loaded_100(dnconsole_path, tab_index):
                    emulator_ready = True
                    boot_time = round(time.time() - boot_start, 1)
                    self.after(0, self.log_info, f"✅ Giả lập LDPlayer đã load 100% thành công sau {boot_time}s! Đang tiến hành mở Game...")
                    break

                elapsed = int(time.time() - boot_start)
                if elapsed > 0 and elapsed % 5 == 0:
                    self.after(0, self.log_info, f"⏳ [Bước 2/3] Giả lập LDPlayer đang nạp màn hình chính... ({elapsed}s)")
                
                if self._sleep_with_stop_check(1.0):
                    self.after(0, self._finish_launch_ts_origin, False, "🛑 Tiến trình mở game đã dừng theo yêu cầu!")
                    return

            if self.stop_requested:
                self.after(0, self._finish_launch_ts_origin, False, "🛑 Tiến trình mở game đã dừng theo yêu cầu!")
                return

            if not emulator_ready:
                self.after(0, self.log_info, "ℹ️ Tiếp tục tiến trình mở ứng dụng Game...")
            else:
                self.after(0, self.log_info, "⏳ Đang hoãn 2 giây cho màn hình giả lập ổn định hoàn toàn...")
                if self._sleep_with_stop_check(2.0):
                    self.after(0, self._finish_launch_ts_origin, False, "🛑 Tiến trình mở game đã dừng theo yêu cầu!")
                    return

            # Bước 3: Khởi chạy Game TS Origin
            target_pkg = "com.vtcmobile.gz06"
            self.after(0, self.log_info, f"🎮 [Bước 3/3] Khởi chạy App Game: '{target_pkg}' trên Tab {tab_name}...")

            # Khởi chạy Game qua LDPlayer Native runapp & ADB monkey để luôn mở thành công 100% trên mọi Tab
            self._exec_cmd([dnconsole_path, "runapp", "--index", str(tab_index), "--packagename", target_pkg])
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell monkey -p {target_pkg} -c android.intent.category.LAUNCHER 1"])

            msg = f"✅ [Hoàn thành] Đã mở App Game TS Origin trên Tab: {tab_name} thành công!"
            self.after(0, self._finish_launch_ts_origin, True, msg)

        except Exception as e:
            self.after(0, self._finish_launch_ts_origin, False, f"Lỗi khởi chạy game: {str(e)}")

    def _finish_launch_ts_origin(self, success: bool, message: str):
        """Hoàn tất quá trình mở game, trả lại trạng thái nút bấm Game"""
        self._is_launching_game = False
        self.btn_enter_game.configure(state="normal", text="Game")
        if success:
            self.log_info(message)
        else:
            self.log_error(message)

    # ---- HỆ THỐNG ĐIỀU PHỐI HÀNG ĐỢI TUẦN TỰ CHO CARD BOSS THẾ GIỚI (A) & PHỤ BẢN ĐƠN/ĐỘI (B) ----
    def _trigger_card_AB_workflow(self, card_name: str):
        """Kích hoạt hoặc xếp hàng chờ điều phối chạy tuần tự cho các Card (A, B, C, D)"""
        tab_name, tab_index = self._get_selected_ld_info()
        if tab_index is None:
            self.log_error(f"Vui lòng chọn một Tab LDPlayer trước khi bật công tắc Card {card_name}!")
            if card_name == "Boss Thế Giới":
                self.var_switch_A.set(False)
            elif card_name == "Phụ Bản Đơn / Đội":
                self.var_switch_B.set(False)
            elif card_name == "Dị Giới":
                self.var_switch_C.set(False)
            elif card_name == "40 NPC / Nhị Kiều":
                self.var_switch_D.set(False)
                if hasattr(self, 'var_pause_D'):
                    self.var_pause_D.set(False)
            self.save_config()
            return

        dnconsole_path = self._get_dnconsole_path()
        if not dnconsole_path:
            self.log_error(f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
            if card_name == "Boss Thế Giới":
                self.var_switch_A.set(False)
            elif card_name == "Phụ Bản Đơn / Đội":
                self.var_switch_B.set(False)
            elif card_name == "Dị Giới":
                self.var_switch_C.set(False)
            elif card_name == "40 NPC / Nhị Kiều":
                self.var_switch_D.set(False)
                if hasattr(self, 'var_pause_D'):
                    self.var_pause_D.set(False)
            self.save_config()
            return

        self.save_config()

        with self._card_AB_lock:
            if self._card_AB_coordinator_running:
                self.log_info(f"📋 [HÀNG ĐỢI] Card {card_name} đã BẬT ON và được xếp hàng chờ! Sẽ tự động thực thi ngay sau khi Card đang chạy hoàn thành.")
                return
            self._card_AB_coordinator_running = True
            self._reset_stop_flags()
            self.log_info(f"⚡ [BẬT CÔNG TẮC] Khởi động luồng điều phối hoạt động cho Card {card_name} trên Tab: {tab_name}...")
            threading.Thread(target=self._run_card_AB_coordinator, daemon=True).start()

    def _run_card_AB_coordinator(self):
        """Worker thread điều phối chạy tuần tự các Card (A ➔ B ➔ C ➔ D) theo hàng đợi chống xung đột"""
        try:
            while not self.stop_requested:
                tab_name, tab_index = self._get_selected_ld_info()
                if tab_index is None:
                    self.after(0, self.log_error, "Không tìm thấy thông tin Tab LDPlayer hợp lệ.")
                    break

                dnconsole_path = self._get_dnconsole_path()
                if not dnconsole_path:
                    self.after(0, self.log_error, f"Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                    break

                # 📌 1. Thực thi Card A (Boss Thế Giới) nếu công tắc A đang ON
                if self.var_switch_A.get() and not self.stop_requested:
                    self.after(0, self.log_info, f"📌 [CARD A: BOSS THẾ GIỚI] Bắt đầu thực thi trên Tab: {tab_name} (Index: {tab_index})...")
                    try:
                        self._execute_card_A_boss_tg(dnconsole_path, tab_name, tab_index)
                    except Exception as e:
                        self.after(0, self.log_error, f"❌ Lỗi tiến trình Card Boss Thế Giới: {e}")

                    # Đảm bảo công tắc A đã tắt trên cả thread và UI sau khi xong
                    self.var_switch_A.set(False)
                    self.after(0, lambda: self.var_switch_A.set(False))
                    self.after(0, self.save_config)
                    msg_A = "👑 [CARD A: BOSS THẾ GIỚI]\n✅ Đã hoàn thành toàn bộ lượt đánh Boss Thế Giới"
                    self.send_telegram_alert(msg_A, capture_screenshot=True, tab_index=str(tab_index))

                    # Nếu còn Card khác đang ON ➔ Hoãn 2.5 giây trước khi thực thi tiếp
                    has_next = self.var_switch_B.get() or (hasattr(self, 'var_switch_C') and self.var_switch_C.get()) or (hasattr(self, 'var_switch_D') and self.var_switch_D.get())
                    if has_next and not self.stop_requested:
                        self.after(0, self.log_info, "⏳ Hoãn 2.5 giây trước khi tự động chuyển sang hoạt động tiếp theo...")
                        if self._sleep_with_stop_check(2.5):
                            break

                # 📌 2. Thực thi Card B (Phụ Bản Đơn / Đội) nếu công tắc B đang ON
                if self.var_switch_B.get() and not self.stop_requested:
                    self.after(0, self.log_info, f"📌 [CARD B: PHỤ BẢN ĐƠN / ĐỘI] Bắt đầu thực thi trên Tab: {tab_name} (Index: {tab_index})...")
                    try:
                        self._execute_card_B_phu_ban_doi(dnconsole_path, tab_name, tab_index)
                    except Exception as e:
                        self.after(0, self.log_error, f"❌ Lỗi tiến trình Card Phụ Bản Đơn / Đội: {e}")

                    # Đảm bảo công tắc B đã tắt trên cả thread và UI sau khi xong
                    self.var_switch_B.set(False)
                    self.after(0, lambda: self.var_switch_B.set(False))
                    self.after(0, self.save_config)
                    msg_B = "🎯 [CARD B: PHỤ BẢN ĐƠN / ĐỘI]\n✅ Đã hoàn thành toàn bộ các mốc Phụ Bản"
                    self.send_telegram_alert(msg_B, capture_screenshot=True, tab_index=str(tab_index))

                    has_next = (hasattr(self, 'var_switch_C') and self.var_switch_C.get()) or (hasattr(self, 'var_switch_D') and self.var_switch_D.get()) or self.var_switch_A.get()
                    if has_next and not self.stop_requested:
                        self.after(0, self.log_info, "⏳ Hoãn 2.5 giây trước khi tự động chuyển sang hoạt động tiếp theo...")
                        if self._sleep_with_stop_check(2.5):
                            break

                # 📌 3. Thực thi Card C (Dị Giới Đêm) nếu công tắc C đang ON
                if hasattr(self, 'var_switch_C') and self.var_switch_C.get() and not self.stop_requested:
                    self.after(0, self.log_info, f"📌 [CARD C: DỊ GIỚI ĐÊM] Bắt đầu thực thi trên Tab: {tab_name} (Index: {tab_index})...")
                    try:
                        self._execute_card_C_di_gioi(dnconsole_path, tab_name, tab_index)
                    except Exception as e:
                        self.after(0, self.log_error, f"❌ Lỗi tiến trình Card Dị Giới: {e}")

                    # Đảm bảo công tắc C đã tắt trên cả thread và UI sau khi xong
                    self.var_switch_C.set(False)
                    self.after(0, lambda: self.var_switch_C.set(False))
                    self.after(0, self.save_config)
                    msg_C = "🌌 [CARD C: DỊ GIỚI ĐÊM]\n✅ Đã hoàn thành toàn bộ chu kỳ Dị Giới Đêm"
                    self.send_telegram_alert(msg_C, capture_screenshot=True, tab_index=str(tab_index))

                    has_next = (hasattr(self, 'var_switch_D') and self.var_switch_D.get()) or self.var_switch_A.get() or self.var_switch_B.get()
                    if has_next and not self.stop_requested:
                        self.after(0, self.log_info, "⏳ Hoãn 2.5 giây trước khi tự động chuyển sang hoạt động tiếp theo...")
                        if self._sleep_with_stop_check(2.5):
                            break

                # 📌 4. Thực thi Card D (Sự Kiện) nếu công tắc D đang ON
                if hasattr(self, 'var_switch_D') and self.var_switch_D.get() and not self.stop_requested:
                    self.after(0, self.log_info, f"📌 [SỰ KIỆN - CARD D] Bắt đầu thực thi trên Tab: {tab_name} (Index: {tab_index})...")
                    try:
                        self._execute_card_D_40_npc(dnconsole_path, tab_name, tab_index)
                    except Exception as e:
                        self.after(0, self.log_error, f"❌ Lỗi tiến trình Tab Sự Kiện (Card D): {e}")

                    # Đảm bảo công tắc D đã tắt trên cả thread và UI sau khi xong
                    self.var_switch_D.set(False)
                    if hasattr(self, 'var_pause_D'):
                        self.var_pause_D.set(False)
                        self.after(0, lambda: self.var_pause_D.set(False))
                    self.after(0, lambda: self.var_switch_D.set(False))
                    self.after(0, self.save_config)

                    has_next = self.var_switch_A.get() or self.var_switch_B.get() or (hasattr(self, 'var_switch_C') and self.var_switch_C.get())
                    if has_next and not self.stop_requested:
                        self.after(0, self.log_info, "⏳ Hoãn 2.5 giây trước khi tự động chuyển sang hoạt động tiếp theo...")
                        if self._sleep_with_stop_check(2.5):
                            break

                # Kiểm tra an toàn nguyên tử: Nếu tất cả các card đều đã tắt hoặc không còn card nào ON ➔ Kết thúc điều phối
                with self._card_AB_lock:
                    any_active = (self.var_switch_A.get() or self.var_switch_B.get()
                                  or (hasattr(self, 'var_switch_C') and self.var_switch_C.get())
                                  or (hasattr(self, 'var_switch_D') and self.var_switch_D.get()))
                    if not any_active:
                        self._card_AB_coordinator_running = False
                        break

            if self.stop_requested:
                self.after(0, self.log_info, "🛑 Điều phối hoạt động Card đã dừng theo yêu cầu!")
            else:
                self.after(0, self.log_info, "🎉 [HOÀN TẤT] Đã thực thi xong toàn bộ hoạt động của các Card đã chọn!")

        except Exception as e:
            self.after(0, self.log_error, f"❌ Lỗi hệ thống điều phối Card: {str(e)}")
        finally:
            with self._card_AB_lock:
                self._card_AB_coordinator_running = False

    def xu_ly_nut_chay(self):
        """Hàm tương thích ngược: Tự động kích hoạt luồng điều phối cho các Card đang bật ON"""
        self._reset_stop_flags()
        has_active_switch = (self.var_switch_A.get() or self.var_switch_B.get()
                             or (hasattr(self, 'var_switch_C') and self.var_switch_C.get())
                             or (hasattr(self, 'var_switch_D') and self.var_switch_D.get()))
        if not has_active_switch:
            self.log_info("Vui lòng bật công tắc ON cho ít nhất một Card (A, B, C, D) để thực thi!")
            return
        self._trigger_card_AB_workflow("Tổng Hợp")

    def _sleep_with_stop_check(self, seconds: float, check_active=None) -> bool:
        """Tạm dừng ngủ ngầm: Đánh thức tức thì (< 0.2s) khi bấm Dừng tổng hoặc khi check_active() trả về False."""
        start = time.time()
        step = 0.2  # 200ms phản hồi siêu nhạy, giảm 90% CPU overhead so với polling 0.02s
        while time.time() - start < seconds:
            if self.stop_requested or (hasattr(self, '_stop_event') and self._stop_event.is_set()):
                return True
            if check_active is not None and not check_active():
                return True
            rem = seconds - (time.time() - start)
            sleep_time = min(step, rem)
            if sleep_time <= 0:
                break
            if hasattr(self, '_stop_event') and self._stop_event.wait(timeout=sleep_time):
                return True
            elif not hasattr(self, '_stop_event'):
                time.sleep(sleep_time)
        return False

    def _reset_stop_flags(self):
        """Khôi phục trạng thái sẵn sàng chạy: Xóa triệt để cờ stop_requested và _stop_event"""
        self.stop_requested = False
        if hasattr(self, '_stop_event') and self._stop_event is not None:
            self._stop_event.clear()

    def dung_tat_ca_hoat_dong(self):
        """Nút Dừng tổng: Ngắt lập tức tất cả các card có trong tool & tiến trình mở game TS Origin"""
        self.stop_requested = True
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
        with self._card_AB_lock:
            self._card_AB_coordinator_running = False

        for prefix in ["A", "B", "C", "D"]:
            switch_attr = f"var_switch_{prefix}"
            if hasattr(self, switch_attr):
                getattr(self, switch_attr).set(False)
            pause_attr = f"var_pause_{prefix}"
            if hasattr(self, pause_attr):
                getattr(self, pause_attr).set(False)

        # Nhả ô tích HP / SP & Phòng Thủ (Tab Chiến Đấu) khi bấm nút Dừng
        if hasattr(self, 'var_buff'):
            self.var_buff.set(False)
        if hasattr(self, 'var_phong_thu'):
            self.var_phong_thu.set(False)
        if hasattr(self, 'var_hen_gio'):
            self.var_hen_gio.set(False)
        if hasattr(self, '_event_hen_gio'):
            self._event_hen_gio.clear()
        if hasattr(self, '_stop_hen_gio_sleep'):
            self._stop_hen_gio_sleep.set()
        self._update_hen_gio_ui()

        # Nhả ô tích Card Ngày khi bấm nút Dừng tổng
        if hasattr(self, 'var_nhan_thu'):
            self.var_nhan_thu.set(False)
        if hasattr(self, '_event_nhan_thu'):
            self._event_nhan_thu.clear()
        if hasattr(self, '_stop_mail_sleep'):
            self._stop_mail_sleep.set()

        self._is_card_E_running = False
        self.save_config()

        self._is_launching_game = False
        self._is_exiting_game = False

        if hasattr(self, 'btn_enter_game'):
            self.btn_enter_game.configure(state="normal", text="Game")
        if hasattr(self, 'btn_exit_game'):
            self.btn_exit_game.configure(state="normal", text="Exit")

        self.after(0, self.log_info, "🛑 [DỪNG KHẨN CẤP] Đã bấm nút Dừng ➔ Dừng lập tức tiến trình TS Origin & TOÀN BỘ các Card trong tool!")



    def _should_stop_card_C(self) -> bool:
        """Kiểm tra điều kiện dừng cho Card C Dị Giới Đêm (bấm Dừng tổng hoặc gạt công tắc C về OFF)"""
        return self.stop_requested or not (hasattr(self, 'var_switch_C') and self.var_switch_C.get())

    def _should_stop_card_B(self) -> bool:
        """Kiểm tra điều kiện dừng cho Card B Phụ Bản Đơn/Đội (bấm Dừng tổng hoặc gạt công tắc B về OFF)"""
        return self.stop_requested or not (hasattr(self, 'var_switch_B') and self.var_switch_B.get())

    def _should_stop_card_A(self) -> bool:
        """Kiểm tra điều kiện dừng cho Card A Boss Thế Giới (bấm Dừng tổng hoặc gạt công tắc A về OFF)"""
        return self.stop_requested or not (hasattr(self, 'var_switch_A') and self.var_switch_A.get())

    def _should_stop_card_D(self) -> bool:
        """Kiểm tra điều kiện dừng / tạm dừng cho Tab Sự Kiện (Card D)"""
        if self.stop_requested or not (hasattr(self, 'var_switch_D') and self.var_switch_D.get()):
            return True
        if hasattr(self, 'var_pause_D') and self.var_pause_D.get():
            self.after(0, self.log_info, "⏸️ [Sự Kiện - Card D] Ô Tạm Dừng đang tích ➔ Tạm dừng tiến trình (nhả ô Tạm Dừng để chạy tiếp)...")
            while self.var_pause_D.get() and self.var_switch_D.get() and not self.stop_requested:
                time.sleep(0.5)
            if self.var_switch_D.get() and not self.stop_requested:
                self.after(0, self.log_info, "▶️ [Sự Kiện - Card D] Đã nhả ô Tạm Dừng ➔ Khôi phục chạy tiếp!")
        return self.stop_requested or not (hasattr(self, 'var_switch_D') and self.var_switch_D.get())

    def _sleep_card_D(self, seconds: float) -> bool:
        """Tạm dừng ngủ ngầm cho Card D (Tab Sự Kiện): Đánh thức tức thì (< 0.02s) khi tắt Switch D, tích Tạm Dừng hoặc bấm Dừng tổng"""
        return self._sleep_with_stop_check(seconds, check_active=lambda: not self._should_stop_card_D())


    # =========================================================================
    # 🛠️ CÁC HÀM TRỢ NĂNG TIỆN ÍCH DÙNG CHUNG ĐỘC LẬP CHO CẢ CARD A, B, C
    # =========================================================================
    def _close_login_x_popup(self, dnconsole_path: str, tab_index: str, log_tag: str = "Popup") -> bool:
        """Helper dùng chung: quét login_x.png (75%, ROI 990,50,1165,200) và tap đóng popup nếu thấy ➔ Hoãn 0.4s"""
        x, y = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_x.png", threshold=0.75, region=(990, 50, 1165, 200))
        if x is None or y is None:
            return False
        self.after(0, self.log_info, f"🎯 [{log_tag}] Phát hiện 'login_x.png' tại ({x}, {y})! Tap đóng popup")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {x} {y}"])
        time.sleep(0.4)
        return True

    def _tap_menu_utility_icon(self, dnconsole_path: str, tab_index: str, px_x: int, px_y: int, template_name: str, item_label: str = "Icon", region=(735, 405, 1280, 720), threshold=0.85, stop_check=None) -> bool:
        """Helper tìm và click icon trong menu tiện ích góc dưới phải (tự động mở menu nếu chưa mở, hỗ trợ stop_check độc lập)"""
        is_stop = stop_check if callable(stop_check) else (lambda: self.stop_requested)
        if is_stop(): return False

        x, y = self._find_template_on_screen(dnconsole_path, tab_index, template_name, threshold=threshold, region=region)
        if x is not None and y is not None:
            self.after(0, self.log_info, f"🎯 Phát hiện '{template_name}' ({item_label}) tại ({x}, {y}) ➔ Tap")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {x} {y}"])
            time.sleep(0.4)
            return True
        else:
            self.after(0, self.log_info, f"👉 Chưa thấy '{template_name}' ({item_label}) ➔ Tap nút xanh ({px_x}, {px_y}) mở menu tiện ích")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {px_x} {px_y}"])
            time.sleep(0.4)
            if is_stop(): return False
            x, y = self._find_template_on_screen(dnconsole_path, tab_index, template_name, threshold=threshold, region=region)
            if x is not None and y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện '{template_name}' ({item_label}) tại ({x}, {y})! Tap")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {x} {y}"])
                time.sleep(0.4)
                return True
            else:
                self.after(0, self.log_info, f"⚠️ Chưa quét thấy '{template_name}' ({item_label}) trong bảng menu tiện ích.")
                return False

    def _open_team_panel(self, dnconsole_path: str, tab_index: str, log_tag: str = "Tổ Đội", stop_check=None) -> bool:
        """Helper mở giao diện Đội: Quét card_b/b_doi.png, nếu chưa thấy thì bấm menu (1213, 648) và quét lại"""
        is_stop = stop_check if callable(stop_check) else (lambda: self.stop_requested)
        if is_stop(): return False
        return self._tap_menu_utility_icon(
            dnconsole_path, tab_index, 1213, 648, "card_b/b_doi.png",
            item_label="Đội", region=(735, 405, 1280, 720), threshold=0.85, stop_check=is_stop
        )

    def _close_team_panel(self, dnconsole_path: str, tab_index: str, log_tag: str = "Tổ Đội", stop_check=None):
        """Helper đóng giao diện Đội: Quét login_x.png để đóng bảng và thu gọn menu (1213, 648) nếu icon Đội còn hiển thị"""
        is_stop = stop_check if callable(stop_check) else (lambda: self.stop_requested)
        if is_stop(): return

        # 1. Quét tìm và tap login_x.png (75%, hoãn 0.4s)
        self._close_login_x_popup(dnconsole_path, tab_index, "Tổ Đội")

        if is_stop(): return

        # 2. Mắt thần quét tìm ảnh icon Đội card_b/b_doi.png (85%) ➔ Click nút xanh (1213, 648) thu gọn menu (hoãn 0.4s)
        b_doi2_x, b_doi2_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_doi.png", threshold=0.85, region=(735, 405, 1280, 720))
        if b_doi2_x is not None and b_doi2_y is not None:
            self.after(0, self.log_info, f"🎯 [{log_tag}] Thấy 'card_b/b_doi.png' ➔ Tap nút xanh (1213, 648) thu gọn menu")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1213 648"])
            time.sleep(0.4)

    def _tap_f_tieptheo_until_lost(self, dnconsole_path: str, tab_index: str, tap_interval: float = 0.5, delay_after: float = 0.0, threshold: float = 0.80, region: tuple = (1050, 530, 1165, 680), log_tag: str = "", stop_check=None):
        """Helper chung: Tap liên tục f_tieptheo.png mỗi tap_interval cho tới khi mất hoàn toàn ➔ Hoãn delay_after"""
        is_stop = stop_check if callable(stop_check) else (lambda: self.stop_requested)
        while not is_stop():
            tt_x, tt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_tieptheo.png", threshold=threshold, region=region)
            if tt_x is not None and tt_y is not None:
                if log_tag:
                    self.after(0, self.log_info, f"👉 [{log_tag}] Tap 'card_f/f_tieptheo.png' tại ({tt_x}, {tt_y}) ➔ Hoãn {tap_interval}s...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tt_x} {tt_y}"])
                time.sleep(tap_interval)
            else:
                break
        if delay_after > 0:
            if delay_after >= 1.0:
                for _ in range(int(delay_after)):
                    if is_stop(): return
                    time.sleep(1.0)
                rem = delay_after - int(delay_after)
                if rem > 0:
                    time.sleep(rem)
            else:
                time.sleep(delay_after)

    def _run_common_safezone(self, dnconsole_path: str, tab_index: str, card_tag: str = "Về Khu An Toàn", stop_check=None, px_x: int = 1213, px_y: int = 648):
        """QUY TRÌNH VỀ KHU AN TOÀN DÙNG CHUNG CHO CẢ CARD A, CARD B VÀ CARD C (ĐỘC LẬP 100% VỚI STOP_CHECK)"""
        is_stop = stop_check if callable(stop_check) else (lambda: self.stop_requested)
        if is_stop(): return

        # 1. Quét tìm nút login_x.png để đóng bảng quảng cáo/thông báo
        self.after(0, self.log_info, f"👁️ [{card_tag}] Quét tìm nút 'login_x.png' (ROI 990,50,1165,200) để đóng bảng quảng cáo/thông báo...")
        self._close_login_x_popup(dnconsole_path, tab_index, "Safezone")

        # 2. Mở menu và quét nút Vị Trí (c_vitri.png) qua helper độc lập
        if is_stop(): return
        self.after(0, self.log_info, f"👁️ [{card_tag}] Quét nút Vị Trí 'card_c/c_vitri.png'...")
        if not self._tap_menu_utility_icon(dnconsole_path, tab_index, px_x, px_y, "card_c/c_vitri.png", item_label="Vị Trí", stop_check=is_stop):
            return

        # 3. Click liên tục (435, 250) mỗi 0.5s đến khi xuất hiện nút Có (a_co.png)
        if is_stop(): return
        self.after(0, self.log_info, f"👉 [{card_tag}] Click liên tục (435, 250) mỗi 0.5s cho đến khi xuất hiện nút Có 'card_a/a_co.png' (85%, ROI 275,540,1150,670)...")
        while not is_stop():
            co_x, co_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_co.png", threshold=0.85, region=(275, 540, 1150, 670))
            if co_x is not None and co_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện nút Có 'card_a/a_co.png' tại ({co_x}, {co_y})! Dừng click (435, 250).")
                break
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 435 250"])
            time.sleep(0.5)

        # 4. Click liên tục nút Có (a_co.png) mỗi 0.5s cho tới khi hết ảnh
        if is_stop(): return
        self.after(0, self.log_info, f"👁️ [{card_tag}] Click liên tục nút Có 'card_a/a_co.png' (0.5s mỗi lần) cho tới khi hết ảnh...")
        while not is_stop():
            co_x, co_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_co.png", threshold=0.85, region=(275, 540, 1150, 670))
            if co_x is not None and co_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện nút Có 'card_a/a_co.png' tại ({co_x}, {co_y}) ➔ Click vào vị trí ảnh...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {co_x} {co_y}"])
                time.sleep(0.5)
            else:
                self.after(0, self.log_info, f"ℹ️ [{card_tag}] Không còn thấy ảnh nút Có 'card_a/a_co.png' ➔ Hoàn thành Về Khu An Toàn!")
                break

        # 5. Hoãn 3.0s và kiểm tra lại nút c_vitri.png, nếu còn thì thu gọn menu
        if is_stop(): return
        self.after(0, self.log_info, f"⏳ [{card_tag}] Hoãn 3.0s trước khi quét kiểm tra lại nút 'card_c/c_vitri.png'...")
        time.sleep(3.0)

        if is_stop(): return
        self.after(0, self.log_info, f"👁️ [{card_tag}] Quét kiểm tra lại nút 'card_c/c_vitri.png' (85%, ROI 735,405,1280,720)...")
        v_check_x, v_check_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_vitri.png", threshold=0.85, region=(735, 405, 1280, 720))
        if v_check_x is not None and v_check_y is not None:
            self.after(0, self.log_info, f"🎯 Phát hiện 'card_c/c_vitri.png' vẫn còn tại ({v_check_x}, {v_check_y}) ➔ Click ({px_x}, {px_y}) để thu gọn menu")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {px_x} {px_y}"])
            time.sleep(0.4)
        else:
            self.after(0, self.log_info, f"ℹ️ [{card_tag}] Không thấy nút 'card_c/c_vitri.png' ➔ Bỏ qua thu gọn menu.")

    def _run_safezone_di_gioi(self, dnconsole_path: str, tab_index: str, px_x: int, px_y: int):
        """Hàm tương thích: Gọi tới _run_common_safezone cho Card C"""
        self._run_common_safezone(dnconsole_path, tab_index, card_tag="Card C: Dị Giới Đêm", stop_check=self._should_stop_card_C, px_x=px_x, px_y=px_y)

    def _wait_until_card_C_target(self, target_dt: datetime, step_label: str) -> bool:
        """Đếm giờ 2 giai đoạn cho Card C:
        - Giai đoạn 1 (Chờ dài): Khi còn cách mốc > 60s, chạy chu kỳ 60s đồng bộ theo đầu phút mới.
        - Giai đoạn 2 (Về đích): Khi còn <= 60s, chuyển về nhịp quét từng 1.0s để kích hoạt chuẩn xác giây 00.
        - Luôn kiểm tra ngắt tức thì trong 1.0s khi bấm Dừng hoặc gạt công tắc C về OFF.
        Trả về True nếu chạm mốc thành công, False nếu bị dừng/ngắt.
        """
        now = datetime.now()
        if now >= target_dt:
            return True

        self.after(0, self.log_info, f"⏳ [{step_label}] Bắt đầu đếm giờ chờ đến {target_dt.strftime('%H:%M')} (Hiện tại: {now.strftime('%H:%M:%S')})...")

        while datetime.now() < target_dt:
            if self._should_stop_card_C():
                return False

            remaining_sec = (target_dt - datetime.now()).total_seconds()
            if remaining_sec <= 0:
                break

            if remaining_sec > 60:
                # Giai đoạn 1: Chờ dài (đồng bộ chu kỳ 60s đầu phút mới, ngắt quãng 1.0s bắt lệnh dừng)
                for _ in range(60):
                    if self._should_stop_card_C():
                        return False
                    if datetime.now().second >= 58:
                        time.sleep(1.0)
                        break
                    time.sleep(1.0)
            else:
                # Giai đoạn 2: Về đích (còn <= 60s) ➔ Quét từng 1.0s để chạm đúng giây 00
                time.sleep(1.0)

        return not self._should_stop_card_C()

    def _execute_card_C_di_gioi(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Thực thi Card DỊ GIỚI (C) theo quy trình mới được tích hợp mặc định vào công tắc trượt ON/OFF"""
        if self._should_stop_card_C():
            return

        # =========================================================================
        # 📌 BƯỚC 1: TÍNH TOÁN TỌA ĐỘ THEO TỶ LỆ MÀN HÌNH
        # =========================================================================
        screen_w, screen_h = self._get_emulator_screen_size(dnconsole_path, tab_index)

        if screen_w == 1280 and screen_h == 720:
            px_x, px_y = 1213, 648
            pt_tap_x, pt_tap_y = 630, 310
            kl_tap_x, kl_tap_y = 630, 355
            rg_tap_x, rg_tap_y = 630, 525
            c_x, c_y = 687, 595
            end_x, end_y = 1090, 125
            v1_x, v1_y = 235, 450
            v2_x, v2_y = 1035, 210
        else:
            px_x = int(round((1213 / 1280.0) * screen_w))
            px_y = int(round((648 / 720.0) * screen_h))
            pt_tap_x = int(round((630 / 1280.0) * screen_w))
            pt_tap_y = int(round((310 / 720.0) * screen_h))
            kl_tap_x = int(round((630 / 1280.0) * screen_w))
            kl_tap_y = int(round((355 / 720.0) * screen_h))
            rg_tap_x = int(round((630 / 1280.0) * screen_w))
            rg_tap_y = int(round((525 / 720.0) * screen_h))
            c_x = int(round((687 / 1280.0) * screen_w))
            c_y = int(round((595 / 720.0) * screen_h))
            end_x = int(round((1090 / 1280.0) * screen_w))
            end_y = int(round((125 / 720.0) * screen_h))
            v1_x = int(round((235 / 1280.0) * screen_w))
            v1_y = int(round((450 / 720.0) * screen_h))
            v2_x = int(round((1035 / 1280.0) * screen_w))
            v2_y = int(round((210 / 720.0) * screen_h))

        self.after(0, self.log_info, f"🖥️ [CARD C: DỊ GIỚI - BƯỚC 1] LDPlayer Tab '{tab_name}' ({screen_w}x{screen_h})")

        # =========================================================================
        # 📌 BƯỚC 2: QUY TRÌNH DỊ GIỚI ĐÊM (TÍCH HỢP MẶC ĐỊNH VÀO CÔNG TẮC TRƯỢT ON/OFF)
        # =========================================================================
        # 1. Đếm giờ đến 22H50 (Nâng cấp đồng bộ 2 giai đoạn: chu kỳ phút ➔ quét giây khi về đích)
        now = datetime.now()
        target_2250 = now.replace(hour=22, minute=50, second=0, microsecond=0)

        if now < target_2250:
            if not self._wait_until_card_C_target(target_2250, "CARD C: DỊ GIỚI - BƯỚC 2.1"):
                return

        if self._should_stop_card_C(): return

        # 2. Tắt Ký Lục lúc 22H50
        self.after(0, self.log_info, "▶️ [CARD C: DỊ GIỚI - BƯỚC 2.2] Đã đến 22H50! Quét Cài Đặt AI để TẮT Ký Lục...")
        if not self._tap_menu_utility_icon(dnconsole_path, tab_index, px_x, px_y, "card_c/c_ai.png", item_label="Cài Đặt AI", stop_check=self._should_stop_card_C):
            return

        if self._should_stop_card_C(): return
        self.after(0, self.log_info, f"👉 Tap Cài đặt AI tại ({c_x}, {c_y})")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {c_x} {c_y}"])
        time.sleep(0.4)

        if self._should_stop_card_C(): return
        self.after(0, self.log_info, "👁️ Quét kiểm tra 'card_c/c_kyluc.png' (95%, ROI 305,165,705,605)...")
        kl_x, kl_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_kyluc.png", threshold=0.95, region=(305, 165, 705, 605))
        if kl_x is None:
            self.after(0, self.log_info, f"🎯 Giao diện ĐANG BẬT Ký Lục ➔ Tap ({kl_tap_x}, {kl_tap_y}) để TẮT Ký Lục")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {kl_tap_x} {kl_tap_y}"])
            time.sleep(0.4)
        else:
            self.after(0, self.log_info, "ℹ️ Giao diện ĐÃ TẮT Ký Lục sẵn ➔ Bỏ qua.")

        if self._should_stop_card_C(): return
        self.after(0, self.log_info, f"👉 Tap đóng bảng tại ({end_x}, {end_y}) ➔ Tap ({px_x}, {px_y}) thu gọn menu")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {end_x} {end_y}"])
        time.sleep(0.4)
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {px_x} {px_y}"])
        time.sleep(0.4)

        # 3. Đếm giờ qua ngày mới (00H00) (Nâng cấp đồng bộ 2 giai đoạn: chu kỳ phút ➔ quét giây khi về đích)
        now = datetime.now()
        target_0000 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now >= target_0000:
            target_0000 += timedelta(days=1)

        if not self._wait_until_card_C_target(target_0000, "CARD C: DỊ GIỚI - BƯỚC 2.3"):
            return

        if self._should_stop_card_C(): return

        # 4. Quét nhận diện bản đồ Dị Giới lúc 00H00
        self.after(0, self.log_info, "👁️ [CARD C: DỊ GIỚI - BƯỚC 2.4 - 00H00] Quét nhận diện map Dị Giới 'card_c/c_digioi.png' (85%, ROI 1060,0,1280,40)...")
        dg_x, dg_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_digioi.png", threshold=0.85, region=(1060, 0, 1280, 40))
        if dg_x is not None and dg_y is not None:
            self.after(0, self.log_info, f"🎯 Đã phát hiện map Dị Giới 'card_c/c_digioi.png' tại ({dg_x}, {dg_y}) ➔ Quét Mắt Thần nút AI Tìm 'card_c/c_aitim.png' (75%, ROI 0,100,240,190) liên tục trong 5.0s...")
            aitim_x, aitim_y = None, None
            for _ in range(10):
                if self._should_stop_card_C(): return
                aitim_x, aitim_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_aitim.png", threshold=0.75, region=(0, 100, 240, 190))
                if aitim_x is not None and aitim_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_c/c_aitim.png' tại ({aitim_x}, {aitim_y})! Click chọn nút AI Tìm để TẮT tự động đánh quái")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {aitim_x} {aitim_y}"])
                    time.sleep(0.4)
                    break
                time.sleep(0.5)

            if self._should_stop_card_C(): return
            self.after(0, self.log_info, "⏳ [Card C - Dị Giới] Hoãn 20s (bỏ qua các bước di chuyển)...")
            if self._sleep_with_stop_check(20.0, check_active=lambda: not self._should_stop_card_C()):
                return
        else:
            self.after(0, self.log_info, "👉 Chưa thấy map 'card_c/c_digioi.png' ➔ Gọi Về Khu An Toàn trước khi vào Dị Giới...")
            self._run_safezone_di_gioi(dnconsole_path, tab_index, px_x, px_y)

            if self._should_stop_card_C(): return
            self.after(0, self.log_info, "👉 Quét nút Vị Trí 'card_c/c_vitri.png'...")
            if not self._tap_menu_utility_icon(dnconsole_path, tab_index, px_x, px_y, "card_c/c_vitri.png", item_label="Vị Trí", stop_check=self._should_stop_card_C):
                return

            if self._should_stop_card_C(): return
            self.after(0, self.log_info, f"👉 Tap tọa độ chuyển map 1 ({v1_x}, {v1_y})")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {v1_x} {v1_y}"])
            time.sleep(0.4)

            if self._should_stop_card_C(): return
            self.after(0, self.log_info, f"👉 Tap tọa độ chuyển map 2 ({v2_x}, {v2_y})")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {v2_x} {v2_y}"])
            time.sleep(0.4)

            if self._should_stop_card_C(): return
            self.after(0, self.log_info, "⏳ [Card C - Dị Giới] Tạm nghỉ 3.0s nạp map Dị Giới...")
            if self._sleep_with_stop_check(3.0, check_active=lambda: not self._should_stop_card_C()):
                return


        # =========================================================================
        # 📌 BƯỚC 3: THIẾT LẬP CÀI ĐẶT AI (PHÚC THẦN, KÝ LỤC, RÚT GỌN) - MỞ BẢNG 1 LẦN DUY NHẤT
        # =========================================================================
        if self._should_stop_card_C(): return
        has_phuc_than = self.var_C1.get()
        has_ky_luc = self.var_C2.get()
        has_rut_gon = self.var_C3.get()

        self.after(0, self.log_info, f"▶️ [CARD C: DỊ GIỚI - BƯỚC 3] Thiết lập Cài Đặt AI [Phúc Thần: {'BẬT' if has_phuc_than else 'TẮT'} | Ký Lục: {'BẬT' if has_ky_luc else 'TẮT'} | Rút Gọn: {'BẬT' if has_rut_gon else 'TẮT'}]...")

        # 3.1. Mở Cài Đặt AI (mở 1 lần duy nhất cho toàn bộ 3 mục)
        if self._tap_menu_utility_icon(dnconsole_path, tab_index, px_x, px_y, "card_c/c_ai.png", item_label="Cài Đặt AI", stop_check=self._should_stop_card_C):
            # 3.2. Cấu hình Phúc Thần (C1) ngay tại giao diện AI chính
            if self._should_stop_card_C(): return
            pt_x, pt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_phucthan.png", threshold=0.95, region=(305, 165, 705, 605))
            if has_phuc_than:
                if pt_x is not None and pt_y is not None:
                    self.after(0, self.log_info, f"🎯 [BẬT] Tap ({pt_tap_x}, {pt_tap_y}) để Bật Phúc Thần")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {pt_tap_x} {pt_tap_y}"])
                    time.sleep(0.4)
            else:
                if pt_x is None:
                    self.after(0, self.log_info, f"🎯 [TẮT] Tap ({pt_tap_x}, {pt_tap_y}) để Tắt Phúc Thần")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {pt_tap_x} {pt_tap_y}"])
                    time.sleep(0.4)

            # 3.3. Tap nút Cài đặt AI (tab con) để chuyển sang cấu hình Ký Lục và Rút Gọn
            if self._should_stop_card_C(): return
            self.after(0, self.log_info, f"👉 Tap chuyển tab Cài đặt AI tại ({c_x}, {c_y})")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {c_x} {c_y}"])
            time.sleep(0.4)

            # 3.4. Cấu hình Ký Lục (C2)
            if self._should_stop_card_C(): return
            kl_x, kl_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_kyluc.png", threshold=0.95, region=(305, 165, 705, 605))
            if has_ky_luc:
                if kl_x is not None and kl_y is not None:
                    self.after(0, self.log_info, f"🎯 [BẬT] Tap ({kl_tap_x}, {kl_tap_y}) để Bật Ký Lục")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {kl_tap_x} {kl_tap_y}"])
                    time.sleep(0.4)
            else:
                if kl_x is None:
                    self.after(0, self.log_info, f"🎯 [TẮT] Tap ({kl_tap_x}, {kl_tap_y}) để Tắt Ký Lục")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {kl_tap_x} {kl_tap_y}"])
                    time.sleep(0.4)

            # 3.5. Cấu hình Rút Gọn (C3) ngay trong cùng tab Cài đặt AI (không cần mở lại)
            if self._should_stop_card_C(): return
            rg_x, rg_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_rutgon.png", threshold=0.95, region=(305, 165, 705, 605))
            if has_rut_gon:
                if rg_x is not None and rg_y is not None:
                    self.after(0, self.log_info, f"🎯 [BẬT] Tap ({rg_tap_x}, {rg_tap_y}) để Bật Rút Gọn")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {rg_tap_x} {rg_tap_y}"])
                    time.sleep(0.4)
            else:
                if rg_x is None:
                    self.after(0, self.log_info, f"🎯 [TẮT] Tap ({rg_tap_x}, {rg_tap_y}) để Tắt Rút Gọn")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {rg_tap_x} {rg_tap_y}"])
                    time.sleep(0.4)

            # 3.6. Đóng bảng AI và thu gọn menu 1 lần duy nhất hoàn tất Bước 3
            if self._should_stop_card_C(): return
            self.after(0, self.log_info, f"👉 Tap đóng bảng AI ({end_x}, {end_y}) ➔ Thu gọn menu ({px_x}, {px_y})")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {end_x} {end_y}"])
            time.sleep(0.4)
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {px_x} {px_y}"])
            time.sleep(0.4)

        # =========================================================================
        # 📌 BƯỚC 4: KÍCH HOẠT NÚT AI TÌM ('card_c/c_aitim.png') HOẶC THOÁT GAME
        # =========================================================================
        if self._should_stop_card_C(): return
        self.after(0, self.log_info, "▶️ [CARD C: DỊ GIỚI - BƯỚC 4] Quét kiểm tra nút AI Tìm 'card_c/c_aitim.png' (75%, ROI 0,100,240,190) liên tục trong 5.0s...")
        aitim_x, aitim_y = None, None
        for _ in range(10):
            if self._should_stop_card_C(): return
            aitim_x, aitim_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_c/c_aitim.png", threshold=0.75, region=(0, 100, 240, 190))
            if aitim_x is not None and aitim_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện nút AI Tìm 'card_c/c_aitim.png' tại ({aitim_x}, {aitim_y})! Click chọn ngay")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {aitim_x} {aitim_y}"])
                time.sleep(0.4)
                break
            time.sleep(0.5)

        if aitim_x is None or aitim_y is None:
            if self._should_stop_card_C(): return
            self.after(0, self.log_info, "⚠️ Không phát hiện thấy ảnh 'card_c/c_aitim.png' sau 5.0s ➔ Tiến hành Thoát Game...")
            target_pkg = "com.vtcmobile.gz06"
            # Chuẩn hóa đóng game theo nút Exit: killapp có packagename + gộp force-stop và phím Home vào 1 lệnh ADB duy nhất
            self._exec_cmd([dnconsole_path, "killapp", "--index", str(tab_index), "--packagename", target_pkg])
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell am force-stop {target_pkg} && input keyevent 3"])

        # =========================================================================
        # 📌 BƯỚC 5: HOÀN TẤT & TỰ ĐỘNG TẮT CÔNG TẮC
        # =========================================================================
        self.after(0, lambda: self.var_switch_C.set(False))
        self.after(0, self.save_config)
        self.after(0, self.log_info, "✅ [CARD C: DỊ GIỚI - BƯỚC 5] Đã hoàn thành toàn bộ chuỗi thao tác Dị Giới Đêm ➔ Tự động tắt công tắc ON/OFF!")
        self.after(0, lambda: self._send_notification("🎉 Dị Giới Đêm Hoàn Thành", f"Đã hoàn thành toàn bộ hoạt động Dị Giới Đêm trên {tab_name}!"))

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: CARD B (PHỤ BẢN ĐƠN / ĐỘI)
    # =========================================================================
    def _switch_card_char_position(self, dnconsole_path: str, tab_index: str, selected_char: str, mode_label: str = "Phụ Bản", card_prefix: str = "B"):
        """Đổi vị trí nhân vật (Xuất Chiến / Vị Trí 1..4) dùng chung chuẩn hóa cho Card A, Card B và Card D"""
        def should_stop():
            if card_prefix == "A": return self._should_stop_card_A()
            if card_prefix == "B": return self._should_stop_card_B()
            if card_prefix == "D": return self._should_stop_card_D()
            return self.stop_requested

        if should_stop(): return
        self.after(0, self.log_info, f"⚙️ [{mode_label} - Bước 2] Vị trí nhân vật chọn: '{selected_char}'")
        if selected_char == "Xuất Chiến":
            self.after(0, self.log_info, f"ℹ️ [{mode_label}] Vị trí 'Xuất Chiến': Giữ nguyên vị trí mặc định, chuyển tiếp bước tiếp theo.")
            return

        # 1. Quét tìm và tap ảnh Đội 'card_b/b_doi.png' (mở menu nếu chưa thấy)
        if should_stop(): return
        if not self._open_team_panel(dnconsole_path, tab_index, log_tag=mode_label, stop_check=should_stop):
            return

        # 2. Thao tác click đổi vị trí theo danh sách tọa độ
        pos_coords = {
            "Vị Trí 1": [(560, 340), (560, 255), (1090, 110)],
            "Vị Trí 2": [(560, 255), (560, 340), (1090, 110)],
            "Vị Trí 3": [(560, 255), (560, 430), (1090, 110)],
            "Vị Trí 4": [(560, 255), (560, 520), (1090, 110)],
        }
        steps = pos_coords.get(selected_char)
        if steps:
            coords_str = " ➔ ".join(f"({x}, {y})" for x, y in steps)
            self.after(0, self.log_info, f"👉 [{mode_label} - {selected_char}] Click {coords_str} (Hoãn 0.5s mỗi tap)...")
            for cx, cy in steps:
                if should_stop(): return
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {cx} {cy}"])
                time.sleep(0.5)

        # 3. Thu gọn menu giao diện Đội
        if should_stop(): return
        self._close_team_panel(dnconsole_path, tab_index, log_tag=mode_label, stop_check=should_stop)

    def _combat_and_confirm_card_B(self, dnconsole_path: str, tab_index: str, pb_name: str, delay_sec: int, prefix_log: str = ""):
        """Thực thi đánh trận: Tap Auto (1165, 210) mỗi 0.5s trong delay_sec ➔ Duy trì Auto & Quét Xác Nhận b_xn.png ➔ Tap nhận thưởng"""
        tag = f"[{prefix_log} - {pb_name}]" if prefix_log else f"[{pb_name}]"

        if self._should_stop_card_B(): return
        self.after(0, self.log_info, f"⏳ {tag} Chờ {delay_sec}s ➔ Tap liên tục nút Auto (1165, 210) mỗi 0.5s...")
        start_wait = time.time()
        while time.time() - start_wait < delay_sec:
            if self._should_stop_card_B(): return
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1165 210"])
            time.sleep(0.5)

        if self._should_stop_card_B(): return
        self.after(0, self.log_info, f"👁️ {tag} Hết {delay_sec}s ➔ Duy trì tap Auto (1165, 210) mỗi 0.5s & quét tìm nút Xác Nhận 'card_b/b_xn.png' (85%, ROI 165,170,1110,615) mỗi 3s...")
        xn_x, xn_y = None, None
        while not self._should_stop_card_B():
            xn_x, xn_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_xn.png", threshold=0.85, region=(165, 170, 1110, 615))
            if xn_x is not None and xn_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện ảnh 'card_b/b_xn.png' tại ({xn_x}, {xn_y})!")
                break

            start_sub = time.time()
            while time.time() - start_sub < 3.0:
                if self._should_stop_card_B(): break
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1165 210"])
                time.sleep(0.5)

        if self._should_stop_card_B(): return
        if xn_x is not None and xn_y is not None:
            self.after(0, self.log_info, f"👉 Tap nhấp chọn ảnh Xác Nhận 'card_b/b_xn.png' tại ({xn_x}, {xn_y}) để hoàn thành {pb_name}...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xn_x} {xn_y}"])

    def _execute_card_B_phu_ban_doi(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Thực thi Card B: PHỤ BẢN ĐƠN / ĐỘI"""
        if not self.var_switch_B.get():
            self.after(0, self.log_info, "ℹ️ [CARD B: PHỤ BẢN ĐƠN / ĐỘI] Công tắc ON/OFF đang TẮT -> Bỏ qua.")
            return

        don_active = self.var_B_don.get()
        team_active = self.var_B_doi.get()

        if not don_active and not team_active:
            self.after(0, self.log_info, "ℹ️ [CARD B: PHỤ BẢN ĐƠN / ĐỘI] Không có mục Đơn / Tổ Đội nào được chọn -> Tắt công tắc & Bỏ qua.")
            self.after(0, lambda: self.var_switch_B.set(False))
            self.after(0, self.save_config)
            return

        # =========================================================================
        # 📌 VỀ KHU AN TOÀN (SAFE ZONE RETURN - Chỉ chạy khi có chọn Phụ Bản Đơn)
        # =========================================================================
        if don_active:
            self._run_common_safezone(dnconsole_path, tab_index, card_tag="Card B: Phụ Bản Đơn", stop_check=self._should_stop_card_B)

        # ---------------- 1. XỬ LÝ MỤC PHỤ BẢN ĐƠN (CÁ NHÂN) ----------------
        if don_active:
            if self._should_stop_card_B(): return
            selected_char_don = self.combo_B_don_char.get() if hasattr(self, 'combo_B_don_char') else "Xuất Chiến"
            self.after(0, self.log_info, f"⚙️ [Phụ Bản Đơn] Bắt đầu quy trình ô Cá Nhân - Vị trí: '{selected_char_don}'")
            time.sleep(0.4)

            # --- Bước 1 & 2: Chuyển đổi Vị Trí Nhân Vật ---
            self._switch_card_char_position(dnconsole_path, tab_index, selected_char_don, mode_label="Phụ Bản Đơn", card_prefix="B")

            # --- Bước 3: Tìm ảnh b_pb.png (trong folder card_b) & click tọa độ ---
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Phụ Bản Đơn - Bước 3] Quét tìm ảnh 'b_pb.png' (ROI 735,405,1280,720)...")
            if not self._tap_menu_utility_icon(dnconsole_path, tab_index, 1213, 648, "card_b/b_pb.png", item_label="Phụ Bản", stop_check=self._should_stop_card_B) and self._should_stop_card_B(): return

            # --- Quét card_b/b_lsknn.png khi hoàn thành các thao tác Quét card_b/b_pb.png ---
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Phụ Bản Đơn - Bước 3] Quét kiểm tra ảnh 'card_b/b_lsknn.png' (ROI 165,170,1110,615)...")
            lsknn_x, lsknn_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_lsknn.png", threshold=0.85, region=(165, 170, 1110, 615))
            if lsknn_x is not None and lsknn_y is not None:
                self.after(0, self.log_info, f"🎯 Khớp ảnh 'b_lsknn.png' tại ({lsknn_x}, {lsknn_y}) ➔ Click tọa độ (350, 585)")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 350 585"])
                time.sleep(0.4)
            else:
                self.after(0, self.log_info, "ℹ️ Không khớp ảnh 'b_lsknn.png' ➔ Bỏ qua.")

            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Phụ Bản Đơn - Bước 3] Quét & tap ảnh 'card_b/b_pbdon.png' (85%, ROI 165,170,1110,615)")
            while not self._should_stop_card_B():
                pbdon_x, pbdon_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_pbdon.png", threshold=0.85, region=(165, 170, 1110, 615))
                if pbdon_x is not None and pbdon_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_b/b_pbdon.png' tại ({pbdon_x}, {pbdon_y})! Click vào ảnh")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {pbdon_x} {pbdon_y}"])
                    time.sleep(0.4)
                    break
                time.sleep(0.3)

            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👉 Click tiếp tọa độ (775, 575)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 775 575"])
            time.sleep(0.4)

            # --- Quét nhận diện Xác Nhận: card_b/b_xn.png (Chờ 5s & Quét liên tục tới khi thấy) ---
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "⏳ [Phụ Bản Đơn - Bước 3] Chờ 5 giây trước khi quét tìm nút Xác Nhận...")
            for _ in range(5):
                if self._should_stop_card_B(): return
                time.sleep(1.0)

            self.after(0, self.log_info, "👁️ [Phụ Bản Đơn - Bước 3] Quét tìm ảnh mẫu 'card_b/b_xn.png' (ROI 165,170,1110,615)...")
            xn_x, xn_y = None, None
            while not self._should_stop_card_B():
                xn_x, xn_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_xn.png", threshold=0.85, region=(165, 170, 1110, 615))
                if xn_x is not None and xn_y is not None:
                    break
                self.after(0, self.log_info, "⏳ Chưa phát hiện 'card_b/b_xn.png' ➔ Tiếp tục quét lại sau 1.5s...")
                time.sleep(1.5)

            if self._should_stop_card_B(): return

            if xn_x is not None and xn_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện ảnh 'b_xn.png' tại ({xn_x}, {xn_y}) ➔ Click 2 lần (cách nhau 0.8s) vào ảnh 'b_xn.png' ➔ Tạm dừng 3.0s...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xn_x} {xn_y}"])
                time.sleep(0.8)
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xn_x} {xn_y}"])
                time.sleep(3.0)

            # --- Bước 4: Quy trình Bước 4 (Bỏ 4.1 và 4.2) ---
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "🚀 [Card B - Phụ Bản Đơn - Bước 4] Khởi chạy Bước 4...")

            # 4.3: Quét nhận diện Phụ Bản & Vào màn
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Card B - Phụ Bản Đơn - Bước 4.3] Quét tìm ảnh 'b_pb.png' (ROI 735,405,1280,720)...")
            if not self._tap_menu_utility_icon(dnconsole_path, tab_index, 1213, 648, "card_b/b_pb.png", item_label="Phụ Bản", stop_check=self._should_stop_card_B) and self._should_stop_card_B(): return

            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Card B - Phụ Bản Đơn - Bước 4] Quét & tap ảnh 'card_b/b_pbdon.png' (85%, ROI 165,170,1110,615)")
            while not self._should_stop_card_B():
                pbdon4_x, pbdon4_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_pbdon.png", threshold=0.85, region=(165, 170, 1110, 615))
                if pbdon4_x is not None and pbdon4_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_b/b_pbdon.png' tại ({pbdon4_x}, {pbdon4_y})! Click vào ảnh")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {pbdon4_x} {pbdon4_y}"])
                    time.sleep(0.4)
                    break
                time.sleep(0.3)

            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👉 Click tiếp tọa độ (640, 575)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 640 575"])
            time.sleep(0.4)

            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👉 Click nút thực thi tại tọa độ (775, 575)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 775 575"])
            time.sleep(0.4)

            # 4.4: Chờ nạp trận đánh (có kiểm tra trạng thái dừng)
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "⏳ [Card B - Phụ Bản Đơn - Bước 4.4] Chờ 5 giây nạp trận đánh...")
            if self._sleep_with_stop_check(5.0, check_active=lambda: not self._should_stop_card_B()):
                return

            # 4.5: Vòng lặp quét liên tục ảnh card_b/b_xn.png cho tới khi tìm thấy (mỗi 1.5s)
            if self._should_stop_card_B(): return
            self.after(0, self.log_info, "👁️ [Card B - Phụ Bản Đơn - Bước 4.5] Quét tìm ảnh mẫu 'card_b/b_xn.png' (ROI 165,170,1110,615)...")
            xn_x4, xn_y4 = None, None
            while not self._should_stop_card_B():
                xn_x4, xn_y4 = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_xn.png", threshold=0.85, region=(165, 170, 1110, 615))
                if xn_x4 is not None and xn_y4 is not None:
                    break
                self.after(0, self.log_info, "⏳ [Card B - Phụ Bản Đơn] Chưa phát hiện 'card_b/b_xn.png' ➔ Tiếp tục quét lại sau 1.5s...")
                if self._sleep_with_stop_check(1.5, check_active=lambda: not self._should_stop_card_B()):
                    break

            if self._should_stop_card_B(): return

            if xn_x4 is not None and xn_y4 is not None:
                self.after(0, self.log_info, f"🎯 [Card B - Phụ Bản Đơn] Phát hiện ảnh 'b_xn.png' tại ({xn_x4}, {xn_y4}) ➔ Click 2 lần vào ảnh 'b_xn.png'...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xn_x4} {xn_y4}"])
                time.sleep(0.5)
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xn_x4} {xn_y4}"])
                if self._sleep_with_stop_check(1.5, check_active=lambda: not self._should_stop_card_B()):
                    return
        else:
            self.after(0, self.log_info, "ℹ️ [Card B - Phụ Bản Đơn] Ô check 'Đơn' KHÔNG ĐƯỢC TÍCH (OFF) -> Bỏ qua không chạy Phụ Bản Đơn.")

        # ---------------- 2. XỬ LÝ MỤC PHỤ BẢN ĐỘI (PB 20 - PB 140) ----------------
        dungeons_to_run = [
            ("PB 20", self.var_B1, "card_b/b_pb20.png", "card_b/b_pb20map.png", 60),
            ("PB 50", self.var_B2, "card_b/b_pb50.png", "card_b/b_pb50map.png", 120),
            ("PB 80", self.var_B3, "card_b/b_pb80.png", "card_b/b_pb80map.png", 180),
            ("PB 110", self.var_B4, "card_b/b_pb110.png", "card_b/b_pb110map.png", 240),
            ("PB 140", self.var_B5, "card_b/b_pb140.png", "card_b/b_pb140map.png", 300)
        ]

        any_pb_checked = any(var_pb.get() for _, var_pb, _, _, _ in dungeons_to_run)
        team_mode_active = self.var_B_doi.get()

        if team_mode_active:
            if any_pb_checked:
                if self._should_stop_card_B(): return
                selected_char_team = self.combo_B_team_char.get() if hasattr(self, 'combo_B_team_char') else "Xuất Chiến"
                self.after(0, self.log_info, f"⚙️ [Phụ Bản Đội - Tổ Đội] Kích hoạt quy trình Phụ Bản Đội (Vị trí: '{selected_char_team}')...")

                # --- Bước 1 & 2: Chuyển đổi Vị Trí Nhân Vật ---
                self._switch_card_char_position(dnconsole_path, tab_index, selected_char_team, mode_label="Phụ Bản Đội", card_prefix="B")

                # --- Bước 3: Mở Phụ Bản & Vào Phụ Bản cho từng ô tích PB 20..140 ---
                for pb_name, var_pb, pb_tmpl, pb_map_tmpl, delay_sec in dungeons_to_run:
                    if var_pb.get():
                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, f"🚀 [Phụ Bản Đội - {pb_name}] Kích hoạt quy trình cho ô tích '{pb_name}'...")

                        # 1. Quét tìm card_b/b_pb.png (ROI 735,405,1280,720)
                        if not self._tap_menu_utility_icon(dnconsole_path, tab_index, 1213, 648, "card_b/b_pb.png", item_label="Phụ Bản", stop_check=self._should_stop_card_B) and self._should_stop_card_B(): return

                        if self._should_stop_card_B(): return
                        # 2. Quét / tap ảnh card_b/b_pbXX.png (85%, ROI 165,170,1110,615) ➔ Click (735, 575)
                        self.after(0, self.log_info, f"👁️ [Phụ Bản Đội - {pb_name}] Quét & tap ảnh '{pb_tmpl}' (85%, ROI 165,170,1110,615)...")
                        while not self._should_stop_card_B():
                            p_x, p_y = self._find_template_on_screen(dnconsole_path, tab_index, pb_tmpl, threshold=0.85, region=(165, 170, 1110, 615))
                            if p_x is not None and p_y is not None:
                                self.after(0, self.log_info, f"🎯 Phát hiện '{pb_tmpl}' tại ({p_x}, {p_y})! Click vào ảnh")
                                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {p_x} {p_y}"])
                                time.sleep(0.4)
                                break
                            time.sleep(0.3)

                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, "👉 Click tiếp tọa độ (735, 575)")
                        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 735 575"])
                        time.sleep(0.4)
                        # 4. Xử lý Mật Khẩu phòng (Dùng thao tác của ô Cá Nhân làm chuẩn cho cả ô Tổ Đội)
                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, "👁️ Quét tìm ảnh mẫu 'card_b/b_matkhau.png' (85%, ROI 165,170,1110,615)...")
                        mk_x, mk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_matkhau.png", threshold=0.85, region=(165, 170, 1110, 615))
                        if mk_x is not None and mk_y is not None:
                            self.after(0, self.log_info, f"🎯 Khớp ảnh 'b_matkhau.png' tại ({mk_x}, {mk_y}) ➔ Click chọn ảnh ➔ Click (640, 435) khóa mật khẩu (Hoãn 0.4s)...")
                            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {mk_x} {mk_y}"])
                            time.sleep(0.4)
                            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 640 435"])
                            time.sleep(0.4)
                        else:
                            self.after(0, self.log_info, "ℹ️ Không thấy 'b_matkhau.png' ➔ Tap (640, 435) để hoàn tất")
                            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 640 435"])
                            time.sleep(0.4)

                        # --- GỌI THAO TÁC CARD TỔ ĐỘI ---
                        if hasattr(self, 'var_B_doi') and self.var_B_doi.get():
                            if self._should_stop_card_B(): return
                            if pb_name in ["PB 20", "PB 50", "PB 80"]:
                                self.after(0, self.log_info, f"ℹ️ [{pb_name}] Bỏ qua bước mời Tổ Đội cho mốc {pb_name} ➔ Tiến thẳng vào Bắt Đầu...")
                            else:
                                self.after(0, self.log_info, f"👥 [{pb_name} - Ô Tổ Đội] Gọi thao tác Card E (Quản Lý Tổ Đội) & ĐỢI HOÀN THÀNH 100%...")
                                self._execute_card_E_for_mode(dnconsole_path, tab_name, tab_index, mode=2)

                        # --- BƯỚC 4: VÀO TRẬN & ĐÁNH TRẬN PHỤ BẢN ĐỘI ---
                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, "👁️ Quét chờ nút Bắt Đầu 'card_b/b_batdau.png' (85%, ROI 165,170,1110,615) xuất hiện...")
                        has_seen_bd = False
                        while not self._should_stop_card_B():
                            bd_x, bd_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_batdau.png", threshold=0.85, region=(165, 170, 1110, 615))
                            if bd_x is not None and bd_y is not None:
                                has_seen_bd = True
                                break
                            time.sleep(0.5)

                        if has_seen_bd and not self._should_stop_card_B():
                            self.after(0, self.log_info, "🎯 Đã thấy 'card_b/b_batdau.png' ➔ Tap liên tục 0.5s/lần cho đến khi mất ảnh (Vào trận)...")
                            while not self._should_stop_card_B():
                                bd_x, bd_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_b/b_batdau.png", threshold=0.85, region=(165, 170, 1110, 615))
                                if bd_x is None or bd_y is None:
                                    self.after(0, self.log_info, "ℹ️ Đã mất ảnh 'card_b/b_batdau.png' (Vào trận thành công) ➔ Tiếp tục thao tác tiếp theo.")
                                    break
                                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {bd_x} {bd_y}"])
                                time.sleep(0.5)

                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, f"⏳ [Card B - Phụ Bản Đội - {pb_name}] Chờ 3.5s nạp trận...")
                        if self._sleep_with_stop_check(3.5, check_active=lambda: not self._should_stop_card_B()):
                            return

                        # Đánh trận & Xác nhận hoàn thành mốc Phụ Bản
                        self._combat_and_confirm_card_B(dnconsole_path, tab_index, pb_name, delay_sec, prefix_log="Card B - Phụ Bản Đội")

                        # Khi hoàn thành 1 mốc Phụ Bản -> hoãn 2.0s để tiếp tục mốc Phụ Bản tiếp theo
                        if self._should_stop_card_B(): return
                        self.after(0, self.log_info, f"⏳ [Card B - Phụ Bản Đội - {pb_name}] Hoàn thành mốc {pb_name}! Hoãn 2.0s để tiếp tục mốc Phụ Bản tiếp theo...")
                        if self._sleep_with_stop_check(2.0, check_active=lambda: not self._should_stop_card_B()):
                            return
            else:
                # --- TRƯỜNG HỢP: CHẾ ĐỘ 2 - HỖ TRỢ ĐỘI KHÁC (Tích [x] Đội nhưng KHÔNG tích ô mốc PB nào) ---
                if self._should_stop_card_B(): return
                self.after(0, self.log_info, "⚙️ [Card B - Phụ Bản Đội - Hỗ Trợ Đội Khác] Tích [x] Đội nhưng KHÔNG tích ô mốc PB nào ➔ Bỏ qua tạo phòng, mời đội & nút Bắt Đầu...")

                # 1. Quét ảnh nhận diện bản đồ góc trên phải (ROI 1060, 0, 1280, 40) liên tục để nhận diện mốc Phụ Bản (hủy chờ 3.5s nạp trận)
                if self._should_stop_card_B(): return
                self.after(0, self.log_info, "👁️ [Card B - Hỗ Trợ] Quét ảnh nhận diện bản đồ góc trên phải (ROI 1060, 0, 1280, 40) liên tục để xác định mốc Phụ Bản...")

                detected_pb_name = None
                detected_delay_sec = 0

                map_to_dungeon_info = [
                    ("card_b/b_pb20map.png", "PB 20", 60),
                    ("card_b/b_pb50map.png", "PB 50", 120),
                    ("card_b/b_pb80map.png", "PB 80", 180),
                    ("card_b/b_pb110map.png", "PB 110", 240),
                    ("card_b/b_pb140map.png", "PB 140", 300),
                ]

                while not self._should_stop_card_B():
                    for map_tmpl, p_name, d_sec in map_to_dungeon_info:
                        mx, my = self._find_template_on_screen(dnconsole_path, tab_index, map_tmpl, threshold=0.80, region=(1060, 0, 1280, 40))
                        if mx is not None and my is not None:
                            detected_pb_name = p_name
                            detected_delay_sec = d_sec
                            self.after(0, self.log_info, f"🎯 Phát hiện map '{map_tmpl}' ➔ Nhận diện mốc: {detected_pb_name} (Thời gian chờ: {detected_delay_sec}s)!")
                            break
                    if detected_pb_name is not None:
                        break
                    time.sleep(0.5)

                if self._should_stop_card_B() or detected_pb_name is None:
                    return

                # 2. Đánh trận & Duy trì Auto theo mốc PB đã nhận diện
                self._combat_and_confirm_card_B(dnconsole_path, tab_index, detected_pb_name, detected_delay_sec, prefix_log="Card B - Hỗ Trợ")

                if self._should_stop_card_B(): return
                self.after(0, self.log_info, f"⏳ [Card B - Hỗ Trợ - {detected_pb_name}] Hoàn thành Phụ Bản Đội Hỗ Trợ! Hoãn 2.0s...")
                if self._sleep_with_stop_check(2.0, check_active=lambda: not self._should_stop_card_B()):
                    return



        # ---------------- 3. TỰ ĐỘNG TẮT CÔNG TẮC & LƯU CẤU HÌNH (GIỮ NGUYÊN Ô TÍCH) ----------------
        self.after(0, lambda: self.var_switch_B.set(False))
        self.after(0, self.save_config)
        self.after(0, self.log_info, "✅ [CARD B: PHỤ BẢN ĐƠN / ĐỘI] Đã thực thi hoàn tất! (Tự động tắt công tắc ON/OFF & giữ nguyên các ô tích)")

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: CARD E (QUẢN LÝ TỔ ĐỘI)
    # =========================================================================
    def _should_stop_card_E(self) -> bool:
        """
        Kiểm tra điều kiện dừng & tạm dừng cho Card E (Tổ Đội) (G):
        - Ngắt ngay nếu bấm Dừng Tổng hoặc công tắc Card đang chạy (var_switch_B/D) bị tắt.
        - Tạm dừng (vòng lặp chờ nhả ô) nếu ô Tạm Dừng của Card đang chạy (var_pause_D) đang được tích.
        """
        if self.stop_requested:
            return True

        # Kiểm tra nếu ô Tạm Dừng của Card đang liên quan (D) đang tích
        def is_any_pause_active() -> bool:
            if hasattr(self, 'var_switch_D') and self.var_switch_D.get() and hasattr(self, 'var_pause_D') and self.var_pause_D.get():
                return True
            return False

        def is_no_active_switch_on() -> bool:
            e_active = hasattr(self, 'var_switch_B') and hasattr(self, 'var_B_doi') and self.var_B_doi.get() and self.var_switch_B.get()
            d_active = hasattr(self, 'var_switch_D') and self.var_switch_D.get() and hasattr(self, 'var_D2') and self.var_D2.get()
            return not (e_active or d_active)

        # Vòng lặp tạm dừng thông minh
        if is_any_pause_active():
            self.after(0, self.log_info, "⏸️ [CARD TỔ ĐỘI] Phát hiện ô Tạm Dừng của Card đang chạy được tích ➔ Tạm dừng hoạt động Tổ Đội (Chờ nhả ô Tạm Dừng)...")
            while is_any_pause_active() and not self.stop_requested:
                if is_no_active_switch_on():
                    return True
                time.sleep(0.5)
            self.after(0, self.log_info, "▶️ [CARD TỔ ĐỘI] Ô Tạm Dừng đã được nhả ➔ Khôi phục chạy tiếp hoạt động Tổ Đội!")

        return is_no_active_switch_on()

    def _run_card_E_action_1(
        self, dnconsole_path: str, tab_index: str, list_B: list, 
        assign_quan_su: bool = True, 
        log_tag: str = "Card E - Thao Tác 1",
        stop_check=None
    ):
        """
        THAO TÁC 1 CỦA CARD TỔ ĐỘI:
        Kích hoạt khi ô 'Tổ Đội' (var_D2) ở Card D được kích hoạt (cho cả 40 NPC và Nhị Kiều).
        Hỗ trợ gọi trực tiếp cho các mốc kiểm tra đội hình trước/sau cổng Lôi Đài 40 NPC.
        """
        if stop_check is None:
            stop_check = self._should_stop_card_E

        if hasattr(self, 'var_D2') and not self.var_D2.get():
            self.after(0, self.log_info, f"ℹ️ [{log_tag}] Ô 'Tổ Đội' (Card D) KHÔNG được tích ➔ Bỏ qua.")
            return
        if stop_check() or not list_B: return

        self.after(0, self.log_info, f"🚀 [{log_tag}] Khởi chạy quy trình mời {len(list_B)} nhân vật trong Danh Sách B: {', '.join(list_B)}...")

        # ---------------- GIAI ĐOẠN 1: MỞ GIAO DIỆN TỔ ĐỘI ----------------
        if stop_check(): return
        # 1. Đóng Quảng Cáo / Thông Báo Nổi
        lx_x, lx_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_x.png", threshold=0.75, region=(990, 50, 1165, 200))
        if lx_x is not None and lx_y is not None:
            self.after(0, self.log_info, f"🎯 Phát hiện 'login_x.png' tại ({lx_x}, {lx_y})! Tap")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {lx_x} {lx_y}"])
            time.sleep(0.4)

        # 2. Quét Mở Giao Diện Đội
        if stop_check(): return
        if not self._open_team_panel(dnconsole_path, tab_index, log_tag=log_tag, stop_check=stop_check):
            return

        # ---------------- VÒNG LẶP MỜI & KIỂM TRA TỔ ĐỘI ----------------
        while not stop_check():
            # 3. Nhận Diện Người Trong Tổ Đội
            if stop_check(): return
            self.after(0, self.log_info, f"👁️ [{log_tag}] Quét kiểm tra độ đầy đủ của các nhân vật trong Danh Sách B...")
            present_members, missing_list, target_count = self._scan_team_members_presence(
                dnconsole_path, tab_index, list_B, stop_check=stop_check, mode="40npc"
            )
            if stop_check(): return

            # 4. Xử Lý Kết Quả Kiểm Tra (Đủ 4 thành viên là xác nhận hoàn thành)
            if len(present_members) >= target_count:
                self.after(0, self.log_info, f"✅ [{log_tag}] Tổ đội đã ĐỦ {len(present_members)}/{target_count} thành viên ({', '.join(present_members)})!")

                # Chỉ định Quân Sư: Kích hoạt khi assign_quan_su=True
                if assign_quan_su:
                    quan_su_char = self.combo_E_quan_su.get() if hasattr(self, 'combo_E_quan_su') else ""
                    if quan_su_char and quan_su_char != "(Trống)":
                        self._assign_quan_su_when_panel_opened(
                            dnconsole_path, tab_index, quan_su_char, 
                            log_tag=f"Quân Sư - {log_tag}", 
                            stop_check=stop_check
                        )
                else:
                    self.after(0, self.log_info, f"ℹ️ [{log_tag}] Đội hình đã đủ ➔ Bỏ qua gán Quân Sư theo quy trình.")

                # Đóng giao diện Đội & thu gọn menu
                if stop_check(): return
                self._close_team_panel(dnconsole_path, tab_index, log_tag=log_tag, stop_check=stop_check)

                self.after(0, self.log_info, f"🚀 [{log_tag}] Hoàn tất dứt điểm quy trình Tổ Đội ➔ Tiếp tục bước tiếp theo.")
                break

            else:
                self._invite_missing_members_when_panel_opened(
                    dnconsole_path, tab_index, missing_list, 
                    log_tag=log_tag, stop_check=stop_check
                )

    def _run_card_E_action_2(self, dnconsole_path: str, tab_index: str, list_B: list):
        """
        THAO TÁC 2 CỦA CARD TỔ ĐỘI:
        Kích hoạt khi ô tích 'Tổ Đội' của Card Phụ Bản Đơn / Đội (var_B_doi) được tích.
        """
        if hasattr(self, 'var_B_doi') and not self.var_B_doi.get():
            self.after(0, self.log_info, "ℹ️ [CARD TỔ ĐỘI - Thao Tác 2] Ô 'Đội' (Phụ Bản Đội) KHÔNG được tích ➔ Bỏ qua Card E.")
            return
        if self._should_stop_card_E() or not list_B: return

        self.after(0, self.log_info, f"🚀 [CARD TỔ ĐỘI - Thao Tác 2] Bắt đầu quy trình mời {len(list_B)} nhân vật trong Danh Sách B: {', '.join(list_B)}...")
        already_invited = set()

        # VÒNG LẶP MỜI VÀ KIỂM TRA ĐỘI HÌNH (Lặp cho tới khi đủ 100% người)
        while not self._should_stop_card_E():
            # --- BƯỚC 1: NHẬN DIỆN THÀNH VIÊN TRONG ĐỘI ---
            if self._should_stop_card_E(): return
            self.after(0, self.log_info, "👁️ [Thao Tác 2 - Bước 1] Quét kiểm tra các nhân vật trong Danh Sách B...")
            present_members = []
            missing_list = []

            for char_name in list_B:
                if self._should_stop_card_E(): return
                chk_x, chk_y = self._find_nhanvat_template(dnconsole_path, tab_index, char_name, threshold=0.80, region=(175, 165, 1105, 605), mode="pbdoi")

                if chk_x is not None and chk_y is not None:
                    present_members.append(char_name)
                    if char_name in already_invited:
                        already_invited.remove(char_name)
                else:
                    missing_list.append(char_name)

            # --- BƯỚC 2: ĐÁNH GIÁ KẾT QUẢ KIỂM TRA (Đủ 4 thành viên là xác nhận hoàn thành) ---
            target_count = min(4, len(list_B))
            if len(present_members) >= target_count:
                self.after(0, self.log_info, f"✅ [Thao Tác 2 - Bước 2: Trường hợp A] Đội hình đã ĐỦ {len(present_members)}/{target_count} thành viên ({', '.join(present_members)})! Thoát vòng lặp & trả thao tác về Phụ Bản Đội.")
                self.after(0, lambda: self._send_notification("🎉 Tổ Đội Hoàn Thành", f"Đội hình đã gom đủ {len(present_members)}/{target_count} thành viên ({', '.join(present_members)})!"))
                break

            # Lọc danh sách những thành viên thiếu chưa được gửi lời mời ở lượt trước
            uninvited_missing = [c for c in missing_list if c not in already_invited]
            if not uninvited_missing:
                self.after(0, self.log_info, f"ℹ️ Tất cả thành viên thiếu ({', '.join(missing_list)}) đã được bấm Mời ➔ Reset danh sách đã mời để tuần tự kiểm tra/mời lại...")
                already_invited.clear()
                uninvited_missing = list(missing_list)

            # 🔴 TRƯỜNG HỢP B: CÒN THIẾU THÀNH VIÊN
            self.after(0, self.log_info, f"⚠️ [Thao Tác 2 - Bước 2: Trường hợp B] Đội chưa đủ {target_count} người (Hiện có: {len(present_members)}, Thiếu: {', '.join(missing_list)} | Cần mời tiếp: {', '.join(uninvited_missing)}) ➔ Quét tìm nút Mời 'card_e/e_moi.png'...")
            
            # Quét Mắt thần tìm nút Mời card_e/e_moi.png (85%, ROI 175,165,1105,605)
            if self._should_stop_card_E(): return
            f_moi_x, f_moi_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_e/e_moi.png", threshold=0.85, region=(175, 165, 1105, 605))
            if f_moi_x is not None and f_moi_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_e/e_moi.png' tại ({f_moi_x}, {f_moi_y})! Tap ➔ Hoãn 0.3s mở bảng danh sách bạn bè...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {f_moi_x} {f_moi_y}"])
                time.sleep(0.3)
            else:
                self.after(0, self.log_info, "⚠️ Chưa quét thấy ảnh 'card_e/e_moi.png' trên màn hình ➔ Thử lại sau 1.0s...")
                time.sleep(1.0)
                continue

            # Dò Tìm Thành Viên Tiếp Theo Chưa Mời
            still_missing = list(uninvited_missing)
            invited_any = False

            def scan_and_invite_mode2(missing_tracker: list) -> tuple:
                """
                Quét tìm thành viên tiếp theo chưa mời.
                Mỗi khi bấm Mời offset (Found_X + 205, Found_Y), lưu vào already_invited và trả về (True, char_name).
                """
                for char_name in list(missing_tracker):
                    if self._should_stop_card_E(): break
                    found_x, found_y = self._find_nhanvat_template(dnconsole_path, tab_index, char_name, threshold=0.80, region=(175, 165, 1105, 605), mode="pbdoi")

                    if found_x is not None and found_y is not None:
                        invite_x = 740
                        invite_y = found_y
                        self.after(0, self.log_info, f"🎯 Phát hiện thành viên tiếp theo '{char_name}' tại ({found_x}, {found_y})! Tap nút Mời ({invite_x}, {invite_y})")
                        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {invite_x} {invite_y}"])
                        time.sleep(0.3)
                        already_invited.add(char_name)
                        return True, char_name
                return False, None

            # 1. Quét tìm ngay trên màn hình hiện tại (trước khi vuốt)
            invited_any, char_done = scan_and_invite_mode2(still_missing)

            # 2. Chiều Vuốt XUỐNG thông minh: input swipe 625 410 625 260 350 (giữ 0.35s) ➔ Hoãn 1.5s (Tối đa 5 lần)
            if not invited_any and still_missing:
                for swipe_down_cnt in range(5):
                    if self._should_stop_card_E() or not still_missing: break
                    self.after(0, self.log_info, f"📜 [Vuốt xuống {swipe_down_cnt+1}/5] Swipe 625 410 625 260 350 (hoãn 1.5s)")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 625 410 625 260 350"])
                    time.sleep(1.5)
                    invited_any, char_done = scan_and_invite_mode2(still_missing)
                    if invited_any: break

            # 3. Tự Động Sửa Lỗi (Fallback) Nếu Không Tìm Thấy
            if not invited_any:
                self.after(0, self.log_info, "⚠️ [Thao Tác 2 - Sửa Lỗi] Sau 5 lượt vuốt xuống không tìm thấy acc ➔ Tap (330, 25) tắt bảng Mời ➔ Hoãn 0.3s & quay lại kiểm tra sảnh phòng...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 330 25"])
                time.sleep(0.3)
                continue

            # Sau khi bấm Mời acc thành công: Tạm nghỉ 1.0s chờ đồng ý & quay lại Bước 2.1
            if self._should_stop_card_E(): return
            self.after(0, self.log_info, "⏳ [Thao Tác 2] Đã tap nút Mời ➔ Tạm nghỉ 1.0s chờ thành viên nhận và vào phòng...")
            time.sleep(1.0)

    def _execute_card_E_for_mode(self, dnconsole_path: str, tab_name: str, tab_index: str, mode: int):
        """
        Khung thực thi phân luồng Card Tổ Đội (G):
        - mode=1: Thao tác 1 (Kích hoạt khi ô Tổ Đội Card D var_D2 được tích cho 40 NPC / Nhị Kiều)
        - mode=2: Thao tác 2 (Kích hoạt khi ô Tổ Đội Phụ Bản Đội var_B_doi được tích)
        """
        if mode == 1 and hasattr(self, 'var_D2') and not self.var_D2.get():
            self.after(0, self.log_info, "ℹ️ [Card E - Thao Tác 1] Ô 'Tổ Đội' (Card D) KHÔNG được tích ➔ Bỏ qua Card E.")
            return
        if mode == 2 and hasattr(self, 'var_B_doi') and not self.var_B_doi.get():
            self.after(0, self.log_info, "ℹ️ [Card E - Thao Tác 2] Ô 'Đội' (Phụ Bản Đội) KHÔNG được tích ➔ Bỏ qua Card E.")
            return

        list_B = list(getattr(self, 'list_E_B', []))
        if not list_B:
            self.after(0, self.log_info, f"ℹ️ [Card E - Thao Tác {mode}] [Danh Sách B] chưa có nhân vật nào -> Bỏ qua.")
            return

        self._is_card_E_running = True
        try:
            self.after(0, self.log_info, f"▶️ [Card E - Thao Tác {mode}] Bắt đầu thực thi {len(list_B)} nhân vật từ [Danh Sách B]: {', '.join(list_B)}...")
            if mode == 1:
                self._run_card_E_action_1(dnconsole_path, tab_index, list_B)
            elif mode == 2:
                self._run_card_E_action_2(dnconsole_path, tab_index, list_B)
        finally:
            try:
                self._close_team_panel(dnconsole_path, tab_index, log_tag=f"Card E - Thao Tác {mode}")
            except Exception:
                pass
            self._is_card_E_running = False

    # =========================================================================
    # 🔓 QUẢN LÝ QUÂN SƯ CARD E
    # =========================================================================
    def _on_combo_quan_su_changed(self, choice=None):
        """Callback khi menu Quân Sư thay đổi"""
        if hasattr(self, 'combo_E_quan_su') and hasattr(self, 'var_E_quan_su'):
            qs_val = self.combo_E_quan_su.get()
            self.var_E_quan_su.set(bool(qs_val and qs_val != "(Trống)"))
        self.save_config()


    def _find_nhanvat_template(self, dnconsole_path: str, tab_index: str, char_name: str, threshold: float = 0.80, region: tuple = (305, 150, 1105, 625), mode: str = "auto"):
        """Tìm ảnh nhân vật trong assets/card_e/nhanvat với thứ tự ưu tiên chuẩn xác theo từng chế độ"""
        if mode == "pbdoi":
            candidates = [
                f"card_e/nhanvat/pbdoi/{char_name}.png",
                f"card_e/nhanvat/{char_name}.png",
                f"card_e/nhanvat/40npc2k/{char_name}.png"
            ]
        elif mode == "40npc":
            candidates = [
                f"card_e/nhanvat/40npc2k/{char_name}.png",
                f"card_e/nhanvat/{char_name}.png",
                f"card_e/nhanvat/pbdoi/{char_name}.png"
            ]
        elif mode == "standalone":
            candidates = [
                f"card_e/nhanvat/{char_name}.png",
                f"card_e/nhanvat/40npc2k/{char_name}.png",
                f"card_e/nhanvat/pbdoi/{char_name}.png"
            ]
        else:
            candidates = [
                f"card_e/nhanvat/40npc2k/{char_name}.png",
                f"card_e/nhanvat/pbdoi/{char_name}.png",
                f"card_e/nhanvat/{char_name}.png"
            ]
        # Tối ưu hóa: Dùng _nhanvat_path_cache tránh đọc đĩa lặp lại (Zero Disk I/O sau lần đầu quét)
        if not hasattr(self, '_nhanvat_path_cache'):
            self._nhanvat_path_cache = {}

        app_dir = get_app_dir()
        bundle_dir = get_bundle_dir()
        for t_name in candidates:
            if t_name in self._nhanvat_path_cache:
                file_found = self._nhanvat_path_cache[t_name]
            else:
                file_found = False
                for base in [app_dir, bundle_dir]:
                    p = os.path.join(base, "assets", t_name)
                    if os.path.exists(p) and os.path.isfile(p):
                        file_found = True
                        break
                self._nhanvat_path_cache[t_name] = file_found

            if file_found:
                x, y = self._find_template_on_screen(dnconsole_path, tab_index, t_name, threshold=threshold, region=region)
                if x is not None and y is not None:
                    return x, y
        return None, None

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: CARD A (BOSS THẾ GIỚI)
    # =========================================================================
    def _run_boss_safezone(self, dnconsole_path: str, tab_index: str):
        """PHẦN 1: QUY TRÌNH VỀ KHU AN TOÀN CỦA BOSS THẾ GIỚI"""
        self._run_common_safezone(dnconsole_path, tab_index, card_tag="Card A: Boss Thế Giới", stop_check=self._should_stop_card_A)

    def _run_boss_pre_move(self, dnconsole_path: str, tab_index: str) -> bool:
        """3.1. Thao tác qua bảng Sự Kiện (_run_boss_pre_move): Sau 12h trưa mới kích hoạt"""
        if self._should_stop_card_A(): return False

        now_dt = datetime.now()
        if now_dt.hour < 12:
            self.after(0, self.log_info, f"ℹ️ [Boss - 3.1 Sự Kiện] Hiện tại {now_dt.strftime('%H:%M:%S')} (trước 12h trưa) ➔ Bỏ qua thao tác bảng Sự Kiện.")
            return False

        self.after(0, self.log_info, "👁️ [Boss - 3.1 Sự Kiện] Mở Sự Kiện: Quét tìm 'card_a/a_sukien.png'...")
        if not self._tap_menu_utility_icon(dnconsole_path, tab_index, 1213, 648, "card_a/a_sukien.png", item_label="Sự Kiện", stop_check=self._should_stop_card_A):
            return False

        if self._should_stop_card_A(): return False
        self.after(0, self.log_info, "👁️ [Boss - 3.1 Sự Kiện] Chọn Boss Thế Giới: Quét tìm 'card_a/a_skboss.png' (85%, ROI 155,95,305,625)...")
        skb_x, skb_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_skboss.png", threshold=0.85, region=(155, 95, 305, 625))
        if skb_x is not None and skb_y is not None:
            self.after(0, self.log_info, f"🎯 Phát hiện 'card_a/a_skboss.png' tại ({skb_x}, {skb_y})! Tap chọn")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {skb_x} {skb_y}"])
            time.sleep(0.5)
        else:
            self.after(0, self.log_info, "ℹ️ Không tìm thấy 'card_a/a_skboss.png' ➔ Bỏ qua.")

        if self._should_stop_card_A(): return False
        self.after(0, self.log_info, "👉 [Card A - Boss - 3.1 Sự Kiện] Tap tọa độ (975, 475) ➔ Hoãn 2.0s dịch chuyển map...")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 975 475"])
        if self._sleep_with_stop_check(2.0, check_active=lambda: not self._should_stop_card_A()):
            return False
        return True

    def _run_boss_move_manual(self, dnconsole_path: str, tab_index: str):
        """3.2. Di chuyển bộ D-Pad (_run_boss_move_manual): Trước 12h trưa mới kích hoạt"""
        if self._should_stop_card_A(): return
        now_dt = datetime.now()
        if now_dt.hour >= 12:
            self.after(0, self.log_info, f"ℹ️ [Boss - 3.2 D-Pad] Hiện tại {now_dt.strftime('%H:%M:%S')} (sau 12h trưa) ➔ Bỏ qua di chuyển bộ D-Pad.")
            return

        self.after(0, self.log_info, "🚀 [Boss - Giai Đoạn 3.2] Bắt đầu Di chuyển bộ D-Pad (trước 12h trưa)...")

        # Bước 3.2.1: Kéo Joystick hướng Chéo Phải - Trên (UP_RIGHT / W+D) liên tục trong 3.0s (640,360 ➔ 890,110). Nghỉ 0.3s.
        if self._should_stop_card_A(): return
        self.after(0, self.log_info, "🕹️ [Boss - Bước 3.2.1] Kéo Joystick hướng Chéo Phải - Trên (UP_RIGHT / W+D) liên tục trong 3.0s (640,360 ➔ 890,110)...")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 110 3000"])
        if self._should_stop_card_A(): return
        time.sleep(0.3)

        # Bước 3.2.2: Kéo Joystick hướng Phải (RIGHT / D) liên tục trong 5.5s (640,360 ➔ 890,360). Nghỉ 0.3s.
        if self._should_stop_card_A(): return
        self.after(0, self.log_info, "🕹️ [Boss - Bước 3.2.2] Kéo Joystick hướng Phải (RIGHT / D) liên tục trong 5.5s (640,360 ➔ 890,360)...")
        self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 360 5500"])
        if self._should_stop_card_A(): return
        time.sleep(0.3)

    def _run_boss_workflow(self, dnconsole_path: str, tab_name: str, tab_index: str, max_turns: int = 5, skip_move: bool = False):
        """QUY TRÌNH THỰC THI THAO TÁC ĐÁNH BOSS THẾ GIỚI (Về Khu An Toàn ➔ Sự Kiện / Di Chuyển ➔ Đánh Boss với số lượt max_turns)"""
        if self._should_stop_card_A(): return

        if not skip_move:
            self._run_boss_safezone(dnconsole_path, tab_index)
            skip_di_chuyen = self._run_boss_pre_move(dnconsole_path, tab_index)

            if not skip_di_chuyen:
                self._run_boss_move_manual(dnconsole_path, tab_index)
        else:
            self.after(0, self.log_info, "ℹ️ [Boss] Đã ở vị trí Boss / Đã hoàn thành di chuyển ➔ Tiến thẳng vào quy trình Đánh Boss...")

        # 📌 PHẦN 4: ĐÁNH BOSS THẾ GIỚI - QUY TRÌNH "BOSS"
        self.after(0, self.log_info, f"🔄 [Boss] Bắt đầu thực thi {max_turns} lượt đánh...")
        for turn in range(1, max_turns + 1):
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"🔄 [Boss - Lượt {turn}/{max_turns}] Đang thực thi lượt {turn}...")

            # [Bước 2 của Lượt] - Tìm Boss:
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"👁️ [Lượt {turn} - Bước 2] Click liên tục (1240, 605) tìm ảnh Boss 'card_a/a_boss.png' (85%, ROI 735,405,1280,720)...")
            boss_x, boss_y = None, None
            for click_idx in range(20):
                if self._should_stop_card_A(): break
                boss_x, boss_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_boss.png", threshold=0.85, region=(735, 405, 1280, 720))
                if boss_x is not None and boss_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện ảnh 'card_a/a_boss.png' tại ({boss_x}, {boss_y})! Dừng click (1240, 605).")
                    break
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1240 605"])
                time.sleep(0.4)

            if self._should_stop_card_A(): return
            if boss_x is None or boss_y is None:
                self.after(0, self.log_info, f"⚠️ [Lượt {turn} - Bước 2] Sau 20 lần click không thấy 'card_a/a_boss.png' ➔ Chạy lại Về Khu An Toàn & Di chuyển...")
                self._run_boss_safezone(dnconsole_path, tab_index)
                skip_fallback = self._run_boss_pre_move(dnconsole_path, tab_index)
                if not skip_fallback:
                    self._run_boss_move_manual(dnconsole_path, tab_index)

            if self._should_stop_card_A(): return

            # [Bước 3 của Lượt] - Đặt vị trí đánh:
            self.after(0, self.log_info, f"👉 [Lượt {turn} - Bước 3] Click (1160, 570)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1160 570"])
            time.sleep(0.4)

            if self._should_stop_card_A(): return
            hl_x, hl_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_hetluot.png", threshold=0.85, region=(275, 540, 1150, 670))
            if hl_x is not None and hl_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_a/a_hetluot.png' tại ({hl_x}, {hl_y})! Đã HẾT LƯỢT ➔ Tap vào vị trí ảnh ➔ Hoãn 0.4s & Dừng quy trình đánh Boss.")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {hl_x} {hl_y}"])
                time.sleep(0.4)
                break
            else:
                self.after(0, self.log_info, "ℹ️ Không thấy 'card_a/a_hetluot.png' ➔ Tap (500, 635)")
                if self._should_stop_card_A(): return
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 500 635"])
                time.sleep(0.4)

            # [Bước 4 của Lượt] - Bắt đầu chiến đấu & Quét card_f/f_vaotran.png:
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"⏳ [Lượt {turn}/{max_turns} - Bước 4] Hoãn 2.0s trước khi click vào trận (185, 145)...")
            if self._sleep_with_stop_check(2.0, check_active=lambda: not self._should_stop_card_A()): return

            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"👉 [Lượt {turn}/{max_turns} - Bước 4] Click (185, 145) vào trận ➔ Hoãn 45s trước khi quét...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 185 145"])
            if self._sleep_with_stop_check(45.0, check_active=lambda: not self._should_stop_card_A()): return

            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"👁️ [Lượt {turn}/{max_turns} - Bước 4] Đã hoãn 45s ➔ Quét tìm ảnh 'card_f/f_vaotran.png' (80%, ROI: 1215, 0, 1280, 45) mỗi 2.0s cho đến khi xuất hiện...")
            while not self._should_stop_card_A():
                vt_x, vt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                if vt_x is not None and vt_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_f/f_vaotran.png' tại ({vt_x}, {vt_y})! Hoàn thành lượt đánh {turn}.")
                    break
                if self._sleep_with_stop_check(2.0, check_active=lambda: not self._should_stop_card_A()):
                    break

    def _run_boss_ve_process(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """THAO TÁC TÌM & DÙNG VÉ BOSS (CHỈ CHẠY SAU 12H TRƯA, TỰ ĐỘNG LẶP CHO TỚI KHÔNG CÒN VÉ)"""
        ve_count = 0
        while not self._should_stop_card_A():
            ve_count += 1
            self.after(0, self.log_info, f"🎫 [Vé Boss - Lượt {ve_count}] Bắt đầu quy trình kiểm tra & dùng Vé Boss...")

            # 1. Quét tap login_x.png (75%, ROI 990,50,1165,200) đóng thông báo
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, "👁️ [Vé - Bước 1] Quét tìm nút 'card_top/login/login_x.png' (ROI 990,50,1165,200)...")
            self._close_login_x_popup(dnconsole_path, tab_index, "Vé Boss")

            # 2. Quét tap nút Túi card_a/a_tui.png (85%, ROI 735,405,1280,720) ➔ Hoãn 0.4s
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, "👁️ [Vé - Bước 2] Quét nút Túi 'card_a/a_tui.png' (85%, ROI 735,405,1280,720)...")
            tui_x, tui_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_tui.png", threshold=0.85, region=(735, 405, 1280, 720))
            if tui_x is not None and tui_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện Túi tại ({tui_x}, {tui_y})! Tap")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tui_x} {tui_y}"])
                time.sleep(0.4)
            else:
                self.after(0, self.log_info, "⚠️ Chưa thấy ảnh 'card_a/a_tui.png' trên màn hình.")

            # 3. Cuộn tìm Vé Boss trong Túi:
            # - Vuốt xuống: Swipe (920, 480 ➔ 920, 230 1000ms) tối đa 5 lần (dừng nếu tìm thấy a_veboss.png hoặc phát hiện a_khoa.png).
            # - Vuốt ngược lên: Swipe (920, 330 ➔ 920, 580 1200ms) tối đa 3 lần nếu chưa thấy vé.
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, "📜 [Vé - Bước 3] Cuộn tìm ảnh Vé Boss 'card_a/a_veboss.png' (70%, ROI 745,230,1095,580)...")
            veboss_x, veboss_y = None, None

            for swipe_down_cnt in range(5):
                if self._should_stop_card_A(): break
                veboss_x, veboss_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_veboss.png", threshold=0.70, region=(745, 230, 1095, 580))
                if veboss_x is not None and veboss_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_a/a_veboss.png' tại ({veboss_x}, {veboss_y})!")
                    break
                khoa_x, khoa_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_khoa.png", threshold=0.85, region=(745, 230, 1095, 580))
                if khoa_x is not None and khoa_y is not None:
                    self.after(0, self.log_info, f"🔒 Phát hiện 'card_a/a_khoa.png' tại ({khoa_x}, {khoa_y}) nhưng chưa thấy Vé Boss ➔ Dừng cuộn xuống, chuyển sang cuộn ngược lên...")
                    break
                self.after(0, self.log_info, f"📜 [Vé - Vuốt xuống {swipe_down_cnt+1}/5] Swipe (920, 480 ➔ 920, 230 1000ms)...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 920 480 920 230 1000"])
                time.sleep(1.0)

            if veboss_x is None or veboss_y is None:
                self.after(0, self.log_info, "📜 [Vé - Cuộn ngược lên] Bắt đầu cuộn ngược lên tìm Vé Boss...")
                for swipe_up_cnt in range(3):
                    if self._should_stop_card_A(): break
                    veboss_x, veboss_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_a/a_veboss.png", threshold=0.70, region=(745, 230, 1095, 580))
                    if veboss_x is not None and veboss_y is not None:
                        self.after(0, self.log_info, f"🎯 Phát hiện 'card_a/a_veboss.png' tại ({veboss_x}, {veboss_y})!")
                        break
                    self.after(0, self.log_info, f"📜 [Vé - Vuốt ngược lên {swipe_up_cnt+1}/3] Swipe (920, 330 ➔ 920, 580 1200ms)...")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 920 330 920 580 1200"])
                    time.sleep(1.0)

            # Nếu không tìm thấy vé ➔ Đóng túi và kết thúc vòng lặp dùng vé
            if veboss_x is None or veboss_y is None:
                self.after(0, self.log_info, "ℹ️ [Vé] Đã cuộn tối đa số lần trong túi và không còn phát hiện Vé Boss ➔ Tap 'login_x.png' đóng Túi ➔ Hoàn thành quy trình Vé Boss!")
                if self._should_stop_card_A(): return
                lx_x2, lx_y2 = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_x.png", threshold=0.75, region=(990, 50, 1165, 200))
                if lx_x2 is not None and lx_y2 is not None:
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {lx_x2} {lx_y2}"])
                    time.sleep(0.4)
                break

            # 4. Tap ảnh Vé Boss a_veboss.png ➔ Tap (755, 460) ➔ Tap (320, 25) (Hoãn 0.4s mỗi tap).
            if self._should_stop_card_A(): return
            self.after(0, self.log_info, f"👉 Tap chọn Vé Boss tại ({veboss_x}, {veboss_y}) ➔ Tap (755, 460) ➔ Tap (320, 25) (Hoãn 0.4s)...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {veboss_x} {veboss_y}"])
            time.sleep(0.4)
            if self._should_stop_card_A(): return
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 755 460"])
            time.sleep(0.4)
            if self._should_stop_card_A(): return
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 320 25"])
            time.sleep(0.4)

            # 5. Quét tap login_x.png đóng bảng Túi ➔ Hoãn 0.4s.
            if self._should_stop_card_A(): return
            lx_x2, lx_y2 = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_x.png", threshold=0.75, region=(990, 50, 1165, 200))
            if lx_x2 is not None and lx_y2 is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_top/login/login_x.png' tại ({lx_x2}, {lx_y2})! Tap đóng Túi")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {lx_x2} {lx_y2}"])
                time.sleep(0.4)

            # Thực thi đánh Boss bằng vé:
            # Thống nhất tất cả các lượt vé: Nhân vật đã đứng sẵn trước Boss nên bỏ qua di chuyển, tiến thẳng vào trận đánh 1 lượt
            self.after(0, self.log_info, f"🚀 [Vé - Lượt {ve_count}] Đã đứng sẵn trước Boss ➔ Bỏ qua di chuyển, tiến thẳng vào trận đánh 1 lượt...")
            self._run_boss_workflow(dnconsole_path, tab_name, tab_index, max_turns=1, skip_move=True)

    def _execute_card_A_boss_tg(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Thực thi Card A: BOSS THẾ GIỚI"""
        if self._should_stop_card_A():
            self.after(0, self.log_info, "ℹ️ [CARD A: BOSS THẾ GIỚI] Công tắc ON/OFF đang TẮT -> Bỏ qua.")
            return

        if not self.var_A1.get():
            self.after(0, self.log_info, "ℹ️ [CARD A: BOSS THẾ GIỚI] Ô 'Boss' KHÔNG được tích -> Bỏ qua.")
            self.after(0, lambda: self.var_switch_A.set(False))
            self.after(0, self.save_config)
            return

        selected_char = self.combo_A_char.get() if hasattr(self, 'combo_A_char') else "Xuất Chiến"

        # =========================================================================
        # 📌 1. VỀ KHU AN TOÀN (_run_boss_safezone)
        # =========================================================================
        if self._should_stop_card_A(): return
        self._run_boss_safezone(dnconsole_path, tab_index)

        # =========================================================================
        # 📌 2. CHUYỂN ĐỔI VỊ TRÍ NHÂN VẬT
        # =========================================================================
        if self._should_stop_card_A(): return
        self._switch_card_char_position(dnconsole_path, tab_index, selected_char, mode_label="Boss Thế Giới", card_prefix="A")

        # =========================================================================
        # 📌 3. SỰ KIỆN BOSS & DI CHUYỂN BỘ
        # =========================================================================
        if self._should_stop_card_A(): return
        skip_di_chuyen = self._run_boss_pre_move(dnconsole_path, tab_index)
        if not skip_di_chuyen:
            self._run_boss_move_manual(dnconsole_path, tab_index)

        # =========================================================================
        # 📌 4. ĐÁNH BOSS 5 LƯỢT CHÍNH (Khi ô Boss được tích)
        # =========================================================================
        if self._should_stop_card_A(): return
        self.after(0, self.log_info, "🚀 [Boss Thế Giới] Khởi chạy quy trình Boss (5 lượt chính)...")
        self._run_boss_workflow(dnconsole_path, tab_name, tab_index, max_turns=5, skip_move=True)

        # =========================================================================
        # 📌 5. THỰC THI VÉ BOSS (CHỈ CHẠY SAU 12H TRƯA)
        # =========================================================================
        if self._should_stop_card_A(): return
        now_dt = datetime.now()
        if now_dt.hour < 12:
            self.after(0, self.log_info, f"ℹ️ [Vé Boss] Hiện tại là {now_dt.strftime('%H:%M:%S')} (trước 12h trưa) ➔ Thao tác Vé Boss chỉ hoạt động sau 12h trưa ➔ Bỏ qua.")
        else:
            self.after(0, self.log_info, "🚀 [Vé Boss] Hiện tại đã sau 12h trưa ➔ Bắt đầu quy trình tự động quét & dùng Vé Boss...")
            self._run_boss_ve_process(dnconsole_path, tab_name, tab_index)

        # ---------------- 6. TỰ ĐỘNG TẮT CÔNG TẮC & LƯU CẤU HÌNH ----------------
        self.after(0, lambda: self.var_switch_A.set(False))
        self.after(0, self.save_config)
        self.after(0, self.log_info, "✅ [CARD A: BOSS THẾ GIỚI] Đã thực thi hoàn tất quy trình! (Tự động tắt công tắc ON/OFF & giữ nguyên các ô tích)")

    # =========================================================================
    # 🔓 [ĐÃ MỞ KHÓA TOÀN DIỆN - SẴN SÀNG SỬ DỤNG]: CARD D (40 NPC / NHỊ KIỀU)
    # =========================================================================
    def _run_40_npc_team_and_char_position(self, dnconsole_path: str, tab_index: str, selected_team_char: str, skip_char_change: bool = False):
        """CHUYỂN ĐỔI VỊ TRÍ NHÂN VẬT CHO CARD D (40 NPC / NHỊ KIỀU) - HOẠT ĐỘNG ĐỘC LẬP VỚI Ô TỔ ĐỘI"""
        if self._should_stop_card_D(): return

        if skip_char_change or selected_team_char == "Xuất Chiến":
            self.after(0, self.log_info, "ℹ️ [Card D - Đổi Vị Trí] Giữ nguyên vị trí nhân vật hiện tại ('Xuất Chiến') ➔ Bỏ qua bước đổi đội hình.")
            return

        self.after(0, self.log_info, f"🚀 [Card D - Đổi Vị Trí] Kích hoạt chuyển đổi vị trí: '{selected_team_char}'...")
        self._switch_card_char_position(dnconsole_path, tab_index, selected_team_char, mode_label="Card D - 40 NPC", card_prefix="D")

    def _assign_quan_su_when_panel_opened(self, dnconsole_path: str, tab_index: str, quan_su_char: str, log_tag: str = "Quân Sư", stop_check=None) -> bool:
        """
        Thao tác quét và tap nút Quân Sư (960, qs_y + 40) khi giao diện Đội ĐÃ ĐƯỢC MỞ SẴN.
        Tối ưu siêu tốc: Tái sử dụng tọa độ đã quét trong _scan_team_members_presence (Zero Latency hit).
        Trả về True nếu gán thành công, False nếu không tìm thấy ảnh tướng hoặc bị hủy.
        """
        if stop_check is None:
            stop_check = self._should_stop_card_D
        if stop_check() or not quan_su_char or quan_su_char == "(Trống)":
            return False

        # 1. Tận dụng tọa độ cache tức thời nếu vừa quét trong bảng Đội gần nhất
        cached_coords = getattr(self, '_last_team_member_coords', {}).get(quan_su_char)
        if cached_coords is not None:
            qs_x, qs_y = cached_coords
            self.after(0, self.log_info, f"👑 [{log_tag}] Tọa độ Quân Sư '{quan_su_char}' đã nhận diện tức thời tại ({qs_x}, {qs_y}) ➔ Gán ngay!")
        else:
            self.after(0, self.log_info, f"👑 [{log_tag}] Quét nhận diện nhân vật Quân Sư '{quan_su_char}' (ROI 305, 150, 1105, 625)...")
            qs_x, qs_y = self._find_nhanvat_template(dnconsole_path, tab_index, quan_su_char, threshold=0.80, region=(305, 150, 1105, 625), mode="40npc")

        if qs_x is not None and qs_y is not None:
            qs_btn_x = 960
            qs_btn_y = qs_y + 40
            self.after(0, self.log_info, f"🎯 [{log_tag}] Phát hiện '{quan_su_char}' tại ({qs_x}, {qs_y}) ➔ Tap nút Quân Sư ({qs_btn_x}, {qs_btn_y})")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {qs_btn_x} {qs_btn_y}"])
            if hasattr(self, '_sleep_card_D'):
                self._sleep_card_D(0.35)
            else:
                time.sleep(0.35)
            return True
        else:
            self.after(0, self.log_info, f"⚠️ [{log_tag}] Chưa quét thấy ảnh nhân vật Quân Sư '{quan_su_char}' trên màn hình Đội.")
            return False

    def _scan_team_members_presence(self, dnconsole_path: str, tab_index: str, list_B: list, stop_check=None, mode: str = "40npc") -> tuple:
        """
        Hàm dùng chung quét nhận diện độ đầy đủ thành viên Danh Sách B trong giao diện Đội.
        Lưu cache tọa độ các thành viên vào self._last_team_member_coords để gán Quân Sư tức thời.
        Trả về tuple chuẩn: (present_members: list, missing_members: list, target_count: int)
        """
        if stop_check is None:
            stop_check = self._should_stop_card_D

        present_members = []
        missing_members = []
        member_coords = {}
        target_count = min(4, len(list_B))

        for char_name in list_B:
            if stop_check():
                break
            chk_x, chk_y = self._find_nhanvat_template(
                dnconsole_path, tab_index, char_name,
                threshold=0.80, region=(305, 150, 1105, 625), mode=mode
            )
            if chk_x is not None and chk_y is not None:
                present_members.append(char_name)
                member_coords[char_name] = (chk_x, chk_y)
            else:
                missing_members.append(char_name)

        self._last_team_member_coords = member_coords
        return present_members, missing_members, target_count

    def _invite_missing_members_when_panel_opened(
        self, dnconsole_path: str, tab_index: str, missing_members: list, 
        log_tag: str = "Tổ Đội", stop_check=None
    ) -> bool:
        """
        Thao tác mời thành viên còn thiếu ngay khi giao diện Đội ĐÃ ĐƯỢC MỞ SẴN:
        1. Tap 'e_nguoi.png' mở danh sách bạn bè / xung quanh (vòng quét thử 2 lần chống lag).
        2. Quét màn hình hiện tại mời các acc trong missing_members.
        3. Vuốt thông minh xuống tối đa 4 lần (tối ưu swipe 300ms, hoãn 1.5s).
        4. Vuốt thông minh lên 2 lần duy nhất (tối ưu swipe 200ms, không hoãn) đưa về đầu trang nếu cần.
        5. Nghỉ 1.5s chờ người chơi vào đội.
        6. Tap 'e_doingu.png' quay lại bảng Đội Ngũ (vòng quét thử 2 lần).
        Trả về True nếu đã hoàn tất quy trình mời, False nếu bị dừng.
        """
        if stop_check is None:
            stop_check = self._should_stop_card_D
        if stop_check() or not missing_members:
            return False

        self.after(0, self.log_info, f"⚠️ [{log_tag}] Đội chưa đủ người ➔ Tiến hành mở danh sách mời ({len(missing_members)} thành viên thiếu: {', '.join(missing_members)})...")

        # 1. Mở danh sách Mời bạn bè: Quét tìm ảnh / tap card_e/e_nguoi.png (85%, ROI 175, 165, 295, 455)
        if stop_check(): return False
        nguoi_x, nguoi_y = None, None
        for _ in range(2):
            if stop_check(): return False
            nguoi_x, nguoi_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_e/e_nguoi.png", threshold=0.85, region=(175, 165, 295, 455))
            if nguoi_x is not None and nguoi_y is not None:
                break
            time.sleep(0.3)

        if nguoi_x is not None and nguoi_y is not None:
            self.after(0, self.log_info, f"🎯 [{log_tag}] Phát hiện icon Bạn Bè 'e_nguoi.png' tại ({nguoi_x}, {nguoi_y}) ➔ Tap mở danh sách mời...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {nguoi_x} {nguoi_y}"])
            time.sleep(0.35)
        else:
            self.after(0, self.log_info, f"⚠️ [{log_tag}] Chưa quét thấy icon 'e_nguoi.png' trên màn hình.")
            time.sleep(0.35)

        still_missing = list(missing_members)

        def scan_and_invite_current_screen(missing_tracker: list, step_tag: str = "Quét") -> list:
            invited_chars = []
            for char_name in list(missing_tracker):
                if stop_check(): break
                found_char_x, found_char_y = self._find_nhanvat_template(
                    dnconsole_path, tab_index, char_name, threshold=0.80, region=(305, 150, 1105, 625), mode="40npc"
                )
                if found_char_x is not None and found_char_y is not None:
                    invite_x = 995
                    invite_y = found_char_y
                    self.after(0, self.log_info, f"🎯 [{log_tag} - {step_tag}] Phát hiện '{char_name}' tại ({found_char_x}, {found_char_y}) ➔ Tap Mời ({invite_x}, {invite_y})")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {invite_x} {invite_y}"])
                    time.sleep(0.35)
                    invited_chars.append(char_name)
            for c in invited_chars:
                if c in missing_tracker:
                    missing_tracker.remove(c)
            return missing_tracker

        # 2. Quét tìm ngay trên màn hình hiện tại (trước khi vuốt)
        if stop_check(): return False
        self.after(0, self.log_info, f"👁️ [{log_tag}] Quét màn hình hiện tại tìm: {', '.join(still_missing)}...")
        still_missing = scan_and_invite_current_screen(still_missing, step_tag="Hiện Tại")
        if not still_missing:
            self.after(0, self.log_info, f"✅ [{log_tag}] Đã mời xong toàn bộ thành viên còn thiếu trên màn hình hiện tại!")

        # 3. Cuộn danh sách xuống (Vuốt thông minh 300ms, hoãn 1.5s, lặp tối đa 4 lần)
        if still_missing:
            for swipe_down_cnt in range(4):
                if stop_check() or not still_missing: break
                self.after(0, self.log_info, f"📜 [{log_tag} - Vuốt xuống {swipe_down_cnt+1}/4] Cuộn danh sách tìm: {', '.join(still_missing)} (hoãn 1.5s)...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 795 400 795 205 300"])
                time.sleep(1.5)
                still_missing = scan_and_invite_current_screen(still_missing, step_tag=f"Xuống {swipe_down_cnt+1}")
            if not still_missing:
                self.after(0, self.log_info, f"✅ [{log_tag}] Đã tìm và bấm Mời đầy đủ các nhân vật còn thiếu ➔ Dừng vuốt xuống sớm!")

        # 4. Cuộn danh sách lên trả về đầu trang (2 lần duy nhất, swipe 200ms, không hoãn)
        if still_missing:
            self.after(0, self.log_info, f"⚠️ [{log_tag}] Sau 4 lần vuốt xuống vẫn còn thiếu ({', '.join(still_missing)}) ➔ Vuốt lên 2 lần trả về đầu trang (200ms, không hoãn)...")
            for up_idx in range(2):
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 795 205 795 575 200"])
            still_missing = scan_and_invite_current_screen(still_missing, step_tag="Đầu Trang")
            if not still_missing:
                self.after(0, self.log_info, f"✅ [{log_tag}] Đã tìm và bấm Mời đầy đủ các nhân vật còn thiếu!")

        # 5. Chờ người vào đội:
        if stop_check(): return False
        self.after(0, self.log_info, f"⏳ [{log_tag}] Đã bấm Mời các thành viên ➔ Hoãn 1.5s chờ người chơi vào đội...")
        if hasattr(self, '_sleep_card_D'):
            if self._sleep_card_D(1.5): return False
        else:
            time.sleep(1.5)

        # 6. Quét tìm & tap ảnh 'card_e/e_doingu.png' (85%, ROI 175, 165, 295, 455)
        if stop_check(): return False
        self.after(0, self.log_info, f"👁️ [{log_tag}] Quét tìm & tap 'card_e/e_doingu.png' (85%) chuyển về bảng Đội Ngũ...")
        for _ in range(2):
            if stop_check(): return False
            dn_x, dn_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_e/e_doingu.png", threshold=0.85, region=(175, 165, 295, 455))
            if dn_x is not None and dn_y is not None:
                self.after(0, self.log_info, f"🎯 [{log_tag}] Phát hiện 'card_e/e_doingu.png' tại ({dn_x}, {dn_y})! Tap chuyển về bảng Đội Ngũ...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {dn_x} {dn_y}"])
                time.sleep(0.35)
                break
            time.sleep(0.3)
        return True

    def _execute_card_d_buff_cycle_auto(self, dnconsole_path: str, tab_index: str, log_tag: str = "Nhị Kiều Auto", active_skill: str = "Buff HP / SP", is_mid_battle: bool = False):
        """Wrapper tương thích: Chuyển tiếp sang _execute_card_d_buff_cycle với is_auto_mode=True.
        Chuyên dụng cho Nhị Kiều Đỉnh 10 & Nhận Đội — tái sử dụng toàn bộ logic từ hàm thống nhất."""
        return self._execute_card_d_buff_cycle(
            dnconsole_path, tab_index,
            log_tag=log_tag, is_nhi_kieu=True,
            active_skill=active_skill,
            is_auto_mode=True,
            is_mid_battle=is_mid_battle
        )

    def _wait_enter_battle_auto(self, dnconsole_path: str, tab_index: str, log_tag: str, active_skill: str, is_mid_battle: bool = False) -> str:
        """
        Bước đệm chờ vào trận chuyên biệt cho chế độ Auto / Nhận Đội:
        - Nếu is_mid_battle=True: Đang giữa trận đổi chiêu ➔ Bỏ qua bước đệm, vào thẳng trận.
        - Nếu is_mid_battle=False: Bắt đầu trận mới ngoài map ➔ Bắt buộc chờ 'card_f/f_vaotran.png' biến mất (vào trận).
        Trả về:
        - 'ENTERED': Đã vào trận đấu thành công
        - 'SWITCH_SKILL': Người dùng đổi kỹ năng trong lúc chờ vào trận
        - 'STOP': Người dùng ngắt hoặc tạm dừng
        """
        if is_mid_battle:
            return "ENTERED"
        if self._should_stop_card_D():
            return "STOP"

        self.after(0, self.log_info, f"⏳ [{log_tag} - Chờ Vào Trận] Chờ 'card_f/f_vaotran.png' (80%, ROI 1215,0,1280,45) biến mất để vào trận...")
        while not self._should_stop_card_D():
            if active_skill and hasattr(self, 'var_D_skill') and self.var_D_skill.get() != active_skill:
                return "SWITCH_SKILL"
            vt_x, vt_y = self._find_template_on_screen(
                dnconsole_path, tab_index, "card_f/f_vaotran.png",
                threshold=0.80, region=(1215, 0, 1280, 45)
            )
            if vt_x is None or vt_y is None:
                self.after(0, self.log_info, f"⚔️ [{log_tag}] 'card_f/f_vaotran.png' đã biến mất ➔ Đã chính thức vào trận đấu!")
                return "ENTERED"
            if self._sleep_card_D(0.5):
                return "STOP"
        return "STOP"



    def _execute_card_d_defense_cycle_core(self, dnconsole_path: str, tab_index: str, skill_name: str, skill_template: str, log_tag: str, is_nhi_kieu: bool = False, is_auto_mode: bool = False, active_skill: str = None, is_mid_battle: bool = False):
        """
        Chuỗi kỹ năng Phòng Thủ (Linh Kính / Kết Giới) chuẩn Chế Độ TEAM áp dụng trong Card D:
        - Sử dụng thứ tự mục tiêu TEAM chuẩn (Mục tiêu 3 đầu tiên khi vào trận, sau đó lần lượt 1 - 2 - 4 - 5):
            Index 0: Mục tiêu 3 -> (905, 515) (Đầu trận)
            Index 1: Mục tiêu 1 -> (1065, 435)
            Index 2: Mục tiêu 2 -> (985, 475)
            Index 3: Mục tiêu 4 -> (825, 555)
            Index 4: Mục tiêu 5 -> (745, 595)
        - is_auto_mode = True: Chế độ Auto (dùng ở Đỉnh 10 Nhị Kiều & Nhận Đội): có bước đệm chờ f_vaotran biến mất, hết trận khi f_vaotran xuất hiện lại.
        - is_auto_mode = False: Chế độ Thường (dùng ở 40 NPC & leo đài Nhị Kiều): nhận diện lượt bằng f_dung, hết trận bằng d_xacdinh (40 NPC) hoặc d_hoanthanh (Nhị Kiều).
        """
        if self._should_stop_card_D(): return

        if active_skill is None:
            active_skill = skill_name

        # 1. BƯỚC ĐỆM (Chỉ thực thi khi ở chế độ Auto của Nhị Kiều hoặc Nhận Đội)
        if is_auto_mode:
            step_res = self._wait_enter_battle_auto(dnconsole_path, tab_index, log_tag, active_skill, is_mid_battle=is_mid_battle)
            if step_res in ("STOP", "SWITCH_SKILL"):
                return step_res

        end_battle_img_name = "f_vaotran (xuất hiện lại)" if is_auto_mode else ("d_hoanthanh.png" if is_nhi_kieu else "d_xacdinh.png")

        def _wait_for_turn_start_defense():
            while not self._should_stop_card_D():
                # 0. Kiểm tra thay đổi kỹ năng realtime giữa trận
                if active_skill and hasattr(self, 'var_D_skill'):
                    cur_sk = self.var_D_skill.get()
                    if cur_sk != active_skill:
                        self.after(0, self.log_info, f"🔄 [{log_tag} - Realtime] Phát hiện đổi kỹ năng giữa trận: '{active_skill}' ➔ '{cur_sk}'!")
                        return "SWITCH_SKILL"

                # Kiểm tra hết trận đánh
                if is_auto_mode:
                    vt_chk_x, vt_chk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                    if vt_chk_x is not None and vt_chk_y is not None:
                        self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] 'card_f/f_vaotran.png' xuất hiện lại tại ({vt_chk_x}, {vt_chk_y}) ➔ Kết thúc trận đánh!")
                        return "END_BATTLE"
                    ht_x, ht_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/d_hoanthanh.png", threshold=0.70, region=(905, 0, 985, 70))
                    if ht_x is not None and ht_y is not None:
                        self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Phát hiện 'd_hoanthanh.png' ➔ Kết thúc trận đánh!")
                        return "END_BATTLE"
                elif is_nhi_kieu:
                    ht_x, ht_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/d_hoanthanh.png", threshold=0.70, region=(905, 0, 985, 70))
                    if ht_x is not None and ht_y is not None:
                        self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Phát hiện 'card_d/d_hoanthanh.png' ➔ Kết thúc trận đánh (Nhị Kiều)!")
                        return "END_BATTLE"
                else:
                    xd_x, xd_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_xacdinh.png", threshold=0.80, region=(275, 540, 980, 670))
                    if xd_x is not None and xd_y is not None:
                        self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Phát hiện 'card_d/40npc/d_xacdinh.png' ➔ Kết thúc trận đánh (40 NPC)!")
                        return "END_BATTLE"

                # Quét f_dung.png báo hiệu lượt mới
                dung_x, dung_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
                if dung_x is not None and dung_y is not None:
                    self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Phát hiện 'card_f/f_dung.png' tại ({dung_x}, {dung_y}) ➔ Bắt đầu lượt mới!")
                    # Quét phụ f_tieptheo.png trong 0.5s
                    start_tt = time.time()
                    tapped_tieptheo = False
                    while time.time() - start_tt < 0.5:
                        if self._should_stop_card_D(): return "END_BATTLE"
                        tt_x, tt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_tieptheo.png", threshold=0.80, region=(1050, 530, 1165, 680))
                        if tt_x is not None and tt_y is not None:
                            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tt_x} {tt_y}"])
                            time.sleep(0.3)
                            tapped_tieptheo = True
                            break
                        time.sleep(0.25)

                    if not tapped_tieptheo:
                        self.after(0, self.log_info, f"ℹ️ Không thấy 'f_tieptheo.png' trong 0.5s ➔ Chuyển sang ra chiêu {skill_name}...")
                    return "START_TURN"

                if self._sleep_card_D(0.5): return "END_BATTLE"
            return "END_BATTLE"

        # Danh sách mục tiêu Team chuẩn theo Card F
        target_list = [
            {"num": 3, "name": "Mục tiêu 3 (Đầu trận)", "coord": (905, 515)},
            {"num": 1, "name": "Mục tiêu 1", "coord": (1065, 435)},
            {"num": 2, "name": "Mục tiêu 2", "coord": (985, 475)},
            {"num": 4, "name": "Mục tiêu 4", "coord": (825, 555)},
            {"num": 5, "name": "Mục tiêu 5", "coord": (745, 595)},
        ]

        turn = 1
        curr_idx = 0
        while not self._should_stop_card_D():
            target_info = target_list[curr_idx]
            tx, ty = target_info["coord"]
            target_label = target_info["name"]

            self.after(0, self.log_info, f"🔄 [{log_tag} - {skill_name} - TEAM] [LƯỢT {turn}] [{target_label} ({tx}, {ty})] Quét f_dung (0.5s) hoặc {end_battle_img_name}...")
            if active_skill and hasattr(self, 'var_D_skill') and self.var_D_skill.get() != active_skill:
                return "SWITCH_SKILL"
            res = _wait_for_turn_start_defense()
            if res in ("END_BATTLE", "SWITCH_SKILL"):
                return res

            if self._should_stop_card_D(): return

            # Kiểm tra Thao Tác Ưu Tiên Hồi Sinh (Hồi Sinh Trọng Điểm Thông Minh >= 2 người chết)
            self.after(0, self.log_info, f"🔍 [{log_tag} - {skill_name} - TEAM] [LƯỢT {turn}] [{target_label}] Kiểm tra Thao Tác Ưu Tiên (Hồi Sinh)...")
            handled_priority = self._handle_priority_hs(dnconsole_path, "", tab_index, log_tag=f"{log_tag} - {skill_name} HS", is_card_d=True)
            if handled_priority:
                self.after(0, self.log_info, f"⭐ [{log_tag} - {skill_name} - TEAM] Đã hoàn tất Thao Tác Ưu Tiên (Hồi Sinh) trong lượt này! Giữ nguyên [LƯỢT {turn}] [{target_label}] để tiếp tục chu kỳ buff...")
                continue

            if self._should_stop_card_D(): return

            # BƯỚC 2: Nhận diện Skill & Ra Chiêu vào Mục Tiêu Đồng Đội trong Team
            self.after(0, self.log_info, f"👉 [{log_tag} - {skill_name} - TEAM] [LƯỢT {turn}] [{target_label}] BƯỚC 2: Quét tìm skill '{skill_template}' (85%, ROI 640,0,1280,145)...")
            s_x, s_y = self._find_template_on_screen(dnconsole_path, tab_index, skill_template, threshold=0.85, region=(640, 0, 1280, 145))
            if s_x is None or s_y is None:
                self.after(0, self.log_info, f"⚠️ [{log_tag} - {skill_name} - TEAM] KHÔNG thấy '{skill_template}' ➔ Tap 2 lần nút Auto (190, 140)")
                self._tap_login_auto_twice(dnconsole_path, tab_index)
                if self._sleep_card_D(5.0): return
            else:
                self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Đã thấy '{skill_template}' tại ({s_x}, {s_y}) ➔ Tap")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {s_x} {s_y}"])
                if self._sleep_card_D(0.2): return

                self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Tap {target_label} ({tx}, {ty})")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tx} {ty}"])
                if self._sleep_card_D(0.2): return

                self.after(0, self.log_info, f"🎯 [{log_tag} - {skill_name} - TEAM] Tap 2 lần nút Auto (190, 140) kết thúc lượt buff")
                self._tap_login_auto_twice(dnconsole_path, tab_index)
                if self._sleep_card_D(5.0): return

                # Đã buff thành công vào mục tiêu này ➔ Chuyển sang mục tiêu tiếp theo trong Team
                curr_idx = (curr_idx + 1) % len(target_list)
                next_target = target_list[curr_idx]
                self.after(0, self.log_info, f"✅ [{log_tag} - {skill_name} - TEAM] Đã buff xong {target_label}! Mục tiêu tiếp theo: {next_target['name']} ({next_target['coord'][0]}, {next_target['coord'][1]})...")

            turn += 1

    def _execute_card_d_danh_tay_thuong(self, dnconsole_path: str, tab_index: str, log_tag: str = "40 NPC", is_nhi_kieu: bool = False, active_skill: str = "Đánh Tay"):
        """Chế độ Đánh Tay (Thường): Người chơi tự điều khiển tay trong trận, bot chờ quét ảnh kết thúc trận rồi đi tiếp"""
        if self._should_stop_card_D(): return "STOP"
        self.after(0, self.log_info, f"⚔️ [{log_tag} - Đánh Tay] Đã vào trận đấu! Chờ người chơi tự đánh tay (Bot KHÔNG bấm skill)...")
        while not self._should_stop_card_D():
            # Kiểm tra thay đổi kỹ năng realtime giữa trận
            if active_skill and hasattr(self, 'var_D_skill'):
                cur_sk = self.var_D_skill.get()
                if cur_sk != active_skill:
                    self.after(0, self.log_info, f"🔄 [{log_tag} - Realtime] Phát hiện đổi kỹ năng giữa trận: '{active_skill}' ➔ '{cur_sk}'!")
                    return "SWITCH_SKILL"

            if is_nhi_kieu:
                ht_x, ht_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/d_hoanthanh.png", threshold=0.70, region=(905, 0, 985, 70))
                if ht_x is not None and ht_y is not None:
                    self.after(0, self.log_info, f"🎯 [{log_tag} - Đánh Tay] Phát hiện 'card_d/d_hoanthanh.png' tại ({ht_x}, {ht_y}) ➔ Kết thúc trận đánh!")
                    return "END_BATTLE"
            else:
                xd_x, xd_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_xacdinh.png", threshold=0.80, region=(275, 540, 980, 670))
                if xd_x is not None and xd_y is not None:
                    self.after(0, self.log_info, f"🎯 [{log_tag} - Đánh Tay] Phát hiện 'card_d/40npc/d_xacdinh.png' tại ({xd_x}, {xd_y}) ➔ Kết thúc trận đánh!")
                    return "END_BATTLE"
            if self._sleep_card_D(0.5): return "STOP"
        return "STOP"

    def _execute_card_d_danh_tay_auto(self, dnconsole_path: str, tab_index: str, log_tag: str = "Nhị Kiều Auto", active_skill: str = "Đánh Tay", is_mid_battle: bool = False):
        """Chế độ Đánh Tay (Nhị Kiều Auto - Đỉnh Tháp 10): Chờ người chơi tự đánh tay và quét d_hoanthanh.png kết thúc trận"""
        if self._should_stop_card_D(): return "STOP"

        # Bước đệm: Chờ f_vaotran.png biến mất hoàn toàn
        step_res = self._wait_enter_battle_auto(dnconsole_path, tab_index, log_tag, active_skill, is_mid_battle=is_mid_battle)
        if step_res in ("STOP", "SWITCH_SKILL"):
            return step_res

        self.after(0, self.log_info, f"⚔️ [{log_tag} - Đánh Tay] Đang trong trận đấu! Chờ người chơi tự đánh tay (Bot KHÔNG bấm skill)...")
        while not self._should_stop_card_D():
            # Kiểm tra thay đổi kỹ năng realtime giữa trận
            if active_skill and hasattr(self, 'var_D_skill'):
                cur_sk = self.var_D_skill.get()
                if cur_sk != active_skill:
                    self.after(0, self.log_info, f"🔄 [{log_tag} - Realtime] Phát hiện đổi kỹ năng giữa trận: '{active_skill}' ➔ '{cur_sk}'!")
                    return "SWITCH_SKILL"

            ht_x, ht_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/d_hoanthanh.png", threshold=0.70, region=(905, 0, 985, 70))
            if ht_x is not None and ht_y is not None:
                self.after(0, self.log_info, f"🎯 [{log_tag} - Đánh Tay] Phát hiện 'card_d/d_hoanthanh.png' ➔ Kết thúc trận đánh!")
                return "END_BATTLE"
            if self._sleep_card_D(0.5): return "STOP"
        return "STOP"

    def _execute_card_d_skill_thuong(self, dnconsole_path: str, tab_index: str, log_tag: str = "40 NPC", is_nhi_kieu: bool = False):
        """Hàm điều phối Kỹ Năng Thường trong Card D (hỗ trợ chuyển đổi kỹ năng realtime ngay trong trận)"""
        if self._should_stop_card_D(): return
        while not self._should_stop_card_D():
            skill_mode = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"
            self.after(0, self.log_info, f"⚡ [{log_tag}] Kích hoạt kỹ năng: '{skill_mode}' (Chế độ Thường)...")

            if skill_mode == "Buff HP / SP":
                res = self._execute_card_d_buff_cycle(dnconsole_path, tab_index, log_tag=log_tag, is_nhi_kieu=is_nhi_kieu, active_skill="Buff HP / SP")
            elif skill_mode == "Linh Kính":
                res = self._execute_card_d_defense_cycle_core(dnconsole_path, tab_index, skill_name="Linh Kính", skill_template="card_f/skill/f_lk.png", log_tag=log_tag, is_nhi_kieu=is_nhi_kieu, is_auto_mode=False, active_skill="Linh Kính")
            elif skill_mode == "Kết Giới":
                res = self._execute_card_d_defense_cycle_core(dnconsole_path, tab_index, skill_name="Kết Giới", skill_template="card_f/skill/f_kg.png", log_tag=log_tag, is_nhi_kieu=is_nhi_kieu, is_auto_mode=False, active_skill="Kết Giới")
            elif skill_mode == "Đánh Tay":
                res = self._execute_card_d_danh_tay_thuong(dnconsole_path, tab_index, log_tag=log_tag, is_nhi_kieu=is_nhi_kieu, active_skill="Đánh Tay")
            else:
                res = self._execute_card_d_buff_cycle(dnconsole_path, tab_index, log_tag=log_tag, is_nhi_kieu=is_nhi_kieu, active_skill="Buff HP / SP")

            if res == "SWITCH_SKILL":
                continue
            break

    def _execute_card_d_skill_auto(self, dnconsole_path: str, tab_index: str, log_tag: str = "Nhị Kiều Auto", is_nhan_doi: bool = False):
        """Hàm điều phối Kỹ Năng Auto trong Card D (áp dụng cho Đỉnh 10 Nhị Kiều & Nhận Đội, hỗ trợ chuyển đổi kỹ năng realtime ngay trong trận)"""
        if self._should_stop_card_D(): return
        is_mid_battle = False
        while not self._should_stop_card_D():
            skill_mode = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"

            # Nếu là Nhận Đội và kỹ năng được chọn là Đánh Tay: Thoát ngay khỏi vòng lặp trận đấu
            if is_nhan_doi and skill_mode == "Đánh Tay":
                self.after(0, self.log_info, "🔄 [Nhận Đội - Realtime] Phát hiện chuyển sang kỹ năng 'Đánh Tay' ➔ Thoát trận đấu, quay về vòng lặp chờ lời mời tiếp theo!")
                return "SWITCH_TO_DANH_TAY"

            mode_desc = "Nhận Đội - Dấu hiệu 'card_f/f_vaotran.png'" if is_nhan_doi else "Chế độ Auto Chuyên Biệt"
            self.after(0, self.log_info, f"⚡ [{log_tag}] Kích hoạt kỹ năng: '{skill_mode}' ({mode_desc})...")

            if skill_mode == "Buff HP / SP":
                res = self._execute_card_d_buff_cycle_auto(dnconsole_path, tab_index, log_tag=log_tag, active_skill="Buff HP / SP", is_mid_battle=is_mid_battle)
            elif skill_mode == "Linh Kính":
                res = self._execute_card_d_defense_cycle_core(dnconsole_path, tab_index, skill_name="Linh Kính", skill_template="card_f/skill/f_lk.png", log_tag=log_tag, is_nhi_kieu=True, is_auto_mode=True, active_skill="Linh Kính", is_mid_battle=is_mid_battle)
            elif skill_mode == "Kết Giới":
                res = self._execute_card_d_defense_cycle_core(dnconsole_path, tab_index, skill_name="Kết Giới", skill_template="card_f/skill/f_kg.png", log_tag=log_tag, is_nhi_kieu=True, is_auto_mode=True, active_skill="Kết Giới", is_mid_battle=is_mid_battle)
            elif skill_mode == "Đánh Tay":
                res = self._execute_card_d_danh_tay_auto(dnconsole_path, tab_index, log_tag=log_tag, active_skill="Đánh Tay", is_mid_battle=is_mid_battle)
            else:
                res = self._execute_card_d_buff_cycle_auto(dnconsole_path, tab_index, log_tag=log_tag, active_skill="Buff HP / SP", is_mid_battle=is_mid_battle)

            if res == "SWITCH_SKILL":
                is_mid_battle = True
                continue
            break

    def _execute_card_d_skill_nhan_doi(self, dnconsole_path: str, tab_index: str, log_tag: str = "Nhận Đội"):
        """Wrapper điều phối Kỹ Năng chuyên biệt cho Nhận Đội (tái sử dụng _execute_card_d_skill_auto)"""
        return self._execute_card_d_skill_auto(dnconsole_path, tab_index, log_tag=log_tag, is_nhan_doi=True)

    def _run_40_npc_loidai_battle_loop(self, dnconsole_path: str, tab_index: str, mode_label: str = "Auto"):
        """Vòng lặp đánh Lôi Đài 37 lượt trận (chuẩn hóa cho Card 40 NPC Auto)"""
        if self._should_stop_card_D(): return
        self.after(0, self.log_info, "🚀 [Card D - 40 NPC] Bắt đầu Vòng lặp đánh Lôi Đài 37 lượt trận...")
        has_seen_d35 = False
        auto_tapped_d35 = False

        for loidai_round in range(1, 38):
            if self._should_stop_card_D(): return

            # Quét (không tap) f_vaotran.png (80%, ROI 1215,0,1280,45) mỗi 0.5s cho đến khi thấy
            self.after(0, self.log_info, f"🔄 [Card D - 40 NPC - Lượt {loidai_round}/37] Quét (không tap) 'card_f/f_vaotran.png' (80%) mỗi 0.5s...")
            while not self._should_stop_card_D():
                vt_chk_x, vt_chk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                if vt_chk_x is not None and vt_chk_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_f/f_vaotran.png' tại ({vt_chk_x}, {vt_chk_y})!")
                    break
                # Kiểm tra thêm nếu nút Xác Định đang hiển thị sẵn thì cũng thoát chờ ngay
                xd_chk_x, xd_chk_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_xacdinh.png", threshold=0.80, region=(275, 540, 980, 670))
                if xd_chk_x is not None and xd_chk_y is not None:
                    self.after(0, self.log_info, "🎯 Đang có sẵn nút Xác Định 'card_d/40npc/d_xacdinh.png' trên màn hình!")
                    break
                if self._sleep_card_D(0.5): return

            # Quét & Tap d_xacdinh.png (80%, ROI 275,540,980,670) ➔ Hoãn 2.5s vào trận
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, f"👁️ [Card D - 40 NPC - Lượt {loidai_round}/37] Quét & Tap nút Xác Định 'card_d/40npc/d_xacdinh.png' (80%)...")
            while not self._should_stop_card_D():
                xd_x, xd_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_xacdinh.png", threshold=0.80, region=(275, 540, 980, 670))
                if xd_x is not None and xd_y is not None:
                    self.after(0, self.log_info, f"🎯 Tap 'd_xacdinh.png' tại ({xd_x}, {xd_y})!")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {xd_x} {xd_y}"])
                    if self._sleep_card_D(2.5): return
                    break
                if self._sleep_card_D(0.5): return

            # Kiểm tra mốc d_35.png (80%, ROI 175,220,265,245)
            if self._should_stop_card_D(): return
            found_d35_this_round = False
            if has_seen_d35:
                self.after(0, self.log_info, "⚡ [Card D - 40 NPC] Đã từng thấy d_35.png ở lượt trước ➔ BỎ QUA QUÉT d_35.png, nhảy thẳng sang Buff/Skill!")
                found_d35_this_round = True
            else:
                self.after(0, self.log_info, "👁️ [Card D - 40 NPC] Quét (không tap) 'card_d/40npc/d_35.png' (80%, ROI 175,220,265,245) mỗi 0.5s (tối đa 4 lần)...")
                for _ in range(4):
                    if self._should_stop_card_D(): break
                    d35_x, d35_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_35.png", threshold=0.80, region=(175, 220, 265, 245))
                    if d35_x is not None and d35_y is not None:
                        found_d35_this_round = True
                        has_seen_d35 = True
                        self.after(0, self.log_info, f"🎯 Phát hiện 'card_d/40npc/d_35.png' tại ({d35_x}, {d35_y})!")
                        self.send_telegram_alert(
                            "⚔️ [40 NPC]\n🎯 Tầng 36 ( Vào Đánh Đi ) !",
                            capture_screenshot=True,
                            tab_index=str(tab_index),
                            is_card_d=True
                        )
                        break
                    if self._sleep_card_D(0.5): return

            # Phân nhánh Buff HP / SP & Skill
            if self._should_stop_card_D(): return
            if found_d35_this_round or has_seen_d35:
                if not auto_tapped_d35:
                    self.after(0, self.log_info, "🔴 [Card D - 40 NPC] Lần đầu tiên thấy d_35.png ➔ Tap 1 LẦN duy nhất nút Auto (190, 140)")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 190 140"])
                    if self._sleep_card_D(0.3): return
                    auto_tapped_d35 = True
                else:
                    self.after(0, self.log_info, "⚡ [Card D - 40 NPC] Các lượt sau d_35 ➔ Bỏ qua tap nút Auto!")

                # Kích hoạt Kỹ Năng theo Menu Kỹ Năng Card D
                self._execute_card_d_skill_thuong(dnconsole_path, tab_index, log_tag="Card D - 40 NPC", is_nhi_kieu=False)
            else:
                self.after(0, self.log_info, "🔴 [Card D - 40 NPC] Không thấy d_35.png (sau 4 lần) ➔ Quay lại quét f_vaotran cho lượt kế tiếp.")

        if not self._should_stop_card_D():
            self.after(0, self.log_info, "🏆 [Card D - 40 NPC] Đã hoàn thành toàn bộ 37 lượt trận Lôi Đài 40 NPC!")

    def _detect_40_npc_start_position(self, dnconsole_path: str, tab_index: str) -> str:
        """
        Quét nhận diện vị trí thông minh cho mốc Auto của 40 NPC:
        Sử dụng vùng ROI (275, 540, 980, 670):
        1. d_xacdinh.png (ngưỡng 80%) -> 'XAC_DINH'  (Đang ở Lôi Đài chuẩn bị vào round tiếp theo)
        2. d_vaotran.png (ngưỡng 75%) -> 'VAO_TRAN'  (Đang mở hộp thoại đăng ký vào trận)
        Quét 2 chu kỳ (mỗi ảnh ~1.0s).
        Nếu không thấy ảnh nào -> Trả về 'FULL' (Chạy toàn bộ quy trình Auto từ đầu).
        """
        if self._should_stop_card_D(): return "FULL"
        self.after(0, self.log_info, "👁️ [40 NPC Auto] Quét nhận diện vị trí thông minh ('d_xacdinh.png', 'd_vaotran.png')...")

        for cycle in range(1, 3):
            if self._should_stop_card_D(): return "FULL"
            if cycle > 1:
                self.after(0, self.log_info, "🔄 [40 NPC Auto] Đang thử lại lượt quét nhận diện thứ 2...")

            # 1. Quét d_xacdinh.png (80%, ROI 275, 540, 980, 670)
            t_start = time.time()
            while time.time() - t_start < 1.0:
                if self._should_stop_card_D(): return "FULL"
                xd_x, xd_y = self._find_template_on_screen(
                    dnconsole_path, tab_index, "card_d/40npc/d_xacdinh.png",
                    threshold=0.80, region=(275, 540, 980, 670)
                )
                if xd_x is not None and xd_y is not None:
                    self.after(0, self.log_info, f"🎯 [40 NPC Auto] Phát hiện 'card_d/40npc/d_xacdinh.png' tại ({xd_x}, {xd_y}) ➔ Đang ở Lôi Đài!")
                    return "XAC_DINH"
                if self._sleep_card_D(0.3): return "FULL"

            # 2. Quét d_vaotran.png (75%, ROI 275, 540, 980, 670)
            t_start = time.time()
            while time.time() - t_start < 1.0:
                if self._should_stop_card_D(): return "FULL"
                vt_x, vt_y = self._find_template_on_screen(
                    dnconsole_path, tab_index, "card_d/40npc/d_vaotran.png",
                    threshold=0.75, region=(275, 540, 980, 670)
                )
                if vt_x is not None and vt_y is not None:
                    self.after(0, self.log_info, f"🎯 [40 NPC Auto] Phát hiện 'card_d/40npc/d_vaotran.png' tại ({vt_x}, {vt_y}) ➔ Đang ở Hộp thoại Vào Trận!")
                    return "VAO_TRAN"
                if self._sleep_card_D(0.3): return "FULL"

        self.after(0, self.log_info, "ℹ️ [40 NPC Auto] Không phát hiện 'd_xacdinh.png' hay 'd_vaotran.png' ➔ Chạy đầy đủ quy trình Auto từ đầu (Tổ Đội / Kỹ Năng / Hẹn Giờ).")
        return "FULL"

    def _run_40_npc_su_kien_tang(self, dnconsole_path: str, tab_index: str, detected_pos: str = None, **kwargs):
        """THAO TÁC 2: 40 NPC (CHỈ THỰC THI KHI Ô 40 NPC VAR_D3 ĐƯỢC TÍCH)"""
        if self._should_stop_card_D(): return

        if not self.var_D3.get():
            self.after(0, self.log_info, "ℹ️ [Card D - 40 NPC] Ô '40 NPC' KHÔNG được tích -> Bỏ qua.")
            return

        self.after(0, self.log_info, "🚀 [Card D - 40 NPC] Khởi chạy ô 40 NPC (Auto)...")

        # =========================================================================
        # 📌 QUY TRÌNH: CHẾ ĐỘ AUTO 40 NPC (CƠ CHẾ NHẬN DIỆN VỊ TRÍ THÔNG MINH)
        # =========================================================================
        if detected_pos is None:
            detected_pos = self._detect_40_npc_start_position(dnconsole_path, tab_index)
            if self._should_stop_card_D(): return

        # -------------------------------------------------------------
        # NHÁNH 1: PHÁT HIỆN d_xacdinh.png -> NHẢY THẲNG VÀO VÒNG LẶP 37 ROUND
        # -------------------------------------------------------------
        if detected_pos == "XAC_DINH":
            self.after(0, self.log_info, "🎯 [Card D - 40 NPC] Phát hiện 'd_xacdinh.png' ➔ Nhảy thẳng vào BƯỚC 6: Cơ Chế Vòng Lặp 37 Round Lôi Đài!")
            self._run_40_npc_loidai_battle_loop(dnconsole_path, tab_index)
            return

        def _run_steps_1_to_5_7():
            # BƯỚC 1 (Chờ Hẹn Giờ): Vòng lặp chờ đồng hồ hệ thống chạm mốc theo ô ghi giờ.
            if self._should_stop_card_D(): return
            time_val = self.var_D_time.get().strip() if hasattr(self, 'var_D_time') else "20:00"
            if len(time_val) == 4 and time_val[1] == ':':
                time_val = f"0{time_val}"
            try:
                target_h, target_m = map(int, time_val.split(':'))
            except Exception:
                target_h, target_m = 20, 0

            now = datetime.now()
            target_time = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)

            if now < target_time:
                self.after(0, self.log_info, f"⏳ [Card D - 40 NPC - Bước 1] Đang chờ đến mốc hẹn giờ {time_val} (Hiện tại: {now.strftime('%H:%M:%S')})...")
                while datetime.now() < target_time:
                    if self._should_stop_card_D(): return
                    rem_sec = (target_time - datetime.now()).total_seconds()
                    if rem_sec <= 2.0:
                        if self._sleep_card_D(0.2): return
                    elif rem_sec <= 10.0:
                        if self._sleep_card_D(1.0): return
                    else:
                        # Cách xa mốc hẹn: ngủ nhịp dài tối đa 5.0s, vẫn kiểm tra dừng tức thì qua _sleep_card_D
                        if self._sleep_card_D(min(rem_sec - 2.0, 5.0)): return
            else:
                self.after(0, self.log_info, f"ℹ️ [Card D - 40 NPC - Bước 1] Thời gian hiện tại ({now.strftime('%H:%M:%S')}) đã qua mốc hẹn {time_val} ➔ Bỏ qua chờ, chạy tiếp ngay!")

            if self._should_stop_card_D(): return
            self.after(0, self.log_info, f"🎯 [Card D - 40 NPC - Bước 1] Đã đến mốc hẹn giờ {time_val}!")

            # BƯỚC 2: Kiểm Tra Đội Trước Khi vào Cổng Lôi Đài (Không cần gán quân sư)
            if self._should_stop_card_D(): return
            if hasattr(self, 'var_D2') and self.var_D2.get():
                list_B = list(getattr(self, 'list_E_B', []))
                if list_B:
                    self.after(0, self.log_info, "🚀 [Card D - 40 NPC - Bước 2] Khởi chạy kiểm tra & mời tổ đội (Chuẩn Card E, Không gán Quân Sư)...")
                    self._run_card_E_action_1(
                        dnconsole_path, tab_index, list_B, 
                        assign_quan_su=False, 
                        log_tag="Card D - 40 NPC - Bước 2",
                        stop_check=self._should_stop_card_D
                    )
            if self._should_stop_card_D(): return

            # BƯỚC 3 (Vào Lôi Đài):
            # 3.1: Quét & Tap d_conglt.png (80%, ROI 0,400,1280,720) -> Hoãn 2.0s
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, "👁️ [Card D - 40 NPC - Bước 3.1] Quét & tap Cổng Lôi Đài 'card_d/40npc/d_conglt.png' (80%, ROI 0,400,1280,720)...")
            while not self._should_stop_card_D():
                clt_x, clt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_conglt.png", threshold=0.80, region=(0, 400, 1280, 720))
                if clt_x is not None and clt_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện Cổng Lôi Đài 'card_d/40npc/d_conglt.png' tại ({clt_x}, {clt_y})! Tap")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {clt_x} {clt_y}"])
                    if self._sleep_card_D(2.0): return
                    break
                if self._sleep_card_D(0.5): return

            # 3.2: Quét & Tap d_vaolt.png (80%, ROI 0,400,1280,720) -> Hoãn 3.0s
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, "👁️ [Card D - 40 NPC - Bước 3.2] Quét & tap nút Vào Lôi Đài 'card_d/40npc/d_vaolt.png' (80%, ROI 0,400,1280,720)...")
            while not self._should_stop_card_D():
                vlt_x, vlt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_vaolt.png", threshold=0.80, region=(0, 400, 1280, 720))
                if vlt_x is not None and vlt_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_d/40npc/d_vaolt.png' tại ({vlt_x}, {vlt_y})! Tap ➔ Hoãn 3.0s bước vào Lôi Đài...")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {vlt_x} {vlt_y}"])
                    if self._sleep_card_D(3.0): return
                    self.send_telegram_alert(
                        "⚔️ [40 NPC]\n🎯 Đã Vào Lôi Đài !",
                        capture_screenshot=True,
                        tab_index=str(tab_index),
                        is_card_d=True
                    )
                    break
                if self._sleep_card_D(0.5): return

            # BƯỚC 4: Kiểm Tra Đội & Gán Quân Sư
            if self._should_stop_card_D(): return
            if hasattr(self, 'var_D2') and self.var_D2.get():
                list_B = list(getattr(self, 'list_E_B', []))
                if list_B:
                    self.after(0, self.log_info, "🚀 [Card D - 40 NPC - Bước 4] Khởi chạy kiểm tra & mời tổ đội (Chuẩn Card E, Có gán Quân Sư)...")
                    self._run_card_E_action_1(
                        dnconsole_path, tab_index, list_B, 
                        assign_quan_su=True, 
                        log_tag="Card D - 40 NPC - Bước 4",
                        stop_check=self._should_stop_card_D
                    )
            if self._should_stop_card_D(): return

            # BƯỚC 5 (Vào trận đầu tiên - 9 Thao tác):
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, "🚀 [Card D - 40 NPC - Bước 5] Bắt đầu 9 Thao tác vào trận đầu tiên...")

            # 5.1: Di chuyển Chéo Phải - Trên (W+D) giữ 3.0s (640,360 -> 890,110) -> Hoãn 0.2s
            self.after(0, self.log_info, "🕹️ [Bước 5.1] Swipe Chéo Phải - Trên (W+D) 3.0s (640,360 ➔ 890,110)...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 110 3000"])
            if self._sleep_card_D(0.2): return

            # 5.2: Di chuyển Phải (D) giữ 0.3s (640,360 -> 890,360) -> Hoãn 0.2s
            self.after(0, self.log_info, "🕹️ [Bước 5.2] Swipe Phải (D) 0.3s (640,360 ➔ 890,360)...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 360 300"])
            if self._sleep_card_D(0.2): return

            # 5.3: Di chuyển Chéo Phải - Trên (W+D) giữ 1.0s (640,360 -> 890,110) -> Hoãn 0.2s
            self.after(0, self.log_info, "🕹️ [Bước 5.3] Swipe Chéo Phải - Trên (W+D) 1.0s (640,360 ➔ 890,110)...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 110 1000"])
            if self._sleep_card_D(0.2): return

            # 5.4: Di chuyển Phải (D) giữ 1.0s (640,360 -> 890,360) -> Hoãn 0.2s
            self.after(0, self.log_info, "🕹️ [Bước 5.4] Swipe Phải (D) 1.0s (640,360 ➔ 890,360)...")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input swipe 640 360 890 360 1000"])
            if self._sleep_card_D(0.2): return

            # 5.5: Tap liên tục (1240, 605) mỗi 0.4s (tối đa 20 lần) tìm d_chien.png (80%, ROI 280,490,1280,720)
            self.after(0, self.log_info, "👉 [Bước 5.5] Tap liên tục (1240, 605) mỗi 0.4s (tối đa 20 lần) tìm 'card_d/40npc/d_chien.png' (80%)...")
            for retry in range(20):
                if self._should_stop_card_D(): return
                ch_x, ch_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_chien.png", threshold=0.80, region=(280, 490, 1280, 720))
                if ch_x is not None and ch_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_d/40npc/d_chien.png' tại ({ch_x}, {ch_y})! Dừng click.")
                    break
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1240 605"])
                if self._sleep_card_D(0.4): return

            # 5.6: Tap (1135, 565) -> Hoãn 0.4s (Chọn trận)
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, "👉 [Bước 5.6] Tap (1135, 565) chọn trận")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 1135 565"])
            if self._sleep_card_D(0.4): return

            # 5.7: Quét & Tap card_f/f_tieptheo.png (70%, ROI 1050,530,1165,680) -> Hoãn 0.4s
            if self._should_stop_card_D(): return
            self.after(0, self.log_info, "👁️ [Bước 5.7] Quét & tap 'card_f/f_tieptheo.png' (70%)")
            while not self._should_stop_card_D():
                tt1_x, tt1_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_tieptheo.png", threshold=0.70, region=(1050, 530, 1165, 680))
                if tt1_x is not None and tt1_y is not None:
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {tt1_x} {tt1_y}"])
                    if self._sleep_card_D(0.4): return
                    break
                if self._sleep_card_D(0.4): return

        # -------------------------------------------------------------
        # ĐIỀU PHỐI: NẾU THẤY d_vaotran.png THÌ BỎ QUA BƯỚC 1 -> 5.7, NHẢY THẲNG VÀO 5.8
        # NẾU KHÔNG THẤY ẢNH NÀO THÌ CHẠY ĐẦY ĐỦ BƯỚC 1 -> 5.7 TRƯỚC KHI VÀO 5.8
        # -------------------------------------------------------------
        if detected_pos == "VAO_TRAN":
            self.after(0, self.log_info, "🎯 [Card D - 40 NPC] Phát hiện 'd_vaotran.png' ➔ Bỏ qua Hẹn Giờ, Cổng & Di chuyển, nhảy thẳng vào BƯỚC 5.8 (Vào Trận)!")
        else:
            self.after(0, self.log_info, "🚀 [Card D - 40 NPC] Bắt đầu Quy Trình Auto đầy đủ (Bước 1 ➔ Bước 5.7)...")
            _run_steps_1_to_5_7()
            if self._should_stop_card_D(): return

        # 5.8: Quét & Tap card_d/40npc/d_vaotran.png (75%, ROI 275,540,980,670) -> Hoãn 0.4s
        if self._should_stop_card_D(): return
        self.after(0, self.log_info, "👁️ [Bước 5.8] Quét & tap 'card_d/40npc/d_vaotran.png' (75%)")
        while not self._should_stop_card_D():
            vt_x, vt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/40npc/d_vaotran.png", threshold=0.75, region=(275, 540, 980, 670))
            if vt_x is not None and vt_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_d/40npc/d_vaotran.png' tại ({vt_x}, {vt_y})! Tap")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {vt_x} {vt_y}"])
                if self._sleep_card_D(0.4): return
                break
            if self._sleep_card_D(0.4): return

        # 5.9: Quét & Tap card_f/f_tieptheo.png (70%, ROI 1050,530,1165,680) liên tục mỗi 0.4s cho tới khi mất hẳn
        if self._should_stop_card_D(): return
        self.after(0, self.log_info, "👉 [Bước 5.9] Quét & tap 'card_f/f_tieptheo.png' (70%) cho tới khi mất hoàn toàn...")
        self._tap_f_tieptheo_until_lost(dnconsole_path, tab_index, tap_interval=0.4, threshold=0.70, region=(1050, 530, 1165, 680), stop_check=self._should_stop_card_D)

        # Hoãn 3.0s tải vào trận sau khi xóa thoại Tiếp Theo & Gửi cảnh báo Telegram
        if self._should_stop_card_D(): return
        self.after(0, self.log_info, "⏳ [Bước 5.9] Đã xóa thoại Tiếp Theo ➔ Hoãn 3.0s tải vào trận...")
        if self._sleep_card_D(3.0): return
        self.send_telegram_alert(
            "⚔️ [40 NPC]\n🎯 Bắt Đầu Trận !",
            capture_screenshot=True,
            tab_index=str(tab_index),
            is_card_d=True
        )

        # BƯỚC 6 (Vòng lặp đánh Lôi Đài 37 lượt trận - Lượt 1 -> 37):
        self._run_40_npc_loidai_battle_loop(dnconsole_path, tab_index)

    def _run_nhan_doi_action(self, dnconsole_path: str, tab_index: str, check_skill_switch: bool = False):
        """
        THAO TÁC Ô TÍCH NHẬN ĐỘI (CARD D):
        1. Quét tìm ảnh card_e/e_nhandoi.png (98%, ROI 880, 635, 980, 720).
           - Không thấy: nghỉ 3.0s quét lại (kèm kiểm tra dừng _should_stop_card_D).
           - Thấy ảnh: tap vào ảnh ➔ hoãn 0.4s.
        2. Quét tìm tên theo Danh Sách B Card Tổ Đội (thử lại mỗi 0.5s tối đa 4 lần).
           - Tái sử dụng hàm _find_nhanvat_template(mode="40npc", region=(250, 165, 580, 535), threshold=0.80).
        3. Rẽ nhánh:
           - Thấy tên trong Danh Sách B ➔ Offset X + 680 tap vào tọa độ nút Đồng Ý (char_x + 680, char_y) ➔ Hoãn 0.5s ➔ Hoàn thành, kết thúc hàm chuyển tiếp sang vòng lặp kỹ năng.
           - Không thấy sau 4 lần ➔ Tap tọa độ (330, 25) đóng bảng Đội ➔ Hoãn 0.5s ➔ Quay lại Bước 1 tiếp tục quét chờ lời mời mới.
        """
        if self._should_stop_card_D(): return False
        self.after(0, self.log_info, "📥 [Sự Kiện - Nhận Đội] Bắt đầu quy trình Nhận Đội...")

        list_B = list(getattr(self, 'list_E_B', []))
        if not list_B:
            self.after(0, self.log_info, "⚠️ [Nhận Đội] Danh Sách B (Card Tổ Đội) đang trống! Không có nhân vật nào để nhận đội.")
            return False

        # VÒNG LẶP TOÀN BỘ QUY TRÌNH (Tự động quay lại Bước 1 nếu hết 4 lần quét không thấy nhân vật)
        while not self._should_stop_card_D():
            # --- BƯỚC 1: QUÉT CHỜ NÚT NHẬN ĐỘI (98%, ROI 880, 635, 980, 720) ---
            wait_step1_start = time.time()
            last_wait_log_time = 0.0
            logged_initial_wait = False

            while not self._should_stop_card_D():
                # Hỗ trợ chuyển đổi kỹ năng realtime ngay trong lúc chờ lời mời
                if check_skill_switch and hasattr(self, 'var_D_skill'):
                    cur_sk = self.var_D_skill.get()
                    if cur_sk != "Đánh Tay":
                        self.after(0, self.log_info, f"🔄 [Nhận Đội - Realtime] Phát hiện đổi kỹ năng sang '{cur_sk}' ➔ Chuyển sang thực thi kỹ năng mới...")
                        return "SWITCH_SKILL"

                nd_x, nd_y = self._find_template_on_screen(
                    dnconsole_path, tab_index, "card_e/e_nhandoi.png",
                    threshold=0.98, region=(880, 635, 980, 720)
                )
                if nd_x is not None and nd_y is not None:
                    self.after(0, self.log_info, "🎯 [Nhận Đội - Bước 1] Phát hiện lời mời ! Tap ➔ Hoãn 0.4s...")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {nd_x} {nd_y}"])
                    if self._sleep_card_D(0.4): return False
                    break
                else:
                    now = time.time()
                    if not logged_initial_wait:
                        self.after(0, self.log_info, "⏳ [Nhận Đội - Bước 1] Đang chờ lời mời")
                        logged_initial_wait = True
                        last_wait_log_time = now
                    elif now - last_wait_log_time >= 30.0:
                        elapsed = int(now - wait_step1_start)
                        self.after(0, self.log_info, f"⏳ [Nhận Đội - Chờ Mời] Vẫn đang chờ lời mời hợp lệ từ Danh Sách B (đã chờ {elapsed}s)...")
                        last_wait_log_time = now

                    if self._sleep_card_D(3.0): return False

            if self._should_stop_card_D(): return False

            # --- BƯỚC 2: QUÉT TÌM TÊN TRONG DANH SÁCH B (TỐI ĐA 4 LẦN, MỖI LẦN 0.5s) ---
            self.after(0, self.log_info, f"👁️ [Nhận Đội - Bước 2] Bắt đầu quét tìm tên theo Danh Sách B ({len(list_B)} nhân vật: {', '.join(list_B)}) tối đa 4 lần (ROI 250, 165, 580, 535)...")
            found_char = None
            found_x, found_y = None, None

            for attempt in range(1, 5):
                if self._should_stop_card_D(): return False
                for char_name in list_B:
                    if self._should_stop_card_D(): return False
                    chk_x, chk_y = self._find_nhanvat_template(
                        dnconsole_path, tab_index, char_name,
                        threshold=0.80, region=(250, 165, 580, 535), mode="40npc"
                    )
                    if chk_x is not None and chk_y is not None:
                        found_char = char_name
                        found_x, found_y = chk_x, chk_y
                        break

                if found_char is not None:
                    break

                if attempt < 4:
                    self.after(0, self.log_info, f"⏳ [Nhận Đội - Bước 2] Lần {attempt}/4 chưa thấy tên nhân vật ➔ Chờ 0.5s tải popup rồi quét lại...")
                    if self._sleep_card_D(0.5): return False

            # --- BƯỚC 3: RẼ NHÁNH ---
            if found_char is not None:
                # Nhánh thấy: Tap nút Đồng Ý ➔ Hoàn thành, thoát hàm sang kỹ năng
                dong_y_x = found_x + 680
                dong_y_y = found_y
                self.after(0, self.log_info, f"🎯 [Nhận Đội - Bước 3] Phát hiện '{found_char}' tại ({found_x}, {found_y}) ➔ Tap nút Đồng Ý ({dong_y_x}, {dong_y_y}) [Offset X +680]...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {dong_y_x} {dong_y_y}"])
                if self._sleep_card_D(0.5): return False
                self.after(0, self.log_info, f"✅ [Nhận Đội - Hoàn Thành] Đã đồng ý vào đội của '{found_char}'! Chuyển sang thao tác tiếp theo...")
                return True
            else:
                # Nhánh không thấy sau 4 lần: Bị người lạ mời hoặc sai người ➔ Tap tọa độ (330, 25) đóng bảng Đội
                self.after(0, self.log_info, "⚠️ [Nhận Đội - Bước 3] Đã hết 4 lần quét không thấy nhân vật trong Danh Sách B (người lạ mời hoặc sai người) ➔ Tap (330, 25) đóng bảng Đội ➔ Hoãn 0.5s...")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 330 25"])
                if self._sleep_card_D(0.5): return False
        return False

    def _execute_card_D_40_npc(self, dnconsole_path: str, tab_name: str, tab_index: str):
        """Thực thi Tab Sự Kiện (Card D): Vị Trí -> Tổ Đội / Nhận Đội / 40 NPC / Nhị Kiều"""
        if self._should_stop_card_D():
            self.after(0, self.log_info, "ℹ️ [SỰ KIỆN - CARD D] Công tắc ON/OFF đang TẮT -> Bỏ qua.")
            return

        checked = [
            ("Tổ Đội", self.var_D2),
            ("Nhận Đội", self.var_D_nhan_doi),
            ("40 NPC", self.var_D3),
            ("Nhị Kiều", self.var_D4),
        ]
        selected_team_char = self.combo_D_team_char.get() if hasattr(self, 'combo_D_team_char') else "Xuất Chiến"
        selected_tang = self.combo_D_tang.get() if hasattr(self, 'combo_D_tang') else "Auto"

        has_pos_change = (selected_team_char != "Xuất Chiến")

        active_items = [(name, var) for name, var in checked if var.get()]
        if not active_items and not has_pos_change:
            self.after(0, self.log_info, "ℹ️ [SỰ KIỆN - CARD D] Công tắc ON nhưng không có mục nào được chọn -> Tắt công tắc & Bỏ qua.")
            self.after(0, lambda: self.var_switch_D.set(False))
            self.after(0, self.save_config)
            return

        info_details = []
        if has_pos_change:
            info_details.append(f"Vị trí: '{selected_team_char}'")
        if self.var_D2.get():
            info_details.append("Tổ Đội (Mời thành viên)")
        if hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get():
            info_details.append("Nhận Đội")
        if self.var_D3.get():
            info_details.append("40 NPC (Auto)")
        if self.var_D4.get():
            info_details.append("Nhị Kiều (Auto)")

        self.after(0, self.log_info, f"▶️ [SỰ KIỆN - CARD D] Đang thực thi {len(info_details)} mục đã chọn: {', '.join(info_details)}...")

        # =========================================================================
        # 📌 KIỂM TRA NHẬN BIẾT VỊ TRÍ THÔNG MINH CHO 40 NPC AUTO
        # =========================================================================
        detected_pos_40npc = "FULL"
        is_40npc_auto = self.var_D3.get() and (not self.var_D4.get())

        if is_40npc_auto:
            detected_pos_40npc = self._detect_40_npc_start_position(dnconsole_path, tab_index)
            if self._should_stop_card_D(): return

        # =========================================================================
        # 📌 BƯỚC 1: CHỌN VỊ TRÍ (CHẠY KHI KHÁC 'Xuất Chiến')
        # =========================================================================
        if self._should_stop_card_D(): return
        if detected_pos_40npc in ("VAO_TRAN", "XAC_DINH"):
            if has_pos_change:
                self.after(0, self.log_info, f"ℹ️ [Sự Kiện - Chọn Vị Trí] Đã phát hiện vị trí trong trận ('{detected_pos_40npc}') ➔ Bỏ qua đổi vị trí tướng để tránh tắt giao diện.")
        elif has_pos_change:
            self.after(0, self.log_info, f"🚀 [Sự Kiện - Chọn Vị Trí] Khởi chạy đổi vị trí tướng (Vị trí: '{selected_team_char}')...")
            self._run_40_npc_team_and_char_position(dnconsole_path, tab_index, selected_team_char)
            if self._should_stop_card_D(): return
        else:
            self.after(0, self.log_info, "ℹ️ [Sự Kiện - Chọn Vị Trí] Giữ nguyên vị trí nhân vật hiện tại ('Xuất Chiến') ➔ Bỏ qua đổi vị trí.")

        # =========================================================================
        # 📌 BƯỚC 2: KIỂM TRA PHÂN NHÁNH Ô TÍCH
        # =========================================================================
        # --- NHÁNH 3.1: TỔ ĐỘI TÍCH -> CHẠY TỔ ĐỘI RỒI ĐẾN CÁC MỐC NHỊ KIỀU / 40 NPC ---
        if self._should_stop_card_D(): return
        if self.var_D2.get():
            if is_40npc_auto and detected_pos_40npc in ("VAO_TRAN", "XAC_DINH"):
                self.after(0, self.log_info, f"ℹ️ [Sự Kiện - Tổ Đội] Đã phát hiện vị trí trong trận ('{detected_pos_40npc}') ➔ Bỏ qua mời Tổ Đội Card E ngoài sảnh để tránh tắt hộp thoại Lôi Đài.")
            else:
                self.after(0, self.log_info, "🚀 [Sự Kiện - Tổ Đội] Khởi chạy gọi mời thành viên tạo tổ đội (Card E)...")
                self._execute_card_E_for_mode(dnconsole_path, tab_name, tab_index, mode=1)
                if self._should_stop_card_D(): return

            if self.var_D4.get():
                self.after(0, self.log_info, "🚀 [Sự Kiện - Nhị Kiều] Khởi chạy ô Nhị Kiều Auto...")
                self._run_nhi_kieu_tang(dnconsole_path, tab_index, selected_tang)
                if self._should_stop_card_D(): return

            elif self.var_D3.get():
                self.after(0, self.log_info, "🚀 [Sự Kiện - 40 NPC] Khởi chạy ô 40 NPC (Auto)...")
                self._run_40_npc_su_kien_tang(dnconsole_path, tab_index, detected_pos=detected_pos_40npc)
                if self._should_stop_card_D(): return

        # --- NHÁNH 3.2: NHẬN ĐỘI TÍCH -> CHẠY NHẬN ĐỘI LIÊN TỤC & VÒNG LẶP KỸ NĂNG ---
        elif hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get():
            self.after(0, self.log_info, "🚀 [Sự Kiện - Nhận Đội] Khởi chạy quy trình Nhận Đội liên tục...")

            is_in_team = False
            battle_round = 0
            while not self._should_stop_card_D() and hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get():
                curr_skill = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"

                # 1. NẾU CHỌN SKILL LÀ "ĐÁNH TAY":
                if curr_skill == "Đánh Tay":
                    # Luôn quét nhận đội (hỗ trợ phát hiện đổi skill realtime sang Buff/Kính/Kết Giới)
                    nd_res = self._run_nhan_doi_action(dnconsole_path, tab_index, check_skill_switch=True)
                    if self._should_stop_card_D(): break
                    if nd_res == "SWITCH_SKILL":
                        # Người dùng vừa đổi skill trong lúc chờ ➔ tiếp tục vòng lặp với skill mới
                        continue
                    if nd_res is True or nd_res == "SUCCESS":
                        is_in_team = True
                        self.after(0, self.log_info, "⚔️ [Nhận Đội - Đánh Tay] Đã vào đội thành công ➔ Chế độ Đánh Tay: Tự động quay lại tiếp tục quét chờ lời mời hợp lệ tiếp theo...")
                        if self._sleep_card_D(0.5): break
                        continue
                    else:
                        # Bị ngắt dừng hoặc lỗi danh sách trống
                        break

                # 2. NẾU CHỌN CÁC SKILL KHÁC (Buff HP / SP, Linh Kính, Kết Giới):
                else:
                    # Nếu chưa vào đội thì phải nhận đội trước
                    if not is_in_team:
                        nd_res = self._run_nhan_doi_action(dnconsole_path, tab_index, check_skill_switch=True)
                        if self._should_stop_card_D(): break
                        if nd_res == "SWITCH_SKILL":
                            continue
                        if nd_res is True or nd_res == "SUCCESS":
                            is_in_team = True
                        else:
                            break

                    # Khi đã vào đội ➔ Vòng lặp chiến đấu liên tục các trận
                    while not self._should_stop_card_D() and hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get():
                        curr_skill = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"
                        if curr_skill == "Đánh Tay":
                            # Người dùng đổi về Đánh Tay ➔ Thoát vòng lặp chiến đấu, quay về vòng lặp nhận đội
                            break

                        battle_round += 1
                        self.after(0, self.log_info, f"⚔️ [Sự Kiện - Nhận Đội] Đang chạy trận đấu thứ {battle_round} (Kỹ năng: '{curr_skill}')...")
                        res = self._execute_card_d_skill_nhan_doi(dnconsole_path, tab_index, log_tag=f"Nhận Đội - Trận {battle_round}")

                        if res == "SWITCH_TO_DANH_TAY":
                            # Đã chuyển sang Đánh Tay giữa trận ➔ Thoát ra ngay
                            break

                        if self._should_stop_card_D(): break
                        if self._sleep_card_D(1.0): break

            if self._should_stop_card_D():
                self.after(0, self.log_info, "🛑 [Sự Kiện - Nhận Đội] Đã phát hiện công tắc Switch D tắt tay / nút Dừng ➔ Đã ngắt toàn bộ quy trình Nhận Đội!")

        # --- NHÁNH 3.3: CHỈ NHỊ KIỀU TÍCH (SOLO - KHÔNG TỔ ĐỘI) ---
        elif self.var_D4.get():
            self.after(0, self.log_info, "🚀 [Sự Kiện - Nhị Kiều] Khởi chạy ô Nhị Kiều Auto (Solo)...")
            self._run_nhi_kieu_tang(dnconsole_path, tab_index, selected_tang)
            if self._should_stop_card_D(): return

        # --- NHÁNH 3.4: 40 NPC TÍCH ---
        elif self.var_D3.get():
            self.after(0, self.log_info, "🚀 [Sự Kiện - 40 NPC] Khởi chạy ô 40 NPC (Auto)...")
            self._run_40_npc_su_kien_tang(dnconsole_path, tab_index, detected_pos=detected_pos_40npc)
            if self._should_stop_card_D(): return

        # =========================================================================
        # 📌 KẾT THÚC TIẾN TRÌNH: TỰ ĐỘNG TẮT SWITCH D
        # =========================================================================
        self.after(0, lambda: self.var_switch_D.set(False))
        if hasattr(self, 'var_pause_D'):
            self.after(0, lambda: self.var_pause_D.set(False))
        self.after(0, self.save_config)
        is_nhan_doi = hasattr(self, 'var_D_nhan_doi') and self.var_D_nhan_doi.get()
        if not is_nhan_doi:
            self.after(0, self.log_info, "✅ [SỰ KIỆN - CARD D] Đã thực thi hoàn tất dứt điểm! (Đã tự động tắt công tắc ON/OFF & giữ nguyên các ô tích)")

    def _run_nhi_kieu_leo_thap_core(self, dnconsole_path: str, tab_index: str, loop_count: int = 0, mode_name: str = "Auto", run_stage_1: bool = True, run_stage_2: bool = True, target_finish_img: str = None):
        """THAO TÁC CHI TIẾT LEO ĐÀI NHỊ KIỀU (Giai Đoạn 1, 2 và Vòng Lặp Leo Đài 4 -> 7)"""

        def should_stop() -> bool:
            return self._should_stop_card_D()

        def _tap_tieptheo(tap_interval: float = 0.5, delay_after: float = 0.0):
            """Wrapper gọi self._tap_f_tieptheo_until_lost với dnconsole_path/tab_index cục bộ"""
            self._tap_f_tieptheo_until_lost(dnconsole_path, tab_index, tap_interval=tap_interval, delay_after=delay_after, stop_check=should_stop)

        def _wait_for_f_vaotran():
            """Quét (không tap) card_f/f_vaotran.png (ROI: 1215, 0, 1280, 45, 80%) cho tới khi thấy"""
            self.after(0, self.log_info, "👁️ Quét (không tap) 'card_f/f_vaotran.png' (ROI 1215,0,1280,45)...")
            while not should_stop():
                vt_x, vt_y = self._find_template_on_screen(
                    dnconsole_path, tab_index, "card_f/f_vaotran.png",
                    threshold=0.80, region=(1215, 0, 1280, 45)
                )
                if vt_x is not None and vt_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'card_f/f_vaotran.png' tại ({vt_x}, {vt_y})!")
                    break
                if self._sleep_card_D(1.0): return

        def _swipe_dpad_direction(direction: str, duration_ms: int):
            """Vuốt D-Pad theo hướng chỉ định qua ADB swipe (Tâm 640, 360)"""
            swipe_coords = {
                "UP": (640, 360, 640, 110),
                "DOWN": (640, 360, 640, 610),
                "LEFT": (640, 360, 390, 360),
                "RIGHT": (640, 360, 890, 360),
                "UP_RIGHT": (640, 360, 890, 110),
                "UP_LEFT": (640, 360, 390, 110),
                "DOWN_RIGHT": (640, 360, 890, 610),
                "DOWN_LEFT": (640, 360, 390, 610),
            }
            coords = swipe_coords.get(direction, (640, 360, 890, 110))
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input swipe {coords[0]} {coords[1]} {coords[2]} {coords[3]} {duration_ms}"])

        def _swipe_dpad_until_tieptheo(direction: str, timeout_sec: float = 8.0, duration_ms: int = 3000) -> bool:
            """Vuốt D-Pad giữ duration_ms lặp lại sau 0.2s cho tới khi thấy f_tieptheo.png (ROI 1050,530,1165,680) hoặc hết timeout"""
            start_t = time.time()
            while time.time() - start_t < timeout_sec:
                if should_stop(): return False
                _swipe_dpad_direction(direction, duration_ms)
                tt_x, tt_y = self._find_template_on_screen(
                    dnconsole_path, tab_index, "card_f/f_tieptheo.png",
                    threshold=0.80, region=(1050, 530, 1165, 680)
                )
                if tt_x is not None and tt_y is not None:
                    return True
                if self._sleep_card_D(0.2): return False
            return False

        # -------------------------------------------------------------
        # THỰC THI GIAI ĐOẠN 1 (NẾU ĐƯỢC KÍCH HOẠT)
        # -------------------------------------------------------------
        if run_stage_1:
            # === GIAI ĐOẠN 1 ===
            self.after(0, self.log_info, f"🚀 [{mode_name}] Bắt đầu Giai Đoạn 1...")

            # 1.1: Vuốt LEFT giữ 2.0s (2000ms), lặp lại mỗi 0.2s cho tới khi xuất hiện f_tieptheo.png (ROI: 1050, 530, 1165, 680, 80%) (timeout tối đa 8s)
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.1] Vuốt LEFT 2.0s lặp lại mỗi 0.2s tìm 'f_tieptheo.png' (timeout 8s)...")
            _swipe_dpad_until_tieptheo("LEFT", timeout_sec=8.0, duration_ms=2000)
            if should_stop(): return

            # 1.2: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn ➔ Hoãn chờ 5.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.2] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất ➔ Hoãn chờ 5.0s...")
            _tap_tieptheo(tap_interval=0.5, delay_after=5.0)
            if should_stop(): return

            # 1.3: Quét (chỉ đợi, không tap) f_vaotran.png (ROI: 1215, 0, 1280, 45, 80%).
            self.after(0, self.log_info, f"👁️ [{mode_name} - Bước 1.3] Quét (chỉ đợi, không tap) 'f_vaotran.png'...")
            _wait_for_f_vaotran()
            if should_stop(): return

            # 1.4: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn ➔ Hoãn 0.5s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.4] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.5)
            if should_stop(): return

            # 1.5: Vuốt UP_LEFT giữ 0.5s (500ms) ➔ delay 0.2s
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.5] Vuốt UP_LEFT 0.5s")
            _swipe_dpad_direction("UP_LEFT", 500)
            if self._sleep_card_D(0.2): return

            # 1.6: Vuốt LEFT giữ 4.5s (4500ms) ➔ delay 0.2s
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.6] Vuốt LEFT 4.5s")
            _swipe_dpad_direction("LEFT", 4500)
            if self._sleep_card_D(0.2): return

            # 1.7: Quét tìm ảnh d_buoc1.png (ngưỡng 75%) ROI (0, 0, 640, 720) ➔ Tap click lần 1.
            self.after(0, self.log_info, f"👁️ [{mode_name} - Bước 1.7] Quét 'd_buoc1.png' (75%, ROI 0,0,640,720)...")
            while not should_stop():
                b1_x, b1_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/nhikieu/d_buoc1.png", threshold=0.75, region=(0, 0, 640, 720))
                if b1_x is not None and b1_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'd_buoc1.png' tại ({b1_x}, {b1_y})! Tap lần 1...")
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {b1_x} {b1_y}"])
                    break
                if self._sleep_card_D(0.5): return
            if should_stop(): return

            # 1.8: Quét chờ xuất hiện f_tieptheo.png.
            self.after(0, self.log_info, f"👁️ [{mode_name} - Bước 1.8] Quét chờ xuất hiện 'f_tieptheo.png' (ROI 1050,530,1165,680)...")
            while not should_stop():
                tt_x, tt_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_f/f_tieptheo.png", threshold=0.80, region=(1050, 530, 1165, 680))
                if tt_x is not None and tt_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện 'f_tieptheo.png' tại ({tt_x}, {tt_y})!")
                    break
                if self._sleep_card_D(0.5): return
            if should_stop(): return

            # 1.9: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn ➔ Hoãn chờ 5.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.9] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất ➔ Hoãn chờ 5.0s...")
            _tap_tieptheo(tap_interval=0.5, delay_after=5.0)
            if should_stop(): return

            # 1.10: Quét (không tap) f_vaotran.png.
            self.after(0, self.log_info, f"👁️ [{mode_name} - Bước 1.10] Quét (không tap) 'f_vaotran.png'...")
            _wait_for_f_vaotran()
            if should_stop(): return

            # 1.11: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn ➔ Hoãn 0.5s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.11] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.5)
            if should_stop(): return

            # 1.12: Tap lặp lại d_buoc1.png (ngưỡng 75%) ROI (0, 0, 640, 720) mỗi 1s cho đến khi mất hẳn ➔ Hoãn 2.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 1.12] Tap 'd_buoc1.png' (75%, ROI 0,0,640,720) mỗi 1.0s đến khi mất")
            while not should_stop():
                b1_curr_x, b1_curr_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/nhikieu/d_buoc1.png", threshold=0.75, region=(0, 0, 640, 720))
                if b1_curr_x is not None and b1_curr_y is not None:
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {b1_curr_x} {b1_curr_y}"])
                    if self._sleep_card_D(1.0): return
                else:
                    self.after(0, self.log_info, "✅ 'd_buoc1.png' đã mất!")
                    self.send_telegram_alert(
                        "🏯 [NHỊ KIỀU]\n🎯 Đã Vào Đại Điện",
                        capture_screenshot=True,
                        tab_index=str(tab_index),
                        is_card_d=True,
                        delay_seconds=3.0
                    )
                    if self._sleep_card_D(2.0): return
                    break
            if should_stop(): return
        else:
            self.after(0, self.log_info, f"ℹ️ [{mode_name}] Bỏ qua Giai đoạn 1...")

        # -------------------------------------------------------------
        # THỰC THI GIAI ĐOẠN 2 (NẾU ĐƯỢC KÍCH HOẠT)
        # -------------------------------------------------------------
        if run_stage_2:
            # === GIAI ĐOẠN 2 ===
            self.after(0, self.log_info, f"🚀 [{mode_name}] Bắt đầu Giai Đoạn 2...")

            # 2.1: Tap tọa độ cố định (225, 220) (vị trí dẫn đường/cổng) ➔ Hoãn 2.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 2.1] Tap cố định (225, 220)")
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 225 220"])
            if self._sleep_card_D(2.0): return
            if should_stop(): return

            # 2.2: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn, kiểm tra lại sau 1s (nếu còn thì tap tiếp), khi sạch hẳn ➔ Hoãn chờ 5.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 2.2] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất, kiểm tra lại sau 1.0s trước khi hoãn 5.0s...")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.0)
            if should_stop(): return
            if self._sleep_card_D(1.0): return
            if should_stop(): return

            recheck_x, recheck_y = self._find_template_on_screen(
                dnconsole_path, tab_index, "card_f/f_tieptheo.png",
                threshold=0.80, region=(1050, 530, 1165, 680)
            )
            if recheck_x is not None and recheck_y is not None:
                self.after(0, self.log_info, f"ℹ️ [{mode_name} - Bước 2.2] Sau 1.0s vẫn còn nút Tiếp Theo ➔ Tiếp tục tap...")
                _tap_tieptheo(tap_interval=0.5, delay_after=0.0)
                if should_stop(): return

            self.after(0, self.log_info, f"✅ [{mode_name} - Bước 2.2] Đã hết hẳn hội thoại sau 1.0s kiểm tra ➔ Bắt đầu hoãn chờ 5.0s...")
            if self._sleep_card_D(5.0): return
            if should_stop(): return

            # 2.3: Quét (không tap) f_vaotran.png.
            self.after(0, self.log_info, f"👁️ [{mode_name} - Bước 2.3] Quét (không tap) 'f_vaotran.png'...")
            _wait_for_f_vaotran()
            if should_stop(): return

            # 2.4: Tap liên tục f_tieptheo.png mỗi 0.5s đến khi mất hẳn ➔ Hoãn 0.5s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 2.4] Tap 'f_tieptheo.png' mỗi 0.5s đến khi mất")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.5)
            if should_stop(): return

            # 2.5: Tap lặp lại d_buoc2.png (ngưỡng 80%) ROI (0, 0, 1280, 360) mỗi 2.0s cho đến khi mất hẳn ➔ Hoãn 3.0s.
            self.after(0, self.log_info, f"👉 [{mode_name} - Bước 2.5] Tap 'd_buoc2.png' (80%, ROI 0,0,1280,360) mỗi 2.0s đến khi mất")
            while not should_stop():
                b2_x, b2_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_d/nhikieu/d_buoc2.png", threshold=0.80, region=(0, 0, 1280, 360))
                if b2_x is not None and b2_y is not None:
                    self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {b2_x} {b2_y}"])
                    if self._sleep_card_D(2.0): return
                else:
                    self.after(0, self.log_info, "✅ 'd_buoc2.png' đã mất!")
                    if self._sleep_card_D(3.0): return
                    self.send_telegram_alert(
                        "🏯 [NHỊ KIỀU]\n🎯 Đã Vào Thang Tháp",
                        capture_screenshot=True,
                        tab_index=str(tab_index),
                        is_card_d=True
                    )
                    break
            if should_stop(): return

            # 2.6: Tap nút Auto tại tọa độ (190, 140) ➔ Bỏ qua nếu kỹ năng là "Đánh Tay"
            curr_skill = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"
            if curr_skill == "Đánh Tay":
                self.after(0, self.log_info, f"ℹ️ [{mode_name} - Bước 2.6] Kỹ năng đang chọn là 'Đánh Tay' ➔ Bỏ qua kích hoạt nút Auto (190, 140).")
            else:
                self.after(0, self.log_info, f"👉 [{mode_name} - Bước 2.6] Tap nút Auto (190, 140) [Kỹ năng: '{curr_skill}']")
                self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell input tap 190 140"])
                if self._sleep_card_D(0.3): return
                if should_stop(): return
        else:
            self.after(0, self.log_info, f"ℹ️ [{mode_name}] Bỏ qua Giai đoạn 2...")

        if not run_stage_1 and not run_stage_2:
            self.after(0, self.log_info, f"ℹ️ [{mode_name}] Bỏ qua Giai đoạn 1 & 2 ➔ Bắt đầu Vòng lặp Giai đoạn 4 ➔ 7...")

        # --- LẶP GIAI ĐOẠN 4, 5, 6, 7 ---
        max_loops = loop_count if (loop_count and loop_count > 0) else (3 if "Chặng 2" in mode_name else 0)
        loop_idx = 0
        while not should_stop():
            loop_idx += 1
            if max_loops > 0:
                self.after(0, self.log_info, f"🔄 [{mode_name}] Khởi chạy Vòng lặp Giai Đoạn 4 ➔ 7 (Lượt {loop_idx}/{max_loops})...")
            else:
                self.after(0, self.log_info, f"🔄 [{mode_name}] Khởi chạy Vòng lặp Giai Đoạn 4 ➔ 7 (Lượt {loop_idx})...")

            # === GIAI ĐOẠN 4 ===
            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 4.1: Vuốt UP_RIGHT tìm f_tieptheo.png...")
            _swipe_dpad_until_tieptheo("UP_RIGHT", timeout_sec=8.0)
            
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 4.2: Tap f_tieptheo.png mỗi 0.5s đến khi mất...")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.0)

            # Kích hoạt Kỹ Năng theo Menu Kỹ Năng Card D (chế độ Thường khi leo đài Nhị Kiều)
            self._execute_card_d_skill_thuong(dnconsole_path, tab_index, log_tag=f"Nhị Kiều - {mode_name}", is_nhi_kieu=True)

            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 4.3: Quét f_vaotran.png...")
            _wait_for_f_vaotran()

            # 4.4: Tap f_tieptheo.png mỗi 0.3s đến khi mất ➔ Hoãn 0.5s
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 4.4: Tap f_tieptheo.png mỗi 0.3s đến khi mất")
            _tap_tieptheo(tap_interval=0.3, delay_after=0.5)

            # === GIAI ĐOẠN 5 ===
            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 5.1: Vuốt UP_RIGHT trong 0.5s...")
            _swipe_dpad_direction("UP_RIGHT", 500)
            if self._sleep_card_D(0.2): return

            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 5.2: Vuốt UP_LEFT tìm f_tieptheo.png...")
            _swipe_dpad_until_tieptheo("UP_LEFT", timeout_sec=8.0)

            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 5.3: Tap f_tieptheo.png mỗi 0.5s đến khi mất...")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.0)

            # Kích hoạt Kỹ Năng theo Menu Kỹ Năng Card D (chế độ Thường khi leo đài Nhị Kiều)
            self._execute_card_d_skill_thuong(dnconsole_path, tab_index, log_tag=f"Nhị Kiều - {mode_name}", is_nhi_kieu=True)

            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 5.4: Quét f_vaotran.png...")
            _wait_for_f_vaotran()

            # 5.5: Tap f_tieptheo.png mỗi 0.3s đến khi mất ➔ Hoãn 0.5s
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 5.5: Tap f_tieptheo.png mỗi 0.3s đến khi mất")
            _tap_tieptheo(tap_interval=0.3, delay_after=0.5)

            # === GIAI ĐOẠN 6 ===
            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 6.1: Vuốt UP_LEFT trong 0.5s...")
            _swipe_dpad_direction("UP_LEFT", 500)
            if self._sleep_card_D(0.2): return

            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 6.2: Vuốt UP_RIGHT tìm f_tieptheo.png...")
            _swipe_dpad_until_tieptheo("UP_RIGHT", timeout_sec=8.0)

            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 6.3: Tap f_tieptheo.png mỗi 0.5s đến khi mất...")
            _tap_tieptheo(tap_interval=0.5, delay_after=0.0)

            # Kích hoạt Kỹ Năng theo Menu Kỹ Năng Card D (chế độ Thường khi leo đài Nhị Kiều)
            self._execute_card_d_skill_thuong(dnconsole_path, tab_index, log_tag=f"Nhị Kiều - {mode_name}", is_nhi_kieu=True)

            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 6.4: Quét f_vaotran.png...")
            _wait_for_f_vaotran()

            # 6.5: Tap f_tieptheo.png mỗi 0.3s đến khi mất ➔ Hoãn 0.5s
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 6.5: Tap f_tieptheo.png mỗi 0.3s đến khi mất")
            _tap_tieptheo(tap_interval=0.3, delay_after=0.5)

            # === GIAI ĐOẠN 7: HOÀN THÀNH ===
            if should_stop(): return
            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 7.1: Vuốt UP_RIGHT trong 2.0s...")
            _swipe_dpad_direction("UP_RIGHT", 2000)
            if self._sleep_card_D(0.2): return

            self.after(0, self.log_info, f"👉 [{mode_name} - Lượt {loop_idx}] Giai Đoạn 7.2: Vuốt DOWN_RIGHT trong 1.0s...")
            _swipe_dpad_direction("DOWN_RIGHT", 1000)
            if self._sleep_card_D(0.5): return

            # 7.3: Kiểm tra hoàn thành theo mốc tầng
            self.after(0, self.log_info, f"👁️ [{mode_name} - Lượt {loop_idx}] Giai Đoạn 7.3: Quét kiểm tra hoàn thành...")
            if target_finish_img:
                target_img = target_finish_img
            else:
                target_img = "card_d/nhikieu/d_dinh.png"
            
            found_finish = False
            # Nếu có số lượt lặp tối đa (ví dụ 3 lần), chỉ quét ở lượt cuối cùng để tránh thoát nhầm khi chưa tới đỉnh
            if max_loops == 0 or loop_idx >= max_loops:
                start_chk = time.time()
                while time.time() - start_chk < 3.0:
                    if should_stop(): return
                    fin_x, fin_y = self._find_template_on_screen(
                        dnconsole_path, tab_index, target_img,
                        threshold=0.80, region=(1060, 0, 1280, 40)
                    )
                    if fin_x is not None and fin_y is not None:
                        self.after(0, self.log_info, f"🎯 Phát hiện '{target_img}' tại ({fin_x}, {fin_y})! Hoàn thành dứt điểm mốc '{mode_name}'.")
                        found_finish = True
                        if "Chặng 2" in mode_name:
                            self.send_telegram_alert(
                                "🏯 [NHỊ KIỀU]\n🎯 Hoàn Thành Nhị Kiều !",
                                capture_screenshot=True,
                                tab_index=str(tab_index),
                                is_card_d=True,
                                delay_seconds=3.0
                            )
                        elif "d_dinh" in target_img:
                            self.send_telegram_alert(
                                "🏯 [NHỊ KIỀU]\n🎯 Đã Lên Đỉnh Tháp ( Vào Đánh Đi ) !",
                                capture_screenshot=True,
                                tab_index=str(tab_index),
                                is_card_d=True,
                                delay_seconds=3.0
                            )
                        break
                    if self._sleep_card_D(0.5): return

            if found_finish:
                self.after(0, self.log_info, f"✅ [Card D - Nhị Kiều] Đã hoàn thành mốc '{mode_name}' thành công!")
                break

            if max_loops > 0 and loop_idx >= max_loops:
                self.after(0, self.log_info, f"✅ [Card D - Nhị Kiều] Đã hoàn thành đủ {max_loops} lượt lặp cho mốc '{mode_name}' thành công!")
                if "Chặng 2" in mode_name and not found_finish:
                    self.send_telegram_alert(
                        "🏯 [NHỊ KIỀU]\n🎯 Hoàn Thành Nhị Kiều !",
                        capture_screenshot=True,
                        tab_index=str(tab_index),
                        is_card_d=True,
                        delay_seconds=3.0
                    )
                break

            # -------------------------------------------------------------
            # 7.4: KIỂM TRA ĐỘ ĐẦY ĐỦ ĐỘI HÌNH KHI CHƯA LÊN ĐỈNH
            # (Chỉ thực thi khi ô 'Tổ Đội' var_D2 được tích và Danh Sách B có người)
            # -------------------------------------------------------------
            if hasattr(self, 'var_D2') and self.var_D2.get():
                list_B = list(getattr(self, 'list_E_B', []))
                if list_B:
                    self.after(0, self.log_info, f"👥 [{mode_name} - Tầng {loop_idx}] Chưa lên đỉnh ➔ Mở bảng Đội kiểm tra thành viên ({len(list_B)} thành viên)...")
                    if self._open_team_panel(dnconsole_path, tab_index, log_tag=f"{mode_name} - Tầng {loop_idx}", stop_check=should_stop):
                        present_members, missing_members, target_count = self._scan_team_members_presence(dnconsole_path, tab_index, list_B, stop_check=should_stop)

                        if len(present_members) >= target_count:
                            self.after(0, self.log_info, f"✅ [{mode_name} - Tầng {loop_idx}] Đội hình đã ĐỦ {len(present_members)}/{target_count} thành viên ({', '.join(present_members)}) ➔ Tiếp tục tầng kế tiếp!")
                            self._close_team_panel(dnconsole_path, tab_index, log_tag=f"{mode_name} - Tầng {loop_idx}", stop_check=should_stop)
                        else:
                            # THIẾU THÀNH VIÊN: Gửi Telegram cảnh báo & Tự kích hoạt Tạm Dừng
                            warn_msg = (
                                f"🏯 [NHỊ KIỀU - THIẾU ĐỘI]\n"
                                f"⚠️ Phát Hiện Thiếu Thành Viên Ở Tầng {loop_idx}!\n"
                                f"👥 Hiện có: {len(present_members)}/{target_count} ({', '.join(present_members) if present_members else 'Trống'})\n"
                                f"❌ Thiếu: {', '.join(missing_members)}\n"
                                f"⏸️ Đã Kích Hoạt Tạm Dừng!"
                            )
                            self.after(0, self.log_error, f"⚠️ [{mode_name} - Tầng {loop_idx}] Đội hình THIẾU THÀNH VIÊN ({len(present_members)}/{target_count}, thiếu: {', '.join(missing_members)}) ➔ Kích hoạt TẠM DỪNG & Gửi Telegram!")
                            self.send_telegram_alert(
                                warn_msg,
                                capture_screenshot=True,
                                tab_index=str(tab_index),
                                is_card_d=True
                            )

                            # Tự động bật Tạm Dừng trên biến và đồng bộ UI Desktop / Web
                            self.var_pause_D.set(True)
                            if hasattr(self, '_on_pause_D_toggled'):
                                self.after(0, self._on_pause_D_toggled)

                            # Treo luồng chờ người dùng can thiệp và nhả ô Tạm Dừng
                            self.after(0, self.log_info, f"⏸️ [{mode_name} - Tầng {loop_idx}] Đang tạm dừng chờ bạn bổ sung thành viên. Sau khi xong, hãy nhả/bỏ tích ô Tạm Dừng để chạy tiếp...")
                            self._should_stop_card_D()  # Chờ người dùng nhả ô Tạm Dừng (tái sử dụng cơ chế tạm dừng chuẩn)

                            if should_stop(): return
                            self.after(0, self.log_info, f"▶️ [{mode_name} - Tầng {loop_idx}] Đã nhận lệnh chạy tiếp ➔ Đóng bảng Đội & tiếp tục tầng kế tiếp!")
                            self._close_team_panel(dnconsole_path, tab_index, log_tag=f"{mode_name} - Tầng {loop_idx}", stop_check=should_stop)
            else:
                self.after(0, self.log_info, f"ℹ️ [{mode_name} - Tầng {loop_idx}] Ô 'Tổ Đội' không được tích ➔ Bỏ qua kiểm tra đội giữa tầng.")

    def _detect_nhi_kieu_start_position(self, dnconsole_path: str, tab_index: str) -> str:
        """
        Quét tuần tự 4 mốc ảnh tại góc trên bên phải màn hình (ROI 1060, 0, 1280, 40, ngưỡng 80%):
        1. d_thongdao.png -> 'THONG_DAO' (Giai đoạn 1: Ngoài sân vào Đại Điện)
        2. d_daidien.png  -> 'DAI_DIEN'  (Giai đoạn 2: Đại Điện vào Thang Tháp)
        3. d_thap.png     -> 'THANG_THAP' (Vòng lặp GĐ 4->7: Leo đài các tầng)
        4. d_dinh.png     -> 'DINH_THAP'  (Đỉnh Tháp 10 & Chuyển tiếp Tháp 11)
        Mỗi ảnh quét tối đa 1.2s. Ngay khi phát hiện ảnh nào trước thì ngắt quét ngay lập tức.
        Nếu sau 2 chu kỳ quét vẫn không thấy -> Fallback về 'THONG_DAO'.
        """
        scan_list = [
            ("card_d/nhikieu/d_thongdao.png", "THONG_DAO", "🎯 [Nhị Kiều Auto] Phát hiện Thông Đạo (Ngoài sân) ➔ Bắt đầu từ Giai Đoạn 1!"),
            ("card_d/nhikieu/d_daidien.png", "DAI_DIEN", "🎯 [Nhị Kiều Auto] Phát hiện Đại Điện ➔ Bắt đầu từ Giai Đoạn 2!"),
            ("card_d/nhikieu/d_thap.png", "THANG_THAP", "🎯 [Nhị Kiều Auto] Phát hiện Thang Tháp ➔ Bắt đầu từ Vòng Lặp Leo Đài!"),
            ("card_d/nhikieu/d_dinh.png", "DINH_THAP", "🎯 [Nhị Kiều Auto] Phát hiện Đỉnh Tháp ➔ Bắt đầu từ Đỉnh Tháp & Tháp 11!"),
        ]

        self.after(0, self.log_info, "👁️ [Nhị Kiều Auto] Bắt đầu quét tuần tự nhận diện vị trí xuất phát (ROI 1060, 0, 1280, 40)...")
        for cycle in range(1, 3):
            if self._should_stop_card_D(): return "THONG_DAO"
            if cycle > 1:
                self.after(0, self.log_info, "🔄 [Nhị Kiều Auto] Chưa nhận diện được vị trí, đang thử lại lượt quét thứ 2...")

            for img_path, pos_key, log_msg in scan_list:
                if self._should_stop_card_D(): return "THONG_DAO"
                t_start = time.time()
                while time.time() - t_start < 1.2:
                    if self._should_stop_card_D(): return "THONG_DAO"
                    x, y = self._find_template_on_screen(
                        dnconsole_path, tab_index, img_path,
                        threshold=0.80, region=(1060, 0, 1280, 40)
                    )
                    if x is not None and y is not None:
                        self.after(0, self.log_info, log_msg)
                        return pos_key
                    if self._sleep_card_D(0.3): return "THONG_DAO"

        self.after(0, self.log_info, "⚠️ [Nhị Kiều Auto] Không nhận diện được vị trí map cụ thể ➔ Mặc định bắt đầu từ Thông Đạo (Giai Đoạn 1).")
        return "THONG_DAO"

    def _run_nhi_kieu_tang_auto(self, dnconsole_path: str, tab_index: str, **kwargs):
        """
        QUY TRÌNH MỐC AUTO (NHỊ KIỀU):
        - Tự động nhận diện vị trí xuất phát:
          + Thông Đạo -> Chạy Chặng 1 từ Giai đoạn 1.
          + Đại Điện  -> Chạy Chặng 1 từ Giai đoạn 2 (bỏ qua Giai đoạn 1).
          + Thang Tháp -> Chạy Chặng 1 từ Vòng lặp GĐ 4->7 (bỏ qua GĐ 1 & 2).
          + Đỉnh Tháp -> Bỏ qua toàn bộ Chặng 1, chạy thẳng từ Đỉnh Tháp 10.
        - Chặng 1 (Trệt / Đại Điện / Tháp ➔ Đỉnh 10):
          + Chạy theo vị trí nhận diện đến khi thấy d_dinh.png ➔ Hoãn 5.0s.
        - PHẦN 1: Tại Đỉnh Tháp 10:
          + Nếu chọn 'Đánh Tay' + tích 'Tổ Đội': Bỏ qua Quân Sư 1 và Kỹ Năng Đỉnh 10 để người chơi tự đánh tay.
          + Nếu là các kỹ năng khác: Kiểm tra Đội, mời nếu thiếu & gán Quân Sư lần 1 (Card E) ➔ Hoãn 5.0s ➔ Kích hoạt Kỹ Năng Auto Đỉnh 10.
        - PHẦN 2: Chuyển tiếp Tháp 11:
          + Quét d_thap.png mỗi 1.0s (Ưu tiên quét tháp trước, hỗ trợ Realtime Switch đổi chiêu giữa chừng tại Đỉnh 10).
          + Thấy d_thap.png ➔ Báo Telegram. Nếu 'Đánh Tay' + 'Tổ Đội' ➔ Bỏ qua hoãn 20s; ngược lại hoãn 20.0s.
        - PHẦN 3: Xử lý tại Tháp 11:
          + Nếu 'Đánh Tay' + 'Tổ Đội': Bỏ qua PHẦN 3.
          + Nếu các kỹ năng khác: Kiểm tra Đội, mời nếu thiếu & gán Quân Sư lần 2 (Card E).
        - Hoãn đệm 5.0s trước khi leo Chặng 2.
        - PHẦN 4: Chặng 2 (Tháp 11 ➔ Tháp 14): Chạy vòng lặp Giai đoạn 4 ➔ 7 đúng 3 lượt ➔ Hoàn Thành Nhị Kiều!
        """
        if self._should_stop_card_D(): return

        tag_log = "Nhị Kiều Auto"

        # ---------------- TỰ ĐỘNG NHẬN DIỆN VỊ TRÍ XUẤT PHÁT ----------------
        start_pos = self._detect_nhi_kieu_start_position(dnconsole_path, tab_index)
        if self._should_stop_card_D(): return

        if start_pos == "DINH_THAP":
            start_desc = "Đỉnh Tháp 10"
            self.after(0, self.log_info, f"🏰 [{tag_log}] Đã ở Đỉnh Tháp 10 ➔ Bỏ qua toàn bộ Chặng 1, chạy thẳng Đỉnh Tháp 10 & Chuyển tiếp Tháp 11!")
            self.after(0, self.log_info, f"⏳ [{tag_log}] Đã ở Đỉnh Tháp 10 ➔ Hoãn 5.0s trước khi chuyển tiếp Tháp 11...")
            if self._sleep_card_D(5.0): return
        else:
            # Xác định các giai đoạn cần chạy ở Chặng 1
            if start_pos == "THONG_DAO":
                start_desc = "Trệt (Thông Đạo)"
                run_g1, run_g2 = True, True
            elif start_pos == "DAI_DIEN":
                start_desc = "Đại Điện"
                run_g1, run_g2 = False, True
            elif start_pos == "THANG_THAP":
                start_desc = "Thang Tháp / Leo Đài"
                run_g1, run_g2 = False, False
            else:
                run_g1, run_g2 = True, True

            # ---------------- CHẶNG 1: TRỆT / ĐẠI ĐIỆN / THÁP ➔ ĐỈNH THÁP 10 ----------------
            self.after(0, self.log_info, f"🏰 [{tag_log} - Chặng 1] Bắt đầu Chặng 1: {start_desc} ➔ Đỉnh Tháp 10...")
            self._run_nhi_kieu_leo_thap_core(
                dnconsole_path, tab_index, loop_count=0, mode_name="Auto - Chặng 1",
                run_stage_1=run_g1, run_stage_2=run_g2, target_finish_img="card_d/nhikieu/d_dinh.png"
            )
            if self._should_stop_card_D(): return

            self.after(0, self.log_info, f"⏳ [{tag_log}] Đã lên Đỉnh Tháp 10 ➔ Hoãn 5.0s trước khi thao tác Quân Sư...")
            if self._sleep_card_D(5.0): return

        # Hàm con nội bộ thực thi tại Đỉnh Tháp 10
        def _execute_dinh_10_actions() -> bool:
            # ---------------- THAO TÁC QUÂN SƯ LẦN 1 (ĐỈNH THÁP 10 - CARD E) ----------------
            if hasattr(self, 'var_D2') and self.var_D2.get():
                list_B = list(getattr(self, 'list_E_B', []))
                if list_B:
                    self.after(0, self.log_info, f"👑 [{tag_log}] Khởi chạy kiểm tra Đội & Gán Quân Sư lần 1 (Đỉnh Tháp 10 - Card E)...")
                    self._run_card_E_action_1(
                        dnconsole_path, tab_index, list_B,
                        assign_quan_su=True,
                        log_tag=f"{tag_log} - Đỉnh 10",
                        stop_check=self._should_stop_card_D
                    )
                    if self._should_stop_card_D(): return True
                    # Hoãn 5 giây sau khi thao tác quân sư lần 1 xong
                    self.after(0, self.log_info, f"⏳ [{tag_log}] Hoãn 5.0s sau Quân Sư lần 1 trước khi kích hoạt Kỹ Năng Auto...")
                    if self._sleep_card_D(5.0): return True
                else:
                    self.after(0, self.log_warning, f"⚠️ [{tag_log}] Ô 'Tổ Đội' được tích nhưng Danh Sách B (Card E) đang trống! Bỏ qua kiểm tra đội & Quân Sư lần 1.")
            else:
                self.after(0, self.log_info, f"ℹ️ [{tag_log}] Ô 'Tổ Đội' KHÔNG được tích ➔ Bỏ qua Thao tác Quân Sư lần 1 (Đỉnh Tháp 10).")

            # ---------------- KÍCH HOẠT KỸ NĂNG AUTO ĐỈNH 10 ----------------
            self.after(0, self.log_info, f"🔄 [{tag_log}] Kích hoạt Kỹ Năng theo Menu Kỹ Năng Card D (Chuyên biệt Auto Đỉnh 10)...")
            self._execute_card_d_skill_auto(dnconsole_path, tab_index, log_tag=f"{tag_log} - Đỉnh 10")
            if self._should_stop_card_D(): return True
            return False

        # Kiểm tra điều kiện mốc Đánh Tay + Tổ Đội tại Đỉnh Tháp 10
        is_danh_tay = (hasattr(self, 'var_D_skill') and self.var_D_skill.get() == "Đánh Tay")
        has_to_doi = (hasattr(self, 'var_D2') and self.var_D2.get())
        already_executed_dinh10 = False

        if is_danh_tay and has_to_doi:
            self.after(0, self.log_info, f"ℹ️ [{tag_log}] Đang chọn 'Đánh Tay' & có tích 'Tổ Đội' ➔ Bỏ qua Quân Sư lần 1 và Kỹ Năng Đỉnh 10, chuyển thẳng sang quét Tháp 11...")
        else:
            if _execute_dinh_10_actions(): return
            already_executed_dinh10 = True

        # ---------------- PHẦN 2: CHUYỂN TIẾP THÁP 11 ----------------
        self.after(0, self.log_info, f"👁️ [{tag_log}] Quét tìm 'card_d/nhikieu/d_thap.png' (80%, ROI 1060, 0, 1280, 40) mỗi 1.0s...")
        while not self._should_stop_card_D():
            # 1. ƯU TIÊN 1: Quét tìm d_thap.png TRƯỚC
            t11_x, t11_y = self._find_template_on_screen(
                dnconsole_path, tab_index, "card_d/nhikieu/d_thap.png",
                threshold=0.80, region=(1060, 0, 1280, 40)
            )
            if t11_x is not None and t11_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_d/nhikieu/d_thap.png' tại ({t11_x}, {t11_y}) ➔ Bắt đầu Tháp 11!")
                self.send_telegram_alert(
                    "🏯 [NHỊ KIỀU]\n🎯 Bắt Đầu Tháp 11 !",
                    capture_screenshot=True,
                    tab_index=str(tab_index),
                    is_card_d=True,
                    delay_seconds=3.0
                )
                break

            # 2. ƯU TIÊN 2: Nếu chưa thấy d_thap.png (vẫn đang ở Đỉnh 10) ➔ Giám sát đổi kỹ năng realtime từ 'Đánh Tay' sang chiêu khác
            if not already_executed_dinh10:
                curr_sk = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"
                if curr_sk != "Đánh Tay":
                    self.after(0, self.log_info, f"🔄 [{tag_log} - Realtime] Phát hiện đổi kỹ năng từ 'Đánh Tay' sang '{curr_sk}' ➔ Kích hoạt lại quy trình Đỉnh 10 (Kiểm tra Đội, Quân Sư 1 & Kỹ Năng Auto)!")
                    if _execute_dinh_10_actions(): return
                    already_executed_dinh10 = True
                    self.after(0, self.log_info, f"👁️ [{tag_log}] Hoàn tất Đỉnh 10 ➔ Tiếp tục quét tìm 'card_d/nhikieu/d_thap.png'...")

            if self._sleep_card_D(1.0): return

        if self._should_stop_card_D(): return

        # Xác định trạng thái kỹ năng khi vào Tháp 11
        curr_sk_t11 = self.var_D_skill.get() if hasattr(self, 'var_D_skill') else "Buff HP / SP"
        is_dt_td = (curr_sk_t11 == "Đánh Tay" and hasattr(self, 'var_D2') and self.var_D2.get())

        # Chuẩn bị Tháp 11: Đếm hoãn 20s (BỎ QUA NẾU LÀ ĐÁNH TAY + TỔ ĐỘI)
        if is_dt_td:
            self.after(0, self.log_info, f"ℹ️ [{tag_log}] Đang chọn 'Đánh Tay' & có tích 'Tổ Đội' ➔ Bỏ qua hoãn 20s chuẩn bị Tháp 11.")
        else:
            self.after(0, self.log_info, f"⏳ [{tag_log}] Hoãn 20.0s chuẩn bị Tháp 11...")
            if self._sleep_card_D(20.0): return

        # ---------------- PHẦN 3: KIỂM TRA ĐỦ ĐỘI & QUÂN SƯ LẦN 2 (THÁP 11 - CARD E) ----------------
        if is_dt_td:
            self.after(0, self.log_info, f"ℹ️ [{tag_log}] Đang chọn 'Đánh Tay' & có tích 'Tổ Đội' ➔ Bỏ qua PHẦN 3 (Kiểm tra Đội & Quân Sư lần 2)!")
        else:
            if hasattr(self, 'var_D2') and self.var_D2.get():
                list_B = list(getattr(self, 'list_E_B', []))
                if list_B:
                    self.after(0, self.log_info, f"👑 [{tag_log}] Khởi chạy kiểm tra Đội & Gán Quân Sư lần 2 (Tháp 11 - Card E)...")
                    self._run_card_E_action_1(
                        dnconsole_path, tab_index, list_B,
                        assign_quan_su=True,
                        log_tag=f"{tag_log} - Tháp 11",
                        stop_check=self._should_stop_card_D
                    )
                else:
                    self.after(0, self.log_warning, f"⚠️ [{tag_log}] Ô 'Tổ Đội' được tích nhưng Danh Sách B (Card E) đang trống! Bỏ qua kiểm tra đội & Quân Sư lần 2.")
            if self._should_stop_card_D(): return

        # THỜI GIAN HOÃN 5.0S TRƯỚC CHẶNG 2: VẪN GIỮ LẠI CHO TẤT CẢ CÁC TRƯỜNG HỢP
        self.after(0, self.log_info, f"⏳ [{tag_log}] Hoãn 5.0s trước khi bắt đầu Chặng 2 (Tháp 11 ➔ 14)...")
        if self._sleep_card_D(5.0): return

        # ---------------- CHẶNG 2: THÁP 11 ➔ THÁP 14 ----------------
        self.after(0, self.log_info, f"🚀 [{tag_log} - Chặng 2] Bắt đầu Chặng 2: Tháp 11 ➔ Tháp 14 (Lặp lại đúng 3 lần, Vòng lặp GĐ 4-7 với Chuỗi Buff)...")
        self._run_nhi_kieu_leo_thap_core(
            dnconsole_path, tab_index, loop_count=3, mode_name="Auto - Chặng 2",
            run_stage_1=False, run_stage_2=False, target_finish_img="card_d/nhikieu/d_dinh.png"
        )
        if self._should_stop_card_D(): return

        self.after(0, self.log_info, "🎉 [Nhị Kiều] Hoàn Thành Nhị Kiều (Tháp 14)!")
        self.after(0, lambda: self._send_notification("🎉 Hoàn Thành Nhị Kiều", "Đã hoàn thành toàn bộ leo tháp Nhị Kiều đến Tháp 14 thành công!"))

    def _run_nhi_kieu_tang(self, dnconsole_path: str, tab_index: str, selected_tang: str = "Auto", **kwargs):
        """Wrapper khởi chạy quy trình Nhị Kiều Auto (Card D). Tham số selected_tang hiện không dùng (luôn là 'Auto')."""
        if self._should_stop_card_D(): return
        self.after(0, self.log_info, "🚀 [Card D - Nhị Kiều] Khởi chạy quy trình Nhị Kiều Auto...")
        self._run_nhi_kieu_tang_auto(dnconsole_path, tab_index)

    # =========================================================================
    # 🔓 [KẾT THÚC KHỐI HOẠT ĐỘNG]: CARD D (40 NPC / NHỊ KIỀU)
    # =========================================================================
    def _get_emulator_screen_size(self, dnconsole_path: str, tab_index: str) -> tuple:
        """Tự động quét đo độ phân giải thực tế (Width, Height) của giả lập LDPlayer qua ADB wm size"""
        try:
            res = self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell wm size"], text=True)
            if res and res.stdout:
                match = re.search(r'(\d+)x(\d+)', res.stdout)
                if match:
                    w, h = int(match.group(1)), int(match.group(2))
                    if w < h:
                        w, h = h, w
                    return w, h
        except Exception:
            pass
        return 1280, 720

    # =========================================================================
    # 📬 TỰ ĐỘNG NHẬN THƯ (CARD NGÀY)
    # =========================================================================
    def _on_nhan_thu_toggled(self):
        """Xử lý khi người dùng bật / tắt ô tích Nhận Thư"""
        is_enabled = bool(self.var_nhan_thu.get()) if hasattr(self, 'var_nhan_thu') else False
        moc_gio = self.combo_nhan_thu_time.get() if hasattr(self, 'combo_nhan_thu_time') else "Tất Cả"
        if is_enabled:
            if hasattr(self, '_event_nhan_thu'):
                self._event_nhan_thu.set()
            self.after(0, self.log_info, f"📬 [CARD NGÀY] Đã bật Tự Động Nhận Thư (Mốc: {moc_gio}) - Hệ thống sẽ tự động thực hiện khi đến giờ.")
        else:
            if hasattr(self, '_event_nhan_thu'):
                self._event_nhan_thu.clear()
            # Ngắt sleep đang chờ trong luồng ngầm ngay lập tức
            if hasattr(self, '_stop_mail_sleep'):
                self._stop_mail_sleep.set()
            self.after(0, self.log_info, "📬 [CARD NGÀY] Đã tắt Tự Động Nhận Thư.")
        self.save_config()

    def _on_nhan_thu_combo_changed(self, choice: str):
        """Xử lý khi người dùng thay đổi mốc giờ nhận thư từ giao diện"""
        self.save_config()
        if hasattr(self, 'var_nhan_thu') and self.var_nhan_thu.get():
            self.after(0, self.log_info, f"📬 [CARD NGÀY] Đã chuyển đổi mốc nhận thư sang: '{choice}'.")

    def _execute_nhan_thu(self, dnconsole_path: str, tab_index: str, time_slot: str = "Tự Động") -> bool:
        """QUY TRÌNH NHẬN THƯ (BƯỚC 1 ➔ BƯỚC 2 ➔ BƯỚC 3 ➔ BƯỚC 4)"""
        if getattr(self, '_is_nhan_thu_running', False):
            self.after(0, self.log_info, "ℹ️ [CARD NGÀY] Tiến trình Nhận Thư đang chạy, vui lòng chờ...")
            return False

        if self.stop_requested:
            return False

        self._is_nhan_thu_running = True

        def _tap(x: int, y: int, delay: float = 0.4):
            if self.stop_requested:
                return
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"shell input tap {x} {y}"])
            time.sleep(delay)

        try:
            self.after(0, self.log_info, f"📬 [CARD NGÀY ({time_slot})] Bắt đầu thực thi quy trình Nhận Thư...")

            # =========================================================================
            # BƯỚC 1: QUÉT ĐÓNG QUẢNG CÁO / POPUP
            # =========================================================================
            if self.stop_requested:
                self.after(0, self.log_info, "🛑 [CARD NGÀY] Đã nhận lệnh Dừng, hủy thao tác Nhận Thư.")
                return False

            self.after(0, self.log_info, "👁️ [CARD NGÀY - Bước 1] Quét tìm 'card_top/login/login_x.png' (75%, ROI 990,50,1165,200)...")
            self._close_login_x_popup(dnconsole_path, tab_index, "CARD NGÀY")

            # =========================================================================
            # BƯỚC 2: MỞ MENU VÀ BẤM NÚT THƯ (QUÉT ĐẾN KHI THẤY NÚT MENU)
            # =========================================================================
            if self.stop_requested:
                self.after(0, self.log_info, "🛑 [CARD NGÀY] Đã nhận lệnh Dừng, hủy thao tác Nhận Thư.")
                return False

            self.after(0, self.log_info, "👁️ [CARD NGÀY - Bước 2] Quét tìm nút Thư 'card_top/login/login_thu.png' (80%, ROI 735,405,1280,720)...")
            v_x, v_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_thu.png", threshold=0.80, region=(735, 405, 1280, 720))
            if v_x is not None and v_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện nút Thư tại ({v_x}, {v_y})! Tap trực tiếp")
                _tap(v_x, v_y, 0.4)
            else:
                self.after(0, self.log_info, "👉 Chưa thấy nút Thư ➔ Quét tìm nút Menu 'card_top/login/login_menu.png' (80%, ROI 1190,640,1280,720) cho đến khi thấy...")
                menu_x, menu_y = None, None
                last_log_wait = 0
                while not self.stop_requested:
                    # 1. Quét tìm nút Menu
                    menu_x, menu_y = self._find_template_on_screen(
                        dnconsole_path, tab_index, "card_top/login/login_menu.png",
                        threshold=0.80, region=(1190, 640, 1280, 720)
                    )
                    if menu_x is not None and menu_y is not None:
                        break

                    # 2. Đồng thời kiểm tra nếu nút Thư bất ngờ xuất hiện (Menu đã mở sẵn)
                    chk_thu_x, chk_thu_y = self._find_template_on_screen(
                        dnconsole_path, tab_index, "card_top/login/login_thu.png",
                        threshold=0.80, region=(735, 405, 1280, 720)
                    )
                    if chk_thu_x is not None and chk_thu_y is not None:
                        v_x, v_y = chk_thu_x, chk_thu_y
                        break

                    # 3. Quét đóng popup nếu có che màn hình
                    pop_x, pop_y = self._find_template_on_screen(
                        dnconsole_path, tab_index, "card_top/login/login_x.png",
                        threshold=0.75, region=(990, 50, 1165, 200)
                    )
                    if pop_x is not None and pop_y is not None:
                        _tap(pop_x, pop_y, 0.4)

                    now = time.time()
                    if now - last_log_wait >= 5.0:
                        last_log_wait = now
                        self.after(0, self.log_info, "⏳ [CARD NGÀY - Bước 2] Đang quét chờ nút Menu 'login_menu.png' xuất hiện...")
                    time.sleep(0.5)

                if self.stop_requested:
                    self.after(0, self.log_info, "🛑 [CARD NGÀY] Đã nhận lệnh Dừng, hủy thao tác Nhận Thư.")
                    return False

                if v_x is not None and v_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện nút Thư tại ({v_x}, {v_y})! Tap trực tiếp")
                    _tap(v_x, v_y, 0.4)
                elif menu_x is not None and menu_y is not None:
                    self.after(0, self.log_info, f"🎯 Phát hiện nút Menu tại ({menu_x}, {menu_y})! Tap mở menu")
                    _tap(menu_x, menu_y, 0.4)

                    if self.stop_requested:
                        self.after(0, self.log_info, "🛑 [CARD NGÀY] Đã nhận lệnh Dừng, hủy thao tác Nhận Thư.")
                        return False

                    self.after(0, self.log_info, "👁️ Quét lại nút Thư 'card_top/login/login_thu.png' (80%)...")
                    v_x, v_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_thu.png", threshold=0.80, region=(735, 405, 1280, 720))
                    if v_x is not None and v_y is not None:
                        self.after(0, self.log_info, f"🎯 Phát hiện nút Thư tại ({v_x}, {v_y})! Tap")
                        _tap(v_x, v_y, 0.4)
                    else:
                        self.after(0, self.log_info, "⚠️ [CARD NGÀY - Bước 2] Chưa quét thấy biểu tượng nút Thư 'login_thu.png' sau khi mở menu ➔ Dừng nhận thư.")
                        return False

            # =========================================================================
            # BƯỚC 3: BẤM CHỌN NHẬN THƯ & ĐÓNG BẢNG
            # =========================================================================
            if self.stop_requested:
                self.after(0, self.log_info, "🛑 [CARD NGÀY] Đã nhận lệnh Dừng, hủy thao tác Nhận Thư.")
                return False

            self.after(0, self.log_info, "👉 [CARD NGÀY - Bước 3] Tap tọa độ (365, 575)")
            _tap(365, 575, 0.4)

            self.after(0, self.log_info, "👉 [CARD NGÀY - Bước 3] Tap tọa độ (540, 575)")
            _tap(540, 575, 0.4)

            self.after(0, self.log_info, "👁️ [CARD NGÀY - Bước 3] Quét tìm 'card_top/login/login_x.png' (75%, ROI 990,50,1165,200)...")
            lx_x, lx_y = self._find_template_on_screen(dnconsole_path, tab_index, "card_top/login/login_x.png", threshold=0.75, region=(990, 50, 1165, 200))
            if lx_x is not None and lx_y is not None:
                self.after(0, self.log_info, f"🎯 Phát hiện 'card_top/login/login_x.png' tại ({lx_x}, {lx_y})! Tap đóng bảng thư")
                _tap(lx_x, lx_y, 0.4)

            self.after(0, self.log_info, "👉 [CARD NGÀY - Bước 3] Tap tọa độ (1213, 648)")
            _tap(1213, 648, 0.4)

            self.after(0, self.log_info, f"✅ [CARD NGÀY ({time_slot})] Đã hoàn thành toàn bộ thao tác Nhận Thư!")

            # =========================================================================
            # BƯỚC 4: QUẢN LÝ NHẢ Ô TÍCH THÔNG MINH
            # =========================================================================
            selected_mode = self.combo_nhan_thu_time.get() if hasattr(self, 'combo_nhan_thu_time') else "Tất Cả"
            if selected_mode == "Tất Cả" and time_slot in ["12H01", "18H01"]:
                self.after(0, self.log_info, f"ℹ️ [CARD NGÀY] Chế độ 'Tất Cả' đang bật ➔ Giữ ô tích để tiếp tục đón mốc tiếp theo trong ngày.")
            else:
                if hasattr(self, 'var_nhan_thu'):
                    self.after(0, lambda: self.var_nhan_thu.set(False))
                if hasattr(self, '_event_nhan_thu'):
                    self._event_nhan_thu.clear()
                self.after(0, self.save_config)
            return True
        except Exception as e:
            self.after(0, self.log_error, f"❌ [CARD NGÀY] Lỗi tiến trình Nhận Thư: {e}")
            return False
        finally:
            self._is_nhan_thu_running = False

    def _is_tool_busy_with_activities(self) -> tuple[bool, str]:
        """Kiểm tra xem tool có đang bận thực thi các hoạt động chính (Boss, Phụ Bản, Dị Giới, 40 NPC / Nhị Kiều...) không"""
        if getattr(self, '_is_hen_gio_running', False):
            return True, "Tiến trình Hẹn Giờ"

        if getattr(self, '_is_card_E_running', False):
            return True, "Card Quản Lý Tổ Đội (E)"

        # Nếu đang bật Hẹn Giờ và chưa đến giờ kích hoạt, các Card đang ON chỉ ở trạng thái chờ lịch, không chiếm quyền LDPlayer
        is_hen_gio_waiting = hasattr(self, 'var_hen_gio') and self.var_hen_gio.get() and not getattr(self, '_is_hen_gio_running', False)

        if not is_hen_gio_waiting:
            if getattr(self, '_card_AB_coordinator_running', False):
                return True, "Điều phối Boss TG / Phụ Bản"
            if hasattr(self, 'var_switch_A') and self.var_switch_A.get():
                return True, "Card Boss Thế Giới (A)"
            if hasattr(self, 'var_switch_B') and self.var_switch_B.get():
                return True, "Card Phụ Bản Đơn / Đội (B)"
            if hasattr(self, 'var_switch_C') and self.var_switch_C.get():
                return True, "Card Dị Giới (C)"
            if hasattr(self, 'var_switch_D') and self.var_switch_D.get():
                return True, "Card 40 NPC / Nhị Kiều (D)"

        if hasattr(self, 'btn_enter_game'):
            try:
                if self.btn_enter_game.cget("text") == "Đang mở Game...":
                    return True, "Đang mở Game TS Origin"
            except Exception:
                pass
        return False, ""

    def _worker_auto_mail_daemon(self):
        """Luồng ngầm canh giờ Nhận Thư: Tĩnh hoàn toàn khi tắt, kích hoạt qua _event_nhan_thu khi ô Nhận Thư được tích, có cơ chế Kiểm tra Bận (Busy Check) chống xung đột"""
        if not hasattr(self, '_completed_mail_slots'):
            self._completed_mail_slots = set()
        last_logged_busy_slot = None
        retry_counts = {}

        while True:
            try:
                # 1. Nếu ô Nhận Thư không được tích (False), luồng ngưng hoạt động tĩnh hoàn toàn (Zero CPU)
                if hasattr(self, '_event_nhan_thu'):
                    self._event_nhan_thu.wait()

                # Kiểm tra lại biến ô tích phòng trường hợp event vừa bị clear
                if not getattr(self, 'var_nhan_thu', None) or not self.var_nhan_thu.get():
                    if hasattr(self, '_event_nhan_thu'):
                        self._event_nhan_thu.clear()
                    continue

                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                selected_mode = self.combo_nhan_thu_time.get() if hasattr(self, 'combo_nhan_thu_time') else "Tất Cả"

                # 2. Xác định các mốc giờ 12H01, 18H01, 22H01 (khung giờ từ phút 01 đến phút 30)
                matched_slot = None
                if 1 <= now.minute <= 30:
                    if now.hour == 12 and (selected_mode in ["12H01", "Tất Cả"]):
                        matched_slot = "12H01"
                    elif now.hour == 18 and (selected_mode in ["18H01", "Tất Cả"]):
                        matched_slot = "18H01"
                    elif now.hour == 22 and (selected_mode in ["22H01", "Tất Cả"]):
                        matched_slot = "22H01"

                if matched_slot is not None:
                    slot_key = f"{today_str}_{matched_slot}"
                    if slot_key not in self._completed_mail_slots:
                        # 3. CƠ CHẾ KIỂM TRA TRẠNG THÁI BẬN (BUSY CHECK)
                        is_busy, busy_reason = self._is_tool_busy_with_activities()
                        if is_busy:
                            if last_logged_busy_slot != slot_key:
                                last_logged_busy_slot = slot_key
                                self.after(0, self.log_info, f"⏳ [CARD NGÀY ({matched_slot})] Hoạt động '{busy_reason}' đang chạy dở ➔ Tạm hoãn nhận thư, sẽ tự động thực thi ngay khi hoàn thành...")
                        else:
                            last_logged_busy_slot = None
                            if self.stop_requested or not getattr(self, 'var_nhan_thu', None) or not self.var_nhan_thu.get():
                                continue
                            self.after(0, self.log_info, f"⏰ [CARD NGÀY ({matched_slot})] Bắt đầu thực thi Tự Động Nhận Thư ({matched_slot})...")

                            dnconsole_path = self._get_dnconsole_path()
                            if not dnconsole_path:
                                self.after(0, self.log_error, f"⚠️ [CARD NGÀY] Không tìm thấy ldconsole/dnconsole tại: {self.ld_path}")
                            else:
                                tab_name, tab_index = self._get_selected_ld_info()
                                if tab_index is None:
                                    tab_index = "0"
                                success = self._execute_nhan_thu(dnconsole_path, str(tab_index), time_slot=matched_slot)
                                if success:
                                    self._completed_mail_slots.add(slot_key)
                                    retry_counts.pop(slot_key, None)
                                    self.after(0, self.log_info, f"✅ [CARD NGÀY ({matched_slot})] Đã hoàn tất mốc {matched_slot} hôm nay.")
                                else:
                                    cur_retries = retry_counts.get(slot_key, 0) + 1
                                    retry_counts[slot_key] = cur_retries
                                    if cur_retries >= 3:
                                        self.after(0, self.log_warning, f"⚠️ [CARD NGÀY ({matched_slot})] Đã thử lại 3 lần không thành công ➔ Đánh dấu kết thúc mốc này để tránh lặp vô tận.")
                                        self._completed_mail_slots.add(slot_key)
                                    else:
                                        self.after(0, self.log_info, f"🔄 [CARD NGÀY ({matched_slot})] Chưa hoàn thành (lần {cur_retries}/3) ➔ Sẽ tự động thử lại sau vài giây...")

                # Dọn dẹp các mốc cũ của ngày hôm trước trong set để chống phình bộ nhớ
                if len(self._completed_mail_slots) > 20:
                    self._completed_mail_slots = {s for s in self._completed_mail_slots if s.startswith(today_str)}

                # 4. CHU KỲ NGHỈ THÔNG MINH 2 NHỊP (TRUE ZERO-CPU SLEEP via Event.wait)
                # - Nhịp nhanh (3.0s): Khi đang trong khung giờ vàng (12h, 18h, 22h phút 01-30) và chưa nhận thư / đang chờ hết bận.
                # - Nhịp dài (60.0s): Khi ở ngoài khung giờ hoặc mốc đã nhận xong → ngủ OS-level, Zero CPU.
                # Dùng Event.wait(timeout) thay for-loop để thread ngủ hoàn toàn, không poll liên tục.
                is_active_window = (now.hour in [12, 18, 22]) and (1 <= now.minute <= 30)
                current_slot_key = f"{today_str}_{matched_slot}" if matched_slot else None
                slot_already_done = current_slot_key in self._completed_mail_slots if current_slot_key else False

                needs_fast_check = is_active_window and not slot_already_done

                # Khi sắp chuyển sang giờ mới (ví dụ 11:59, 17:59, 21:59), tự động chuyển nhịp nhanh để đón chuẩn mốc 01 phút
                if (now.hour in [11, 17, 21]) and (now.minute >= 59):
                    needs_fast_check = True

                # Reset cờ ngắt trước khi ngủ (phòng trường hợp được set từ lần trước)
                if hasattr(self, '_stop_mail_sleep'):
                    self._stop_mail_sleep.clear()

                sleep_sec = 3.0 if needs_fast_check else 60.0
                if hasattr(self, '_stop_mail_sleep'):
                    # Ngủ thực sự (OS-level), thức dậy khi hết timeout hoặc khi _stop_mail_sleep được set
                    self._stop_mail_sleep.wait(timeout=sleep_sec)
                else:
                    time.sleep(sleep_sec)

            except Exception as e:
                self.after(0, self.log_error, f"⚠️ [CARD NGÀY] Lỗi luồng tự động nhận thư: {e}")
                time.sleep(5.0)

    def _worker_hen_gio_daemon(self):
        """Luồng ngầm canh giờ Hẹn Giờ: Tĩnh hoàn toàn khi tắt, kích hoạt qua _event_hen_gio khi ô Hẹn Giờ được tích"""
        last_triggered_key = None
        while True:
            try:
                # 1. Nếu ô Hẹn Giờ không được tích, luồng ngưng hoạt động tĩnh hoàn toàn (Zero CPU)
                if hasattr(self, '_event_hen_gio'):
                    self._event_hen_gio.wait()

                # Kiểm tra lại biến ô tích phòng trường hợp event vừa bị clear
                if not getattr(self, 'var_hen_gio', None) or not self.var_hen_gio.get():
                    if hasattr(self, '_event_hen_gio'):
                        self._event_hen_gio.clear()
                    continue

                now = datetime.now()
                now_str = now.strftime("%H:%M")
                target_time = self.var_hen_gio_time.get().strip() if hasattr(self, 'var_hen_gio_time') else "05:00"

                # Chuẩn hóa target_time (đảm bảo dạng HH:MM)
                if len(target_time) == 4 and target_time[1] == ':':
                    target_time = f"0{target_time}"

                today_str = now.strftime("%Y-%m-%d")
                trigger_key = f"{today_str}_{target_time}"

                if now_str == target_time and last_triggered_key != trigger_key:
                    last_triggered_key = trigger_key

                    # Kiểm tra xem có Card nào (A, B, C, D) đang gạt công tắc ON không
                    has_A = hasattr(self, 'var_switch_A') and self.var_switch_A.get()
                    has_B = hasattr(self, 'var_switch_B') and self.var_switch_B.get()
                    has_C = hasattr(self, 'var_switch_C') and self.var_switch_C.get()
                    has_D = hasattr(self, 'var_switch_D') and self.var_switch_D.get()

                    if not (has_A or has_B or has_C or has_D):
                        self.after(0, self.log_warning, f"⚠️ [HẸN GIỜ] Đã đến giờ hẹn {target_time} nhưng không có Card nào (A, B, C, D) được gạt công tắc ON! Tự động tắt Hẹn Giờ.")
                        self.var_hen_gio.set(False)
                        if hasattr(self, '_event_hen_gio'):
                            self._event_hen_gio.clear()
                        self.after(0, self._update_hen_gio_ui)
                        self.after(0, self.save_config)
                        continue

                    self.after(0, self.log_info, f"⏰ [HẸN GIỜ] ĐÃ ĐẾN GIỜ HẸN ({target_time})! Bắt đầu thực thi tuần tự các Card đã bật ON...")
                    self._reset_stop_flags()
                    self._is_hen_gio_running = True

                    try:
                        tab_name, tab_index = self._get_selected_ld_info()
                        dnconsole_path = self._get_dnconsole_path()

                        if tab_index is None or not dnconsole_path:
                            self.after(0, self.log_error, "⚠️ [HẸN GIỜ] Không tìm thấy thông tin Tab LDPlayer hoặc đường dẫn ldconsole hợp lệ để chạy hẹn giờ!")
                        else:
                            # Chờ nếu đang có hoạt động nhận thư chạy dở (thường chỉ mất 5-10 giây)
                            mail_wait = 0
                            while getattr(self, '_is_nhan_thu_running', False) and mail_wait < 15 and not self.stop_requested:
                                time.sleep(1.0)
                                mail_wait += 1

                            # 1. Chạy Card A & Card B qua Coordinator tuần tự
                            if (has_A or has_B) and not self.stop_requested:
                                self.after(0, self.log_info, "🚀 [HẸN GIỜ ➔ BƯỚC 1] Khởi chạy Card A (Boss TG) & Card B (Phụ Bản)...")
                                self._run_card_AB_coordinator()

                            # 2. Chạy Card C (Dị Giới)
                            if hasattr(self, 'var_switch_C') and self.var_switch_C.get() and not self.stop_requested:
                                self.after(0, self.log_info, "🚀 [HẸN GIỜ ➔ BƯỚC 2] Khởi chạy [CARD C: DỊ GIỚI ĐÊM]...")
                                try:
                                    self._execute_card_C_di_gioi(dnconsole_path, tab_name, tab_index)
                                except Exception as e:
                                    self.after(0, self.log_error, f"❌ [HẸN GIỜ] Lỗi Card Dị Giới: {e}")
                                finally:
                                    self.var_switch_C.set(False)
                                    self.after(0, lambda: self.var_switch_C.set(False))

                            # 3. Chạy Card D (40 NPC / Nhị Kiều)
                            if hasattr(self, 'var_switch_D') and self.var_switch_D.get() and not self.stop_requested:
                                self.after(0, self.log_info, "🚀 [HẸN GIỜ ➔ BƯỚC 3] Khởi chạy Card D (40 NPC / Nhị Kiều)...")
                                try:
                                    self._execute_card_D_40_npc(dnconsole_path, tab_name, tab_index)
                                except Exception as e:
                                    self.after(0, self.log_error, f"❌ [HẸN GIỜ] Lỗi Card 40 NPC: {e}")
                                finally:
                                    self.var_switch_D.set(False)
                                    if hasattr(self, 'var_pause_D'):
                                        self.var_pause_D.set(False)
                                    self.after(0, lambda: self.var_switch_D.set(False))
                    finally:
                        self._is_hen_gio_running = False

                    # 4. Hoàn tất toàn bộ quy trình hẹn giờ: Nhả công tắc về OFF & Tắt Hẹn Giờ
                    for prefix in ["A", "B", "C", "D"]:
                        switch_attr = f"var_switch_{prefix}"
                        if hasattr(self, switch_attr):
                            getattr(self, switch_attr).set(False)
                    self.var_hen_gio.set(False)
                    if hasattr(self, '_event_hen_gio'):
                        self._event_hen_gio.clear()
                    self._update_card_E_visibility()
                    self.after(0, self._update_hen_gio_ui)
                    self.after(0, self.save_config)
                    self.after(0, self.log_info, f"🎉 [HẸN GIỜ] Đã hoàn thành toàn bộ hoạt động theo lịch hẹn ({target_time})! Đã tự động trả tất cả công tắc về OFF.")

                # Chu kỳ nghỉ thông minh Zero-CPU: Ngủ OS-level cho đến đầu phút tiếp theo (hoặc ngắt tức thì khi tắt)
                if hasattr(self, '_stop_hen_gio_sleep'):
                    self._stop_hen_gio_sleep.clear()

                sec_remain = max(1.0, 60.0 - datetime.now().second)
                if hasattr(self, '_stop_hen_gio_sleep'):
                    self._stop_hen_gio_sleep.wait(timeout=sec_remain)
                else:
                    time.sleep(sec_remain)

            except Exception as e:
                self.after(0, self.log_error, f"⚠️ Lỗi luồng hẹn giờ: {e}")
                time.sleep(2.0)

    def _capture_screen_fast(self, dnconsole_path: str, tab_index: str, max_cache_age: float = 0.35):
        """📸 Chụp ảnh màn hình LDPlayer siêu tốc: Tận dụng bộ nhớ đệm RAM (0.35s) và đọc In-Memory qua ADB Direct Stream (Zero Disk I/O)"""
        now = time.time()
        tab_key = str(tab_index)

        # 1. Kiểm tra bộ nhớ đệm màn hình ngắn hạn (Screen Reuse Cache)
        if not hasattr(self, '_screen_cache'):
            self._screen_cache = {}

        cached = self._screen_cache.get(tab_key)
        if cached is not None:
            if (now - cached.get("time", 0)) < max_cache_age and cached.get("img") is not None:
                return cached["img"]

        # 2. Ưu tiên 1: Chụp trực tiếp qua ADB exec-out stream (Zero Disk I/O - Không ghi đĩa SSD)
        ld_dir = getattr(self, 'ld_path', '') or os.path.dirname(dnconsole_path)
        adb_path = os.path.join(ld_dir, "adb.exe")
        if not os.path.exists(adb_path):
            adb_path = os.path.join(os.path.dirname(dnconsole_path), "adb.exe")

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if os.path.exists(adb_path):
            try:
                tab_num = int(tab_index)
            except Exception:
                tab_num = 0
            port_5554 = 5554 + (tab_num * 2)
            port_5555 = 5555 + (tab_num * 2)
            candidate_devices = [
                f"emulator-{port_5554}",
                f"127.0.0.1:{port_5555}",
            ]

            if not hasattr(self, '_active_adb_device'):
                self._active_adb_device = {}

            # Ưu tiên thiết bị đã kết nối thành công trước đó, sau đó thử các candidate còn lại
            active_dev = self._active_adb_device.get(tab_key)
            devices_to_try = ([active_dev] if active_dev in candidate_devices else []) + \
                             [d for d in candidate_devices if d != active_dev]

            for dev in devices_to_try:
                try:
                    res = subprocess.run(
                        [adb_path, "-s", dev, "exec-out", "screencap", "-p"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=3,
                        creationflags=creation_flags
                    )
                    if res.returncode == 0 and len(res.stdout) > 10000:
                        img = cv2.imdecode(np.frombuffer(res.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                            self._active_adb_device[tab_key] = dev
                            self._screen_cache[tab_key] = {"time": time.time(), "img": img}
                            return img
                except Exception:
                    pass

        # 3. Ưu tiên 2 (Fallback an toàn): Chụp qua file tạm trên đĩa nếu ADB Direct Stream chưa sẵn sàng
        temp_dir = os.path.join(tempfile.gettempdir(), "ts_origin_temp")
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception:
            pass
        temp_local = os.path.join(temp_dir, f"temp_cap_{tab_index}.png")

        try:
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", "shell screencap -p /sdcard/mat_than.png"])
            self._exec_cmd([dnconsole_path, "adb", "--index", str(tab_index), "--command", f"pull /sdcard/mat_than.png \"{temp_local}\""])

            if os.path.exists(temp_local) and os.path.getsize(temp_local) > 0:
                d = np.fromfile(temp_local, dtype=np.uint8)
                img = cv2.imdecode(d, cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                    self._screen_cache[tab_key] = {"time": time.time(), "img": img}
                    return img
        except Exception:
            pass
        finally:
            try:
                if os.path.exists(temp_local):
                    os.remove(temp_local)
            except Exception:
                pass

        return None

    def _find_template_on_screen(self, dnconsole_path: str, tab_index: str, template_filename: str, threshold: float = 0.85, check_color: bool = False, region: tuple = None, force_fresh: bool = False):
        """👁️ Mắt Thần OpenCV Siêu Tốc: Khớp vị trí hình ảnh mẫu .png trong thư mục assets/ với hiệu năng tối đa (Zero Disk I/O & In-Memory Cache)"""
        if not hasattr(self, '_tmpl_path_cache'):
            self._tmpl_path_cache = {}

        cached_path = self._tmpl_path_cache.get(template_filename)
        if cached_path is False:
            # Kiểm tra nhanh xem file vừa mới được thêm vào thư mục assets/ không (hỗ trợ thêm map mới khi đang chạy)
            direct_p = os.path.join(get_app_dir(), "assets", template_filename)
            if os.path.exists(direct_p) and os.path.isfile(direct_p):
                cached_path = direct_p
                self._tmpl_path_cache[template_filename] = direct_p
            else:
                return None, None

        if cached_path is not None and os.path.exists(cached_path):
            tmpl_path = cached_path
        else:
            tmpl_path = None
            clean_name = os.path.basename(template_filename)
            possible_paths = []

            for base in [get_app_dir(), get_bundle_dir()]:
                assets_dir = os.path.join(base, "assets")
                possible_paths.append(os.path.join(assets_dir, template_filename))
                possible_paths.append(os.path.join(base, template_filename))
                try:
                    if os.path.exists(assets_dir):
                        for root, dirs, files in os.walk(assets_dir):
                            if clean_name in files:
                                possible_paths.append(os.path.join(root, clean_name))
                            p = os.path.join(root, template_filename)
                            if os.path.exists(p) and p not in possible_paths:
                                possible_paths.append(p)
                except Exception:
                    pass

            for p in possible_paths:
                if os.path.exists(p) and os.path.isfile(p):
                    tmpl_path = p
                    self._tmpl_path_cache[template_filename] = tmpl_path
                    break

            if tmpl_path is None:
                # Đánh dấu negative cache để không walk lại lần sau
                self._tmpl_path_cache[template_filename] = False
                self.after(0, self.log_error, f"⚠️ Chưa có file ảnh mẫu '{template_filename}' trong các thư mục assets/ (card_a..f, login, server...)!")
                return None, None

        # 1. Load và Cache toàn diện Template (Raw, BGR, Alpha Mask, Gray, Edge, Precomputed V-Mean)
        if not hasattr(self, '_template_cache'):
            self._template_cache = {}

        file_mtime = os.path.getmtime(tmpl_path) if (tmpl_path and os.path.exists(tmpl_path)) else 0
        tmpl_info = self._template_cache.get(tmpl_path)
        # Hot-reload: Nếu file trên đĩa đã bị thay đổi / đè ảnh mới -> Nạp lại tức thì ảnh mới vào RAM
        if tmpl_info is not None and tmpl_info.get("mtime") != file_mtime:
            tmpl_info = None

        is_nkn = ("nkn" in template_filename.lower()) or ("diemdanh" in template_filename.lower()) or ("veboss" in template_filename.lower())

        if tmpl_info is None:
            try:
                def _read_img_unicode(fpath, flags=cv2.IMREAD_UNCHANGED):
                    try:
                        d = np.fromfile(fpath, dtype=np.uint8)
                        return cv2.imdecode(d, flags)
                    except Exception:
                        return None

                raw_template = _read_img_unicode(tmpl_path, cv2.IMREAD_UNCHANGED)
                if raw_template is not None:
                    # Tách kênh BGR và Alpha Mask
                    if len(raw_template.shape) == 3 and raw_template.shape[2] == 4:
                        alpha = raw_template[:, :, 3]
                        tmpl_bgr = cv2.cvtColor(raw_template, cv2.COLOR_BGRA2BGR)
                        tmpl_mask = alpha if np.any(alpha < 255) else None
                    else:
                        tmpl_bgr = raw_template
                        tmpl_mask = None

                    # Tiền xử lý Gray và Canny Edge nếu là ảnh động
                    if is_nkn:
                        try:
                            tmpl_gray = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
                            tmpl_edge = cv2.Canny(tmpl_gray, 50, 150)
                        except Exception:
                            tmpl_gray, tmpl_edge = None, None
                    else:
                        tmpl_gray, tmpl_edge = None, None

                    # Tính trước tmpl_v_mean một lần duy nhất cho template
                    tmpl_v_mean = None
                    try:
                        tmpl_hsv = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2HSV)
                        if tmpl_mask is not None:
                            mask_valid = tmpl_mask > 50
                            tmpl_v_mean = float(np.mean(tmpl_hsv[:, :, 2][mask_valid])) if np.any(mask_valid) else float(np.mean(tmpl_hsv[:, :, 2]))
                        else:
                            tmpl_v_mean = float(np.mean(tmpl_hsv[:, :, 2]))
                    except Exception:
                        tmpl_v_mean = None

                    tmpl_info = {
                        "raw": raw_template,
                        "bgr": tmpl_bgr,
                        "mask": tmpl_mask,
                        "gray": tmpl_gray,
                        "edge": tmpl_edge,
                        "v_mean": tmpl_v_mean,
                        "shape": raw_template.shape,
                        "mtime": file_mtime
                    }
                    # Giới hạn cache để tránh phình RAM khi chạy lâu (FIFO, ảnh bị loại sẽ tự nạp lại khi cần)
                    if len(self._template_cache) >= 250:
                        self._template_cache.pop(next(iter(self._template_cache)), None)
                    self._template_cache[tmpl_path] = tmpl_info
            except Exception:
                pass

        if tmpl_info is None:
            return None, None

        template_raw = tmpl_info["raw"]
        template_bgr = tmpl_info["bgr"]
        alpha_mask = tmpl_info["mask"]

        max_attempts = 3 if is_nkn else 1

        for attempt in range(max_attempts):
            # Nếu force_fresh=True hoặc attempt > 0: max_cache_age = 0 để chụp frame mới
            max_age = 0.0 if (force_fresh or attempt > 0) else 0.35
            screen = self._capture_screen_fast(dnconsole_path, tab_index, max_cache_age=max_age)

            if screen is not None:
                try:
                    offset_x, offset_y = 0, 0
                    search_screen = screen
                    target_region = region
                    if target_region is None:
                        tmpl_lower = template_filename.lower()
                        if any(k in tmpl_lower for k in ["login_auto", "c_aitim"]):
                            target_region = (0, 100, 240, 190)
                        elif "login_x" in tmpl_lower:
                            target_region = (860, 70, 1170, 200)
                        elif "login_menu" in tmpl_lower:
                            target_region = (1190, 640, 1280, 720)
                        elif "a_co" in tmpl_lower:
                            target_region = (925, 540, 1150, 670)
                        elif "a_skboss" in tmpl_lower:
                            target_region = (155, 95, 305, 625)
                        elif any(k in tmpl_lower for k in ["a_boss", "a_hetluot"]):
                            target_region = (275, 540, 1280, 720)
                        elif any(k in tmpl_lower for k in ["a_dung", "c_digioi", "d_tret", "d_daidien", "d_thongdao", "d_dinh", "d_tang", "e_dinh", "pbmap", "pb20map", "pb50map", "pb80map", "pb110map", "pb140map", "d_loidai", "d_thap", "d_thap14"]):
                            target_region = (1060, 0, 1280, 40)
                        elif any(k in tmpl_lower for k in ["a_veboss", "a_khoa"]):
                            target_region = (730, 165, 1105, 610)
                        elif "f_tieptheo" in tmpl_lower:
                            target_region = (1050, 530, 1165, 680)
                        elif "card_f" in tmpl_lower:
                            target_region = (640, 0, 1280, 145)
                        elif any(k in tmpl_lower for k in ["b_pbdon", "b_pb20", "b_pb50", "b_pb80", "b_pb110", "b_pb140", "b_lsknn", "b_xn", "b_matkhau", "b_batdau"]):
                            target_region = (165, 170, 1110, 615)
                        elif any(k in tmpl_lower for k in ["e_nguoi", "e_doingu"]):
                            target_region = (175, 165, 295, 455)
                        elif "e_nhandoi" in tmpl_lower:
                            target_region = (880, 635, 980, 720)
                        elif any(k in tmpl_lower for k in ["pbdoi", "e_moi"]):
                            target_region = (175, 165, 1105, 605)
                        elif "40npc2k" in tmpl_lower:
                            target_region = (305, 150, 1105, 625)
                        elif "d_35" in tmpl_lower:
                            target_region = (175, 220, 265, 245)
                        elif any(k in tmpl_lower for k in ["d_dichuyen", "d_conglt", "d_vaolt"]):
                            target_region = (0, 400, 980, 720)
                        elif any(k in tmpl_lower for k in ["d_chien", "d_tieptheo"]):
                            target_region = (280, 490, 1280, 720)
                        elif any(k in tmpl_lower for k in ["d_vaotran", "d_xacdinh"]):
                            target_region = (275, 540, 980, 670)
                        elif "d_hoanthanh" in tmpl_lower:
                            target_region = (905, 0, 985, 70)
                        elif "nhikieu/d_buoc1" in tmpl_lower:
                            target_region = (0, 0, 640, 720)
                        elif "nhikieu/d_buoc2" in tmpl_lower:
                            target_region = (0, 0, 1280, 360)
                        elif any(k in tmpl_lower for k in ["a_sukien", "a_tui", "b_doi", "b_pb", "c_ai", "c_vitri"]):
                            target_region = (730, 405, 1200, 720)

                    if target_region is not None:
                        rx1, ry1, rx2, ry2 = target_region
                        h_s, w_s = screen.shape[:2]
                        rx1 = max(0, min(rx1, w_s))
                        rx2 = max(rx1 + 1, min(rx2, w_s))
                        ry1 = max(0, min(ry1, h_s))
                        ry2 = max(ry1 + 1, min(ry2, h_s))
                        search_screen = screen[ry1:ry2, rx1:rx2]
                        offset_x, offset_y = rx1, ry1

                    # Nới lỏng ngưỡng mặc định cho file nkn.png hoặc c_veboss.png (do có hiệu ứng chuyển động nhẹ)
                    current_threshold = threshold
                    if "veboss" in template_filename.lower():
                        current_threshold = min(threshold, 0.65)
                    elif "f_dung" in template_filename.lower():
                        current_threshold = min(threshold, 0.65)
                    elif is_nkn:
                        current_threshold = min(threshold, 0.45)

                    # Xử lý Alpha Mask (trong suốt) đã tiền xử lý
                    if alpha_mask is not None:
                        res = cv2.matchTemplate(search_screen, template_bgr, cv2.TM_CCOEFF_NORMED, mask=alpha_mask)
                        res = np.nan_to_num(res, nan=-1.0)
                    else:
                        res = cv2.matchTemplate(search_screen, template_bgr, cv2.TM_CCOEFF_NORMED)

                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                    # Quét bổ sung theo Grayscale & Canny Edge nếu là nkn
                    if is_nkn and tmpl_info.get("gray") is not None:
                        try:
                            gray_screen = cv2.cvtColor(search_screen, cv2.COLOR_BGR2GRAY)
                            res_gray = cv2.matchTemplate(gray_screen, tmpl_info["gray"], cv2.TM_CCOEFF_NORMED)
                            _, max_v_g, _, max_l_g = cv2.minMaxLoc(res_gray)
                            if max_v_g > max_val:
                                max_val = max_v_g
                                max_loc = max_l_g

                            if tmpl_info.get("edge") is not None:
                                edge_screen = cv2.Canny(gray_screen, 50, 150)
                                res_edge = cv2.matchTemplate(edge_screen, tmpl_info["edge"], cv2.TM_CCOEFF_NORMED)
                                _, max_v_e, _, max_l_e = cv2.minMaxLoc(res_edge)
                                if max_v_e > max_val:
                                    max_val = max_v_e
                                    max_loc = max_l_e
                        except Exception:
                            pass

                    match_pct = round(max_val * 100, 1)

                    if max_val >= current_threshold:
                        h, w = template_raw.shape[:2]
                        center_x = offset_x + max_loc[0] + w // 2
                        center_y = offset_y + max_loc[1] + h // 2

                        # Kiểm tra độ tươi sáng/màu sắc (chỉ kích hoạt khi check_color=True)
                        if check_color:
                            try:
                                crop_x = offset_x + max_loc[0]
                                crop_y = offset_y + max_loc[1]
                                crop = screen[crop_y:crop_y+h, crop_x:crop_x+w]
                                if crop.shape[0] == h and crop.shape[1] == w:
                                    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                                    tmpl_v_mean = tmpl_info.get("v_mean")
                                    if tmpl_v_mean is None:
                                        tmpl_v_mean = 120.0

                                    if alpha_mask is not None:
                                        mask_valid = alpha_mask > 50
                                        if np.any(mask_valid):
                                            crop_v_mean = float(np.mean(crop_hsv[:, :, 2][mask_valid]))
                                            crop_s_mean = float(np.mean(crop_hsv[:, :, 1][mask_valid]))
                                        else:
                                            crop_v_mean = float(np.mean(crop_hsv[:, :, 2]))
                                            crop_s_mean = float(np.mean(crop_hsv[:, :, 1]))
                                    else:
                                        crop_v_mean = float(np.mean(crop_hsv[:, :, 2]))
                                        crop_s_mean = float(np.mean(crop_hsv[:, :, 1]))

                                    if crop_s_mean < 45 or crop_v_mean < 110 or (tmpl_v_mean - crop_v_mean) > 70:
                                        self.after(0, self.log_info, f"👁️ Mắt thần quét '{template_filename}' ({match_pct}%) nhưng bị TỐI/MỜ MÀU (V: {round(crop_v_mean, 1)}, S: {round(crop_s_mean, 1)} / Chuẩn: {round(tmpl_v_mean, 1)}) ➔ Bỏ qua.")
                                        return None, None
                            except Exception:
                                pass

                        self.after(0, self.log_info, f"👁️ Mắt thần khớp thành công '{template_filename}' ({match_pct}%) tại ({center_x}, {center_y})")
                        return center_x, center_y
                    else:
                        # Tối ưu giao diện: Chỉ cập nhật nhẹ lên Status Bar, KHÔNG spam txt_log để tránh giật lag GUI
                        if hasattr(self, 'lbl_status'):
                            self.after(0, lambda fn=template_filename, mp=match_pct, th=int(current_threshold*100): self.lbl_status.configure(text=f"Đang quét: {fn} ({mp}%/{th}%)"))
                except Exception:
                    pass

            if attempt < max_attempts - 1:
                time.sleep(0.3)

        return None, None



def _ensure_single_instance():
    """Đảm bảo chỉ có duy nhất 1 phiên bản tool chạy cùng lúc trên Windows.
    Nếu phát hiện tool đã mở trước đó, gửi lệnh đưa cửa sổ tool cũ lên đầu màn hình và thoát ngay."""
    import ctypes
    import urllib.request
    import json

    MUTEX_NAME = "Global\\TS_Origin_Control_v3_SingleInstance_Mutex_Unique"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183

    if last_error == ERROR_ALREADY_EXISTS:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8082/api/action",
                data=json.dumps({"action": "show_window"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=1.5)
        except Exception:
            pass
        sys.exit(0)
    return mutex


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _app_instance_mutex = _ensure_single_instance()
    app = ToolLDPlayerGUI()
    app.mainloop()
