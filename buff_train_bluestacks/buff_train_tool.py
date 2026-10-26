# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import threading
import subprocess
import tempfile
import cv2
import numpy as np
import customtkinter as ctk

# Thử import pystray & PIL cho tính năng khay hệ thống (System Tray / thanh mini)
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Thiết lập theme tối hiện đại
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config_buff_train.json")
MAIN_CONFIG_FILE = os.path.join(os.path.dirname(BASE_DIR), "config.json")

def get_resource_path(relative_path: str):
    """Tìm file tài nguyên trong sys._MEIPASS (PyInstaller đóng gói) hoặc thư mục dự án"""
    if hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(p):
            return p
    p = os.path.join(BASE_DIR, relative_path)
    if os.path.exists(p):
        return p
    return None


class BuffTrainTool(ctk.CTk):
    # Danh sách 10 vị trí thành viên trong đội (ROI chuẩn 1280x720, w=20, h=11 gồm 6px HP đỏ + 5px SP xanh)
    # Thứ tự ưu tiên cứu: Hàng Sau (HS) 1->5 trước, sau đó Hàng Trước (HT) 1->5
    # Tọa độ chuẩn xác 100% đo đạc từ game 1280x720:
    # - hp_x, hp_y: Tọa độ gốc thanh máu HP. _detect_dead_members quét ruột trong (x+1, y+1, w=62, h=4) loại bỏ viền kim loại
    # - sp_x, sp_y: Tọa độ gốc thanh năng lượng SP Cyan. Quét ruột trong (x+1, y, w=62, h=4)
    # - x, y: Tọa độ gốc dùng để tính click hồi sinh trúng cơ thể trên sàn (x+35, y+95)
    _TEAM_HP_MEMBERS = (
        {"key": "HS_1", "name": "HS_1 (Chủ PT)", "x": 703, "y": 498, "hp_x": 703, "hp_y": 498, "sp_x": 703, "sp_y": 505, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HS_2", "name": "HS_2",          "x": 783, "y": 457, "hp_x": 783, "hp_y": 457, "sp_x": 783, "sp_y": 464, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HS_3", "name": "HS_3",          "x": 864, "y": 426, "hp_x": 864, "hp_y": 426, "sp_x": 864, "sp_y": 433, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HS_4", "name": "HS_4",          "x": 944, "y": 382, "hp_x": 944, "hp_y": 382, "sp_x": 944, "sp_y": 389, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HS_5", "name": "HS_5",          "x": 1024, "y": 348, "hp_x": 1024, "hp_y": 348, "sp_x": 1024, "sp_y": 355, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HT_1", "name": "HT_1 (Pet 1)",  "x": 622, "y": 451, "hp_x": 622, "hp_y": 451, "sp_x": 622, "sp_y": 458, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HT_2", "name": "HT_2 (Pet 2)",  "x": 703, "y": 408, "hp_x": 703, "hp_y": 408, "sp_x": 703, "sp_y": 415, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HT_3", "name": "HT_3 (Pet 3)",  "x": 783, "y": 372, "hp_x": 783, "hp_y": 372, "sp_x": 783, "sp_y": 379, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HT_4", "name": "HT_4 (Pet 4)",  "x": 864, "y": 329, "hp_x": 864, "hp_y": 329, "sp_x": 864, "sp_y": 336, "w": 65, "h_hp": 6, "h_sp": 4},
        {"key": "HT_5", "name": "HT_5 (Pet 5)",  "x": 944, "y": 289, "hp_x": 944, "hp_y": 289, "sp_x": 944, "sp_y": 296, "w": 65, "h_hp": 6, "h_sp": 4},
    )

    def __init__(self):
        super().__init__()

        # Cấu hình cửa sổ siêu nhỏ gọn, ghim trên cùng màn hình
        self.title("TS Origin - Buff Train (BlueStacks)")
        self.geometry("340x88")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Đăng ký sự kiện nút X: Thu nhỏ xuống khay hệ thống (System Tray) thay vì tắt hẳn
        self.tray_icon = None
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)
        self.bind("<Map>", self._on_window_mapped)

        # Thiết lập Icon nếu có
        icon_path = get_resource_path(os.path.join("assets", "app_icon.ico"))
        if icon_path and os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Biến trạng thái & kết nối BlueStacks (ADB)
        self.adb_path = self._find_adb_path()
        self.tab_map = {}  # { "BlueStacks App Player (5555)": "127.0.0.1:5555", ... }
        self.selected_tab_name = None
        self.selected_tab_device = None

        self.var_buff_train_hp = ctk.BooleanVar(value=False)
        self.stop_requested = False
        self._stop_event = threading.Event()
        self._thread_worker = None

        # Bộ nhớ đệm mắt thần siêu tốc (In-Memory Cache)
        self._screen_cache = {}
        self._template_cache = {}
        self._tmpl_path_cache = {}
        self._capture_fail_count = 0

        self._build_ui()
        self._load_config()
        self._start_tab_monitor()

    # =========================================================================
    # TỰ ĐỘNG TÌM KIẾM ADB & QUẢN LÝ INSTANCE BLUESTACKS
    # =========================================================================
    def _find_adb_path(self):
        """Tìm đường dẫn adb.exe hoặc HD-Adb.exe (Ưu tiên thư mục tool, BlueStacks, PATH, LDPlayer)"""
        for cfg_p in [CONFIG_FILE, MAIN_CONFIG_FILE]:
            if os.path.exists(cfg_p):
                try:
                    with open(cfg_p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p = data.get("adb_path")
                        if p and os.path.exists(p):
                            return p
                        bs_dir = data.get("bluestacks_path")
                        if bs_dir:
                            for n in ["HD-Adb.exe", "adb.exe"]:
                                cand = os.path.join(bs_dir, n)
                                if os.path.exists(cand):
                                    return cand
                except Exception:
                    pass

        # 1. Thư mục hiện tại của tool hoặc subfolder platform-tools
        for n in ["adb.exe", "HD-Adb.exe"]:
            p = os.path.join(BASE_DIR, n)
            if os.path.exists(p):
                return p
        p = os.path.join(BASE_DIR, "platform-tools", "adb.exe")
        if os.path.exists(p):
            return p

        # 2. Registry cài đặt BlueStacks (BlueStacks 5 / BlueStacks_nxt)
        try:
            import winreg
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for subkey in [r"SOFTWARE\BlueStacks_nxt", r"SOFTWARE\BlueStacks"]:
                    try:
                        with winreg.OpenKey(hkey, subkey) as k:
                            install_dir, _ = winreg.QueryValueEx(k, "InstallDir")
                            if install_dir and os.path.exists(install_dir):
                                for n in ["HD-Adb.exe", "adb.exe"]:
                                    cand = os.path.join(install_dir, n)
                                    if os.path.exists(cand):
                                        return cand
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. Các đường dẫn mặc định phổ biến của BlueStacks 5
        for bs_cand in [
            r"C:\Program Files\BlueStacks_nxt",
            r"C:\Program Files (x86)\BlueStacks_nxt",
            r"D:\Program Files\BlueStacks_nxt",
            r"E:\Program Files\BlueStacks_nxt",
            r"C:\Program Files\BlueStacks",
            r"D:\BlueStacks_nxt",
            r"E:\BlueStacks_nxt"
        ]:
            for n in ["HD-Adb.exe", "adb.exe"]:
                cand = os.path.join(bs_cand, n)
                if os.path.exists(cand):
                    return cand

        # 4. Fallback qua adb từ LDPlayer (nếu có sẵn trên máy)
        for ld_cand in [r"C:\LDPlayer\LDPlayer9\adb.exe", r"D:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]:
            if os.path.exists(ld_cand):
                return ld_cand

        # 5. Trong PATH hệ thống
        try:
            import shutil
            which_p = shutil.which("adb")
            if which_p and os.path.exists(which_p):
                return which_p
        except Exception:
            pass

        return None

    def _get_adb_path(self):
        if not self.adb_path or not os.path.exists(self.adb_path):
            self.adb_path = self._find_adb_path()
        return self.adb_path

    def _find_bluestacks_conf(self):
        """Tìm file cấu hình bluestacks.conf để đọc tên hiển thị của các Tab và cổng ADB"""
        try:
            import winreg
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for subkey in [r"SOFTWARE\BlueStacks_nxt", r"SOFTWARE\BlueStacks"]:
                    try:
                        with winreg.OpenKey(hkey, subkey) as k:
                            val, _ = winreg.QueryValueEx(k, "UserDefinedDir")
                            if val:
                                p = os.path.join(val, "bluestacks.conf")
                                if os.path.exists(p):
                                    return p
                    except Exception:
                        pass
        except Exception:
            pass

        for p in [
            r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf",
            r"C:\ProgramData\BlueStacks\bluestacks.conf",
            r"D:\ProgramData\BlueStacks_nxt\bluestacks.conf",
            r"E:\ProgramData\BlueStacks_nxt\bluestacks.conf",
        ]:
            if os.path.exists(p):
                return p
        return None

    def _parse_bluestacks_conf(self, conf_path: str):
        """Phân tích bluestacks.conf lấy mapping instance: { inst_key: { 'display_name': ..., 'port': ... } }"""
        instances = {}
        if not conf_path or not os.path.exists(conf_path):
            return instances
        try:
            with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("bst.instance."):
                        continue
                    parts = line.split("=", 1)
                    if len(parts) != 2:
                        continue
                    key, val = parts[0].strip(), parts[1].strip().strip('"')
                    subparts = key.split(".")
                    if len(subparts) >= 4:
                        inst_id = subparts[2]
                        prop = ".".join(subparts[3:])
                        if inst_id not in instances:
                            instances[inst_id] = {}
                        if prop == "display_name":
                            instances[inst_id]["display_name"] = val
                        elif prop in ("status.adb_port", "adb_port"):
                            instances[inst_id]["port"] = val
        except Exception:
            pass
        return instances

    def _exec_cmd(self, cmd_list, text=False, timeout=12):
        """Thực thi lệnh ADB - chỉ mở PIPE khi cần đọc output (Zero-pipe overhead cho lệnh không cần output)"""
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        kwargs = {"creationflags": creation_flags}
        if text:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE
            kwargs["text"] = True
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "ignore"
        else:
            # Lỗi 8: Không cấp phát pipe kernel vô ích cho lệnh chỉ thực thi (tap, connect, shell...)
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        try:
            return subprocess.run(cmd_list, timeout=timeout, **kwargs)
        except Exception:
            return None

    def _adb_cmd(self, device_id: str, cmd_args: list, text=False, timeout=8):
        adb_path = self._get_adb_path()
        if not adb_path:
            return None
        full_cmd = [adb_path]
        if device_id:
            full_cmd.extend(["-s", device_id])
        full_cmd.extend(cmd_args)
        return self._exec_cmd(full_cmd, text=text, timeout=timeout)

    def _tap(self, device_id: str, x: int, y: int):
        """Click tap vào tọa độ x, y trên BlueStacks qua ADB"""
        self._adb_cmd(device_id, ["shell", "input", "tap", str(x), str(y)], timeout=5)

    # =========================================================================
    # GIAO DIỆN CHUẨN TOOL CHÍNH (THIẾT KẾ CARD BO GÓC & NÚT ĐỒNG BỘ)
    # =========================================================================
    def _build_ui(self):
        # Khung Card bo góc 8px đồng bộ theo chuẩn Card của Tool chính
        self.card_main = ctk.CTkFrame(self, corner_radius=8)
        self.card_main.pack(fill="both", expand=True, padx=6, pady=6)

        # HÀNG 1: Menu chọn Tab BlueStacks | Nút Stop (Chuẩn màu xám ghi & đỏ)
        row1 = ctk.CTkFrame(self.card_main, fg_color="transparent", height=28)
        row1.pack(fill="x", padx=6, pady=(6, 4))
        row1.pack_propagate(False)

        self.combo_tabs = ctk.CTkOptionMenu(
            row1,
            values=["Đang quét BlueStacks..."],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color="#FFFFFF",
            dropdown_text_color="#FFFFFF",
            fg_color="#374151",
            button_color="#4B5563",
            button_hover_color="#6B7280",
            height=26,
            width=225,
            dynamic_resizing=False,
            command=self._on_tab_selected
        )
        self.combo_tabs.pack(side="left")

        self.btn_stop = ctk.CTkButton(
            row1,
            text="Stop",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FFFFFF",
            fg_color="#DC2626",
            hover_color="#B91C1C",
            height=26,
            width=80,
            corner_radius=6,
            command=self.dung_hoat_dong
        )
        self.btn_stop.pack(side="right")

        # HÀNG 2: [ ] [ Buff Train HP ▼ ] [ 3 trận ▼ ] | Nhãn trạng thái
        row2 = ctk.CTkFrame(self.card_main, fg_color="transparent", height=28)
        row2.pack(fill="x", padx=6, pady=(0, 6))
        row2.pack_propagate(False)

        col_buff = ctk.CTkFrame(row2, fg_color="transparent", height=26)
        col_buff.pack(side="left")

        self.chk_buff = ctk.CTkCheckBox(
            col_buff,
            text="",
            variable=self.var_buff_train_hp,
            command=self._on_buff_hp_toggled,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            fg_color="#EA580C",
            hover_color="#C2410C",
            checkmark_color="#FFFFFF",
            checkbox_width=16,
            checkbox_height=16,
            border_width=2,
            corner_radius=5,
            width=16
        )
        self.chk_buff.pack(side="left", padx=(0, 4))

        buff_skills = ["Buff Train HP", "Buff Train SP", "Buff HP / SP"]
        self.combo_buff_skill = ctk.CTkOptionMenu(
            col_buff,
            values=buff_skills,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            text_color="#FFFFFF",
            dropdown_text_color="#FFFFFF",
            height=26,
            width=115,
            dynamic_resizing=False,
            fg_color="#374151",
            button_color="#4B5563",
            button_hover_color="#6B7280",
            corner_radius=6,
            command=self._on_buff_skill_changed
        )
        self.combo_buff_skill.set("Buff Train HP")
        self.combo_buff_skill.pack(side="left")

        self.combo_buff_interval = ctk.CTkOptionMenu(
            col_buff,
            values=["1 trận", "2 trận", "3 trận", "4 trận", "5 trận", "6 trận", "7 trận", "8 trận", "9 trận", "10 trận"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
            text_color="#FFFFFF",
            dropdown_text_color="#FFFFFF",
            height=26,
            width=75,
            dynamic_resizing=False,
            fg_color="#374151",
            button_color="#4B5563",
            button_hover_color="#6B7280",
            corner_radius=6,
            command=self._on_buff_interval_changed
        )
        self.combo_buff_interval.set("3 trận")
        self.combo_buff_interval.pack(side="left", padx=(4, 0))

        self.lbl_status = ctk.CTkLabel(
            row2,
            text="Sẵn sàng",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="normal"),
            text_color="#9CA3AF",
            anchor="e"
        )
        self.lbl_status.pack(side="right", fill="x", expand=True, padx=(4, 0))

        self._update_interval_state()

    def _on_buff_skill_changed(self, choice):
        self._update_interval_state()
        self._save_config()

    def _on_buff_interval_changed(self, choice):
        self._save_config()

    def _update_interval_state(self):
        """Khóa menu chọn trận nếu không phải chế độ Buff Train HP hoặc khi đang chạy"""
        if not hasattr(self, 'combo_buff_interval'):
            return
        if self.var_buff_train_hp.get():
            self.combo_buff_interval.configure(state="disabled")
        else:
            selected_skill = self.combo_buff_skill.get() if hasattr(self, 'combo_buff_skill') else "Buff Train HP"
            if selected_skill == "Buff Train HP":
                self.combo_buff_interval.configure(state="normal")
            else:
                self.combo_buff_interval.configure(state="disabled")

    def _get_buff_interval(self) -> int:
        selected_skill = self.combo_buff_skill.get() if hasattr(self, 'combo_buff_skill') else "Buff Train HP"
        if selected_skill != "Buff Train HP":
            return 1
        try:
            val_str = self.combo_buff_interval.get() if hasattr(self, 'combo_buff_interval') else "3 trận"
            return max(1, int(val_str.split()[0]))
        except Exception:
            return 3

    def _set_status(self, text: str, color: str = "#9CA3AF"):
        """Cập nhật nhãn trạng thái trực tiếp trên luồng giao diện"""
        try:
            self.after(0, lambda: self.lbl_status.configure(text=text, text_color=color))
        except Exception:
            pass

    # =========================================================================
    # TÍNH NĂNG KHAY HỆ THỐNG (SYSTEM TRAY / THANH MINI)
    # =========================================================================
    def _create_tray_icon_image(self):
        """Tạo icon đại diện cho khay hệ thống"""
        icon_path = get_resource_path(os.path.join("assets", "app_icon.ico"))
        if icon_path and os.path.exists(icon_path):
            try:
                return Image.open(icon_path)
            except Exception:
                pass
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
                pystray.MenuItem("Mở Tool Buff Train", self._show_window_from_tray, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Thoát Ứng Dụng", self._exit_app_from_tray)
            )
            self.tray_icon = pystray.Icon("TS_Buff_Train_BS", icon_img, "TS Origin - Buff Train (BlueStacks)", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            pass

    def _on_close_window(self):
        """Sự kiện bấm nút X trên thanh tiêu đề: Lưu vị trí và thu nhỏ xuống khay hệ thống"""
        self._save_config()
        if HAS_PYSTRAY:
            self.withdraw()  # Ẩn cửa sổ chính
            if self.tray_icon is None:
                self._setup_system_tray()
        else:
            self.iconify()  # Thu nhỏ xuống Taskbar nếu không có thư viện tray

    def _on_window_mapped(self, event=None):
        """Đảm bảo đồng bộ khi cửa sổ được hệ thống unhide / restore"""
        try:
            if self.state() == "normal":
                self.attributes("-topmost", True)
        except Exception:
            pass

    def _show_window_from_tray(self, icon=None, item=None):
        """Mở lại giao diện từ khay hệ thống"""
        self.after(0, self._restore_window_ui)

    def _restore_window_ui(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
        except Exception:
            pass

    def _exit_app_from_tray(self, icon=None, item=None):
        """Thoát hoàn toàn ứng dụng từ menu khay hệ thống"""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(0, self._destroy_app_completely)

    def _destroy_app_completely(self):
        try:
            self._tab_monitor_active = False  # Dừng luồng Tab Monitor trước khi thoát
            self.stop_requested = True
            self._stop_event.set()
        except Exception:
            pass
        try:
            self._save_config()
        except Exception:
            pass
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        # Thoát sạch tiến trình và giải phóng Mutex lập tức
        os._exit(0)

    # =========================================================================
    # QUẢN LÝ TAB & CẤU HÌNH (TỰ ĐỘNG QUÉT KHI MỞ / ĐÓNG BLUESTACKS)
    # =========================================================================
    def _start_tab_monitor(self):
        """Bắt đầu luồng kiểm tra BlueStacks ngầm định kỳ khi rảnh rỗi"""
        self._tab_monitor_active = True
        threading.Thread(target=self._tab_monitor_loop, daemon=True).start()

    def _tab_monitor_loop(self):
        # Quét lần đầu
        self._scan_tabs_logic(first_run=True)
        # Lỗi 3: Dùng cờ riêng _tab_monitor_active (không phụ thuộc stop_requested)
        # → Luồng không chết vĩnh viễn sau mỗi lần bấm Stop / bỏ tích checkbox
        while getattr(self, '_tab_monitor_active', True):
            # Ngủ 8 giây giữa các lần quét (ngắt ngay khi thoát app)
            for _ in range(80):
                if not getattr(self, '_tab_monitor_active', True):
                    return
                time.sleep(0.1)

            # Chỉ tự động quét khi Buff Train đang KHÔNG chạy để không can thiệp ADB
            if not self.var_buff_train_hp.get():
                self._scan_tabs_logic(first_run=False)

    def _is_bluestacks_device(self, dev_id: str, conf_instances: dict) -> tuple:
        """Kiểm tra thiết bị có đúng là BlueStacks không.
        Lỗi 5: Trả về (is_bs: bool, label: str, sort_key: int) để hỗ trợ sắp xếp Tab theo cổng"""
        # Rút trích số cổng ADB từ dev_id
        port_num = None
        if ":" in dev_id:
            try:
                port_num = int(dev_id.split(":")[-1])
            except Exception:
                pass
        elif dev_id.startswith("emulator-"):
            try:
                port_num = int(dev_id.split("-")[1]) + 1
            except Exception:
                pass

        # 1. Khớp từ bluestacks.conf nếu có (ưu tiên cao nhất - không cần getprop)
        for inst in conf_instances.values():
            p = inst.get("port")
            if p and p.isdigit():
                p_int = int(p)
                if port_num == p_int or dev_id == f"127.0.0.1:{p}" or dev_id.endswith(f":{p}"):
                    dname = inst.get("display_name") or "BlueStacks"
                    return True, f"{dname} ({p})", p_int

        # 2. Kiểm tra sâu qua getprop (dành cho cổng tùy biến hoặc khi không có conf)
        # LDPlayer sẽ trả về chuỗi rỗng → tự động bị loại ở đây
        try:
            adb_path = self._get_adb_path()
            chk = self._exec_cmd([adb_path, "-s", dev_id, "shell", "getprop", "ro.boot.bst_instance"], text=True, timeout=1.5)
            if chk and chk.stdout.strip():
                bst_name = chk.stdout.strip()
                port = dev_id.split(":")[-1] if ":" in dev_id else dev_id
                return True, f"BlueStacks {bst_name} ({port})", (port_num if port_num else 9999)

            chk2 = self._exec_cmd([adb_path, "-s", dev_id, "shell", "getprop", "ro.bsp.emulator"], text=True, timeout=1.5)
            if chk2 and "blue" in chk2.stdout.lower():
                port = dev_id.split(":")[-1] if ":" in dev_id else dev_id
                return True, f"BlueStacks ({port})", (port_num if port_num else 9999)
        except Exception:
            pass

        return False, "", 99999

    def _scan_tabs_logic(self, first_run: bool = False):
        adb_path = self._get_adb_path()
        if not adb_path:
            if first_run or not self.tab_map:
                self.after(0, lambda: self.combo_tabs.configure(values=["Thiếu adb.exe"]))
                self._set_status("Thiếu adb.exe", "#EF4444")
            return

        conf_path = self._find_bluestacks_conf()
        conf_instances = self._parse_bluestacks_conf(conf_path) if conf_path else {}

        # 1. Tìm cổng ADB từ bluestacks.conf; nếu không có dùng danh sách mặc định
        conf_ports = set()
        for inst in conf_instances.values():
            p = inst.get("port")
            if p and p.isdigit():
                conf_ports.add(int(p))
        ports_to_connect = conf_ports if conf_ports else set([5555, 5565, 5575, 5585, 5595, 5605, 5615, 5625])

        cflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        # Lỗi 4: Lọc bỏ cổng ADB thuộc LDPlayer đang chạy (emulator-XXXX → cổng XXXX+1)
        # Tránh kết nối nhầm vào LDPlayer, gây xung đột ADB server
        try:
            chk_devs = subprocess.run(
                [adb_path, "devices"], timeout=1.5,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="ignore",
                creationflags=cflags
            )
            if chk_devs and chk_devs.stdout:
                for line in chk_devs.stdout.splitlines()[1:]:
                    parts = line.strip().split()
                    if parts and parts[0].startswith("emulator-"):
                        try:
                            c_p = int(parts[0].split("-")[1])
                            ports_to_connect.discard(c_p + 1)  # Bỏ cổng TCP tương ứng LDPlayer
                        except Exception:
                            pass
        except Exception:
            pass

        # Kết nối nhanh tới các cổng BlueStacks thực sự (dùng DEVNULL, không đọc output)
        for port in sorted(ports_to_connect):
            try:
                subprocess.run(
                    [adb_path, "connect", f"127.0.0.1:{port}"],
                    timeout=0.6, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=cflags
                )
            except Exception:
                pass

        # 2. Lấy danh sách thiết bị thực tế đang online từ adb devices
        res = self._exec_cmd([adb_path, "devices"], text=True, timeout=3)
        if not res or not res.stdout:
            if first_run or not self.tab_map:
                self.after(0, lambda: self.combo_tabs.configure(values=["Chưa mở BlueStacks"]))
                self._set_status("Chưa mở BlueStacks", "#EF4444")
            return

        # Thu thập thiết bị online
        raw_devices = []
        for line in res.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "device":
                raw_devices.append(parts[0].strip())

        # Lỗi 5: Khử trùng lặp: bỏ emulator-XXXX nếu đã có 127.0.0.1:(XXXX+1) tương ứng
        unique_devices = []
        for dev in raw_devices:
            if dev.startswith("emulator-"):
                try:
                    c_p = int(dev.split("-")[1])
                    if f"127.0.0.1:{c_p + 1}" in raw_devices:
                        continue
                except Exception:
                    pass
            unique_devices.append(dev)

        # Phân loại thiết bị BlueStacks và thu thập sort_key (số cổng) để sắp xếp
        detected_tabs = []
        for dev_id in unique_devices:
            is_bs, label, sort_k = self._is_bluestacks_device(dev_id, conf_instances)
            if not is_bs:
                continue
            detected_tabs.append((sort_k, label, dev_id))

        # Sắp xếp tab theo thứ tự cổng tăng dần (Tab 1 → 5555, Tab 2 → 5565...)
        detected_tabs.sort(key=lambda x: x[0])

        new_map = {}
        tab_names = []
        for _, label, dev_id in detected_tabs:
            new_map[label] = dev_id
            tab_names.append(label)

        # Nếu danh sách tab không đổi và không phải lần chạy đầu ➔ Bỏ qua
        if new_map == self.tab_map and not first_run:
            return

        self.tab_map = new_map
        if tab_names:
            saved_tab = self.selected_tab_name
            target_tab = saved_tab if saved_tab in tab_names else tab_names[0]
            self.selected_tab_name = target_tab
            self.selected_tab_device = self.tab_map.get(target_tab)

            self.after(0, lambda: self.combo_tabs.configure(values=tab_names))
            self.after(0, lambda: self.combo_tabs.set(target_tab))
            if first_run or self.lbl_status.cget("text") in ("Chưa mở BlueStacks", "Thiếu adb.exe", "0 Tab BlueStacks"):
                self._set_status(f"Tab: {target_tab}", "#10B981")
        else:
            self.after(0, lambda: self.combo_tabs.configure(values=["Chưa mở BlueStacks"]))
            self._set_status("Chưa mở BlueStacks", "#EF4444")

    def _on_tab_selected(self, choice):
        self.selected_tab_name = choice
        self.selected_tab_device = self.tab_map.get(choice)
        self._save_config()
        self._set_status(f"Chọn: {choice}", "#10B981")

    def _load_config(self):
        """Tải cấu hình tab và vị trí tọa độ cửa sổ trên màn hình"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.selected_tab_name = cfg.get("selected_tab")
                    skill_val = cfg.get("selected_skill")
                    if skill_val and hasattr(self, 'combo_buff_skill'):
                        if skill_val in ["Buff Train", "Buff Train HP", "Buff Trian HP"]:
                            self.combo_buff_skill.set("Buff Train HP")
                        elif skill_val in ["Buff Train SP"]:
                            self.combo_buff_skill.set("Buff Train SP")
                        elif skill_val in ["Buff HP / SP", "HP / SP / HS"]:
                            self.combo_buff_skill.set("Buff HP / SP")
                        else:
                            self.combo_buff_skill.set("Buff Train HP")
                    interval_val = cfg.get("buff_interval")
                    if interval_val and hasattr(self, 'combo_buff_interval'):
                        if interval_val in [f"{i} trận" for i in range(1, 11)]:
                            self.combo_buff_interval.set(interval_val)
                    self._update_interval_state()
                    pos_x = cfg.get("window_x")
                    pos_y = cfg.get("window_y")
                    if pos_x is not None and pos_y is not None:
                        sw = self.winfo_screenwidth()
                        sh = self.winfo_screenheight()
                        if 0 <= pos_x <= sw - 80 and 0 <= pos_y <= sh - 50:
                            self.geometry(f"340x88+{pos_x}+{pos_y}")
            except Exception:
                pass

    def _save_config(self):
        """Lưu cấu hình và tọa độ cửa sổ hiện tại"""
        try:
            cfg_data = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                except Exception:
                    cfg_data = {}

            cfg_data["selected_tab"] = self.selected_tab_name
            if hasattr(self, 'combo_buff_skill'):
                cfg_data["selected_skill"] = self.combo_buff_skill.get()
            if hasattr(self, 'combo_buff_interval'):
                cfg_data["buff_interval"] = self.combo_buff_interval.get()
            # Chỉ ghi đè tọa độ khi cửa sổ đang mở bình thường
            if self.state() == "normal":
                x = self.winfo_x()
                y = self.winfo_y()
                if x >= 0 and y >= 0:
                    cfg_data["window_x"] = x
                    cfg_data["window_y"] = y

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, indent=4)
        except Exception:
            pass

    # =========================================================================
    # ĐIỀU KHIỂN BẬT / DỪNG
    # =========================================================================
    def _on_buff_hp_toggled(self):
        if self.var_buff_train_hp.get():
            self.stop_requested = False
            self._stop_event.clear()

            if not self.selected_tab_device:
                self._set_status("Chưa chọn Tab!", "#EF4444")
                self.var_buff_train_hp.set(False)
                return

            adb_path = self._get_adb_path()
            if not adb_path:
                self._set_status("Thiếu ADB!", "#EF4444")
                self.var_buff_train_hp.set(False)
                return

            # Khóa menu chọn Tab, menu chọn Skill và menu chọn số trận khi đang chạy
            try:
                self.combo_tabs.configure(state="disabled")
                if hasattr(self, 'combo_buff_skill'):
                    self.combo_buff_skill.configure(state="disabled")
                if hasattr(self, 'combo_buff_interval'):
                    self.combo_buff_interval.configure(state="disabled")
            except Exception:
                pass

            self._set_status("Đang khởi động...", "#F59E0B")
            if self._thread_worker and self._thread_worker.is_alive():
                return
            self._thread_worker = threading.Thread(
                target=self._run_buff_train_hp_standalone,
                args=(self.selected_tab_name, self.selected_tab_device),
                daemon=True
            )
            self._thread_worker.start()
        else:
            self.stop_requested = True
            self._stop_event.set()
            try:
                self.combo_tabs.configure(state="normal")
                if hasattr(self, 'combo_buff_skill'):
                    self.combo_buff_skill.configure(state="normal")
                self._update_interval_state()
            except Exception:
                pass
            self._set_status("Đã dừng", "#EF4444")

    def dung_hoat_dong(self):
        """Nút Stop khẩn cấp: ngắt tức thì trong < 0.02s"""
        self.stop_requested = True
        self._stop_event.set()
        self.var_buff_train_hp.set(False)
        try:
            self.combo_tabs.configure(state="normal")
            if hasattr(self, 'combo_buff_skill'):
                self.combo_buff_skill.configure(state="normal")
            self._update_interval_state()
        except Exception:
            pass
        self._set_status("Đã dừng", "#EF4444")

    def _sleep_with_stop_check(self, seconds: float) -> bool:
        """Tạm dừng ngủ ngầm siêu tốc: Đánh thức tức thì (< 0.02s) khi dừng"""
        start = time.time()
        while time.time() - start < seconds:
            if self.stop_requested or self._stop_event.is_set() or not self.var_buff_train_hp.get():
                return True
            time.sleep(0.02)
        return False

    # =========================================================================
    # MẮT THẦN OPENCV SIÊU TỐC & ADB DIRECT STREAM (ZERO DISK I/O)
    # =========================================================================
    def _capture_screen_fast(self, device_id: str, max_cache_age: float = 0.35):
        cached = self._screen_cache.get(device_id)
        now = time.time()

        if cached is not None and (now - cached["time"]) < max_cache_age:
            return cached["img"]

        adb_path = self._get_adb_path()
        if not adb_path:
            return None

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        # Phương án 1: Direct stream binary qua exec-out screencap -p (Siêu tốc ~0.05s, không tốn Disk I/O)
        try:
            res = subprocess.run(
                [adb_path, "-s", device_id, "exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
                creationflags=creation_flags
            )
            if res.returncode == 0 and len(res.stdout) > 10000:
                raw_bytes = res.stdout
                # Kiểm tra trực tiếp dữ liệu PNG chuẩn
                if raw_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    img = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                        self._screen_cache[device_id] = {"time": time.time(), "img": img}
                        self._capture_fail_count = 0
                        return img
                # Khắc phục trường hợp Windows cũ chuyển đổi \n thành \r\n
                fixed_bytes = raw_bytes.replace(b'\r\n', b'\n')
                if fixed_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    img = cv2.imdecode(np.frombuffer(fixed_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                        self._screen_cache[device_id] = {"time": time.time(), "img": img}
                        self._capture_fail_count = 0
                        return img
                # Decode thông thường
                img = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
                    self._screen_cache[device_id] = {"time": time.time(), "img": img}
                    self._capture_fail_count = 0
                    return img
        except Exception:
            pass

        # Phương án 2 (Fallback): screencap ra file tạm /sdcard rồi pull về
        try:
            temp_local = os.path.join(tempfile.gettempdir(), f"bs_cap_{device_id.replace(':', '_')}.png")
            self._adb_cmd(device_id, ["shell", "screencap", "-p", "/sdcard/bs_bt.png"], timeout=4)
            self._adb_cmd(device_id, ["pull", "/sdcard/bs_bt.png", temp_local], timeout=4)
            if os.path.exists(temp_local) and os.path.getsize(temp_local) > 0:
                d = np.fromfile(temp_local, dtype=np.uint8)
                img = cv2.imdecode(d, cv2.IMREAD_COLOR)
                try:
                    os.remove(temp_local)
                except Exception:
                    pass
                if img is not None and img.shape[0] > 0:
                    self._screen_cache[device_id] = {"time": time.time(), "img": img}
                    self._capture_fail_count = 0
                    return img
        except Exception:
            pass

        self._capture_fail_count = getattr(self, '_capture_fail_count', 0) + 1
        if self._capture_fail_count >= 8:
            self._set_status("Mất kết nối BlueStacks!", "#EF4444")
        return None

    def _find_template_on_screen(self, device_id: str, template_filename: str, threshold: float = 0.85, region: tuple = None):
        cached_path = self._tmpl_path_cache.get(template_filename)
        if cached_path is None:
            clean_name = os.path.basename(template_filename)
            candidates = [
                template_filename,
                os.path.join("assets", template_filename),
                os.path.join("assets", "card_f", clean_name),
                os.path.join("assets", "card_f", "skill", clean_name)
            ]
            for rel in candidates:
                res_p = get_resource_path(rel)
                if res_p and os.path.isfile(res_p):
                    cached_path = res_p
                    self._tmpl_path_cache[template_filename] = res_p
                    break
            if cached_path is None:
                return None, None

        tmpl_info = self._template_cache.get(cached_path)
        if tmpl_info is None:
            try:
                d = np.fromfile(cached_path, dtype=np.uint8)
                raw = cv2.imdecode(d, cv2.IMREAD_UNCHANGED)
                if raw is not None:
                    if len(raw.shape) == 3 and raw.shape[2] == 4:
                        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                    else:
                        bgr = raw
                    tmpl_info = {"bgr": bgr, "shape": bgr.shape}
                    self._template_cache[cached_path] = tmpl_info
            except Exception:
                return None, None

        if tmpl_info is None:
            return None, None

        template_bgr = tmpl_info["bgr"]
        screen = self._capture_screen_fast(device_id, max_cache_age=0.35)
        if screen is None:
            return None, None

        offset_x, offset_y = 0, 0
        search_screen = screen
        if region is not None:
            rx1, ry1, rx2, ry2 = region
            h, w = screen.shape[:2]
            rx1 = max(0, min(rx1, w - 1))
            ry1 = max(0, min(ry1, h - 1))
            rx2 = max(rx1 + 1, min(rx2, w))
            ry2 = max(ry1 + 1, min(ry2, h))
            search_screen = screen[ry1:ry2, rx1:rx2]
            offset_x, offset_y = rx1, ry1

        th, tw = template_bgr.shape[:2]
        sh, sw = search_screen.shape[:2]
        if sh < th or sw < tw:
            return None, None

        res = cv2.matchTemplate(search_screen, template_bgr, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            center_x = offset_x + max_loc[0] + tw // 2
            center_y = offset_y + max_loc[1] + th // 2
            return center_x, center_y

        return None, None

    def _tap_auto(self, device_id: str, times: int = 1):
        """Tap vào nút Auto (190, 140) số lần chỉ định (mặc định 1 lần, cách nhau 0.3s)"""
        for i in range(times):
            if self.stop_requested or self._stop_event.is_set() or not self.var_buff_train_hp.get():
                break
            self._tap(device_id, 190, 140)
            if i < times - 1:
                time.sleep(0.3)

    def _tap_login_auto_twice(self, device_id: str):
        """Tương thích ngược: Tap 2 lần cách nhau 0.3s vào tọa độ nút Auto (190, 140)"""
        self._tap_auto(device_id, times=2)

    def _wait_enter_battle(self, device_id: str) -> bool:
        """Chờ f_vaotran.png biến mất và hoãn 0.6s để game tải đủ giao diện trận đấu mới"""
        while not self.stop_requested and self.var_buff_train_hp.get() and not self._stop_event.is_set():
            if self._sleep_with_stop_check(0.35):
                return False
            vt_x, vt_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
            if vt_x is None or vt_y is None:
                break
        return not self._sleep_with_stop_check(0.6)

    def _on_match_finished(self, device_id: str, current_match: int, interval: int) -> tuple:
        """Xử lý hành động điều phối khi phát hiện hết trận đấu (f_vaotran.png xuất hiện)"""
        if interval == 1:
            self._set_status("Hết trận ➔ Auto x2", "#F59E0B")
            self._tap_auto(device_id, times=2)
            self._set_status("Chờ trận mới...", "#38BDF8")
            self._wait_enter_battle(device_id)
            return 1, 1, False
        elif current_match == 1:
            # Hết Trận 1 của chu kỳ: Tap 1 lần nút Auto -> Chờ trận 2
            self._set_status(f"[T1/{interval}] Hết T1 ➔ Auto x1", "#F59E0B")
            self._tap_auto(device_id, times=1)
            self._set_status(f"[T2/{interval}] Chờ trận 2...", "#38BDF8")
            self._wait_enter_battle(device_id)
            return 1, 2, False
        elif current_match < interval:
            # Các trận giãn cách 2..N-1: Không tap nút Auto nào cả
            next_m = current_match + 1
            self._set_status(f"[T{next_m}/{interval}] Chờ trận {next_m}...", "#38BDF8")
            self._wait_enter_battle(device_id)
            return 1, next_m, False
        else:
            # Trận cuối cùng (Trận N): Hoãn 2.0s -> Tap 1 lần nút Auto -> Chu kỳ mới
            self._set_status(f"[T{interval}/{interval}] Hết trận ➔ Chờ 2s", "#F59E0B")
            if self._sleep_with_stop_check(2.0):
                return 1, 1, False
            self._set_status(f"[T{interval}/{interval}] Auto x1 ➔ Vòng mới", "#10B981")
            self._tap_auto(device_id, times=1)
            self._set_status(f"[T1/{interval}] Chờ Trận 1 mới...", "#38BDF8")
            self._wait_enter_battle(device_id)
            return 1, 1, False

    # =========================================================================
    # CORE LOGIC CHẾ ĐỘ BUFF TRAIN (KẾ THỪA 100% CƠ CHẾ GỐC)
    # =========================================================================
    def _run_buff_train_hp_standalone(self, tab_name: str, device_id: str):
        try:
            train_turn = 1
            current_match = 1
            in_battle = False
            while self.var_buff_train_hp.get() and not self.stop_requested:
                selected_skill = self.combo_buff_skill.get() if hasattr(self, 'combo_buff_skill') else "Buff Train HP"
                if selected_skill == "Buff HP / SP":
                    # Chu kỳ 3 lượt HP ➔ 1 lượt SP (mỗi lượt đều có kiểm tra ưu tiên Hồi Sinh)
                    # 3 lượt Buff HP
                    for hp_i in range(1, 4):
                        if not self.var_buff_train_hp.get() or self.stop_requested or self._stop_event.is_set():
                            break
                        if self.combo_buff_skill.get() != "Buff HP / SP":
                            break
                        self._set_status(f"Buff HP ({hp_i}/3)...", "#10B981")
                        self._handle_buff_hp_sp_turn(device_id, action_type="HP")
                        if self._sleep_with_stop_check(0.1):
                            break

                    # 1 lượt Buff SP
                    if self.var_buff_train_hp.get() and not self.stop_requested and not self._stop_event.is_set():
                        if self.combo_buff_skill.get() == "Buff HP / SP":
                            self._set_status("Buff SP (1/1)...", "#10B981")
                            self._handle_buff_hp_sp_turn(device_id, action_type="SP")
                            if self._sleep_with_stop_check(0.1):
                                break
                else:
                    train_turn, current_match, in_battle = self._handle_buff_train_hp_turn(
                        tab_name, device_id, train_turn, current_match, in_battle
                    )
                    if self._sleep_with_stop_check(0.1):
                        break
        except Exception:
            self._set_status("Lỗi tiến trình", "#EF4444")
        finally:
            self._thread_worker = None
            try:
                # Lỗi 6: Luôn nhả checkbox về False khi worker kết thúc (kể cả do exception bất ngờ)
                self.after(0, lambda: self.var_buff_train_hp.set(False))
                self.after(0, lambda: self.combo_tabs.configure(state="normal"))
                if hasattr(self, 'combo_buff_skill'):
                    self.after(0, lambda: self.combo_buff_skill.configure(state="normal"))
                self.after(0, self._update_interval_state)
            except Exception:
                pass
            self._set_status("Đã dừng", "#EF4444")

    def _handle_buff_train_hp_turn(self, tab_name: str, device_id: str, train_turn: int, current_match: int, in_battle: bool) -> tuple:
        if not self.var_buff_train_hp.get() or self.stop_requested:
            return train_turn, current_match, in_battle

        interval = self._get_buff_interval()
        current_turn = 1 if train_turn not in (1, 2) else train_turn
        pfx = f"[T{current_match}/{interval}] " if interval > 1 else ""

        # -------------------------------------------------------------------------
        # A. TRẬN 1 (current_match == 1, áp dụng cho cả interval == 1 và interval >= 2)
        # -------------------------------------------------------------------------
        if current_match == 1:
            if train_turn >= 3:
                # Đã buff xong ở Lượt 2 ➔ Quét chờ hết trận HOẶC xử lý tiếp Lượt 3+ nếu quái chưa chết
                self._set_status(f"{pfx}Đã buff ➔ Chờ T1/Lượt {train_turn}", "#38BDF8")
                while not self.stop_requested and self.var_buff_train_hp.get():
                    # 1. Quét kiểm tra hết trận (f_vaotran.png)
                    vt_x, vt_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                    if vt_x is not None and vt_y is not None:
                        return self._on_match_finished(device_id, current_match=1, interval=interval)

                    # 2. Quét kiểm tra Lượt 3+ (f_dung.png xuất hiện khi quái chưa chết hết)
                    d_x, d_y = self._find_template_on_screen(device_id, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
                    if d_x is not None and d_y is not None:
                        self._set_status(f"{pfx}Lượt {train_turn}: Auto x2 (2s)", "#10B981")
                        self._tap_auto(device_id, times=2)
                        train_turn += 1
                        if self._sleep_with_stop_check(2.0):
                            return train_turn, current_match, in_battle
                        continue

                    if self._sleep_with_stop_check(0.5):
                        return train_turn, current_match, in_battle
                return 1, current_match, in_battle

            self._set_status(f"{pfx}Chờ lượt {current_turn}...", "#38BDF8")
            found_turn = False
            while not self.stop_requested and self.var_buff_train_hp.get():
                # 1. Quét song song f_vaotran.png kiểm tra hết trận / ngoài map
                vt_x, vt_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                if vt_x is not None and vt_y is not None:
                    if in_battle:
                        # Trận 1 kết thúc
                        return self._on_match_finished(device_id, current_match=1, interval=interval)
                    else:
                        # Vừa bật tool ở ngoài map: kích hoạt auto trận 1
                        self._set_status(f"{pfx}Ngoài trận ➔ Auto", "#F59E0B")
                        self._tap_auto(device_id, times=2 if interval == 1 else 1)
                        self._wait_enter_battle(device_id)

                # 2. BẮT BUỘC CHỜ f_dung.png XUẤT HIỆN Ở CẢ LƯỢT 1 VÀ LƯỢT 2
                d_x, d_y = self._find_template_on_screen(device_id, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
                if d_x is not None and d_y is not None:
                    found_turn = True
                    in_battle = True
                    break

                if self._sleep_with_stop_check(0.35):
                    return current_turn, current_match, in_battle

            if not found_turn or not self.var_buff_train_hp.get() or self.stop_requested:
                return current_turn, current_match, in_battle

            # XỬ LÝ LƯỢT ĐÁNH TRẬN 1 (DÙNG CHUNG 100% CHO CẢ INTERVAL == 1 VÀ INTERVAL >= 2)
            if current_turn == 1:
                self._set_status(f"{pfx}Lượt 1: Auto x2 (2s)", "#10B981")
                self._tap_auto(device_id, times=2)
                if self._sleep_with_stop_check(2.0):
                    return 1, current_match, in_battle
                return 2, current_match, in_battle
            else:
                # LƯỢT 2: ĐÃ THẤY f_dung.png ➔ QUÉT CHIÊU BUFF HP/SP
                selected_skill = self.combo_buff_skill.get() if hasattr(self, 'combo_buff_skill') else "Buff Train HP"
                is_sp = (selected_skill == "Buff Train SP")
                skill_tag = "SP" if is_sp else "HP"
                skill_template = "card_f/skill/f_sp.png" if is_sp else "card_f/skill/f_hp.png"

                self._set_status(f"{pfx}Quét chiêu {skill_tag}...", "#38BDF8")
                s_x, s_y = self._find_template_on_screen(device_id, skill_template, threshold=0.85, region=(640, 0, 1280, 145))
                if s_x is None or s_y is None:
                    self._set_status(f"{pfx}K có {skill_tag} ➔ Auto (4s)", "#F59E0B")
                    self._tap_auto(device_id, times=2)
                    if self._sleep_with_stop_check(4.0):
                        return 1, current_match, in_battle
                    return 3, current_match, in_battle
                else:
                    self._set_status(f"{pfx}Buff {skill_tag} ➔ Auto (4s)", "#10B981")
                    self._tap(device_id, s_x, s_y)
                    if not self.var_buff_train_hp.get() or self.stop_requested:
                        return 1, current_match, in_battle

                    self._tap(device_id, 905, 515)
                    if not self.var_buff_train_hp.get() or self.stop_requested:
                        return 1, current_match, in_battle

                    self._tap_auto(device_id, times=2)
                    if self._sleep_with_stop_check(4.0):
                        return 1, current_match, in_battle
                    return 3, current_match, in_battle

        # -------------------------------------------------------------------------
        # B. CÁC TRẬN GIÃN CÁCH (current_match > 1, từ trận 2 đến trận N)
        # -------------------------------------------------------------------------
        else:
            # Trong trận: Hoàn toàn KHÔNG thao tác gì! Game tự động đánh bằng Auto
            # Lỗi 2: Tăng interval lên 1.2s (trận giãn cách auto, có thể kéo dài 20-60s)
            self._set_status(f"{pfx}Đang tự Auto...", "#38BDF8")

            while not self.stop_requested and self.var_buff_train_hp.get():
                # Quét nhận diện khi trận đấu kết thúc (f_vaotran.png xuất hiện)
                vt_x, vt_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                if vt_x is not None and vt_y is not None:
                    return self._on_match_finished(device_id, current_match=current_match, interval=interval)

                if self._sleep_with_stop_check(1.2):
                    return 1, current_match, in_battle

            return 1, current_match, in_battle

    # =========================================================================
    # CORE LOGIC CHẾ ĐỘ BUFF HP / SP (CHUYỂN ĐỔI TỪ HP / SP / HS CỦA MAIN_V2)
    # =========================================================================
    def _detect_dead_members(self, device_id: str):
        """
        Nhận diện thành viên gục ngã (chết) chuẩn xác 100% dựa trên tọa độ lòng trong thanh HP và SP:
        - Vùng quét lòng trong (Inner Fill): Bỏ viền kim loại ngoài, chỉ quét phần hiển thị màu (w=62, h=4).
        - Điều kiện 1 (Có thành viên/pet tham chiến): Dải màu Cyan SP (B>=140, G>=100, R<=80) >= 3px.
          -> Ngay cả khi cạn kiệt SP còn 1-2%, vẫn có >= 3px xanh -> Không bao giờ bị bỏ qua nhầm.
          -> Slot trống không có nhân vật/pet: 0px xanh -> Bỏ qua ngay.
        - Điều kiện 2 (Thành viên thực sự gục ngã): Dải máu đỏ HP (R>=140, G<=80, B<=80) <= 1px (thực tế 0px).
          -> Khi còn sống (kể cả sắp chết còn ít máu): Luôn có vệt đỏ > 1px -> Không bao giờ hồi sinh nhầm.
          -> Khi gục ngã (chết hẳn, máu về 0): Máu đỏ cạn sạch 0px -> Kích hoạt cứu ngay.
        """
        screen = self._capture_screen_fast(device_id, max_cache_age=0.0)
        if screen is None or screen.size == 0:
            return []

        # Đảm bảo chuẩn kích thước 1280x720
        if screen.shape[0] != 720 or screen.shape[1] != 1280:
            screen = cv2.resize(screen, (1280, 720), interpolation=cv2.INTER_LINEAR)

        dead_list = []

        for m in self._TEAM_HP_MEMBERS:
            # Lấy vùng lòng trong ruột thanh (Inner Fill): x+1, w=62, h=4 (loại bỏ hoàn toàn viền kim loại ngoài)
            x_hp = m["hp_x"] + 1
            y_hp = m["hp_y"] + 1
            x_sp = m["sp_x"] + 1
            y_sp = m["sp_y"]
            w = 62
            h_hp = 4
            h_sp = 4

            # 1. KIỂM TRA ĐIỀU KIỆN 1: DẢI NĂNG LƯỢNG SP (Xác nhận slot có thành viên tham chiến)
            roi_sp = screen[y_sp:y_sp + h_sp, x_sp:x_sp + w]
            if roi_sp.size == 0:
                continue

            b_sp, g_sp, r_sp = cv2.split(roi_sp)
            cyan_mask = (b_sp >= 140) & (g_sp >= 100) & (r_sp <= 80)
            cyan_sp = int(np.sum(cyan_mask))

            # Slot trống không có thành viên / không mang pet (cyan_sp < 3px) -> Bỏ qua
            if cyan_sp < 3:
                continue

            # Chống nhận diện nhầm chữ số/hiệu ứng bay ở giữa thanh (như số lượt, sát thương ở map Boss):
            # Thanh SP thật của nhân vật/pet luôn hiển thị bắt đầu từ mép trái (10 pixel đầu tiên của thanh).
            if not np.any(cyan_mask[:, :10]):
                continue

            # 2. KIỂM TRA ĐIỀU KIỆN 2: DẢI MÁU ĐỎ HP (Xác nhận thành viên đã gục ngã)
            roi_hp = screen[y_hp:y_hp + h_hp, x_hp:x_hp + w]
            if roi_hp.size == 0:
                continue

            b_hp, g_hp, r_hp = cv2.split(roi_hp)
            red_hp = int(np.sum((r_hp >= 140) & (g_hp <= 80) & (b_hp <= 80)))

            # Thành viên gục ngã khi máu đỏ cạn sạch về 0 (red_hp <= 1px)
            if red_hp <= 1:
                dead_list.append({
                    **m,
                    "x": m["hp_x"],
                    "y": m["hp_y"],
                    "red_pixels": red_hp,
                    "cyan_sp": cyan_sp
                })

        return dead_list

    def _handle_priority_hs(self, device_id: str, min_dead: int = 1) -> bool:
        """
        Thao tác ưu tiên Hồi Sinh:
        Kích hoạt khi có từ min_dead thành viên chết trở lên (mặc định 1).
        Ưu tiên cứu Hàng Sau 1->5 trước, sau đó Hàng Trước 1->5.
        Tap chiêu card_f/skill/f_hs.png ➔ Tap mục tiêu chết (x+35, y+95) ➔ Tap Auto 2 lần ➔ Hoãn 5s.
        """
        if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return False

        dead_members = self._detect_dead_members(device_id)
        total_dead = len(dead_members)

        if total_dead < min_dead:
            return False

        priority_member = dead_members[0]
        key_name = priority_member.get("name", "Unknown")
        d_x = priority_member.get("x", 0)
        d_y = priority_member.get("y", 0)

        self._set_status(f"Ưu tiên HS {key_name} (chết {total_dead})...", "#F59E0B")
        if self._sleep_with_stop_check(0.1):
            return False

        hs_x, hs_y = self._find_template_on_screen(device_id, "card_f/skill/f_hs.png", threshold=0.85, region=(640, 0, 1280, 145))
        if hs_x is None or hs_y is None:
            self._set_status("Không thấy chiêu HS", "#EF4444")
            self._sleep_with_stop_check(0.1)
            return False

        self._set_status(f"HS {key_name} ➔ Auto (chờ 5s)", "#10B981")
        self._tap(device_id, hs_x, hs_y)
        if self._sleep_with_stop_check(0.2):
            return True

        target_x = d_x + 35
        target_y = d_y + 95
        self._tap(device_id, target_x, target_y)
        if self._sleep_with_stop_check(0.2):
            return True

        self._tap_login_auto_twice(device_id)
        if self._sleep_with_stop_check(5.0):
            return True

        return True

    def _check_and_tap_f_tieptheo(self, device_id: str):
        """Quét tìm card_f/f_tieptheo.png trong 0.5s sau khi thấy f_dung.png và tap nếu có"""
        if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return
        start_tt = time.time()
        while time.time() - start_tt < 0.5:
            if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
                return
            tt_x, tt_y = self._find_template_on_screen(device_id, "card_f/f_tieptheo.png", threshold=0.80, region=(1050, 530, 1165, 680))
            if tt_x is not None and tt_y is not None:
                self._tap(device_id, tt_x, tt_y)
                self._sleep_with_stop_check(0.3)
                break
            if self._sleep_with_stop_check(0.25):
                return

    def _handle_buff_hp_sp_turn(self, device_id: str, action_type: str = "HP") -> bool:
        """
        Xử lý 1 lượt đánh hoàn chỉnh cho Mốc Buff HP / SP (HP / SP / HS cũ):
        1. Quét chờ f_dung.png (hoặc f_vaotran.png nếu ở ngoài/hết trận) (chỉ quét không tap).
        2. Quét & tap f_tieptheo.png nếu có trong 0.5s.
        3. Kiểm tra Thao Tác Ưu Tiên Hồi Sinh (_handle_priority_hs):
           - Nếu có >= 1 thành viên chết và có chiêu HS -> hồi sinh mục tiêu, tap Auto, hoãn 5s.
        4. Nếu không hồi sinh -> Ra chiêu theo chu kỳ (HP hoặc SP):
           - Quét f_hp.png hoặc f_sp.png.
           - Có thấy: tap chiêu -> hoãn 0.2s -> tap tọa độ trung tâm (905, 515) -> hoãn 0.2s -> tap Auto 2 lần -> hoãn 5s.
           - Không thấy: tap Auto 2 lần -> hoãn 5s.
        """
        if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return False

        self._set_status(f"Chờ lượt ({action_type})...", "#38BDF8")

        found_turn = False
        while not self.stop_requested and self.var_buff_train_hp.get() and not self._stop_event.is_set():
            # 1. Quét song song f_vaotran.png kiểm tra hết trận / ngoài trận
            vt_x, vt_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
            if vt_x is not None and vt_y is not None:
                self._set_status("Hết trận ➔ Tap Auto", "#F59E0B")
                self._tap_login_auto_twice(device_id)
                self._set_status("Hết trận ➔ Chờ trận mới", "#F59E0B")
                while not self.stop_requested and self.var_buff_train_hp.get() and not self._stop_event.is_set():
                    # Lỗi 2: 0.35s → 0.5s (đang chờ trận mới bắt đầu, không cần siêu nhanh)
                    if self._sleep_with_stop_check(0.5):
                        return False
                    d_chk_x, d_chk_y = self._find_template_on_screen(device_id, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
                    if d_chk_x is not None and d_chk_y is not None:
                        found_turn = True
                        break
                    vt_chk_x, vt_chk_y = self._find_template_on_screen(device_id, "card_f/f_vaotran.png", threshold=0.80, region=(1215, 0, 1280, 45))
                    if vt_chk_x is None or vt_chk_y is None:
                        break

                self._set_status("Vào trận ➔ Chờ 0.6s", "#38BDF8")
                if self._sleep_with_stop_check(0.6):
                    return False

                if found_turn:
                    break
                else:
                    self._set_status(f"Chờ lượt ({action_type})...", "#38BDF8")

            # 2. Quét f_dung.png kiểm tra đến lượt
            d_x, d_y = self._find_template_on_screen(device_id, "card_f/f_dung.png", threshold=0.80, region=(640, 0, 1280, 145))
            if d_x is not None and d_y is not None:
                found_turn = True
                break

            # Lỗi 2: 0.35s → 0.5s (chờ đến lượt trong chế độ HP/SP)
            if self._sleep_with_stop_check(0.5):
                return False

        if not found_turn or self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return False

        # Thấy f_dung.png ➔ Quét tìm & tap f_tieptheo.png nếu có
        self._check_and_tap_f_tieptheo(device_id)
        if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return False

        # 2. Kiểm tra thao tác ưu tiên Hồi Sinh (>= 1 người chết)
        handled_hs = self._handle_priority_hs(device_id, min_dead=1)
        if handled_hs:
            return True

        if self.stop_requested or not self.var_buff_train_hp.get() or self._stop_event.is_set():
            return False

        # 3. Kỹ năng buff theo chu kỳ (HP hoặc SP)
        skill_img = "card_f/skill/f_hp.png" if action_type == "HP" else "card_f/skill/f_sp.png"
        self._set_status(f"Quét chiêu {action_type}...", "#38BDF8")

        s_x, s_y = self._find_template_on_screen(device_id, skill_img, threshold=0.85, region=(640, 0, 1280, 145))
        if s_x is None or s_y is None:
            self._set_status(f"Không {action_type} ➔ Auto (chờ 5s)", "#F59E0B")
            self._tap_login_auto_twice(device_id)
            if self._sleep_with_stop_check(5.0):
                return False
        else:
            self._set_status(f"Buff {action_type} ➔ Auto (chờ 5s)", "#10B981")
            self._tap(device_id, s_x, s_y)
            if self._sleep_with_stop_check(0.2):
                return False

            self._tap(device_id, 905, 515)
            if self._sleep_with_stop_check(0.2):
                return False

            self._tap_login_auto_twice(device_id)
            if self._sleep_with_stop_check(5.0):
                return False

        return True


def _ensure_single_instance():
    """Đảm bảo chỉ có duy nhất 1 phiên bản tool chạy cùng lúc trên Windows.
    Nếu phát hiện tool đã mở trước đó, khôi phục cửa sổ tool cũ lên đầu màn hình và thoát ngay."""
    import ctypes

    MUTEX_NAME = "Global\\TS_Origin_Buff_Train_BlueStacks_SingleInstance_Mutex"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183

    if last_error == ERROR_ALREADY_EXISTS:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "TS Origin - Buff Train (BlueStacks)")
            if not hwnd:
                hwnd = user32.FindWindowW(None, "TS Origin - Buff Train")
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        os._exit(0)
    return mutex


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    _app_instance_mutex = _ensure_single_instance()
    app = BuffTrainTool()
    app.mainloop()
