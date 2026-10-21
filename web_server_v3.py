import os
import sys
import json
import time
import socket
import tempfile
import threading
import subprocess
import shutil
import urllib.request
import urllib.parse
import re
import cv2
import numpy as np
import concurrent.futures
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

def get_local_ip():
    """Lấy địa chỉ IP mạng LAN nội bộ của máy tính"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class LDStreamManager:
    """Quản lý luồng Giám sát màn hình giả lập Siêu Nhẹ (Zero Disk I/O, Chu kỳ 0.5s - 1s - 2s)"""
    def __init__(self):
        self._frames = {}       # tab_key -> bytes (JPEG)
        self._locks = {}        # tab_key -> Lock
        self._threads = {}      # tab_key -> Thread
        self._running = {}      # tab_key -> bool
        self._last_req = {}     # tab_key -> float
        self._req_quality = {}  # tab_key -> str ("0.5s" | "1s" | "2s")
        self._active_devs = {}  # tab_key -> dev_str
        self._main_lock = threading.Lock()

    def _normalize_mode(self, q):
        s = str(q).lower().strip()
        if s in ("0.5s", "0.5", "1080p"):
            return "0.5s"
        elif s in ("2s", "2.0s", "2", "fast"):
            return "2s"
        return "1s"

    def _resolve_tab_key(self, app, tab_index):
        dict_map = getattr(app, "dict_name_to_index", {}) if app else {}
        if str(tab_index) in dict_map:
            return str(dict_map[str(tab_index)])
        nums = re.findall(r'\d+', str(tab_index))
        return nums[0] if nums else str(tab_index)

    def touch_tab(self, app, tab_index):
        tab_key = self._resolve_tab_key(app, tab_index)
        with self._main_lock:
            self._last_req[tab_key] = time.time()

    def get_frame(self, app, tab_index, quality_mode="1s"):
        tab_key = self._resolve_tab_key(app, tab_index)
        mode = self._normalize_mode(quality_mode)
        now = time.time()
        with self._main_lock:
            self._last_req[tab_key] = now
            self._req_quality[tab_key] = mode
            if tab_key not in self._locks:
                self._locks[tab_key] = threading.Lock()
            if tab_key not in self._threads or not self._threads[tab_key].is_alive():
                self._running[tab_key] = True
                t = threading.Thread(target=self._capture_worker, args=(app, tab_key), daemon=True)
                self._threads[tab_key] = t
                t.start()

        with self._locks[tab_key]:
            return self._frames.get(tab_key)

    def _capture_worker(self, app, tab_key):
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        adb_path = os.path.join(getattr(app, 'ld_path', ''), "adb.exe") if hasattr(app, 'ld_path') else "adb.exe"
        if not os.path.exists(adb_path):
            for candidate_dir in [r"C:\LDPlayer\LDPlayer9", r"C:\LDPlayer", r"C:\leidian\LDPlayer9", r"C:\Program Files\LDPlayer9", r"C:\Program Files\LDPlayer\LDPlayer9"]:
                cand = os.path.join(candidate_dir, "adb.exe")
                if os.path.exists(cand):
                    adb_path = cand
                    break
            else:
                adb_path = shutil.which("adb") or "adb"

        # Tự động map tên tab sang index số thực tế của LDPlayer
        tab_num_str = self._resolve_tab_key(app, tab_key)
        tab_num = int(tab_num_str) if tab_num_str.isdigit() else 0

        candidate_devices = [
            f"emulator-{5554 + tab_num * 2}"
        ]

        active_dev = self._active_devs.get(tab_key, candidate_devices[0])

        while self._running.get(tab_key, False):
            now = time.time()
            # Tự động dừng hẳn thread nếu không còn client nào xem tab này quá 15 giây (Giải phóng 100% CPU/RAM nhàn rỗi)
            if now - self._last_req.get(tab_key, 0) > 15.0:
                with self._main_lock:
                    self._running[tab_key] = False
                break
            elif now - self._last_req.get(tab_key, 0) > 3.0:
                time.sleep(0.5)
                continue

            frame_bytes = None
            if getattr(app, 'is_bluestacks', False) and hasattr(app, '_capture_screen_fast'):
                try:
                    img = app._capture_screen_fast(None, tab_key, max_cache_age=0.5)
                    if img is not None and getattr(img, 'shape', None):
                        ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                        if ok:
                            frame_bytes = buf.tobytes()
                except Exception:
                    pass

            devs = [active_dev] + [d for d in candidate_devices if d != active_dev]

            # 1. Trích xuất raw RGBA framebuffer từ Android bằng adb exec-out screencap (Zero Disk I/O)
            if frame_bytes is None:
                for dev in devs:
                    p = None
                    try:
                        p = subprocess.Popen(
                            [adb_path, "-s", dev, "exec-out", "screencap"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            creationflags=creation_flags
                        )
                        header = p.stdout.read(16)
                        if len(header) >= 16:
                            w = int.from_bytes(header[0:4], "little")
                            h = int.from_bytes(header[4:8], "little")
                            if 100 < w <= 3840 and 100 < h <= 3840:
                                raw_len = w * h * 4
                                raw_bytes = p.stdout.read(raw_len)
                                if len(raw_bytes) == raw_len:
                                    arr = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((h, w, 4))
                                    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                                    if w > 1280 or h > 720:
                                        bgr = cv2.resize(bgr, (1280, 720), interpolation=cv2.INTER_LINEAR)
                                    ok_jpg, buf_jpg = cv2.imencode('.jpg', bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                                    if ok_jpg:
                                        frame_bytes = buf_jpg.tobytes()
                                        self._active_devs[tab_key] = dev
                                        active_dev = dev
                                        break
                    except Exception:
                        pass
                    finally:
                        if p:
                            try:
                                if p.stdout:
                                    p.stdout.close()
                            except Exception:
                                pass
                            try:
                                p.wait(timeout=0.1)
                            except Exception:
                                try:
                                    p.kill()
                                except Exception:
                                    pass

            # 2. Dự phòng qua cơ chế cache in-memory của tool nếu có
            if frame_bytes is None and hasattr(app, '_capture_screen_fast'):
                try:
                    dnconsole_path = os.path.join(getattr(app, 'ld_path', ''), "ldconsole.exe")
                    if not os.path.exists(dnconsole_path):
                        dnconsole_path = os.path.join(getattr(app, 'ld_path', ''), "dnconsole.exe")
                    img = app._capture_screen_fast(dnconsole_path, tab_key, max_cache_age=0.5)
                    if img is not None and getattr(img, 'shape', None):
                        ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                        if ok:
                            frame_bytes = buf.tobytes()
                except Exception:
                    pass

            if frame_bytes:
                with self._locks[tab_key]:
                    self._frames[tab_key] = frame_bytes
                req_mode = self._normalize_mode(self._req_quality.get(tab_key, "1s"))
                # Chu kỳ nghỉ giữa các lần chụp để CPU máy tính hoàn toàn hạ nhiệt:
                sleep_sec = 0.5 if req_mode == "0.5s" else (2.0 if req_mode == "2s" else 1.0)
                time.sleep(sleep_sec)
            else:
                time.sleep(0.5)


_stream_manager = LDStreamManager()


def get_screenshot_bytes(app):
    """Chụp màn hình giả lập LDPlayer đang chọn và trả về JPEG bytes"""
    try:
        tab_name, tab_index = app._get_selected_ld_info() if hasattr(app, '_get_selected_ld_info') else (None, "0")
        if tab_index is not None:
            f = _stream_manager.get_frame(app, str(tab_index), quality_mode="1s")
            if f:
                return f
    except Exception:
        pass
    return None


HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="TS Origin v3">
    <title>TS Origin - Mobile Control v3</title>
    <script>
        if (window.self !== window.top || window.location.search.includes('embed=1')) {
            document.documentElement.classList.add('in-iframe');
        }
    </script>
    <!-- Apple iOS Touch Icon & PWA Manifest -->
    <link rel="apple-touch-icon" href="/assets/icons/apple-touch-icon.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/assets/icons/apple-touch-icon.png">
    <link rel="icon" type="image/png" sizes="192x192" href="/assets/icons/icon-192.png">
    <link rel="icon" type="image/png" sizes="32x32" href="/assets/icons/favicon-32x32.png">
    <link rel="shortcut icon" href="/favicon.ico">
    <link rel="manifest" href="/manifest.json">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #121317;
            --surface: #1a1c23;
            --surface-card: #14161c;
            --surface-input: #25272e;
            --border: #3d4049;
            --border-active: rgba(56, 189, 248, 0.6);
            --primary: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.35);
            --accent: #ea580c;
            --accent-glow: rgba(234, 88, 12, 0.45);
            --btn-navy: #2c3545;
            --btn-navy-hover: #3a455a;
            --btn-game: #00875a;
            --btn-stop: #d32f2f;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --text: #e2e8f0;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --font-main: 'Segoe UI', 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
            font-family: var(--font-main);
        }

        html {
            font-size: 18px;
            height: 100%;
            background-color: var(--bg);
        }

        body {
            background: radial-gradient(circle at 50% -10%, #1a1e28 0%, #121317 50%, #0d0e12 100%);
            background-attachment: fixed;
            color: var(--text);
            min-height: 100%;
            min-height: 100dvh;
            padding-bottom: calc(155px + env(safe-area-inset-bottom, 0px));
            overflow-x: hidden;
            user-select: none;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--success);
            box-shadow: 0 0 8px var(--success);
        }

        .status-dot.running {
            background-color: var(--warning);
            box-shadow: 0 0 10px var(--warning);
            animation: pulse 1.4s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.45; transform: scale(1.3); }
        }

        /* Tab Content Container */
        .container {
            max-width: 580px;
            margin: 0 auto;
            padding: calc(10px + env(safe-area-inset-top, 0px)) 12px 14px 12px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .in-iframe body {
            padding-top: 0 !important;
        }
        .in-iframe .container {
            padding-top: 8px !important;
        }

        .tab-pane {
            display: none;
            flex-direction: column;
            gap: 14px;
            animation: fadeIn 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: calc(100dvh - 230px);
        }

        .tab-pane.active {
            display: flex;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }


        /* Cards */
        .card {
            background: #1a1c23;
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.35), transparent);
            pointer-events: none;
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .card-title {
            font-size: 1.02rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 7px;
            color: #38bdf8;
            text-shadow: 0 0 12px rgba(56, 189, 248, 0.3);
            letter-spacing: -0.2px;
        }

        /* Switch toggle (Modern Gaming Glow - Ergonomic & High Precision) */
        .switch {
            position: relative;
            display: inline-block;
            width: 52px;
            height: 28px;
            flex-shrink: 0;
            user-select: none;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background: radial-gradient(circle at 30% 30%, #1e293b, #0f172a);
            border: 1.5px solid #334155;
            transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
            border-radius: 28px;
            box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.6), 0 1px 2px rgba(255, 255, 255, 0.05);
        }

        .switch:hover .slider {
            border-color: #475569;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 2.5px;
            background: linear-gradient(180deg, #ffffff 0%, #cbd5e1 100%);
            transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
            border-radius: 50%;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255, 255, 255, 0.9);
        }

        .switch:hover .slider:before {
            filter: brightness(1.1);
        }

        input:checked + .slider {
            background: linear-gradient(135deg, #fb923c 0%, #ea580c 50%, #c2410c 100%);
            border-color: #fdba74;
            box-shadow: 0 0 18px rgba(249, 115, 22, 0.65), 0 0 6px rgba(234, 88, 12, 0.9), inset 0 1px 2px rgba(255, 255, 255, 0.4);
        }

        input:checked + .slider:before {
            transform: translateX(23px) scale(1.03);
            background: linear-gradient(180deg, #ffffff 0%, #ffedd5 100%);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), 0 0 8px rgba(255, 255, 255, 0.85);
        }

        /* Circular Checkbox Toggle (Đồng bộ nút tròn Tạm Dừng Card D & Chiến Đấu chuẩn 28px) */
        .chk-round {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            min-height: 28px !important;
            border-radius: 50% !important;
            background: radial-gradient(circle at 30% 30%, #1e293b, #0f172a);
            border: 1.5px solid #334155;
            cursor: pointer;
            transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.6), 0 1px 2px rgba(255, 255, 255, 0.05);
            flex-shrink: 0;
            user-select: none;
            box-sizing: border-box;
        }

        .chk-round:hover {
            border-color: #475569;
            transform: scale(1.06);
        }

        .chk-round:active {
            transform: scale(0.94);
        }

        .chk-round input {
            opacity: 0;
            width: 0;
            height: 0;
            position: absolute;
            margin: 0;
            pointer-events: none;
        }

        .chk-round .chk-mark {
            opacity: 0;
            transform: scale(0.3);
            transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            color: #ffffff;
            font-size: 13px;
            font-weight: 900;
            line-height: 1;
        }

        .chk-round:has(input:checked) {
            background: linear-gradient(135deg, #fb923c 0%, #ea580c 50%, #c2410c 100%);
            border-color: #fdba74;
            box-shadow: 0 0 16px rgba(249, 115, 22, 0.65), inset 0 1px 2px rgba(255, 255, 255, 0.4);
        }

        .chk-round:has(input:checked) .chk-mark {
            opacity: 1;
            transform: scale(1);
        }

        .form-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }

        label {
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.2px;
        }

        select {
            background: #374151;
            color: #ffffff;
            border: 1px solid #4b5563;
            padding: 0 10px;
            border-radius: 8px;
            font-size: 0.84rem;
            font-weight: 600;
            outline: none;
            cursor: pointer;
            width: 100%;
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            box-sizing: border-box !important;
            transition: all 0.2s ease;
            -webkit-tap-highlight-color: transparent;
        }

        select:focus, select:hover {
            border-color: #38bdf8;
            background: #4b5563;
        }

        select option {
            background: #1f2937;
            color: #ffffff;
        }

        /* Ô nhập văn bản / giờ chuẩn hóa trục Y đồng bộ 38px */
        input[type="text"] {
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            line-height: 36px !important;
            box-sizing: border-box !important;
            background: #1e293b;
            border: 1px solid #475569;
            color: #38bdf8;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 700;
            font-family: var(--font-mono), monospace, 'Segoe UI';
            padding: 0 8px;
            outline: none;
            transition: all 0.2s ease;
            -webkit-tap-highlight-color: transparent;
        }

        input[type="text"]:focus, input[type="text"]:hover {
            border-color: #38bdf8;
            background: #334155;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.35);
        }

        /* Ô nhập giờ chuyên dụng - trục Y dày dặn, font to rõ 0.95rem, căn giữa cân đối với các nút */
        .time-input {
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            line-height: 36px !important;
            font-size: 0.95rem !important;
            font-weight: 700 !important;
            font-family: var(--font-mono), monospace, 'Segoe UI' !important;
            text-align: center !important;
            background: #1e293b !important;
            border: 1.5px solid #475569 !important;
            color: #38bdf8 !important;
            border-radius: 8px !important;
            box-sizing: border-box !important;
            padding: 0 4px !important;
            outline: none !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        .time-input:focus, .time-input:hover {
            border-color: #38bdf8 !important;
            background: #334155 !important;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.4) !important;
        }

        /* Dropdown cột phải chuẩn hóa đồng bộ 38px */
        .select-right-standard {
            width: 135px;
            min-width: 110px;
            max-width: 145px;
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            font-size: 0.84rem;
            font-weight: 600;
            padding: 0 8px;
            border-radius: 8px;
            box-sizing: border-box !important;
            background: #374151;
            border: 1px solid #4b5563;
            color: #ffffff;
            outline: none;
            cursor: pointer;
            flex-shrink: 0;
            text-align: center;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        .select-right-standard:hover, .select-right-standard:focus {
            background: #4b5563;
            border-color: var(--accent);
        }

        /* Khung hộp chứa hàng bên trong Card đồng bộ */
        .card-inner-box {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 8px 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            box-sizing: border-box;
            width: 100%;
        }

        /* Đường gạch phân cách cam đồng bộ với Desktop */
        .divider-h {
            height: 2px;
            background: #ea580c;
            border-radius: 1px;
            margin: 6px 0;
            width: 100%;
        }

        .divider-v {
            width: 2px;
            background: #ea580c;
            border-radius: 1px;
            flex-shrink: 0;
            align-self: stretch;
        }

        .checkbox-group {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }

        .chk-label {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: #25272e;
            border: 1px solid var(--border);
            padding: 0 10px;
            border-radius: 8px;
            font-size: 0.84rem;
            font-weight: 600;
            color: var(--text-muted);
            cursor: pointer;
            user-select: none;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            white-space: nowrap;
            box-sizing: border-box !important;
            flex-shrink: 0;
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
        }

        .chk-label:hover {
            border-color: #4b5563;
            background: #2c3545;
            color: var(--text);
        }

        .chk-label:active {
            transform: scale(0.96);
        }

        .chk-label:has(input:checked) {
            background: rgba(234, 88, 12, 0.2);
            border-color: #ea580c;
            color: #ffffff;
            box-shadow: 0 0 10px rgba(234, 88, 12, 0.3);
        }

        .chk-label input {
            accent-color: var(--accent);
            width: 18px;
            height: 18px;
            margin: 0;
            flex-shrink: 0;
            cursor: pointer;
        }

        /* Lưới 5 nút Phụ Bản cân đối 100% bằng nhau */
        .grid-pb-5 {
            display: grid !important;
            grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
            gap: 4px !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        .grid-pb-5 .chk-label {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            padding: 0 2px !important;
            gap: 3px !important;
            font-size: 0.74rem !important;
            letter-spacing: -0.3px !important;
            justify-content: center !important;
            overflow: hidden !important;
            white-space: nowrap !important;
            box-sizing: border-box !important;
        }

        .grid-pb-5 .chk-label input {
            width: 14px !important;
            height: 14px !important;
            min-width: 14px !important;
            min-height: 14px !important;
            margin: 0 !important;
            flex-shrink: 0 !important;
        }

        /* Screen Preview & Fullscreen Theater Mode */
        .preview-box {
            width: 100%;
            border-radius: 12px;
            overflow: hidden;
            background: #090d16;
            border: 1px solid rgba(255, 255, 255, 0.12);
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
            cursor: default;
            user-select: none;
            -webkit-user-select: none;
            -webkit-tap-highlight-color: transparent;
        }

        .preview-img {
            width: 100%;
            height: auto;
            max-height: 70vh;
            display: block;
            object-fit: contain;
            pointer-events: none;
            user-select: none;
            -webkit-user-drag: none;
        }

        .btn-mini {
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(4px);
            border: 1px solid rgba(255,255,255,0.15);
            color: #fff;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s;
        }

        .btn-mini:active {
            transform: scale(0.95);
        }


        /* Đồng bộ kích thước cố định đều nhau 38px cho các hàng điều khiển */
        .combat-col-left {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
        }

        .combat-btn-ctrl {
            height: 38px;
            min-height: 38px;
            max-height: 38px;
            font-size: 0.84rem;
            font-weight: 600;
            color: #ffffff;
            background: #374151;
            border: 1px solid #4b5563;
            border-radius: 8px;
            cursor: pointer;
            box-sizing: border-box;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0 12px;
            line-height: 1;
            white-space: nowrap;
            outline: none;
            -webkit-tap-highlight-color: transparent;
            transition: background 0.15s ease, border-color 0.15s ease;
        }
        button.combat-btn-ctrl:hover {
            background: #4b5563;
            border-color: var(--accent);
        }
        button.combat-btn-ctrl:active {
            transform: scale(0.97);
        }

        select.combat-btn-ctrl {
            padding: 0 8px;
            font-size: 0.84rem;
            color: #ffffff;
            background-color: #374151;
            border: 1px solid #4b5563;
            border-radius: 8px;
            cursor: pointer;
            text-align: left;
            text-align-last: left;
        }
        select.combat-btn-ctrl:hover {
            background: #4b5563;
            border-color: var(--accent);
        }
        select.combat-btn-ctrl:active {
            transform: none !important;
        }
        select.combat-btn-ctrl:focus {
            outline: none !important;
            border-color: var(--accent) !important;
            box-shadow: none !important;
        }

        .chk-combat-sub {
            font-size: 0.72rem;
            color: #9CA3AF;
            white-space: nowrap;
            padding-left: 0;
            margin-left: 0;
            flex-shrink: 0;
        }
        .combat-select-right {
            width: 135px;
            min-width: 110px;
            max-width: 145px;
            height: 38px;
            min-height: 38px;
            max-height: 38px;
            font-size: 0.84rem;
            font-weight: 600;
            padding: 0 10px;
            border-radius: 8px;
            box-sizing: border-box;
            background: #374151;
            border: 1px solid #4b5563;
            color: #ffffff;
            outline: none;
            cursor: pointer;
            -webkit-tap-highlight-color: transparent;
            flex-shrink: 0;
            transition: background 0.15s ease, border-color 0.15s ease;
        }
        select.combat-select-right:hover {
            background: #4b5563;
            border-color: var(--accent);
        }
        select.combat-select-right:active {
            transform: none !important;
        }
        select.combat-select-right:focus {
            outline: none !important;
            border-color: var(--accent) !important;
            box-shadow: none !important;
        }

        /* Lưới 4 Card Hàng Ngày (40 NPC, Nhị Kiều...) - Tối ưu Desktop & Mobile */
        .daily-subcards-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            grid-template-rows: auto 1fr;
            gap: 10px;
            width: 100%;
            box-sizing: border-box;
        }

        .daily-subcards-grid .card {
            display: flex !important;
            flex-direction: column !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
        }

        /* Hàng 1: Card 40 NPC & Nhị Kiều thu gọn trục Y ôm sát như Card Boss Thế Giới */
        .daily-subcard-compact {
            padding: 10px 12px !important;
        }

        .daily-subcard-compact .card-header {
            height: 28px !important;
            min-height: 28px !important;
            max-height: 28px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            padding-bottom: 4px !important;
            margin-bottom: 8px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
            box-sizing: border-box !important;
        }

        .daily-subcard-compact .card-header .card-title {
            font-size: 0.95rem !important;
            white-space: nowrap !important;
        }

        .daily-subcard-compact .card-header #entry_D_time {
            height: 26px !important;
            min-height: 26px !important;
            max-height: 26px !important;
            line-height: 24px !important;
            font-size: 0.84rem !important;
            width: 70px !important;
            padding: 0 4px !important;
            box-sizing: border-box !important;
            margin: 0 !important;
        }

        .daily-subcard-compact .header-time-placeholder {
            width: 70px !important;
            height: 26px !important;
            visibility: hidden !important;
            flex-shrink: 0 !important;
        }

        /* Khung nội dung: Bỏ hoàn toàn fixed height để ôm trọn các mục bên trong, tuyệt đối không bị đè viền */
        .daily-subcard-compact .card-inner-box {
            padding: 6px 8px !important;
            box-sizing: border-box !important;
            width: 100% !important;
            min-width: 0 !important;
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 8px !important;
            height: auto !important;
            min-height: unset !important;
            max-height: unset !important;
        }

        /* Hàng 2: Card Hoạt Động 1 & 2 tăng trục Y bù lại phần đã giảm của Hàng 1 */
        .daily-subcard-expanded {
            padding: 10px 12px !important;
            min-height: 110px !important;
        }

        .daily-subcard-expanded .card-header {
            height: 28px !important;
            min-height: 28px !important;
            max-height: 28px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            padding-bottom: 4px !important;
            margin-bottom: 8px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
            box-sizing: border-box !important;
        }

        .daily-subcard-expanded .card-header .card-title {
            font-size: 0.95rem !important;
            white-space: nowrap !important;
        }

        .daily-subcard-expanded .card-inner-box {
            padding: 8px 10px !important;
            box-sizing: border-box !important;
            width: 100% !important;
            min-width: 0 !important;
            display: flex !important;
            flex: 1 !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: 52px !important;
            color: var(--text-muted) !important;
            font-size: 0.84rem !important;
            font-style: italic !important;
        }

        /* Nút ô tích & Dropdown của lưới Daily Subcards: Đồng bộ chiều cao chuẩn 36px, lọt lòng gọn gàng */
        .daily-subcards-grid .chk-label {
            flex: 1 !important;
            min-width: 0 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 6px !important;
            height: 36px !important;
            min-height: 36px !important;
            max-height: 36px !important;
            padding: 0 8px !important;
            font-size: 0.84rem !important;
            font-weight: 700 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            margin: 0 !important;
            cursor: pointer !important;
            box-sizing: border-box !important;
        }

        .daily-subcards-grid .chk-label input {
            width: 16px !important;
            height: 16px !important;
            min-width: 16px !important;
            margin: 0 !important;
            flex-shrink: 0 !important;
        }

        .daily-subcards-grid select {
            width: 90px !important;
            min-width: 78px !important;
            max-width: 100px !important;
            height: 36px !important;
            min-height: 36px !important;
            max-height: 36px !important;
            line-height: 34px !important;
            text-align: center !important;
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            padding: 0 4px !important;
            box-sizing: border-box !important;
            border-radius: 8px !important;
            background: #25272e !important;
            border: 1px solid var(--border) !important;
            color: #ffffff !important;
            cursor: pointer !important;
            outline: none !important;
            flex-shrink: 0 !important;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        .daily-subcards-grid select:hover, .daily-subcards-grid select:focus {
            background: #4b5563 !important;
            border-color: var(--accent) !important;
        }

        @media (max-width: 440px) {
            .daily-subcards-grid {
                gap: 8px !important;
            }
            .daily-subcard-compact {
                padding: 8px 8px !important;
            }
            .daily-subcard-compact .card-header {
                height: 26px !important;
                min-height: 26px !important;
                max-height: 26px !important;
                margin-bottom: 6px !important;
                padding-bottom: 2px !important;
            }
            .daily-subcard-compact .card-header .card-title {
                font-size: 0.85rem !important;
            }
            .daily-subcard-compact .card-header #entry_D_time {
                width: 60px !important;
                height: 24px !important;
                min-height: 24px !important;
                max-height: 24px !important;
                line-height: 22px !important;
                font-size: 0.78rem !important;
                padding: 0 2px !important;
            }
            .daily-subcard-compact .header-time-placeholder {
                width: 60px !important;
                height: 24px !important;
            }
            .daily-subcard-compact .card-inner-box {
                height: auto !important;
                min-height: unset !important;
                max-height: unset !important;
                padding: 4px 6px !important;
                gap: 6px !important;
            }
            .daily-subcard-expanded {
                padding: 8px 8px !important;
                min-height: 95px !important;
            }
            .daily-subcard-expanded .card-header {
                height: 26px !important;
                min-height: 26px !important;
                max-height: 26px !important;
                margin-bottom: 6px !important;
                padding-bottom: 2px !important;
            }
            .daily-subcard-expanded .card-header .card-title {
                font-size: 0.85rem !important;
            }
            .daily-subcard-expanded .card-inner-box {
                padding: 6px 6px !important;
                min-height: 48px !important;
                font-size: 0.78rem !important;
            }
            .daily-subcards-grid .chk-label {
                height: 32px !important;
                min-height: 32px !important;
                max-height: 32px !important;
                font-size: 0.78rem !important;
                gap: 4px !important;
                padding: 0 6px !important;
                letter-spacing: -0.2px !important;
            }
            .daily-subcards-grid .chk-label input {
                width: 14px !important;
                height: 14px !important;
                min-width: 14px !important;
            }
            .daily-subcards-grid select {
                width: 76px !important;
                min-width: 66px !important;
                max-width: 82px !important;
                height: 32px !important;
                min-height: 32px !important;
                max-height: 32px !important;
                line-height: 30px !important;
                font-size: 0.76rem !important;
                padding: 0 2px !important;
            }
            .select-right-standard, .combat-select-right {
                width: 115px !important;
                min-width: 95px !important;
                font-size: 0.78rem !important;
                padding: 0 4px !important;
            }
            .chk-label {
                font-size: 0.78rem !important;
                padding: 0 6px !important;
                gap: 5px !important;
            }
            .chk-combat-sub {
                font-size: 0.65rem !important;
            }
            .grid-pb-5 {
                gap: 2px !important;
            }
            .grid-pb-5 .chk-label {
                font-size: 0.67rem !important;
                padding: 0 1px !important;
                gap: 2px !important;
                letter-spacing: -0.5px !important;
            }
            .grid-pb-5 .chk-label input {
                width: 12px !important;
                height: 12px !important;
                min-width: 12px !important;
                min-height: 12px !important;
            }
            .card-inner-box {
                padding: 6px 8px !important;
                gap: 6px !important;
            }
            .curved-tab-bar {
                padding: 5px 3px 4px 3px !important;
                border-radius: 22px !important;
            }
            .tab-button.nav-tab-item {
                padding: 3px 2px !important;
            }
            .tab-button.nav-tab-item .tab-icon-wrap svg {
                width: 19px !important;
                height: 19px !important;
            }
            .tab-button.nav-tab-item .tab-label {
                font-size: 0.70rem !important;
                letter-spacing: -0.2px !important;
            }
            .nav-center-slot {
                width: 66px !important;
                margin: 0 2px !important;
            }
            .fab-circle {
                width: 48px !important;
                height: 48px !important;
                min-width: 48px !important;
                min-height: 48px !important;
                transform: translateY(-14px) !important;
            }
            .fab-circle svg {
                width: 22px !important;
                height: 22px !important;
            }
            .fab-label {
                font-size: 0.64rem !important;
                margin-top: -8px !important;
            }
            .team-box {
                height: 340px !important;
                min-height: 340px !important;
                max-height: 340px !important;
            }
        }

        /* Boss Element Colors & Badge Styles */
        .elem-dia {
            color: #FDE047;
            text-shadow: 0 0 8px #FACC15, 0 0 16px rgba(250, 204, 21, 0.6);
        }
        .elem-thuy {
            color: #38BDF8;
            text-shadow: 0 0 8px #38BDF8, 0 0 16px rgba(56, 189, 248, 0.6);
        }
        .elem-hoa {
            color: #FF5252;
            text-shadow: 0 0 8px #FF5252, 0 0 16px rgba(255, 82, 82, 0.6);
        }
        .elem-phong {
            color: #4ADE80;
            text-shadow: 0 0 8px #4ADE80, 0 0 16px rgba(74, 222, 128, 0.6);
        }
        .boss-elem-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 3px 12px;
            font-size: 1.05rem;
            font-weight: 900;
            border-radius: 7px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.18);
            letter-spacing: 0.5px;
            user-select: none;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
        }

        .btn-fs {
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(2, 132, 199, 0.35));
            border: 1px solid #38bdf8;
            color: #38bdf8;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            transition: all 0.2s ease;
        }

        .btn-fs:hover {
            background: #38bdf8;
            color: #090d16;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.5);
        }

        .btn-fs:active {
            transform: scale(0.95);
        }

        /* Stream Controls (Speed selector & Live indicator) */
        .stream-ctrl-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            flex-wrap: wrap;
        }

        .speed-group {
            display: flex;
            flex: 1;
            max-width: 360px;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 9px;
            padding: 3px;
            gap: 3px;
        }

        .speed-btn {
            flex: 1;
            background: transparent;
            border: none;
            color: #94a3b8;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 0.74rem;
            font-weight: 700;
            text-align: center;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .speed-btn:hover {
            color: #f8fafc;
            background: rgba(255, 255, 255, 0.06);
        }

        .speed-btn.active {
            background: var(--accent);
            color: #ffffff;
            box-shadow: 0 2px 10px rgba(234, 88, 12, 0.45);
        }

        .stream-actions-group {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }

        .btn-stream-pause {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.14);
            color: #f1f5f9;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-stream-pause:hover {
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }

        .btn-stream-pause:active {
            transform: scale(0.96);
        }

        .stream-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.74rem;
            font-weight: 600;
            color: #cbd5e1;
            padding: 5px 10px;
            background: rgba(15, 23, 42, 0.65);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .stream-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: #64748b;
            transition: 0.3s;
        }

        .stream-dot.live {
            background-color: #10b981;
            box-shadow: 0 0 8px #10b981;
            animation: pulse 1.2s infinite;
        }

        @media (max-width: 600px) {
            .stream-ctrl-bar {
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }
            .speed-group {
                max-width: 100% !important;
                width: 100%;
            }
            .speed-btn {
                padding: 7px 4px;
                font-size: 0.72rem;
            }
            .stream-actions-group {
                width: 100%;
                justify-content: space-between;
            }
        }

        /* Fullscreen Theater Mode */
        .screen-card.fullscreen-active {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            height: 100dvh !important;
            max-width: 100vw !important;
            margin: 0 !important;
            padding: 0 !important;
            border-radius: 0 !important;
            border: none !important;
            background: #000 !important;
            z-index: 99999 !important;
            display: flex !important;
            flex-direction: column !important;
        }

        .screen-card.fullscreen-active .card-header,
        .screen-card.fullscreen-active .stream-ctrl-bar {
            display: none !important;
        }

        .screen-card.fullscreen-active .preview-box {
            flex: 1;
            width: 100%;
            height: 100%;
            min-height: 0;
            border-radius: 0;
            border: none;
            box-shadow: none;
            background: #000;
        }

        .screen-card.fullscreen-active .preview-img {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }

        .fs-overlay-bar {
            display: none;
            position: absolute;
            top: calc(8px + env(safe-area-inset-top, 0px));
            left: 10px;
            right: 10px;
            z-index: 1000;
            padding: 6px 12px;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border-radius: 12px;
            border: 1px solid rgba(56, 189, 248, 0.25);
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            transition: opacity 0.3s ease;
        }

        .screen-card.fullscreen-active .fs-overlay-bar {
            display: flex;
        }

        .fs-overlay-bar.dimmed {
            opacity: 0.18;
        }

        .fs-overlay-bar.dimmed:hover,
        .fs-overlay-bar.dimmed:active {
            opacity: 1;
        }

        .fs-info {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.8rem;
            font-weight: 700;
            color: #f8fafc;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .fs-btn-close {
            background: rgba(239, 68, 68, 0.2);
            border: 1px solid #ef4444;
            color: #fca5a5;
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 0.78rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: 0.2s;
        }

        .fs-btn-close:active {
            transform: scale(0.95);
            background: #ef4444;
            color: #fff;
        }

        .fs-quick-actions {
            display: flex;
            gap: 6px;
        }

        .fs-btn-action {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 600;
            border: none;
            cursor: pointer;
            color: #fff;
        }

        .fs-rotate-hint {
            display: none;
            position: absolute;
            bottom: calc(14px + env(safe-area-inset-bottom, 0px));
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.82);
            border: 1px solid rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(8px);
            color: #94a3b8;
            font-size: 0.72rem;
            padding: 5px 14px;
            border-radius: 20px;
            pointer-events: none;
            white-space: nowrap;
            z-index: 500;
        }

        @media (orientation: portrait) and (max-width: 900px) {
            .screen-card.fullscreen-active .fs-rotate-hint {
                display: block;
            }
        }

        /* Stream View-Only Mode (Đã tắt thao tác chạm an toàn) */

        /* Team Card */
        .team-list-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 12px;
            align-items: stretch;
        }

        .team-col {
            display: flex;
            flex-direction: column;
            min-width: 0;
            width: 100%;
        }

        .team-col-header {
            height: 32px;
            min-height: 32px;
            max-height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.76rem;
            color: var(--text-muted);
            font-weight: 700;
            white-space: nowrap !important;
            margin-bottom: 6px;
            box-sizing: border-box;
            text-align: center;
        }

        .team-box {
            background: #14161c;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 8px;
            height: 380px;
            min-height: 380px;
            max-height: 380px;
            box-sizing: border-box;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.4);
            flex: 1;
        }

        .team-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            border-radius: 8px;
            background: #25272e;
            border: 1px solid var(--border);
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text);
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 40px;
        }

        .team-item:active {
            transform: scale(0.97);
            border-color: var(--accent);
            background: rgba(234, 88, 12, 0.2);
        }

        .btn-del-member {
            background: linear-gradient(135deg, #dc2626, #ef4444);
            color: white;
            border: none;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 800;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 8px rgba(239, 68, 68, 0.35);
            transition: 0.2s transform;
            flex-shrink: 0;
        }

        .btn-del-member:active {
            transform: scale(0.9);
        }

        /* Log Console */
        .log-box {
            background: #0e1015;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            font-family: var(--font-mono);
            font-size: 1rem;
            height: 330px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 5px;
            box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.6);
        }

        .log-entry {
            line-height: 1.45;
            color: #cbd5e1;
            word-break: break-word;
            font-family: var(--font-mono);
        }

        .log-filter-btn {
            min-height: 34px;
            padding: 6px 12px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.75rem;
            transition: all 0.2s ease;
        }

        /* Unified Floating Mobile Control Dock (Dual Floating Bars) */
        .bottom-fixed-dock {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            z-index: 100;
            max-width: 580px;
            margin: 0 auto;
            padding: 0 10px calc(8px + env(safe-area-inset-bottom, 0px)) 10px;
            pointer-events: none;
            display: flex;
            flex-direction: column;
            gap: 7px;
            transform: translateZ(0);
            -webkit-transform: translateZ(0);
        }

        /* Khung kính nổi bật cho từng thanh điều khiển */
        .dock-shell {
            background: rgba(26, 28, 35, 0.95);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1.5px solid var(--border);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.75), 0 0 16px rgba(56, 189, 248, 0.15);
            pointer-events: auto;
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }
        .dock-shell:hover {
            border-color: rgba(56, 189, 248, 0.65);
            box-shadow: 0 8px 34px rgba(0, 0, 0, 0.8), 0 0 24px rgba(56, 189, 248, 0.3);
        }

        /* 1. Thanh Game - Exit - Stop (Viền nổi bật riêng) */
        .action-bar {
            padding: 6px 8px;
            display: flex;
            gap: 7px;
            border-radius: 14px;
        }

        .btn-action {
            flex: 1;
            padding: 10px 8px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 0.84rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            letter-spacing: 0.3px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 42px;
        }

        .btn-action:active {
            transform: scale(0.95);
        }

        .btn-launch {
            flex: 1.25;
            background: #00875a;
            color: #ffffff;
            border: 1.5px solid #00a36c;
            box-shadow: 0 4px 14px rgba(0, 135, 90, 0.4);
        }

        .btn-exit {
            flex: 1;
            background: #2c3545;
            color: var(--text);
            border: 1.5px solid var(--border);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
        }

        .btn-stop {
            flex: 1.25;
            background: #d32f2f;
            color: #ffffff;
            border: 1.5px solid #ef5350;
            box-shadow: 0 4px 14px rgba(211, 47, 47, 0.4);
        }

        /* 2. Thanh Điều Hướng Đáy Kiểu Cong Nổi Bật (Curved Floating Center Dock - Màn Hình ở giữa) */
        .curved-tab-bar {
            position: relative;
            background: rgba(18, 16, 26, 0.96);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1.5px solid rgba(168, 85, 247, 0.28);
            border-radius: 26px;
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.8), 0 0 20px rgba(168, 85, 247, 0.15);
            pointer-events: auto;
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            padding: 6px 8px 6px 8px;
            box-sizing: border-box;
            min-height: 56px;
            transition: all 0.3s ease;
        }

        .curved-tab-bar:hover {
            border-color: rgba(168, 85, 247, 0.55);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.9), 0 0 25px rgba(168, 85, 247, 0.25);
        }

        /* Hai cánh hai bên chia đều không gian đối xứng */
        .nav-wing {
            display: flex;
            align-items: center;
            justify-content: space-around;
            flex: 1;
            min-width: 0;
            gap: 2px;
            padding-bottom: 2px;
        }

        /* Nút Tab thông thường */
        .tab-button.nav-tab-item {
            background: transparent;
            border: none;
            color: #94a3b8;
            padding: 4px 2px;
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            font-size: 0.68rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 12px;
            flex: 1;
            min-width: 0;
            margin: 0;
            position: relative;
            height: 46px;
            box-sizing: border-box;
            white-space: nowrap !important;
            user-select: none;
            outline: none;
            -webkit-tap-highlight-color: transparent;
        }

        .tab-button.nav-tab-item .tab-icon-wrap {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            color: #94a3b8;
            transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1), color 0.22s ease;
        }

        .tab-button.nav-tab-item .tab-label {
            font-size: 0.67rem;
            line-height: 1;
            color: #94a3b8;
            transition: color 0.22s ease;
            letter-spacing: -0.2px;
        }

        /* Hover */
        .tab-button.nav-tab-item:hover:not(.active) {
            color: #e2e8f0;
        }
        .tab-button.nav-tab-item:hover:not(.active) .tab-icon-wrap {
            color: #e2e8f0;
            transform: translateY(-1px);
        }

        /* Khi Tab Active (Đang chọn) */
        .tab-button.nav-tab-item.active {
            background: rgba(168, 85, 247, 0.16);
            color: #d8b4fe;
        }
        .tab-button.nav-tab-item.active .tab-icon-wrap {
            color: #c084fc;
            transform: scale(1.1) translateY(-1px);
            filter: drop-shadow(0 0 8px rgba(192, 132, 252, 0.6));
        }
        .tab-button.nav-tab-item.active .tab-label {
            color: #f3e8ff;
            font-weight: 800;
        }

        /* Cụm Nút Trung Tâm (Notch & Floating Action Button - Màn Hình ở giữa) */
        .nav-center-slot {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-end;
            width: 74px;
            flex-shrink: 0;
            margin: 0 4px;
            padding-bottom: 2px;
        }

        /* Vòng khuyên tròn trang trí 2 bên mép nút tròn (như trong ảnh mẫu) */
        .notch-decor-ring {
            position: absolute;
            top: 6px;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            border: 1.5px solid rgba(168, 85, 247, 0.6);
            background: rgba(18, 16, 26, 0.95);
            box-shadow: 0 0 6px rgba(168, 85, 247, 0.4);
            pointer-events: none;
        }
        .notch-decor-ring.ring-left {
            left: 2px;
        }
        .notch-decor-ring.ring-right {
            right: 2px;
        }

        /* Nút Màn Hình Nhô Lên Cao */
        .tab-button.center-fab-btn {
            background: transparent;
            border: none;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            padding: 0;
            margin: 0;
            text-decoration: none;
            user-select: none;
            outline: none;
            -webkit-tap-highlight-color: transparent;
            transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            position: relative;
            z-index: 10;
        }

        .fab-circle {
            width: 52px;
            height: 52px;
            min-width: 52px;
            min-height: 52px;
            border-radius: 50%;
            background: linear-gradient(135deg, #a855f7 0%, #7c3aed 50%, #4f46e5 100%);
            border: 2.5px solid rgba(255, 255, 255, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            box-shadow: 0 8px 24px rgba(124, 58, 237, 0.6), 0 0 18px rgba(168, 85, 247, 0.4), inset 0 2px 4px rgba(255, 255, 255, 0.5);
            transform: translateY(-16px);
            transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .center-fab-btn:hover .fab-circle {
            transform: translateY(-19px) scale(1.06);
            box-shadow: 0 12px 28px rgba(124, 58, 237, 0.75), 0 0 24px rgba(168, 85, 247, 0.6), inset 0 2px 6px rgba(255, 255, 255, 0.6);
        }

        .center-fab-btn:active .fab-circle {
            transform: translateY(-14px) scale(0.95);
        }

        /* Khi Màn Hình Active */
        .tab-button.center-fab-btn.active .fab-circle {
            background: linear-gradient(135deg, #c084fc 0%, #9333ea 50%, #6366f1 100%);
            border-color: #ffffff;
            box-shadow: 0 10px 30px rgba(147, 51, 234, 0.8), 0 0 25px rgba(192, 132, 252, 0.7), inset 0 2px 6px #ffffff;
            animation: fabPulse 2s infinite alternate;
        }

        @keyframes fabPulse {
            0% { box-shadow: 0 8px 25px rgba(147, 51, 234, 0.7), 0 0 15px rgba(192, 132, 252, 0.5); }
            100% { box-shadow: 0 12px 32px rgba(147, 51, 234, 0.9), 0 0 30px rgba(192, 132, 252, 0.8); }
        }

        .fab-label {
            font-size: 0.68rem;
            font-weight: 800;
            color: #c084fc;
            line-height: 1;
            margin-top: -10px;
            white-space: nowrap !important;
            letter-spacing: -0.2px;
            transition: color 0.2s ease;
        }

        .tab-button.center-fab-btn.active .fab-label {
            color: #f3e8ff;
            text-shadow: 0 0 8px rgba(192, 132, 252, 0.8);
        }

        .toast {
            position: fixed;
            top: 70px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.92);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            color: #fff;
            padding: 10px 20px;
            border-radius: 12px;
            border: 1px solid rgba(56, 189, 248, 0.3);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5), 0 0 12px rgba(56, 189, 248, 0.25);
            font-size: 0.82rem;
            font-weight: 600;
            z-index: 200;
            opacity: 0;
            pointer-events: none;
            transition: 0.3s opacity, 0.3s transform;
        }
        .toast.show { opacity: 1; transform: translateX(-50%) translateY(4px); }
    </style>
</head>
<body>




    <div class="container">

        <!-- TAB 1: MÀN HÌNH GAME -->
        <div class="tab-pane active" id="tabPane_screen">
            <div class="card screen-card" id="screenCard">
                <div class="card-header">
                    <span class="card-title">Màn Hình Trực Tiếp</span>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <button class="btn-fs" onclick="toggleFullscreen(true)">Toàn Màn Hình</button>
                    </div>
                </div>

                <!-- Floating Toolbar in Fullscreen Mode -->
                <div class="fs-overlay-bar" id="fsOverlayBar">
                    <div class="fs-info">
                        <span class="status-dot" id="fsStatusDot"></span>
                        <span id="fsTabTitle">Tab LDPlayer</span>
                        <span class="stream-badge" id="fsStreamBadge" style="margin-left:4px; color:#38bdf8;">1.0s (Chuẩn)</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <div class="speed-group">
                            <button class="speed-btn" id="btnQ05" onclick="setQuality('0.5s')">0.5s</button>
                            <button class="speed-btn active" id="btnQ1" onclick="setQuality('1s')">1.0s</button>
                            <button class="speed-btn" id="btnQ2" onclick="setQuality('2s')">2.0s</button>
                        </div>
                        <div class="fs-quick-actions">
                            <button class="fs-btn-action btn-stop" onclick="sendAction('stop')">Dừng</button>
                        </div>
                        <button class="fs-btn-close" onclick="toggleFullscreen(false)">Thoát</button>
                    </div>
                </div>

                <div class="preview-box" id="screenPreviewBox">
                    <img id="screenImg" class="preview-img" src="api/screenshot?q=1s" alt="Màn hình giả lập TS Origin">
                    <div class="fs-rotate-hint">Xoay ngang điện thoại để xem cực đại</div>
                </div>

                <div class="stream-ctrl-bar">
                    <div class="speed-group">
                        <button class="speed-btn" id="btnBarQ05" onclick="setQuality('0.5s')">0.5s (Nhanh)</button>
                        <button class="speed-btn active" id="btnBarQ1" onclick="setQuality('1s')">1.0s (Chuẩn)</button>
                        <button class="speed-btn" id="btnBarQ2" onclick="setQuality('2s')">2.0s (Tiết Kiệm)</button>
                    </div>
                    <div class="stream-actions-group">
                        <button class="btn-stream-pause" id="btnStreamToggle" onclick="toggleLiveStream()">Tạm Dừng</button>
                        <span class="stream-badge" id="lblStreamStatus">
                            <span class="stream-dot live" id="streamDot"></span>
                            <span id="streamSpeedText">Trực tiếp: 1.0s (Chuẩn)</span>
                        </span>
                    </div>
                </div>
            </div>

            <!-- Card Hẹn Giờ Hoạt Động (A, B, C, D) -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Hẹn Giờ Hoạt Động (A, B, C, D)</span>
                </div>
                <div class="card-inner-box">
                    <label class="chk-label" style="flex:1; justify-content:flex-start;">
                        <input type="checkbox" id="chk_hen_gio" onchange="onCheckboxChanged('hen_gio', this.checked)"> Hẹn Giờ
                    </label>
                    <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
                        <input type="text" id="entry_hen_gio_time" class="time-input" value="05:00" placeholder="05:00" maxlength="5" style="width:76px;" onchange="onTextChanged('hen_gio_time', this.value)" onkeyup="if(event.key==='Enter') this.blur()">
                        <span id="lbl_realtime_clock" style="font-family:monospace, 'Segoe UI'; font-size:0.82rem; font-weight:700; color:#f97316; background:#1e293b; border:1px solid rgba(249, 115, 22, 0.4); height:38px; line-height:36px; padding:0 8px; border-radius:8px; min-width:68px; text-align:center; box-sizing:border-box; display:inline-block;">--:--:--</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: HOẠT ĐỘNG -->
        <div class="tab-pane" id="tabPane_activity">
            <!-- 1. Boss Thế Giới -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Boss Thế Giới</span>
                    <label class="switch">
                        <input type="checkbox" id="switch_A" onchange="onSwitchChanged('A', this.checked)">
                        <span class="slider"></span>
                    </label>
                </div>
                <div class="card-inner-box">
                    <div style="display:flex; align-items:center; gap:6px; flex:1; min-width:0;">
                        <label class="chk-label" style="flex:1; justify-content:flex-start;">
                            <input type="checkbox" id="chk_A1" onchange="onCheckboxChanged('A1', this.checked)"> Boss
                        </label>
                        <span id="boss_elem_badge" class="boss-elem-badge elem-dia" style="height:38px; box-sizing:border-box; min-width:48px; padding:0 8px; font-size:0.95rem;">Địa</span>
                    </div>
                    <select id="combo_A_char" class="select-right-standard" onchange="onComboChanged('A_char', this.value)"></select>
                </div>
            </div>

            <!-- 2. Phụ Bản Đơn / Đội -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Phụ Bản Đơn / Đội</span>
                    <label class="switch">
                        <input type="checkbox" id="switch_B" onchange="onSwitchChanged('B', this.checked)">
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="card-inner-box" style="flex-direction:column; gap:8px;">
                    <!-- Hàng 1: Đơn (Cá Nhân) -->
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%;">
                        <label class="chk-label" style="flex:1; justify-content:flex-start;">
                            <input type="checkbox" id="chk_B_don" onchange="onCheckboxChanged('B_don', this.checked)"> Đơn
                        </label>
                        <select id="combo_B_don_char" class="select-right-standard" onchange="onComboChanged('B_don_char', this.value)"></select>
                    </div>

                    <!-- Đường gạch ngang phân cách màu cam -->
                    <div class="divider-h"></div>

                    <!-- Hàng 2: Đội (Tổ Đội) -->
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%;">
                        <label class="chk-label" style="flex:1; justify-content:flex-start;">
                            <input type="checkbox" id="chk_B_doi" onchange="onCheckboxChanged('B_doi', this.checked)"> Đội
                        </label>
                        <select id="combo_B_team_char" class="select-right-standard" onchange="onComboChanged('B_team_char', this.value)"></select>
                    </div>
                </div>

                <!-- Hàng mốc Phụ Bản: 5 cột thẳng hàng đều 100% -->
                <div style="background:rgba(255,255,255,0.02); padding:8px 10px; border-radius:8px; border:1px solid var(--border); margin-top:8px;">
                    <div class="grid-pb-5">
                        <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_B1" onchange="onCheckboxChanged('B1', this.checked)"> PB 20</label>
                        <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_B2" onchange="onCheckboxChanged('B2', this.checked)"> PB 50</label>
                        <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_B3" onchange="onCheckboxChanged('B3', this.checked)"> PB 80</label>
                        <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_B4" onchange="onCheckboxChanged('B4', this.checked)"> PB 110</label>
                        <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_B5" onchange="onCheckboxChanged('B5', this.checked)"> PB 140</label>
                    </div>
                </div>
            </div>

            <!-- 3. Card Ngày -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Ngày</span>
                </div>
                <!-- Hàng 1: [ ] Nhận Thư | [ Menu Mốc Giờ ] -->
                <div class="card-inner-box">
                    <label class="chk-label" style="flex:1; justify-content:flex-start;">
                        <input type="checkbox" id="chk_nhan_thu" onchange="onCheckboxChanged('nhan_thu', this.checked)"> Nhận Thư
                    </label>
                    <select id="combo_nhan_thu_time" class="select-right-standard" onchange="onComboChanged('nhan_thu_time', this.value)">
                        <option value="Tất Cả" selected>Tất Cả</option>
                        <option value="12H01">12H01</option>
                        <option value="18H01">18H01</option>
                        <option value="22H01">22H01</option>
                    </select>
                </div>
            </div>

            <!-- 4. Dị Giới Đêm -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Dị Giới Đêm</span>
                    <label class="switch">
                        <input type="checkbox" id="switch_C" onchange="onSwitchChanged('C', this.checked)">
                        <span class="slider"></span>
                    </label>
                </div>
                <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:6px; background:rgba(255,255,255,0.02); padding:8px 10px; border-radius:8px; border:1px solid var(--border);">
                    <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_C1" onchange="onCheckboxChanged('C1', this.checked)"> Phúc Thần</label>
                    <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_C2" onchange="onCheckboxChanged('C2', this.checked)"> Ký Lục</label>
                    <label class="chk-label" style="justify-content:center; width:100%;"><input type="checkbox" id="chk_C3" onchange="onCheckboxChanged('C3', this.checked)"> Rút Gọn</label>
                </div>
            </div>
        </div>

        <!-- TAB 3: QUẢN LÝ TỔ ĐỘI -->
        <div class="tab-pane" id="tabPane_team">
            <!-- Quản Lý Tổ Đội -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Quản Lý Tổ Đội</span>
                </div>
                <div style="background:rgba(255,255,255,0.02); padding:8px 10px; border-radius:8px; border:1px solid var(--border); margin-bottom:12px;">
                    <!-- HÀNG QUÂN SƯ: Quân Sư - Menu Tên Quân Sư -->
                    <div style="display:grid; grid-template-columns: 110px 1fr; gap:8px; align-items:center;">
                        <div style="display:inline-flex; align-items:center; justify-content:center; gap:6px; height:38px; background:rgba(245, 158, 11, 0.12); border:1px solid rgba(245, 158, 11, 0.35); border-radius:8px; color:#F59E0B; font-size:0.84rem; font-weight:700; white-space:nowrap; box-sizing:border-box;">
                            <span>Quân Sư:</span>
                        </div>
                        <select id="combo_E_quan_su" style="width:100%; text-align:center;" onchange="onComboChanged('E_quan_su', this.value)"></select>
                    </div>
                </div>

                <div class="team-list-container">
                    <div class="team-col">
                        <div class="team-col-header">Tướng Có Sẵn (Chạm thêm)</div>
                        <div class="team-box" id="list_E_A_box">
                            <div style="color:#64748b; font-size:0.75rem; padding:4px; text-align:center;">Đang nạp...</div>
                        </div>
                    </div>
                    <div class="team-col">
                        <div class="team-col-header">Đội Hình (Chạm xóa)</div>
                        <div class="team-box" id="list_E_B_box">
                            <div style="color:#64748b; font-size:0.75rem; padding:4px; text-align:center;">(Trống)</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 4: SỰ KIỆN -->
        <div class="tab-pane" id="tabPane_daily">
            <!-- 1. Card Trên: Tổ Đội / Kỹ Năng -->
            <div class="card" style="margin-bottom:12px;">
                <div class="card-header">
                    <span class="card-title">Tổ Đội / Kỹ Năng</span>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <label class="chk-round" title="Tạm Dừng Card D">
                            <input type="checkbox" id="chk_pause_D" onchange="onCheckboxChanged('pause_D', this.checked)">
                            <span class="chk-mark">✓</span>
                        </label>
                        <label class="switch">
                            <input type="checkbox" id="switch_D" onchange="onSwitchChanged('D', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                </div>

                <!-- Hàng 1: Tổ Đội + Dropdown Vị Trí -->
                <div class="card-inner-box" style="margin-bottom:8px;">
                    <label class="chk-label" style="flex:1; justify-content:flex-start;">
                        <input type="checkbox" id="chk_D2" onchange="onCheckboxChanged('D2', this.checked)"> Tổ Đội
                    </label>
                    <select id="combo_D_team_char" class="select-right-standard" onchange="onComboChanged('D_team_char', this.value)"></select>
                </div>

                <!-- Hàng 2: [ ] Nhận Đội + Menu Kỹ Năng (Đối xứng cân đối Hàng 1) -->
                <div class="card-inner-box" style="margin-bottom:8px;">
                    <label class="chk-label" style="flex:1; justify-content:flex-start;">
                        <input type="checkbox" id="chk_D_nhan_doi" onchange="onCheckboxChanged('D_nhan_doi', this.checked)"> Nhận Đội
                    </label>
                    <select id="combo_D_skill" class="select-right-standard" style="text-align:center; font-weight:700;" onchange="onComboChanged('D_skill', this.value)">
                        <option value="Buff HP / SP">Buff HP / SP</option>
                        <option value="Linh Kính">Linh Kính</option>
                        <option value="Kết Giới">Kết Giới</option>
                        <option value="Đánh Tay">Đánh Tay</option>
                    </select>
                </div>
            </div>

            <!-- 2. Khung Hàng Dưới: Lưới 4 Card Cân Đối (2 Hàng x 2 Cột) -->
            <div class="daily-subcards-grid">
                <!-- Hàng 1, Cột Trái: Card 40 NPC (Thu gọn trục Y như Card Boss Thế Giới) -->
                <div class="card daily-subcard daily-subcard-compact">
                    <div class="card-header">
                        <span class="card-title">40 NPC</span>
                        <input type="text" id="entry_D_time" class="time-input" value="20:00" placeholder="20:00" maxlength="5" onchange="onTextChanged('D_time', this.value)" onkeyup="if(event.key==='Enter') this.blur()">
                    </div>
                    <div class="card-inner-box">
                        <label class="chk-label">
                            <input type="checkbox" id="chk_D3" onchange="onCheckboxChanged('D3', this.checked)"> 40 NPC
                        </label>
                        <select id="combo_D_chien_dau" onchange="onComboChanged('D_chien_dau', this.value)">
                            <option value="Auto" selected>Auto</option>
                        </select>
                    </div>
                </div>

                <!-- Hàng 1, Cột Phải: Card Nhị Kiều (Thu gọn trục Y như Card Boss Thế Giới) -->
                <div class="card daily-subcard daily-subcard-compact">
                    <div class="card-header">
                        <span class="card-title">Nhị Kiều</span>
                        <div class="header-time-placeholder"></div>
                    </div>
                    <div class="card-inner-box">
                        <label class="chk-label">
                            <input type="checkbox" id="chk_D4" onchange="onCheckboxChanged('D4', this.checked)"> Nhị Kiều
                        </label>
                        <select id="combo_D_tang" onchange="onComboChanged('D_tang', this.value)">
                            <option value="Auto" selected>Auto</option>
                        </select>
                    </div>
                </div>

                <!-- Hàng 2, Cột Trái: Card Hoạt Động 1 (Tăng kích thước trục Y bù lại) -->
                <div class="card daily-subcard daily-subcard-expanded">
                    <div class="card-header">
                        <span class="card-title">Hoạt Động 1</span>
                        <div class="header-time-placeholder"></div>
                    </div>
                    <div class="card-inner-box">
                        <span>(Chờ cấu hình)</span>
                    </div>
                </div>

                <!-- Hàng 2, Cột Phải: Card Hoạt Động 2 (Tăng kích thước trục Y bù lại) -->
                <div class="card daily-subcard daily-subcard-expanded">
                    <div class="card-header">
                        <span class="card-title">Hoạt Động 2</span>
                        <div class="header-time-placeholder"></div>
                    </div>
                    <div class="card-inner-box">
                        <span>(Chờ cấu hình)</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 5: CHIẾN ĐẤU -->
        <div class="tab-pane" id="tabPane_combat">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Cấu Hình Chiến Đấu</span>
                </div>
                <!-- Hàng 1: HP / SP -->
                <div class="card-inner-box" style="margin-bottom:8px;">
                    <div style="display:flex; align-items:center; gap:8px; flex:1; min-width:0;">
                        <label class="chk-label" style="flex:1; justify-content:flex-start;">
                            <input type="checkbox" id="chk_buff" onchange="onCheckboxChanged('buff', this.checked)"> HP / SP
                        </label>
                        <span class="chk-combat-sub">(Tắt Auto)</span>
                    </div>
                    <select id="combo_buff" class="select-right-standard" onchange="onComboChanged('buff', this.value)">
                        <option value="Buff HP">Buff HP</option>
                        <option value="Buff SP">Buff SP</option>
                        <option value="Buff HP / SP">Buff HP / SP</option>
                    </select>
                </div>
                <!-- Hàng 2: [ ] [ Kỹ Năng ▼ ] (Tắt Auto) | [ Mục Tiêu ▼ ] -->
                <div class="card-inner-box">
                    <div style="display:flex; align-items:center; gap:8px; flex:1; min-width:0;">
                        <label class="chk-label" style="width:38px; min-width:38px; height:38px; padding:0; justify-content:center; flex-shrink:0;">
                            <input type="checkbox" id="chk_phong_thu" onchange="onCheckboxChanged('phong_thu', this.checked)">
                        </label>
                        <select id="combo_phong_thu_skill" style="flex:1; min-width:0; text-align:center;" onchange="onComboChanged('phong_thu_skill', this.value)">
                            <option value="Kết Giới">Kết Giới</option>
                            <option value="Linh Kính">Linh Kính</option>
                            <option value="Băng Tường">Băng Tường</option>
                        </select>
                        <span class="chk-combat-sub">(Tắt Auto)</span>
                    </div>
                    <select id="combo_phong_thu_target" class="select-right-standard" onchange="onComboChanged('phong_thu_target', this.value)">
                        <option value="Chart">Chart</option>
                        <option value="Chart / Pet">Chart / Pet</option>
                        <option value="Team">Team</option>
                        <option value="Pet - Team">Pet - Team</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- TAB 6: NHẬT KÝ HOẠT ĐỘNG (Đã ẩn) -->
        <div class="tab-pane" id="tabPane_logs" style="display:none !important;">
            <div class="card">
                <div class="card-header" style="flex-wrap: wrap; gap: 6px;">
                    <span class="card-title">Nhật Ký Hoạt Động</span>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <button class="btn-mini" style="background:#374151;" onclick="scrollLogsToBottom()">Xuống Dưới</button>
                        <button class="btn-mini" onclick="refreshLogs()">Làm Mới</button>
                    </div>
                </div>
                <!-- Filter Bar -->
                <div style="display:flex; gap:6px; margin-bottom:8px; overflow-x:auto; padding-bottom:2px;">
                    <button class="btn-mini log-filter-btn" id="btnFilterAll" style="background:#2563EB; font-weight:600;" onclick="setLogFilter('all')">Tất cả</button>
                    <button class="btn-mini log-filter-btn" id="btnFilterSuccess" style="background:#374151;" onclick="setLogFilter('success')">Thành công</button>
                    <button class="btn-mini log-filter-btn" id="btnFilterWarn" style="background:#374151;" onclick="setLogFilter('warn')">Cảnh báo</button>
                    <button class="btn-mini log-filter-btn" id="btnFilterAction" style="background:#374151;" onclick="setLogFilter('action')">Nhận diện/ADB</button>
                </div>
                <div class="log-box" id="logConsole">
                    <div class="log-entry">Đang nạp nhật ký...</div>
                </div>
            </div>
        </div>

    </div>

    <!-- Thanh Cố Định Đáy Màn Hình (Dual Floating Island Bars) -->
    <div class="bottom-fixed-dock">
        <!-- 1. Thanh Game - Exit - Stop (Viền nổi bật riêng) -->
        <div class="dock-shell action-bar">
            <button class="btn-action btn-launch" onclick="sendAction('launch_game')">GAME</button>
            <button class="btn-action btn-exit" onclick="sendAction('exit_game')">EXIT</button>
            <button class="btn-action btn-stop" onclick="sendAction('stop')">STOP</button>
        </div>

        <!-- 2. Thanh Màn Hình - Hoạt Động (Curved Floating Center Dock - Cân đối hoàn hảo 5 mục) -->
        <nav class="curved-tab-bar">
            <!-- Cánh trái: Hoạt Động & Tổ Đội (2 nút) -->
            <div class="nav-wing nav-wing-left">
                <button class="tab-button nav-tab-item" onclick="switchTab('activity', this)">
                    <div class="tab-icon-wrap">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                    </div>
                    <span class="tab-label">Hoạt Động</span>
                </button>
                <button class="tab-button nav-tab-item" onclick="switchTab('team', this)">
                    <div class="tab-icon-wrap">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                    </div>
                    <span class="tab-label">Tổ Đội</span>
                </button>
            </div>

            <!-- Nút Trung Tâm: MÀN HÌNH nổi tròn ở chính giữa với viền phát sáng -->
            <div class="nav-center-slot">
                <div class="notch-decor-ring ring-left"></div>
                <button class="tab-button center-fab-btn active" id="btnTabScreen" onclick="switchTab('screen', this)">
                    <div class="fab-circle">
                        <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line><circle cx="12" cy="10" r="2.5" fill="currentColor"></circle></svg>
                    </div>
                    <span class="fab-label">Màn Hình</span>
                </button>
                <div class="notch-decor-ring ring-right"></div>
            </div>

            <!-- Cánh phải: Sự Kiện & Chiến Đấu (2 nút cân xứng hoàn toàn với cánh trái) -->
            <div class="nav-wing nav-wing-right">
                <button class="tab-button nav-tab-item" onclick="switchTab('daily', this)">
                    <div class="tab-icon-wrap">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"></path><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"></path><path d="M4 22h16"></path><path d="M10 14.66V17c0 .55-.45 1-1 1H8c-.55 0-1 .45-1 1v1h10v-1c0-.55-.45-1-1-1h-1c-.55 0-1-.45-1-1v-2.34"></path><path d="M18 2H6v7a6 6 0 0 0 12 0V2z"></path></svg>
                    </div>
                    <span class="tab-label">Sự Kiện</span>
                </button>
                <button class="tab-button nav-tab-item" onclick="switchTab('combat', this)">
                    <div class="tab-icon-wrap">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 17.5L3 6V3h3l11.5 11.5"></path><path d="M13 19l6-6"></path><path d="M16 16l4 4"></path><path d="M19 21l2-2"></path></svg>
                    </div>
                    <span class="tab-label">Chiến Đấu</span>
                </button>
            </div>
        </nav>
    </div>

    <div class="toast" id="toast">Thông báo</div>

    <script>
        let streamTimer = null;

        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
            
            const activePane = document.getElementById('tabPane_' + tabId);
            if (activePane) activePane.classList.add('active');
            if (btn) btn.classList.add('active');

            window.scrollTo({ top: 0, behavior: 'instant' });
            
            if (tabId === 'screen') {
                if (typeof startLiveStream === 'function') startLiveStream();
            } else {
                if (typeof stopLiveStream === 'function') stopLiveStream();
            }
            if (tabId === 'logs') fetchStatus();
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        }

        async function refreshLogs() {
            await fetchStatus();
            showToast('Đã làm mới nhật ký!');
        }

        let currentLogFilter = 'all';
        let cachedLogsList = [];

        function setLogFilter(filterType) {
            currentLogFilter = filterType;
            ['btnFilterAll', 'btnFilterSuccess', 'btnFilterWarn', 'btnFilterAction'].forEach(id => {
                const b = document.getElementById(id);
                if (b) b.style.background = '#374151';
            });
            const activeMap = { 'all': 'btnFilterAll', 'success': 'btnFilterSuccess', 'warn': 'btnFilterWarn', 'action': 'btnFilterAction' };
            const activeBtn = document.getElementById(activeMap[filterType]);
            if (activeBtn) activeBtn.style.background = '#2563EB';
            renderFilteredLogs(cachedLogsList);
        }

        function scrollLogsToBottom() {
            const logConsole = document.getElementById('logConsole');
            if (logConsole) {
                logConsole.scrollTop = logConsole.scrollHeight;
                showToast('Đã cuộn xuống nhật ký mới nhất');
            }
        }

        function renderFilteredLogs(logs) {
            const logConsole = document.getElementById('logConsole');
            if (!logConsole || !logs) return;
            cachedLogsList = logs;

            let filtered = logs;
            if (currentLogFilter === 'success') {
                filtered = logs.filter(l => l.includes('✅') || l.includes('🎉'));
            } else if (currentLogFilter === 'warn') {
                filtered = logs.filter(l => l.includes('⚠️') || l.includes('❌') || l.includes('🛑') || l.includes('Lỗi') || l.includes('Fallback'));
            } else if (currentLogFilter === 'action') {
                filtered = logs.filter(l => l.includes('🎯') || l.includes('👁️') || l.includes('📜') || l.includes('🕹️') || l.includes('👑') || l.includes('Tap') || l.includes('Swipe'));
            }

            if (filtered.length === 0) {
                logConsole.innerHTML = '<div class="log-entry" style="color:#64748b; font-style:italic; padding:8px;">(Không có bản ghi phù hợp với bộ lọc này)</div>';
                return;
            }

            const newHtml = filtered.map(l => {
                let color = '#cbd5e1';
                if (l.includes('✅') || l.includes('🎉')) color = '#4ade80';
                else if (l.includes('⚠️') || l.includes('⏸️')) color = '#fbbf24';
                else if (l.includes('❌') || l.includes('🛑') || l.includes('Lỗi')) color = '#f87171';
                else if (l.includes('🎯') || l.includes('👁️') || l.includes('👑')) color = '#38bdf8';
                else if (l.includes('📜') || l.includes('🕹️')) color = '#c084fc';
                else if (l.includes('⏳') || l.includes('▶️')) color = '#93c5fd';
                return `<div class="log-entry" style="color:${color};">${l}</div>`;
            }).join('');

            const isNearBottom = (logConsole.scrollHeight - logConsole.scrollTop - logConsole.clientHeight) < 60;
            if (logConsole.innerHTML !== newHtml) {
                logConsole.innerHTML = newHtml;
                if (isNearBottom) {
                    logConsole.scrollTop = logConsole.scrollHeight;
                }
            }
        }

        const API_BASE = (function() {
            const parts = window.location.pathname.split('/');
            if (parts[1] === 'proxy' && parts[2]) {
                return '/proxy/' + parts[2];
            }
            return '';
        })();

        let isDisconnected = false;
        async function fetchStatus() {
            try {
                const res = await fetch(API_BASE + '/api/status');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                if (isDisconnected) {
                    isDisconnected = false;
                    showToast('Đã khôi phục kết nối!');
                }
                renderUI(data);
            } catch (e) {
                if (!isDisconnected) {
                    isDisconnected = true;
                    const statusDot = document.getElementById('statusDot');
                    const statusText = document.getElementById('statusText');
                    if (statusDot) statusDot.className = 'status-dot';
                    if (statusText) statusText.innerText = 'Mất kết nối - đang thử lại...';
                }
            }
        }

        let lastServerData = null;

        function renderUI(data) {
            // Hiển thị thanh tiến trình cập nhật tự động (nếu có bản mới đang tải)
            const existingBanner = document.getElementById('autoUpdateBanner');
            if (data.update_info && data.update_info.status === 'downloading') {
                const pct = data.update_info.progress || 0;
                const ver = data.update_info.latest_version || 'mới';
                if (!existingBanner) {
                    const banner = document.createElement('div');
                    banner.id = 'autoUpdateBanner';
                    banner.style = 'position:fixed; top:12px; left:50%; transform:translateX(-50%); z-index:999999; width:92%; max-width:440px; background:linear-gradient(135deg,#1e3a8a,#2563eb); border:1px solid #60a5fa; border-radius:12px; padding:12px 16px; box-shadow:0 8px 30px rgba(0,0,0,0.6); color:#fff; text-align:center; font-family:sans-serif;';
                    banner.innerHTML = `
                        <div style="font-weight:700; font-size:14px; margin-bottom:6px; display:flex; align-items:center; justify-content:center; gap:8px;">
                            <span>🔄</span> Đang tự động cập nhật lên ${ver} (${pct}%)
                        </div>
                        <div style="background:rgba(255,255,255,0.25); border-radius:6px; height:8px; overflow:hidden; margin-bottom:6px;">
                            <div id="autoUpdateProgress" style="background:#67e8f9; height:100%; width:${pct}%; transition:width 0.3s ease;"></div>
                        </div>
                        <div style="font-size:11px; opacity:0.9;">Tool sẽ tự động khởi động lại sau khi tải xong 100%.</div>
                    `;
                    document.body.appendChild(banner);
                } else {
                    const progEl = document.getElementById('autoUpdateProgress');
                    if (progEl) progEl.style.width = pct + '%';
                    const titleEl = existingBanner.querySelector('div');
                    if (titleEl) titleEl.innerHTML = `<span>🔄</span> Đang tự động cập nhật lên ${ver} (${pct}%)`;
                }
            } else if (existingBanner) {
                existingBanner.remove();
            }

            const statusDot = document.getElementById('statusDot');
            const statusText = document.getElementById('statusText');
            if (statusDot) statusDot.className = data.is_running ? 'status-dot running' : 'status-dot';
            if (statusText) statusText.innerText = data.is_running ? 'Đang chạy Auto...' : 'Sẵn sàng';

            const newTabs = data.tabs || [];
            if (data.selected_tab && currentSelectedTab === '0') {
                currentSelectedTab = data.selected_tab;
            }

            const fsTabTitle = document.getElementById('fsTabTitle');
            if (fsTabTitle) {
                const pInfo = data.port ? ` (Port ${data.port})` : '';
                fsTabTitle.innerText = data.selected_tab ? `🖥️ ${data.selected_tab}${pInfo}` : '🖥️ Tab LDPlayer';
            }

            const fsStatusDot = document.getElementById('fsStatusDot');
            if (fsStatusDot) {
                fsStatusDot.className = data.is_running ? 'status-dot running' : 'status-dot';
            }


            const charCombos = ['combo_A_char', 'combo_B_don_char', 'combo_B_team_char', 'combo_D_team_char'];
            charCombos.forEach(cid => {
                const c = document.getElementById(cid);
                if (c && c.children.length === 0) {
                    (data.char_options || []).forEach(co => {
                        const opt = document.createElement('option');
                        opt.value = co; opt.innerText = co;
                        c.appendChild(opt);
                    });
                }
            });

            // Quân sư options (Chỉ tái tạo DOM khi danh sách thay đổi thực sự để tránh lag/giật dropdown)
            const comboQS = document.getElementById('combo_E_quan_su');
            if (comboQS) {
                const newOpts = data.quan_su_options || ['(Trống)'];
                const curOpts = Array.from(comboQS.options).map(o => o.value);
                const isDiff = newOpts.length !== curOpts.length || newOpts.some((v, i) => v !== curOpts[i]);
                if (isDiff) {
                    comboQS.innerHTML = '';
                    newOpts.forEach(qs => {
                        const opt = document.createElement('option');
                        opt.value = qs; opt.innerText = qs;
                        comboQS.appendChild(opt);
                    });
                }
                const nowQS = Date.now();
                if (!userLocks['combo_E_quan_su'] || nowQS >= userLocks['combo_E_quan_su']) {
                    if (document.activeElement !== comboQS) {
                        comboQS.value = data.selected_quan_su || '(Trống)';
                    }
                }
            }

            lastServerData = data;
            renderTeamLists(data);

            const now = Date.now();

            for (const [k, v] of Object.entries(data.switches || {})) {
                const id = 'switch_' + k;
                if (userLocks[id] && now < userLocks[id]) continue;
                const el = document.getElementById(id);
                if (el) el.checked = !!v;
            }

            for (const [k, v] of Object.entries(data.checkboxes || {})) {
                const id = 'chk_' + k;
                if (userLocks[id] && now < userLocks[id]) continue;
                const el = document.getElementById(id);
                if (el) el.checked = !!v;
            }

            for (const [k, v] of Object.entries(data.combos || {})) {
                const id = 'combo_' + k;
                if (userLocks[id] && now < userLocks[id]) continue;
                const el = document.getElementById(id);
                if (el && document.activeElement !== el) el.value = v;
            }

            // Cập nhật nhãn hệ Boss Thế Giới (Card A)
            if (typeof updateBossElementBadge === 'function') {
                updateBossElementBadge(data.boss_elem ? data.boss_elem.name : null);
            }

            for (const [k, v] of Object.entries(data.inputs || {})) {
                const id = 'entry_' + k;
                if (userLocks[id] && now < userLocks[id]) continue;
                const el = document.getElementById(id);
                if (el && document.activeElement !== el) el.value = v;
            }

            applyDynamicUIRules();

            if (data.logs && data.logs.length > 0) {
                const logsPane = document.getElementById('tabPane_logs');
                if (logsPane && logsPane.classList.contains('active')) {
                    renderFilteredLogs(data.logs);
                }
            }
        }

        let localTeamA = [];
        let localTeamB = [];
        let teamSyncLockUntil = 0;

        function renderTeamLists(data) {
            if (!data) return;
            const now = Date.now();

            if (data.list_E_A && Array.isArray(data.list_E_A) && data.list_E_A.length > 0) {
                localTeamA = data.list_E_A;
            }

            // Đồng bộ danh sách B từ server khi không trong thời gian khóa người dùng vừa thao tác
            if (now >= teamSyncLockUntil && data.list_E_B && Array.isArray(data.list_E_B)) {
                localTeamB = [...data.list_E_B];
            }

            const listABox = document.getElementById('list_E_A_box');
            if (listABox) {
                const availA = localTeamA.filter(name => !localTeamB.includes(name));
                if (availA.length === 0) {
                    listABox.innerHTML = '<div style="color:#64748b; font-size:0.75rem; padding:6px; text-align:center;">(Đã thêm hết)</div>';
                } else {
                    listABox.innerHTML = availA.map(name => `
                        <div class="team-item" onclick="addMemberOptimistic('${name}')">
                            <span>${name}</span>
                            <span style="color:var(--accent); font-weight:700; font-size:0.95rem;">➔</span>
                        </div>
                    `).join('');
                }
            }

            const listBBox = document.getElementById('list_E_B_box');
            if (listBBox) {
                if (localTeamB.length === 0) {
                    listBBox.innerHTML = '<div style="color:#64748b; font-size:0.75rem; padding:6px; text-align:center;">(Trống - bấm ➔ để thêm)</div>';
                } else {
                    listBBox.innerHTML = localTeamB.map(name => `
                        <div class="team-item">
                            <span>${name}</span>
                            <button class="btn-del-member" onclick="event.stopPropagation(); removeMemberOptimistic('${name}')">✕</button>
                        </div>
                    `).join('');
                }
            }
        }

        function addMemberOptimistic(name) {
            if (localTeamB.includes(name)) return;
            localTeamB.push(name);
            teamSyncLockUntil = Date.now() + 2500; // Khóa đồng bộ ngược trong 2.5s để UI mượt 100% không bị giật lùi về A
            renderTeamLists(lastServerData || {});
            sendAction('add_to_team', {char_name: name}, false);
        }

        function removeMemberOptimistic(name) {
            if (!localTeamB.includes(name)) return;
            localTeamB = localTeamB.filter(n => n !== name);
            teamSyncLockUntil = Date.now() + 2500; // Khóa đồng bộ ngược trong 2.5s
            renderTeamLists(lastServerData || {});
            sendAction('remove_from_team', {char_name: name}, false);
        }

        const userLocks = {};
        const actionCooldowns = {};

        function applyDynamicUIRules() {
            const chkD2 = document.getElementById('chk_D2');
            const chkDNhanDoi = document.getElementById('chk_D_nhan_doi');
            const chkD3 = document.getElementById('chk_D3');
            const chkD4 = document.getElementById('chk_D4');
            const chkBdoi = document.getElementById('chk_B_doi');
            const comboEQS = document.getElementById('combo_E_quan_su');
            const comboDChienDau = document.getElementById('combo_D_chien_dau');
            const comboDTang = document.getElementById('combo_D_tang');
            const entryDTime = document.getElementById('entry_D_time');
            const listABox = document.getElementById('list_E_A_box');
            const listBBox = document.getElementById('list_E_B_box');

            // 0. Quy tắc ô Nhận Đội: loại trừ Tổ Đội (D2), 40 NPC (D3), Nhị Kiều (D4)
            if (chkDNhanDoi && chkDNhanDoi.checked) {
                if (chkD2) chkD2.checked = false;
                if (chkD3) chkD3.checked = false;
                if (chkD4) chkD4.checked = false;
                if (entryDTime) { entryDTime.disabled = true; entryDTime.style.opacity = '0.35'; }
                if (comboDChienDau) { comboDChienDau.disabled = true; comboDChienDau.style.opacity = '0.35'; }
                if (comboDTang) { comboDTang.disabled = true; comboDTang.style.opacity = '0.35'; }
            }

            // 1. Quy tắc 40 NPC (D3) và Nhị Kiều (D4) loại trừ nhau tức thì (giữ 2 ô luôn sáng để chuyển đổi 1-click)
            if (chkD3 && chkD4) {
                const labelD3 = chkD3.closest('.chk-label');
                const labelD4 = chkD4.closest('.chk-label');

                chkD3.disabled = false;
                chkD4.disabled = false;
                if (labelD3) { labelD3.style.opacity = '1'; labelD3.style.pointerEvents = 'auto'; }
                if (labelD4) { labelD4.style.opacity = '1'; labelD4.style.pointerEvents = 'auto'; }

                if (chkD3.checked) {
                    chkD4.checked = false;
                    if (entryDTime) { entryDTime.disabled = false; entryDTime.style.opacity = '1'; }
                    if (comboDChienDau) { comboDChienDau.disabled = false; comboDChienDau.style.opacity = '1'; }
                    if (comboDTang) { comboDTang.disabled = true; comboDTang.style.opacity = '0.35'; }
                } else if (chkD4.checked) {
                    chkD3.checked = false;
                    if (entryDTime) { entryDTime.disabled = true; entryDTime.style.opacity = '0.35'; }
                    if (comboDTang) { comboDTang.disabled = false; comboDTang.style.opacity = '1'; }
                    if (comboDChienDau) { comboDChienDau.disabled = true; comboDChienDau.style.opacity = '0.35'; }
                } else {
                    if (entryDTime) { entryDTime.disabled = true; entryDTime.style.opacity = '0.35'; }
                    if (comboDChienDau) { comboDChienDau.disabled = true; comboDChienDau.style.opacity = '0.35'; }
                    if (comboDTang) { comboDTang.disabled = true; comboDTang.style.opacity = '0.35'; }
                }
            }

            // 2. Card E luôn mở sáng hoàn toàn 24/7 (Quân Sư và Danh Sách A/B)
            if (comboEQS) { comboEQS.disabled = false; comboEQS.style.opacity = '1'; }
            if (listABox && listBBox) {
                listABox.style.opacity = '1';
                listABox.style.pointerEvents = 'auto';
                listBBox.style.opacity = '1';
                listBBox.style.pointerEvents = 'auto';
            }
        }

        async function sendAction(action, payload = {}, showToastMsg = true) {
            const now = Date.now();
            if (['launch_game', 'exit_game', 'stop', 'refresh_tabs', 'run', 'nhan_thu'].includes(action)) {
                if (actionCooldowns[action] && (now - actionCooldowns[action] < 700)) {
                    return; // Chặn bấm lặp / spam nút trên điện thoại
                }
                actionCooldowns[action] = now;
            }

            if (action === 'stop') {
                // Nhả tức thì các ô và công tắc trên Web ngay khi chạm Stop
                const chkBuff = document.getElementById('chk_buff');
                if (chkBuff) chkBuff.checked = false;
                delete userLocks['chk_buff'];
                const chkPhongThu = document.getElementById('chk_phong_thu');
                if (chkPhongThu) chkPhongThu.checked = false;
                delete userLocks['chk_phong_thu'];
                const chkHenGio = document.getElementById('chk_hen_gio');
                if (chkHenGio) chkHenGio.checked = false;
                delete userLocks['chk_hen_gio'];
                const chkNhanThu = document.getElementById('chk_nhan_thu');
                if (chkNhanThu) chkNhanThu.checked = false;
                delete userLocks['chk_nhan_thu'];
                ['A', 'B', 'C', 'D'].forEach(k => {
                    const sw = document.getElementById('switch_' + k);
                    if (sw) sw.checked = false;
                    delete userLocks['switch_' + k];
                    const p = document.getElementById('chk_pause_' + k);
                    if (p) p.checked = false;
                    delete userLocks['chk_pause_' + k];
                });
                applyDynamicUIRules();
            }
            try {
                const res = await fetch(API_BASE + '/api/action', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action, ...payload})
                });
                const r = await res.json();
                if (showToastMsg && r.msg) showToast(r.msg);
                if (action !== 'tap') {
                    setTimeout(fetchStatus, 350);
                }
            } catch (e) {
                if (showToastMsg) showToast('Lỗi kết nối');
            }
        }

        function onSwitchChanged(name, value) {
            userLocks['switch_' + name] = Date.now() + 2500;
            sendAction('set_switch', {name, value}, false);
            applyDynamicUIRules();
        }

        function onCheckboxChanged(name, value) {
            userLocks['chk_' + name] = Date.now() + 2500;
            if (name === 'D_nhan_doi' && value) {
                ['D2', 'D3', 'D4'].forEach(k => {
                    userLocks['chk_' + k] = Date.now() + 2500;
                    const el = document.getElementById('chk_' + k);
                    if (el) el.checked = false;
                });
            } else if (['D2', 'D3', 'D4'].includes(name) && value) {
                userLocks['chk_D_nhan_doi'] = Date.now() + 2500;
                const el = document.getElementById('chk_D_nhan_doi');
                if (el) el.checked = false;
            }
            if (name === 'D3' && value) {
                userLocks['chk_D4'] = Date.now() + 2500;
                const chkD4 = document.getElementById('chk_D4');
                if (chkD4) chkD4.checked = false;
            } else if (name === 'D4' && value) {
                userLocks['chk_D3'] = Date.now() + 2500;
                const chkD3 = document.getElementById('chk_D3');
                if (chkD3) chkD3.checked = false;
            } else if (['buff', 'phong_thu'].includes(name) && value) {
                const combatCbs = ['buff', 'phong_thu'];
                combatCbs.filter(k => k !== name).forEach(k => {
                    userLocks['chk_' + k] = Date.now() + 2500;
                    const el = document.getElementById('chk_' + k);
                    if (el) el.checked = false;
                });
            } else if (name === 'hen_gio' && !value) {
                ['A', 'B', 'C', 'D'].forEach(k => {
                    userLocks['switch_' + k] = Date.now() + 2500;
                    const sw = document.getElementById('switch_' + k);
                    if (sw) sw.checked = false;
                });
            }
            sendAction('set_checkbox', {name, value}, false);
            applyDynamicUIRules();
        }

        function onComboChanged(name, value) {
            userLocks['combo_' + name] = Date.now() + 2500;
            sendAction('set_combo', {name, value}, false);
        }

        function onTextChanged(name, value) {
            userLocks['entry_' + name] = Date.now() + 2500;
            sendAction('set_text', {name, value}, false);
        }

        function onTabChanged(tab) {
            showToast('⚠️ Cổng này đã được khóa cố định theo Tab để tránh xung đột!');
        }

        function refreshTabs() {
            sendAction('refresh_tabs', {}, true);
            showToast('Đang quét lại tab...');
            setTimeout(fetchStatus, 600);
        }

        let currentQuality = (function() {
            try {
                const s = localStorage.getItem('ts_stream_interval');
                if (s === '0.5s' || s === '1s' || s === '2s') return s;
                return '1s';
            } catch(e) { return '1s'; }
        })();
        let isStreamRunning = true;
        let currentSelectedTab = '0';
        let isFullscreenActive = false;
        let overlayHideTimer = null;
        let activeStreamTimer = null;
        let isStreamBusy = false;
        let streamRetryCount = 0;

        function startLiveStream() {
            const img = document.getElementById('screenImg');
            if (!img) return;
            isStreamRunning = true;
            isStreamBusy = false;
            if (activeStreamTimer) clearTimeout(activeStreamTimer);

            const dot = document.getElementById('streamDot');
            if (dot) dot.classList.add('live');
            const lbl = document.getElementById('streamSpeedText');
            const nameMap = {'0.5s': '0.5s (Nhanh)', '1s': '1.0s (Chuẩn)', '2s': '2.0s (Tiết Kiệm)'};
            if (lbl) lbl.innerText = `Trực tiếp: ${nameMap[currentQuality] || currentQuality}`;
            const btn = document.getElementById('btnStreamToggle');
            if (btn) btn.innerText = 'Tạm Dừng';

            fetchStreamNextFrame();
        }

        function fetchStreamNextFrame() {
            if (!isStreamRunning) return;
            if (activeStreamTimer) clearTimeout(activeStreamTimer);

            if (isStreamBusy) {
                activeStreamTimer = setTimeout(fetchStreamNextFrame, 60);
                return;
            }

            isStreamBusy = true;
            const nextImg = new Image();
            const targetTab = currentSelectedTab || '0';
            const url = API_BASE + '/api/screenshot?tab=' + encodeURIComponent(targetTab) + '&q=' + currentQuality + '&_t=' + Date.now();

            // Timeout an toàn: Nếu mạng lag hoặc điện thoại background, tự động giải phóng sau 2.5s
            const watchdogTimer = setTimeout(() => {
                if (isStreamBusy) {
                    isStreamBusy = false;
                    if (isStreamRunning) {
                        scheduleNextFrame(200);
                    }
                }
            }, 2500);

            nextImg.onload = () => {
                clearTimeout(watchdogTimer);
                isStreamBusy = false;
                streamRetryCount = 0;
                const mainImg = document.getElementById('screenImg');
                if (mainImg && isStreamRunning) {
                    mainImg.src = nextImg.src;
                }
                // Chu kỳ nghỉ bảo vệ 100% CPU máy tính: 0.5s (500ms ~ 2 FPS), 1s (1000ms ~ 1 FPS), 2s (2000ms ~ 0.5 FPS)
                const delayMs = currentQuality === '0.5s' ? 500 : (currentQuality === '2s' ? 2000 : 1000);
                if (isStreamRunning) {
                    scheduleNextFrame(delayMs);
                }
            };

            nextImg.onerror = () => {
                clearTimeout(watchdogTimer);
                isStreamBusy = false;
                streamRetryCount++;
                const retryDelay = streamRetryCount > 5 ? 1000 : 300;
                if (isStreamRunning) {
                    scheduleNextFrame(retryDelay);
                }
            };

            nextImg.src = url;
        }

        function scheduleNextFrame(delay) {
            if (activeStreamTimer) clearTimeout(activeStreamTimer);
            if (isStreamRunning) {
                activeStreamTimer = setTimeout(fetchStreamNextFrame, delay);
            }
        }

        function stopLiveStream() {
            isStreamRunning = false;
            isStreamBusy = false;
            if (activeStreamTimer) clearTimeout(activeStreamTimer);
            const dot = document.getElementById('streamDot');
            if (dot) dot.classList.remove('live');
            const lbl = document.getElementById('streamSpeedText');
            if (lbl) lbl.innerText = 'Đã tạm dừng';
            const btn = document.getElementById('btnStreamToggle');
            if (btn) btn.innerText = 'Phát Lại';
        }

        function toggleLiveStream() {
            if (isStreamRunning) {
                stopLiveStream();
            } else {
                startLiveStream();
            }
        }

        function resumeLiveStream() {
            if (typeof fetchStatus === 'function') fetchStatus();
            const pane = document.getElementById('tabPane_screen');
            if (!pane || !pane.classList.contains('active')) return;
            // Giải phóng sạch sẽ mọi cờ nghẽn khi app quay lại từ background
            isStreamBusy = false;
            if (activeStreamTimer) clearTimeout(activeStreamTimer);
            isStreamRunning = true;
            startLiveStream();
        }

        function setQuality(q, quiet) {
            currentQuality = q;
            try { localStorage.setItem('ts_stream_interval', q); } catch(e) {}
            ['btnQ05', 'btnBarQ05'].forEach(id => {
                const b = document.getElementById(id);
                if (b) b.classList.toggle('active', q === '0.5s');
            });
            ['btnQ1', 'btnBarQ1'].forEach(id => {
                const b = document.getElementById(id);
                if (b) b.classList.toggle('active', q === '1s');
            });
            ['btnQ2', 'btnBarQ2'].forEach(id => {
                const b = document.getElementById(id);
                if (b) b.classList.toggle('active', q === '2s');
            });
            const fsBadge = document.getElementById('fsStreamBadge');
            const badgeMap = {
                '0.5s': '0.5s (Nhanh)',
                '1s': '1.0s (Chuẩn)',
                '2s': '2.0s (Tiết Kiệm)'
            };
            if (fsBadge) fsBadge.innerText = badgeMap[q] || q;
            const lbl = document.getElementById('streamSpeedText');
            if (lbl) lbl.innerText = `Trực tiếp: ${badgeMap[q] || q}`;
            if (isStreamRunning) {
                startLiveStream();
            }
            if (!quiet) {
                const toastMap = {
                    '0.5s': 'Đã chuyển sang chế độ 0.5s (Nhanh - 2 FPS)',
                    '1s': 'Đã chuyển sang chế độ 1.0s (Chuẩn - 1 FPS)',
                    '2s': 'Đã chuyển sang chế độ 2.0s (Tiết kiệm - 0.5 FPS)'
                };
                showToast(toastMap[q] || ('Đã đổi chế độ: ' + q));
            }
        }

        // Bắt trọn vẹn TẤT CẢ các sự kiện khi người dùng quay lại web từ màn hình chính điện thoại
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                resumeLiveStream();
            } else {
                stopLiveStream();
            }
        });

        window.addEventListener('pageshow', resumeLiveStream);
        window.addEventListener('focus', resumeLiveStream);

        function toggleFullscreen(enable) {
            const card = document.getElementById('screenCard');
            if (!card) return;
            if (enable === undefined) {
                enable = !card.classList.contains('fullscreen-active');
            }
            isFullscreenActive = enable;
            if (enable) {
                card.classList.add('fullscreen-active');
                document.body.style.overflow = 'hidden';
                if (document.documentElement.requestFullscreen) {
                    document.documentElement.requestFullscreen().catch(() => {});
                }
                resetOverlayHideTimer();
                showToast('Đã mở Toàn màn hình');
            } else {
                card.classList.remove('fullscreen-active');
                document.body.style.overflow = '';
                if (document.fullscreenElement && document.exitFullscreen) {
                    document.exitFullscreen().catch(() => {});
                }
                if (overlayHideTimer) clearTimeout(overlayHideTimer);
            }
        }

        function resetOverlayHideTimer() {
            const bar = document.getElementById('fsOverlayBar');
            if (!bar) return;
            bar.classList.remove('dimmed');
            if (overlayHideTimer) clearTimeout(overlayHideTimer);
            overlayHideTimer = setTimeout(() => {
                if (isFullscreenActive) bar.classList.add('dimmed');
            }, 4000);
        }

        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement && isFullscreenActive) {
                toggleFullscreen(false);
            }
        });

        // Khởi động
        fetchStatus();
        setInterval(fetchStatus, 3000);

        function updateBossElementBadge(elemName) {
            const badge = document.getElementById('boss_elem_badge');
            if (!badge) return;
            if (!elemName) {
                const d = new Date().getDay();
                const m = {1:'Địa', 2:'Thủy', 3:'Hỏa', 4:'Phong', 5:'Hỏa', 6:'Thủy', 0:'Phong'};
                elemName = m[d] || 'Địa';
            }
            badge.textContent = elemName;
            const clsMap = {'Địa': 'elem-dia', 'Thủy': 'elem-thuy', 'Hỏa': 'elem-hoa', 'Phong': 'elem-phong'};
            badge.className = `boss-elem-badge ${clsMap[elemName] || 'elem-dia'}`;
        }

        function updateRealtimeClock() {
            const badge = document.getElementById('lbl_realtime_clock');
            if (!badge) return;
            const now = new Date();
            const pad = (n) => String(n).padStart(2, '0');
            badge.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
        }
        setInterval(updateRealtimeClock, 1000);

        document.addEventListener('DOMContentLoaded', () => {
            updateBossElementBadge();
            updateRealtimeClock();
            setQuality(currentQuality, true);
        });
    </script>
</body>
</html>
"""


class SilentThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        ex = sys.exc_info()[1]
        if isinstance(ex, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class ToolWebRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def finish(self):
        try:
            super().finish()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_GET(self):
        app = getattr(self.server, "app", None)
        if not app:
            self.send_error(500, "App not ready")
            return

        parsed = self.path.split('?')[0]

        if parsed == "/" or parsed == "/index.html":
            body = HTML_PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            return

        elif parsed == "/manifest.json":
            manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        elif parsed in ["/apple-touch-icon.png", "/apple-touch-icon-180.png", "/apple-touch-icon-precomposed.png"]:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icons", "apple-touch-icon.png")
            if os.path.exists(icon_path):
                with open(icon_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        elif parsed == "/favicon.ico":
            ico_path = os.path.join(os.path.dirname(__file__), "assets", "icons", "favicon.ico")
            if os.path.exists(ico_path):
                with open(ico_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        elif parsed.startswith("/assets/icons/"):
            fname = os.path.basename(parsed)
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icons", fname)
            if os.path.exists(icon_path) and os.path.isfile(icon_path):
                with open(icon_path, "rb") as f:
                    body = f.read()
                mime = "image/png"
                if fname.endswith(".ico"): mime = "image/x-icon"
                elif fname.endswith(".svg"): mime = "image/svg+xml"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        elif parsed == "/api/status":
            tabs = []
            if hasattr(app, 'combo_ld_tabs'):
                tabs = list(app.combo_ld_tabs.cget("values"))
                tabs = [t for t in tabs if t not in ["Đang quét tab...", "Lỗi quét dữ liệu", "Không tìm thấy tab LD nào"]]

            selected_tab, _ = app._get_selected_ld_info() if hasattr(app, '_get_selected_ld_info') else (None, None)

            switches = {
                "A": app.var_switch_A.get() if hasattr(app, 'var_switch_A') else False,
                "B": app.var_switch_B.get() if hasattr(app, 'var_switch_B') else False,
                "C": app.var_switch_C.get() if hasattr(app, 'var_switch_C') else False,
                "D": app.var_switch_D.get() if hasattr(app, 'var_switch_D') else False
            }

            checkboxes = {
                "A1": app.var_A1.get() if hasattr(app, 'var_A1') else False,
                "B_don": app.var_B_don.get() if hasattr(app, 'var_B_don') else False,
                "B_doi": app.var_B_doi.get() if hasattr(app, 'var_B_doi') else False,
                "B1": app.var_B1.get() if hasattr(app, 'var_B1') else False,
                "B2": app.var_B2.get() if hasattr(app, 'var_B2') else False,
                "B3": app.var_B3.get() if hasattr(app, 'var_B3') else False,
                "B4": app.var_B4.get() if hasattr(app, 'var_B4') else False,
                "B5": app.var_B5.get() if hasattr(app, 'var_B5') else False,
                "C1": app.var_C1.get() if hasattr(app, 'var_C1') else False,
                "C2": app.var_C2.get() if hasattr(app, 'var_C2') else False,
                "C3": app.var_C3.get() if hasattr(app, 'var_C3') else False,
                "D2": app.var_D2.get() if hasattr(app, 'var_D2') else False,
                "D_nhan_doi": app.var_D_nhan_doi.get() if hasattr(app, 'var_D_nhan_doi') else False,
                "D3": app.var_D3.get() if hasattr(app, 'var_D3') else False,
                "D4": app.var_D4.get() if hasattr(app, 'var_D4') else False,
                "E_quan_su": app.var_E_quan_su.get() if hasattr(app, 'var_E_quan_su') else False,
                "pause_D": app.var_pause_D.get() if hasattr(app, 'var_pause_D') else False,
                "buff": app.var_buff.get() if hasattr(app, 'var_buff') else False,
                "phong_thu": app.var_phong_thu.get() if hasattr(app, 'var_phong_thu') else False,
                "ket_gioi": app.var_phong_thu.get() if hasattr(app, 'var_phong_thu') else False,
                "linh_kinh": app.var_phong_thu.get() if hasattr(app, 'var_phong_thu') else False,
                "bang_tuong": app.var_phong_thu.get() if hasattr(app, 'var_phong_thu') else False,
                "nhan_thu": app.var_nhan_thu.get() if hasattr(app, 'var_nhan_thu') else False,
                "hen_gio": app.var_hen_gio.get() if hasattr(app, 'var_hen_gio') else False,
                "enable_notify": app.var_enable_notify.get() if hasattr(app, 'var_enable_notify') else True
            }

            combos = {
                "A_char": app.combo_A_char.get() if hasattr(app, 'combo_A_char') else "Xuất Chiến",
                "B_don_char": app.combo_B_don_char.get() if hasattr(app, 'combo_B_don_char') else "Xuất Chiến",
                "B_team_char": app.combo_B_team_char.get() if hasattr(app, 'combo_B_team_char') else "Xuất Chiến",
                "D_team_char": app.combo_D_team_char.get() if hasattr(app, 'combo_D_team_char') else "Xuất Chiến",
                "D_chien_dau": app.combo_D_chien_dau.get() if hasattr(app, 'combo_D_chien_dau') else "Auto",
                "D_tang": app.combo_D_tang.get() if hasattr(app, 'combo_D_tang') else "Auto",
                "D_skill": app.var_D_skill.get() if hasattr(app, 'var_D_skill') else "Buff HP / SP",
                "E_quan_su": app.combo_E_quan_su.get() if hasattr(app, 'combo_E_quan_su') else "(Trống)",
                "buff": app.combo_buff.get() if hasattr(app, 'combo_buff') else "Buff HP",
                "phong_thu_skill": app.combo_phong_thu_skill.get() if hasattr(app, 'combo_phong_thu_skill') else "Kết Giới",
                "phong_thu_target": app.combo_phong_thu_target.get() if hasattr(app, 'combo_phong_thu_target') else "Chart",
                "ket_gioi": app.combo_phong_thu_target.get() if hasattr(app, 'combo_phong_thu_target') else "Chart",
                "linh_kinh": app.combo_phong_thu_target.get() if hasattr(app, 'combo_phong_thu_target') else "Chart",
                "bang_tuong": app.combo_phong_thu_target.get() if hasattr(app, 'combo_phong_thu_target') else "Chart",
                "nhan_thu_time": app.combo_nhan_thu_time.get() if hasattr(app, 'combo_nhan_thu_time') else "Tất Cả",
                "hen_gio_time": app.var_hen_gio_time.get() if hasattr(app, 'var_hen_gio_time') else "05:00"
            }

            inputs = {
                "hen_gio_time": app.var_hen_gio_time.get() if hasattr(app, 'var_hen_gio_time') else "05:00",
                "D_time": app.var_D_time.get() if hasattr(app, 'var_D_time') else "20:00"
            }

            is_running = bool(
                getattr(app, '_card_AB_coordinator_running', False)
                or (getattr(app, '_thread_buff', None) is not None and app._thread_buff.is_alive())
                or (getattr(app, '_thread_phong_thu', None) is not None and app._thread_phong_thu.is_alive())
                or (hasattr(app, 'var_switch_A') and app.var_switch_A.get())
                or (hasattr(app, 'var_switch_B') and app.var_switch_B.get())
                or (hasattr(app, 'var_switch_C') and app.var_switch_C.get())
                or (hasattr(app, 'var_switch_D') and app.var_switch_D.get())
                or (hasattr(app, 'var_buff') and app.var_buff.get())
                or (hasattr(app, 'var_phong_thu') and app.var_phong_thu.get())
            )

            list_E_A = app._get_nhanvat_options() if hasattr(app, '_get_nhanvat_options') else []
            list_E_B = list(getattr(app, 'list_E_B', []))
            quan_su_options = app._get_quan_su_options() if hasattr(app, '_get_quan_su_options') else ["(Trống)"]
            selected_quan_su = app.combo_E_quan_su.get() if hasattr(app, 'combo_E_quan_su') else "(Trống)"

            day_str, elem_name, elem_color = app._get_boss_element_info() if hasattr(app, '_get_boss_element_info') else ("--", "Địa", "#FDE047")

            data = {
                "is_running": is_running,
                "selected_tab": selected_tab or (tabs[0] if tabs else ""),
                "tabs": tabs,
                "char_options": app._get_character_options() if hasattr(app, '_get_character_options') else ["Xuất Chiến"],
                "boss_elem": {
                    "day": day_str,
                    "name": elem_name,
                    "color": elem_color
                },
                "list_E_A": list_E_A,
                "list_E_B": list_E_B,
                "quan_su_options": quan_su_options,
                "selected_quan_su": selected_quan_su,
                "switches": switches,
                "checkboxes": checkboxes,
                "combos": combos,
                "inputs": inputs,
                "logs": getattr(app, 'recent_logs', [])[-40:],
                "local_ip": getattr(app, 'web_ip', get_local_ip()),
                "port": getattr(app, 'web_port', 8081),
                "update_info": getattr(app, 'update_info', None)
            }
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            return

        elif parsed == "/api/stream":
            query_str = urllib.parse.urlparse(self.path).query
            query_params = urllib.parse.parse_qs(query_str) if query_str else {}
            tab_val = query_params.get("tab", [None])[0]
            if tab_val is not None and str(tab_val).strip() != "":
                tab_idx = str(tab_val).strip()
            else:
                _, tab_idx_app = app._get_selected_ld_info() if hasattr(app, '_get_selected_ld_info') else (None, "0")
                tab_idx = str(tab_idx_app) if tab_idx_app is not None else "0"

            quality_val = query_params.get("q", ["1s"])[0]

            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                last_sent = None
                start_stream_time = time.time()
                while time.time() - start_stream_time < 300:
                    frame = _stream_manager.get_frame(app, tab_idx, quality_mode=quality_val)
                    if frame and frame != last_sent:
                        part = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(frame)).encode('ascii') + b"\r\n\r\n"
                            + frame + b"\r\n"
                        )
                        self.wfile.write(part)
                        self.wfile.flush()
                        last_sent = frame
                    time.sleep(0.02)
            except Exception:
                pass
            return

        elif parsed == "/api/screenshot":
            query_str = urllib.parse.urlparse(self.path).query
            query_params = urllib.parse.parse_qs(query_str) if query_str else {}
            tab_val = query_params.get("tab", [None])[0]
            if tab_val is not None and str(tab_val).strip() != "":
                tab_idx = str(tab_val).strip()
            else:
                _, tab_idx_app = app._get_selected_ld_info() if hasattr(app, '_get_selected_ld_info') else (None, "0")
                tab_idx = str(tab_idx_app) if tab_idx_app is not None else "0"
            quality_val = query_params.get("q", ["1s"])[0]

            img_bytes = _stream_manager.get_frame(app, tab_idx, quality_mode=quality_val)
            if not img_bytes:
                img_bytes = get_screenshot_bytes(app)

            try:
                if img_bytes:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(img_bytes)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(img_bytes)
                else:
                    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="225" viewBox="0 0 400 225">
                        <rect width="100%" height="100%" fill="#182238"/>
                        <text x="50%" y="50%" fill="#64748b" font-family="sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">Chưa thể chụp màn hình (Tab chưa bật hoặc ADB bận)</text>
                    </svg>""".encode('utf-8')
                    self.send_response(200)
                    self.send_header("Content-Type", "image/svg+xml")
                    self.send_header("Content-Length", str(len(svg)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(svg)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        app = getattr(self.server, "app", None)
        if not app:
            self.send_error(500, "App not ready")
            return

        if self.path == "/api/action":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                req = json.loads(body.decode('utf-8'))
            except Exception:
                req = {}

            action = req.get("action")
            msg = "Đã thực thi"

            if action == "run":
                app.after(0, app.xu_ly_nut_chay)
                msg = "▶️ Bắt đầu Run Tool!"

            elif action == "stop":
                app.after(0, app.dung_tat_ca_hoat_dong)
                msg = "🛑 Đã Stop khẩn cấp!"

            elif action == "launch_game":
                app.after(0, app.xu_ly_ts_origin)
                msg = "🎮 Đang mở TS Origin..."

            elif action == "exit_game":
                app.after(0, app.xu_ly_exit_game)
                msg = "🚪 Đang đóng game về màn hình chính LDPlayer..."

            elif action == "nhan_thu":
                if hasattr(app, '_reset_stop_flags'):
                    app._reset_stop_flags()
                tab_name, tab_index = app._get_selected_ld_info() if hasattr(app, '_get_selected_ld_info') else (None, None)
                if tab_index is None:
                    tab_index = getattr(app, 'assigned_tab_index', "0")
                dnconsole_path = app._get_dnconsole_path() if hasattr(app, '_get_dnconsole_path') else None
                if not dnconsole_path:
                    dnconsole_path = os.path.join(app.ld_path, "ldconsole.exe")
                    if not os.path.exists(dnconsole_path):
                        dnconsole_path = os.path.join(app.ld_path, "dnconsole.exe")
                threading.Thread(target=app._execute_nhan_thu, args=(dnconsole_path, str(tab_index), "Thủ Công"), daemon=True).start()
                msg = "📬 [Card Ngày] Đang thực thi Nhận Thư (Thủ Công)..."

            elif action == "show_window":
                if hasattr(app, '_restore_window_ui'):
                    app.after(0, app._restore_window_ui)
                elif hasattr(app, '_show_window_from_tray'):
                    app.after(0, app._show_window_from_tray)
                msg = "📖 Đã mở lại giao diện Tool."

            elif action == "refresh_tabs":
                app.after(0, app.refresh_ld_tabs_async)
                msg = "🔄 Đang quét lại Tab..."

            elif action == "set_tab":
                tab = req.get("tab")
                if tab and hasattr(app, 'combo_ld_tabs'):
                    def _set_t():
                        app.combo_ld_tabs.set(tab)
                        app._on_ld_tab_selected(tab)
                    app.after(0, _set_t)
                    msg = f"Đã chọn tab: {tab}"

            elif action == "tap":
                msg = "Chế độ xem trực tiếp (Đã khóa thao tác chạm để an toàn)"

            elif action == "set_switch":
                s_name = req.get("name")
                s_val = bool(req.get("value"))
                switch_var_name = f"var_switch_{s_name}"
                switch_cb_name = f"_on_switch_{s_name}_toggled"

                if hasattr(app, switch_var_name):
                    def _toggle_sw():
                        getattr(app, switch_var_name).set(s_val)
                        if hasattr(app, switch_cb_name):
                            getattr(app, switch_cb_name)()
                    app.after(0, _toggle_sw)
                    msg = f"Công tắc {s_name}: {'BẬT' if s_val else 'TẮT'}"

            elif action == "set_checkbox":
                cb_name = req.get("name")
                cb_val = bool(req.get("value"))
                if cb_name in ["buff", "var_buff"]:
                    var_name = "var_buff"
                elif cb_name in ["phong_thu", "var_phong_thu", "ket_gioi", "var_ket_gioi", "linh_kinh", "var_linh_kinh", "bang_tuong", "var_bang_tuong"]:
                    var_name = "var_phong_thu"
                elif cb_name.startswith("var_"):
                    var_name = cb_name
                else:
                    var_name = f"var_{cb_name}"

                if hasattr(app, var_name):
                    def _toggle_cb():
                        getattr(app, var_name).set(cb_val)
                        if cb_name in ["D_nhan_doi", "var_D_nhan_doi"] and hasattr(app, '_on_D_nhan_doi_toggled'):
                            app._on_D_nhan_doi_toggled()
                        elif cb_name in ["D2", "var_D2"] and hasattr(app, '_on_D2_toggled'):
                            if hasattr(app, '_update_card_E_visibility'):
                                app._update_card_E_visibility()
                            app._on_D2_toggled()
                        elif cb_name in ["B_doi", "var_B_doi"] and hasattr(app, '_update_card_E_visibility'):
                            app._update_card_E_visibility()
                            app._on_checkbox_toggled()
                        elif cb_name in ["D3", "var_D3"] and hasattr(app, '_on_D3_toggled'):
                            app._on_D3_toggled()
                        elif cb_name in ["D4", "var_D4"] and hasattr(app, '_on_D4_toggled'):
                            app._on_D4_toggled()
                        elif cb_name in ["pause_D", "var_pause_D"] and hasattr(app, '_on_pause_D_toggled'):
                            app._on_pause_D_toggled()
                        elif cb_name in ["E_quan_su", "var_E_quan_su"] and hasattr(app, '_on_checkbox_toggled'):
                            app._on_checkbox_toggled()
                        elif cb_name in ["buff", "var_buff"]:
                            if hasattr(app, '_on_buff_toggled'):
                                app._on_buff_toggled()
                            else:
                                app._on_checkbox_toggled()
                        elif cb_name in ["phong_thu", "var_phong_thu", "ket_gioi", "var_ket_gioi", "linh_kinh", "var_linh_kinh", "bang_tuong", "var_bang_tuong"]:
                            if hasattr(app, '_on_phong_thu_toggled'):
                                app._on_phong_thu_toggled()
                            else:
                                app._on_checkbox_toggled()
                        elif cb_name in ["nhan_thu", "var_nhan_thu"]:
                            if hasattr(app, '_on_nhan_thu_toggled'):
                                app._on_nhan_thu_toggled()
                            else:
                                app.save_config()
                        elif cb_name in ["hen_gio", "var_hen_gio"]:
                            if hasattr(app, '_on_hen_gio_toggled'):
                                app._on_hen_gio_toggled()
                            else:
                                app.save_config()
                        else:
                            app._on_checkbox_toggled()
                    app.after(0, _toggle_cb)
                    msg = f"Ô {cb_name}: {'Tích' if cb_val else 'Bỏ'}"

            elif action == "set_combo":
                c_name = req.get("name")
                c_val = req.get("value")
                if c_name in ["buff", "combo_buff"]:
                    combo_widget_name = "combo_buff"
                elif c_name in ["phong_thu_skill", "combo_phong_thu_skill"]:
                    combo_widget_name = "combo_phong_thu_skill"
                elif c_name in ["phong_thu_target", "combo_phong_thu_target", "ket_gioi", "combo_ket_gioi", "linh_kinh", "combo_linh_kinh", "bang_tuong", "combo_bang_tuong"]:
                    combo_widget_name = "combo_phong_thu_target"
                elif c_name in ["nhan_thu_time", "combo_nhan_thu_time"]:
                    combo_widget_name = "combo_nhan_thu_time"
                elif c_name in ["hen_gio_time", "combo_hen_gio_time"]:
                    combo_widget_name = "combo_hen_gio_time"
                elif c_name.startswith("combo_"):
                    combo_widget_name = c_name
                else:
                    combo_widget_name = f"combo_{c_name}"

                if hasattr(app, combo_widget_name):
                    def _set_cmb():
                        getattr(app, combo_widget_name).set(c_val)
                        if c_name in ["E_quan_su", "combo_E_quan_su"] and hasattr(app, '_on_combo_quan_su_changed'):
                            app._on_combo_quan_su_changed()
                        elif c_name in ["nhan_thu_time", "combo_nhan_thu_time"]:
                            if hasattr(app, '_on_nhan_thu_combo_changed'):
                                app._on_nhan_thu_combo_changed(c_val)
                            elif hasattr(app, '_on_nhan_thu_toggled'):
                                app._on_nhan_thu_toggled()
                            else:
                                app.save_config()
                        elif c_name in ["hen_gio_time", "combo_hen_gio_time"]:
                            if hasattr(app, 'var_hen_gio_time'):
                                app.var_hen_gio_time.set(c_val)
                            if hasattr(app, '_on_hen_gio_time_changed'):
                                app._on_hen_gio_time_changed()
                            else:
                                app.save_config()
                        elif c_name in ["D_skill", "combo_D_skill"]:
                            if hasattr(app, 'var_D_skill'):
                                app.var_D_skill.set(c_val)
                            app.save_config()
                        else:
                            app._on_checkbox_toggled()
                    app.after(0, _set_cmb)
                    msg = f"Đã đổi {c_name} sang {c_val}"

            elif action == "set_text":
                t_name = req.get("name")
                t_val = req.get("value")
                if t_name in ["hen_gio_time", "var_hen_gio_time", "entry_hen_gio_time"]:
                    def _set_txt():
                        if hasattr(app, 'var_hen_gio_time'):
                            app.var_hen_gio_time.set(t_val)
                        if hasattr(app, '_on_hen_gio_time_changed'):
                            app._on_hen_gio_time_changed()
                        else:
                            app.save_config()
                    app.after(0, _set_txt)
                    msg = f"Đã đặt {t_name} = {t_val}"
                elif t_name in ["D_time", "var_D_time", "entry_D_time"]:
                    def _set_d_txt():
                        if hasattr(app, 'var_D_time'):
                            app.var_D_time.set(t_val)
                        if hasattr(app, '_on_D_time_changed'):
                            app._on_D_time_changed()
                        else:
                            app.save_config()
                    app.after(0, _set_d_txt)
                    msg = f"Đã đặt {t_name} = {t_val}"
                else:
                    msg = f"Đã cập nhật {t_name}"

            elif action == "add_to_team":
                char_name = req.get("char_name")
                if char_name:
                    if not hasattr(app, 'list_E_B'):
                        app.list_E_B = []
                    # 1. Cập nhật trực tiếp ngay lập tức vào app.list_E_B để GET /api/status phản ánh tức thì
                    if char_name not in app.list_E_B:
                        app.list_E_B.append(char_name)
                    # 2. Đồng bộ giao diện Tkinter trên máy tính
                    def _add():
                        app.selected_E_list_A_char = char_name
                        if hasattr(app, '_render_E_list_B_ui'):
                            app._render_E_list_B_ui()
                        if hasattr(app, '_render_E_list_A_ui'):
                            app._render_E_list_A_ui()
                        if hasattr(app, 'save_config'):
                            app.save_config()
                    app.after(0, _add)
                    msg = f"➕ Đã thêm {char_name} vào Tổ Đội"

            elif action == "remove_from_team":
                char_name = req.get("char_name")
                if char_name:
                    if hasattr(app, 'list_E_B') and char_name in app.list_E_B:
                        app.list_E_B.remove(char_name)
                    def _rem():
                        if hasattr(app, '_render_E_list_B_ui'):
                            app._render_E_list_B_ui()
                        if hasattr(app, '_render_E_list_A_ui'):
                            app._render_E_list_A_ui()
                        if hasattr(app, 'save_config'):
                            app.save_config()
                    app.after(0, _rem)
                    msg = f"➖ Đã xóa {char_name} khỏi Tổ Đội"

            res_body = json.dumps({"success": True, "msg": msg, "list_E_B": list(getattr(app, 'list_E_B', []))}, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(res_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(res_body)
            return

        self.send_error(404, "Not Found")


def start_web_server(app, port=8081):
    """Khởi động Web Server ngầm trên port được cấp phát (mặc định 8081 cho Tab 1)"""
    local_ip = get_local_ip()
    app.web_ip = local_ip
    app.web_port = port

    for attempt_port in [port, port + 1, port + 2, 5000, 8888]:
        try:
            server = SilentThreadingHTTPServer(('0.0.0.0', attempt_port), ToolWebRequestHandler)
            server.app = app
            app.web_port = attempt_port
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            local_url = f"http://{local_ip}:{attempt_port}"
            app.log_info(f"🌐 [WEB SERVER] Đang chạy tại: {local_url} (Mở link này trên điện thoại)")
            if hasattr(app, '_update_web_url_ui'):
                app.after(0, app._update_web_url_ui, local_url, False)
            return server
        except OSError:
            continue
        except Exception as e:
            app.log_error(f"Không thể khởi động Web Server: {e}")
            break

    return None


class HubWebRequestHandler(BaseHTTPRequestHandler):
    """Máy chủ Hub Gateway tại Cổng 8080: Quản lý Tổng Quan Đa Tab và làm Reverse Proxy"""
    def log_message(self, format, *args):
        pass  # Tắt log stdout của server

    def do_GET(self):
        parsed = self.path.split('?')[0]

        # 1. Trang chủ Hub
        if parsed == "/" or parsed == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            html = get_hub_html().encode("utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        # 2. API lấy danh sách toàn bộ tab đang active
        if parsed == "/api/hub/status":
            self.handle_hub_status()
            return

        # 3. Trailing slash redirect cho proxy: /proxy/<port> -> /proxy/<port>/
        if re.match(r"^/proxy/\d+$", self.path):
            self.send_response(302)
            self.send_header("Location", self.path + "/")
            self.end_headers()
            return

        # 4. Reverse Proxy: /proxy/<port>/...
        if self.path.startswith("/proxy/"):
            self.handle_proxy()
            return

        # 5. Favicon / Assets / Manifest
        if parsed in ("/favicon.ico", "/manifest.json") or parsed.startswith("/assets/"):
            target_port = getattr(getattr(self.server, 'app', None), 'web_port', 8081)
            self.forward_raw("127.0.0.1", target_port, self.path)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/hub/launch_tab":
            self.handle_hub_launch_tab()
            return
        if self.path.startswith("/proxy/"):
            self.handle_proxy()
            return
        self.send_error(404, "Not Found")

    def handle_hub_launch_tab(self):
        """Khởi chạy thêm 1 cửa sổ Tool mới (tự động nhận slot và tab tiếp theo)"""
        try:
            app_dir = get_app_dir()
            exe_path = os.path.join(app_dir, "TS_Origin_Control_V3.exe")
            dist_exe_path = os.path.join(app_dir, "dist", "TS_Origin_Control_V3.exe")
            py_path = os.path.join(app_dir, "main_v3.py")
            if os.path.exists(exe_path):
                subprocess.Popen([exe_path], cwd=app_dir)
            elif os.path.exists(dist_exe_path):
                subprocess.Popen([dist_exe_path], cwd=os.path.join(app_dir, "dist"))
            elif os.path.exists(py_path):
                subprocess.Popen([sys.executable, py_path], cwd=app_dir)
            res_body = json.dumps({"success": True, "msg": "Đang khởi chạy Tab tiếp theo..."}).encode('utf-8')
        except Exception as e:
            res_body = json.dumps({"success": False, "msg": str(e)}).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(res_body)))
        self.end_headers()
        self.wfile.write(res_body)

    def handle_hub_status(self):
        """Quét trạng thái toàn bộ các port 8081-8090 song song siêu tốc qua ThreadPoolExecutor"""
        active_tabs = []
        def _fetch_one(p):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{p}/api/status", headers={"User-Agent": "TSHub/1.0"})
                with urllib.request.urlopen(req, timeout=0.25) as resp:
                    if resp.status == 200:
                        d = json.loads(resp.read().decode('utf-8'))
                        d["port"] = p
                        return d
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(_fetch_one, range(8081, 8091)))
            for item in results:
                if item:
                    active_tabs.append(item)

        res_body = json.dumps({
            "hub_active": True,
            "total_tabs": len(active_tabs),
            "tabs": active_tabs
        }, ensure_ascii=False).encode('utf-8')

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(res_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(res_body)

    def handle_proxy(self):
        m = re.match(r"^/proxy/(\d+)(/.*)?$", self.path)
        if not m:
            self.send_error(400, "Bad Proxy URL")
            return
        target_port = int(m.group(1))
        target_subpath = m.group(2) or "/"

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        target_url = f"http://127.0.0.1:{target_port}{target_subpath}"

        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')}

        try:
            req = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                self.send_response(resp.status)
                for h_name, h_val in resp.headers.items():
                    if h_name.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(h_name, h_val)
                self.end_headers()
                shutil.copyfileobj(resp, self.wfile)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for h_name, h_val in e.headers.items():
                self.send_header(h_name, h_val)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_error(502, f"Proxy Error to port {target_port}: {e}")

    def forward_raw(self, host, port, path):
        target_url = f"http://{host}:{port}{path}"
        try:
            req = urllib.request.Request(target_url, headers={k: v for k, v in self.headers.items() if k.lower() != 'host'})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.send_response(resp.status)
                for h_name, h_val in resp.headers.items():
                    if h_name.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(h_name, h_val)
                self.end_headers()
                shutil.copyfileobj(resp, self.wfile)
        except Exception:
            self.send_error(404, "Not Found")


def check_and_start_hub_gateway(app, silent: bool = False):
    """Kiểm tra và khởi động Hub Gateway (Trang Tổng Quản Đa Tab) tại Cổng 8080 nếu chưa có ai chạy"""
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_sock.bind(('0.0.0.0', 8080))
        test_sock.close()
    except OSError:
        app.is_hub_master = False
        if not silent:
            local_ip = get_local_ip()
            app.log_info(f"ℹ️ [HUB GATEWAY] Cổng 8080 đã được quản lý bởi Master Hub. Xem tổng quan tại: http://{local_ip}:8080")
        return None

    try:
        hub_server = SilentThreadingHTTPServer(('0.0.0.0', 8080), HubWebRequestHandler)
        hub_server.app = app
        app.is_hub_master = True
        t = threading.Thread(target=hub_server.serve_forever, daemon=True)
        t.start()
        local_ip = get_local_ip()
        app.log_info(f"🌟 [HUB GATEWAY] Đã khởi động Trang Tổng Quản Đa Tab tại: http://{local_ip}:8080")
        return hub_server
    except Exception as e:
        if not silent:
            app.log_warning(f"Không thể khởi động Hub Gateway 8080: {e}")
        return None


def get_hub_html():
    """Tạo giao diện Trang Tổng Quản Đa Tab (Hub Gateway) hiện đại, trực quan, hỗ trợ xem và điều khiển toàn bộ các Tab."""
    return """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="TS Origin Hub">
    <title>TS Origin</title>
    <style>
        :root {
            --bg-base: #0b0f19;
            --bg-surface: #111827;
            --bg-card: rgba(17, 24, 39, 0.85);
            --border-card: rgba(255, 255, 255, 0.08);
            --border-active: #06b6d4;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-rose: #f43f5e;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-sub: #64748b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            -webkit-text-size-adjust: 100%;
            -webkit-font-smoothing: antialiased;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: radial-gradient(circle at 50% 0%, #1e293b 0%, #0b0f19 80%);
            color: var(--text-main);
            height: 100vh;
            height: 100dvh;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }

        /* Top Bar */
        .hub-navbar {
            background: rgba(11, 15, 25, 0.95);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-card);
            padding: calc(8px + env(safe-area-inset-top, 0px)) 16px 8px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            z-index: 100;
            gap: 12px;
        }
        .hub-nav-top {
            display: contents;
        }
        .hub-brand {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 15px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: #fff;
            white-space: nowrap;
        }


        /* Carousel Navigation Tabs */
        .hub-tabs-scroll {
            display: flex;
            align-items: center;
            gap: 6px;
            overflow-x: auto;
            scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
            padding: 2px 0;
            flex: 1;
        }
        .hub-tabs-scroll::-webkit-scrollbar { display: none; }

        .hub-nav-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-card);
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            white-space: nowrap;
        }
        .hub-nav-pill:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }
        .hub-nav-pill.active {
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.25), rgba(59, 130, 246, 0.25));
            border-color: var(--accent-cyan);
            color: #fff;
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.3);
        }
        .dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #64748b;
        }
        .dot.running {
            background: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
            animation: pulse-dot 1.5s infinite;
        }
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.85); }
        }

        .hub-controls-right {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .hub-btn-icon {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-card);
            color: var(--text-muted);
            border-radius: 8px;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        .hub-btn-icon:hover {
            background: rgba(255, 255, 255, 0.12);
            color: #fff;
        }

        /* Container Views */
        .hub-content {
            flex: 1;
            min-height: 0;
            position: relative;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .hub-view {
            display: none;
            width: 100%;
            height: 100%;
            flex: 1;
            min-height: 0;
        }
        .hub-view.active {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 0;
        }
        #viewOverview {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            overflow-x: hidden;
            -webkit-overflow-scrolling: touch;
        }
        #viewTabDetail {
            flex: 1;
            min-height: 0;
            overflow: hidden;
        }

        /* Overview Grid View */
        .hub-overview-container {
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .hub-stats-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }
        .hub-stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            backdrop-filter: blur(12px);
            border-radius: 12px;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .hub-stat-num {
            font-size: 20px;
            font-weight: 800;
            color: #fff;
        }
        .hub-stat-label {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
        }

        /* Tab Cards Grid */
        .hub-cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }
        .hub-tab-card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            backdrop-filter: blur(12px);
            border-radius: 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }
        .hub-tab-card:hover {
            transform: translateY(-2px);
            border-color: rgba(6, 182, 212, 0.4);
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.6);
        }
        .hub-card-header {
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.02);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .hub-card-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            font-size: 14px;
            color: #fff;
        }

        .hub-status-tag {
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        .hub-status-tag.running {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .hub-status-tag.standby {
            background: rgba(148, 163, 184, 0.12);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }

        /* Screen Preview */
        .hub-screen-box {
            width: 100%;
            background: #000;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            cursor: pointer;
            border-radius: 4px;
        }
        .hub-screen-img {
            width: 100%;
            height: auto;
            max-height: 60vh;
            display: block;
            object-fit: contain;
            background: #000;
            transition: opacity 0.2s;
        }
        .hub-screen-overlay {
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.2s;
            color: #fff;
            font-weight: 700;
            font-size: 13px;
            gap: 6px;
        }
        .hub-screen-box:hover .hub-screen-overlay {
            opacity: 1;
        }

        /* Card Actions */
        .hub-card-actions {
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.02);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
        }
        .hub-btn {
            width: 100%;
            padding: 9px 12px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            border: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: all 0.2s;
        }
        .hub-btn-view {
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(59, 130, 246, 0.25));
            color: #67e8f9;
            border: 1px solid rgba(6, 182, 212, 0.4);
        }
        .hub-btn-view:hover {
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.35), rgba(59, 130, 246, 0.4));
            color: #fff;
            box-shadow: 0 0 14px rgba(6, 182, 212, 0.35);
        }

        /* Dedicated Tab View (IFrame embed) */
        .hub-detail-bar {
            background: #111827;
            border-bottom: 1px solid var(--border-card);
            padding: 6px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
            height: 42px;
            flex-shrink: 0;
            box-sizing: border-box;
        }
        .hub-back-btn {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid var(--border-card);
            color: #fff;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
            transition: all 0.2s;
        }
        .hub-back-btn:hover {
            background: rgba(255, 255, 255, 0.16);
            border-color: var(--accent-cyan);
            color: #67e8f9;
        }
        .hub-iframe-wrapper {
            flex: 1;
            min-height: 0;
            width: 100%;
            height: 100%;
            background: #0b0f19;
            position: relative;
            overflow: hidden;
            -webkit-overflow-scrolling: touch;
        }
        .hub-iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
            display: block;
        }

        /* Empty state */
        .hub-empty-state {
            grid-column: 1 / -1;
            text-align: center;
            padding: 60px 20px;
            background: var(--bg-card);
            border: 1px dashed rgba(255, 255, 255, 0.15);
            border-radius: 16px;
        }
        .hub-empty-state h3 { font-size: 16px; margin-bottom: 8px; color: #fff; }
        .hub-empty-state p { font-size: 13px; color: var(--text-muted); }

        /* Toast */
        #hubToast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 10px 16px;
            background: #0f172a;
            border: 1px solid var(--accent-cyan);
            color: #fff;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            display: none;
            z-index: 1000;
        }

        /* Tối ưu chuyên biệt cho Mobile & iOS Safari */
        @media (max-width: 640px) {
            .hub-navbar {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                padding: calc(6px + env(safe-area-inset-top, 0px)) 10px 6px 10px;
                gap: 6px;
            }
            .hub-nav-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                width: 100%;
            }
            .hub-brand {
                font-size: 14px;
                gap: 5px;
            }
            .hub-badge {
                font-size: 9px;
                padding: 1px 5px;
            }
            .hub-controls-right {
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .hub-btn-icon {
                width: 32px;
                height: 32px;
                font-size: 13px;
            }
            .hub-tabs-scroll {
                width: 100%;
                display: flex;
                align-items: center;
                gap: 6px;
                overflow-x: auto;
                scrollbar-width: none;
                -webkit-overflow-scrolling: touch;
                padding: 4px 0 2px 0;
                border-top: 1px solid rgba(255, 255, 255, 0.07);
            }
            .hub-nav-pill {
                padding: 6px 12px;
                font-size: 12px;
                border-radius: 8px;
                flex-shrink: 0;
                white-space: nowrap;
            }
            .hub-overview-container {
                padding: 10px 8px;
                gap: 10px;
            }
            .hub-stats-row {
                grid-template-columns: repeat(3, 1fr);
                gap: 6px;
            }
            .hub-stat-card {
                padding: 8px 10px;
                border-radius: 10px;
            }
            .hub-stat-label {
                font-size: 9px;
            }
            .hub-stat-num {
                font-size: 16px;
            }
            .hub-stat-card > div:last-child {
                display: none;
            }
            .hub-cards-grid {
                grid-template-columns: 1fr;
                gap: 12px;
            }
            .hub-screen-box {
                height: auto;
            }
            .hub-detail-bar {
                padding: 6px 8px;
                height: 42px;
                gap: 4px;
            }
            .hub-back-btn {
                padding: 4px 8px;
                font-size: 11px;
                gap: 3px;
            }
            #detailTitle {
                font-size: 12px;
                max-width: 45%;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
        }
    </style>
</head>
<body>
    <div class="hub-navbar">
        <div class="hub-nav-top">
            <div class="hub-brand">
                <span>⚔️ TS ORIGIN</span>
            </div>
            <div class="hub-controls-right">
                <button class="hub-btn-icon" title="Khởi chạy thêm Tab mới" onclick="launchNextTab()" style="color: var(--accent-cyan); font-weight: bold; font-size: 16px;">➕</button>
                <button class="hub-btn-icon" title="Làm mới trạng thái" onclick="refreshHubData()">🔄</button>
                <button class="hub-btn-icon" title="Toàn màn hình" onclick="toggleFullScreen()">⛶</button>
            </div>
        </div>
        <div class="hub-tabs-scroll" id="navTabsContainer">
            <button class="hub-nav-pill active" id="pillOverview" onclick="switchView('overview')">
                <span>📊</span><span>Tổng Quan</span>
            </button>
            <!-- Dynamic Tab Pills -->
        </div>
    </div>

    <div class="hub-content">
        <!-- VIEW 1: OVERVIEW DASHBOARD -->
        <div class="hub-view active" id="viewOverview">
            <div class="hub-overview-container">
                <div class="hub-stats-row">
                    <div class="hub-stat-card">
                        <div>
                            <div class="hub-stat-label">Tổng Tab Kết Nối</div>
                            <div class="hub-stat-num" id="statTotalTabs">0</div>
                        </div>
                        <div style="font-size: 24px;">🖥️</div>
                    </div>
                    <div class="hub-stat-card">
                        <div>
                            <div class="hub-stat-label">Đang Chạy Auto</div>
                            <div class="hub-stat-num" style="color: var(--accent-green);" id="statRunningTabs">0</div>
                        </div>
                        <div style="font-size: 24px;">⚡</div>
                    </div>
                    <div class="hub-stat-card">
                        <div>
                            <div class="hub-stat-label">Đang Rảnh / Chờ</div>
                            <div class="hub-stat-num" style="color: var(--text-muted);" id="statStandbyTabs">0</div>
                        </div>
                        <div style="font-size: 24px;">💤</div>
                    </div>
                </div>

                <div class="hub-cards-grid" id="tabCardsGrid">
                    <div class="hub-empty-state">
                        <h3>Đang quét các Tab LDPlayer...</h3>
                        <p>Vui lòng mở Tool để hệ thống tự động nhận diện và đồng bộ các Tab.</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- VIEW 2: DEDICATED TAB VIEW -->
        <div class="hub-view" id="viewTabDetail">
            <div class="hub-detail-bar">
                <button class="hub-back-btn" onclick="switchView('overview')">← Quay Lại Tổng Quan</button>
                <div id="detailTitle" style="font-weight: 700; color: #fff;">🖥️ Tab Detail</div>
                <a id="btnNewWindow" href="" target="_blank" class="hub-back-btn" style="text-decoration: none;">Mở Tab Riêng ↗</a>
            </div>
            <div class="hub-iframe-wrapper">
                <iframe id="tabFrame" class="hub-iframe" src=""></iframe>
            </div>
        </div>
    </div>

    <div id="hubToast"></div>

    <script>
        let hubData = { tabs: [] };
        let activeView = 'overview';
        let activeTabPort = null;
        let pollTimer = null;

        function showToast(msg) {
            const t = document.getElementById('hubToast');
            if (!t) return;
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 2500);
        }

        function toggleFullScreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        }

        function switchView(view, port) {
            activeView = view;
            const viewOverview = document.getElementById('viewOverview');
            const viewTabDetail = document.getElementById('viewTabDetail');
            const pillOverview = document.getElementById('pillOverview');

            document.querySelectorAll('.hub-nav-pill').forEach(p => p.classList.remove('active'));

            if (view === 'overview') {
                viewOverview.classList.add('active');
                viewTabDetail.classList.remove('active');
                pillOverview.classList.add('active');
                activeTabPort = null;
                // Giải phóng iframe khi quay về trang tổng quan để dừng stream ngầm
                const iframe = document.getElementById('tabFrame');
                if (iframe) {
                    iframe.src = 'about:blank';
                    iframe.removeAttribute('data-port');
                }
            } else if (view === 'tab' && port) {
                activeTabPort = port;
                viewOverview.classList.remove('active');
                viewTabDetail.classList.add('active');

                const activePill = document.getElementById('pill_tab_' + port);
                if (activePill) {
                    activePill.classList.add('active');
                    try { activePill.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }); } catch (e) {}
                }

                const iframe = document.getElementById('tabFrame');
                const targetSrc = '/proxy/' + port + '/?embed=1';
                if (iframe.getAttribute('data-port') !== String(port)) {
                    iframe.src = targetSrc;
                    iframe.setAttribute('data-port', String(port));
                }

                const curTab = (hubData.tabs || []).find(t => t.port === port);
                const tabTitle = curTab ? (curTab.selected_tab || 'Tab') : 'Tab';
                document.getElementById('detailTitle').innerText = `🖥️ ${tabTitle}`;
                document.getElementById('btnNewWindow').href = `/proxy/${port}/`;
            }
        }

        async function refreshHubData() {
            try {
                const res = await fetch('/api/hub/status');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                hubData = await res.json();
                renderHubUI(hubData);
            } catch (e) {
                console.warn('Lỗi quét Hub:', e);
            }
        }

        function renderHubUI(data) {
            const tabs = data.tabs || [];
            document.getElementById('statTotalTabs').innerText = tabs.length;
            const runningCount = tabs.filter(t => t.is_running).length;
            document.getElementById('statRunningTabs').innerText = runningCount;
            document.getElementById('statStandbyTabs').innerText = tabs.length - runningCount;

            // 1. Cập nhật Nav Pills mượt mà (Không xóa/tạo lại nếu đã có)
            const navContainer = document.getElementById('navTabsContainer');
            const existingPills = navContainer.querySelectorAll('.hub-nav-pill:not(#pillOverview)');
            existingPills.forEach(p => {
                const pPort = parseInt(p.getAttribute('data-port'));
                if (!tabs.some(t => t.port === pPort)) {
                    p.remove();
                }
            });

            tabs.forEach(t => {
                let pill = document.getElementById('pill_tab_' + t.port);
                const dotClass = t.is_running ? 'dot running' : 'dot';
                const pillLabel = t.selected_tab || 'Tab';
                if (!pill) {
                    pill = document.createElement('button');
                    pill.className = 'hub-nav-pill' + (activeTabPort === t.port ? ' active' : '');
                    pill.id = 'pill_tab_' + t.port;
                    pill.setAttribute('data-port', t.port);
                    pill.onclick = () => switchView('tab', t.port);
                    navContainer.appendChild(pill);
                } else {
                    pill.className = 'hub-nav-pill' + (activeTabPort === t.port ? ' active' : '');
                }
                pill.innerHTML = `<span class="${dotClass}"></span><span>${pillLabel}</span>`;
            });

            // 2. Cập nhật Cards Lưới Tổng Quan
            const grid = document.getElementById('tabCardsGrid');
            if (tabs.length === 0) {
                grid.innerHTML = `
                    <div class="hub-empty-state">
                        <h3>Chưa phát hiện Tab LDPlayer nào đang kết nối</h3>
                        <p>Vui lòng mở ứng dụng TS Origin Control V3 trên máy tính để tự động kết nối.</p>
                    </div>
                `;
                return;
            }

            const emptyState = grid.querySelector('.hub-empty-state');
            if (emptyState) emptyState.remove();

            // Xóa thẻ của tab đã đóng
            const existingCards = grid.querySelectorAll('.hub-tab-card');
            existingCards.forEach(card => {
                const cPort = parseInt(card.getAttribute('data-port'));
                if (!tabs.some(t => t.port === cPort)) {
                    card.remove();
                }
            });

            // Cập nhật hoặc tạo mới từng thẻ tab
            tabs.forEach(t => {
                const isRun = t.is_running;
                const isMissingTab = !t.selected_tab || t.selected_tab.includes('Không có Tab LD') || t.selected_tab.includes('Chưa có Tab LD');

                let card = document.getElementById('card_tab_' + t.port);
                if (!card) {
                    card = document.createElement('div');
                    card.className = 'hub-tab-card';
                    card.id = 'card_tab_' + t.port;
                    card.setAttribute('data-port', t.port);
                    card.innerHTML = `
                        <div class="hub-card-header">
                            <div class="hub-card-title">
                                <span class="tab-title-text">📱 ${t.selected_tab || 'LDPlayer'}</span>
                            </div>
                            <span class="status-tag-box"></span>
                        </div>
                        <div class="hub-screen-box" onclick="switchView('tab', ${t.port})">
                            <img class="hub-screen-img" id="thumb_${t.port}" alt="LDPlayer Screen" src="/proxy/${t.port}/api/screenshot?q=2s">
                            <div class="hub-screen-overlay">🔍 Bấm để vào điều khiển trực tiếp</div>
                        </div>
                        <div class="hub-card-actions">
                            <button class="hub-btn hub-btn-view" onclick="switchView('tab', ${t.port})">🔍 Vào Chi Tiết</button>
                        </div>
                    `;
                    grid.appendChild(card);
                }

                // Cập nhật text động trong card (Zero flickering)
                const titleEl = card.querySelector('.tab-title-text');
                if (titleEl) titleEl.innerText = isMissingTab ? `⚠️ ${t.selected_tab || 'Chưa có Tab'}` : `📱 ${t.selected_tab || 'LDPlayer'}`;

                const tagBox = card.querySelector('.status-tag-box');
                if (tagBox) {
                    if (isMissingTab) {
                        tagBox.innerHTML = '<span class="hub-status-tag" style="background:rgba(239,68,68,0.2);color:#ef4444;border:1px solid rgba(239,68,68,0.4);"><span class="dot" style="background:#ef4444;"></span> THIẾU TAB LD</span>';
                    } else {
                        tagBox.innerHTML = isRun
                            ? '<span class="hub-status-tag running"><span class="dot running"></span> ĐANG AUTO</span>'
                            : '<span class="hub-status-tag standby"><span class="dot"></span> ĐANG NGHỈ</span>';
                    }
                }

                // Cập nhật hình ảnh thumbnail mượt mà qua Image preload (chỉ khi đang ở Overview)
                if (!activeTabPort) {
                    const thumbImg = document.getElementById('thumb_' + t.port);
                    if (thumbImg && !thumbImg._busy) {
                        thumbImg._busy = true;
                        const nextThumb = new Image();
                        nextThumb.onload = () => {
                            thumbImg.src = nextThumb.src;
                            thumbImg._busy = false;
                        };
                        nextThumb.onerror = () => {
                            thumbImg._busy = false;
                        };
                        nextThumb.src = `/proxy/${t.port}/api/screenshot?q=2s&_t=${Date.now()}`;
                    }
                }
            });
        }


        async function launchNextTab() {
            if (!confirm('Khởi chạy thêm 1 cửa sổ Tool cho Tab LDPlayer tiếp theo?')) return;
            try {
                showToast('Đang gửi lệnh mở Tab mới...');
                const res = await fetch('/api/hub/launch_tab', { method: 'POST' });
                const data = await res.json();
                showToast(data.msg || 'Đã khởi chạy!');
                setTimeout(refreshHubData, 2500);
            } catch (e) {
                showToast('Không thể gửi lệnh!');
            }
        }

        // Bắt đầu chu kỳ quét định kỳ
        refreshHubData();
        pollTimer = setInterval(refreshHubData, 2500);
    </script>
</body>
</html>"""



def stop_active_tunnel(app):
    """Dừng tiến trình tunnel cũ đang chạy nếu có"""
    setattr(app, 'stop_tunnel_requested', True)
    proc = getattr(app, 'cloudflared_proc', None)
    if proc:
        try:
            proc.terminate()
            time.sleep(0.3)
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        app.cloudflared_proc = None

    # Quét dọn triệt để các tiến trình ngrok và cloudflared mồ côi (tránh xung đột session đơn lẻ của Ngrok)
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
    except Exception:
        pass


def find_or_download_cloudflared(app):
    """Tìm hoặc tự động tải cloudflared.exe từ Cloudflare nếu chưa có"""
    app_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)

    local_bin = os.path.join(app_dir, "cloudflared.exe")
    if os.path.exists(local_bin) and os.path.getsize(local_bin) > 10000000:
        return local_bin

    sys_bin = shutil.which("cloudflared")
    if sys_bin:
        return sys_bin

    app.log_info("📥 Đang tự động tải cloudflared.exe chính chủ Cloudflare (khoảng 50MB, chỉ tải 1 lần)...")
    download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    temp_bin = local_bin + ".download"

    # 1. Thử tải bằng Python urllib (Native & an toàn nhất)
    try:
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(temp_bin, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        if os.path.exists(temp_bin) and os.path.getsize(temp_bin) > 10000000:
            if os.path.exists(local_bin):
                try: os.remove(local_bin)
                except Exception: pass
            os.rename(temp_bin, local_bin)
            app.log_info("✅ Đã tải xong cloudflared.exe thành công!")
            return local_bin
    except Exception as e:
        app.log_warning(f"Tải bằng urllib chưa thành công: {e}. Đang thử bằng Curl/PowerShell...")
        if os.path.exists(temp_bin):
            try: os.remove(temp_bin)
            except Exception: pass

    # 2. Thử tải bằng Curl nếu có
    try:
        curl_bin = shutil.which("curl")
        if curl_bin:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.run([curl_bin, "-L", "-o", temp_bin, download_url], timeout=90, creationflags=creation_flags)
            if os.path.exists(temp_bin) and os.path.getsize(temp_bin) > 10000000:
                if os.path.exists(local_bin):
                    try: os.remove(local_bin)
                    except Exception: pass
                os.rename(temp_bin, local_bin)
                app.log_info("✅ Đã tải xong cloudflared.exe thành công!")
                return local_bin
    except Exception:
        if os.path.exists(temp_bin):
            try: os.remove(temp_bin)
            except Exception: pass

    # 3. Thử tải bằng PowerShell
    try:
        ps_cmd = f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('{download_url}', '{temp_bin}')"
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=90, creationflags=creation_flags)
        if os.path.exists(temp_bin) and os.path.getsize(temp_bin) > 10000000:
            if os.path.exists(local_bin):
                try: os.remove(local_bin)
                except Exception: pass
            os.rename(temp_bin, local_bin)
            app.log_info("✅ Đã tải xong cloudflared.exe thành công!")
            return local_bin
    except Exception:
        if os.path.exists(temp_bin):
            try: os.remove(temp_bin)
            except Exception: pass

    app.log_error("Không thể tải cloudflared.exe tự động. Sẽ chuyển sang chế độ SSH Tunnel dự phòng.")
    return None


def find_or_download_ngrok(app):
    """Tìm hoặc tự động tải ngrok.exe nếu chưa có"""
    app_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)

    local_bin = os.path.join(app_dir, "ngrok.exe")
    if os.path.exists(local_bin) and os.path.getsize(local_bin) > 5000000:
        return local_bin

    sys_bin = shutil.which("ngrok")
    if sys_bin:
        return sys_bin

    app.log_info("📥 Đang tự động tải ngrok.exe từ server chính chủ...")
    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    temp_zip = os.path.join(tempfile.gettempdir(), "ngrok.zip")

    try:
        req = urllib.request.Request(download_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(temp_zip, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        if os.path.exists(temp_zip):
            import zipfile
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extract("ngrok.exe", app_dir)
            try: os.remove(temp_zip)
            except Exception: pass
            if os.path.exists(local_bin):
                app.log_info("✅ Đã tải xong ngrok.exe thành công!")
                return local_bin
    except Exception as e:
        if hasattr(app, 'log_warning'):
            app.log_warning(f"Lỗi tải ngrok.exe: {e}")
    return None


def get_app_dir():
    """Lấy đường dẫn thư mục thực tế chứa file .exe (hoặc script main.py)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def start_cloudflare_tunnel(app):
    """Khởi động đường truyền Online HTTPS bảo mật truy cập từ xa (4G/Internet) - Tự động hỗ trợ Ngrok Static Domain hoặc Cloudflare"""
    def _tunnel_worker():
        stop_active_tunnel(app)
        setattr(app, 'stop_tunnel_requested', False)
        is_hub = getattr(app, 'is_hub_master', False)
        port = 8080 if is_hub else getattr(app, 'web_port', 8081)
        hub_label = " (Trang Tổng Quản 8080)" if is_hub else f" (Tab Riêng {port})"
        app.log_info(f"🌐 [4G / ONLINE] Đang khởi tạo đường truyền HTTPS qua cổng {port}{hub_label}...")

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        # Check configuration in config.json
        cf_token = ""
        cf_domain = ""
        ngrok_token = ""
        ngrok_domain = ""
        try:
            cfg_path = app._get_config_path() if hasattr(app, '_get_config_path') else os.path.join(get_app_dir(), "config.json")
            if not os.path.exists(cfg_path):
                cfg_path = os.path.join(get_app_dir(), "config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    cf_token = cfg_data.get("cloudflare_token", "").strip()
                    cf_domain = cfg_data.get("fixed_domain", "").strip()
                    ngrok_token = cfg_data.get("ngrok_authtoken", "").strip()
                    if not cf_domain and cfg_data.get("ngrok_domain"):
                        ngrok_domain = cfg_data.get("ngrok_domain", "").strip()
                    elif cf_domain and "ngrok" in cf_domain.lower():
                        ngrok_domain = cf_domain
        except Exception:
            pass

        # 0. ƯU TIÊN NGROK STATIC DOMAIN NẾU CÓ NGROK TOKEN & DOMAIN TRONG CONFIG.JSON
        if ngrok_token and (ngrok_domain or cf_domain):
            domain_target = ngrok_domain or cf_domain
            ngrok_bin = find_or_download_ngrok(app)
            if ngrok_bin and os.path.exists(ngrok_bin):
                try:
                    # Dọn dẹp mọi tiến trình ngrok cũ còn kẹt trước khi tạo session mới
                    try:
                        subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
                        time.sleep(0.3)
                    except Exception:
                        pass

                    subprocess.run([ngrok_bin, "config", "add-authtoken", ngrok_token], creationflags=creation_flags)
                    subprocess.run([ngrok_bin, "authtoken", ngrok_token], creationflags=creation_flags)

                    clean_dom = domain_target.replace("https://", "").replace("http://", "").strip("/")
                    found_url = f"https://{clean_dom}"
                    app.public_web_url = found_url
                    if hasattr(app, '_update_web_url_ui'):
                        app.after(0, app._update_web_url_ui, found_url, True)

                    cmd_options = [
                        [ngrok_bin, "http", f"--domain={clean_dom}", str(port), "--log=stdout", "--log-level=warn"],
                        [ngrok_bin, "http", str(port), "--domain", clean_dom, "--log=stdout", "--log-level=warn"],
                        [ngrok_bin, "http", str(port), "--url", clean_dom, "--log=stdout", "--log-level=warn"],
                        [ngrok_bin, "http", f"--domain={clean_dom}", str(port)]
                    ]

                    ngrok_success = False
                    retry_count = 0

                    def _start_ngrok_proc(ngrok_cmd):
                        p = subprocess.Popen(
                            ngrok_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding='utf-8',
                            errors='ignore',
                            creationflags=creation_flags
                        )
                        # Luồng đọc output liên tục (Draining Thread) để triệt tiêu lỗi đầy OS Pipe Buffer làm treo ngrok
                        def _drain_output(proc_to_drain):
                            try:
                                for line in iter(proc_to_drain.stdout.readline, ''):
                                    if not line or getattr(app, 'stop_tunnel_requested', False):
                                        break
                                    line_clean = line.strip()
                                    if any(k in line_clean for k in ["ERR_NGROK", "critical", "error", "failed"]):
                                        app.log_warning(f"⚠️ [NGROK] {line_clean[:130]}")
                            except Exception:
                                pass
                        threading.Thread(target=_drain_output, args=(p,), daemon=True).start()
                        return p

                    for cmd in cmd_options:
                        app.log_info(f"🚀 [4G / NGROK STATIC DOMAIN] Đang khởi chạy Tên Miền Cố Định: https://{clean_dom}")
                        proc = _start_ngrok_proc(cmd)
                        app.cloudflared_proc = proc
                        time.sleep(2.0)
                        if proc.poll() is None:
                            ngrok_success = True
                            while not getattr(app, 'stop_tunnel_requested', False):
                                proc.wait()
                                if getattr(app, 'stop_tunnel_requested', False):
                                    break
                                retry_count += 1
                                app.log_warning(f"⚠️ [4G / NGROK] Mất kết nối Ngrok. Đang tự động dọn session và kết nối lại (Lần {retry_count})...")
                                try:
                                    subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    time.sleep(1.0)
                                except Exception:
                                    pass
                                proc = _start_ngrok_proc(cmd)
                                app.cloudflared_proc = proc
                            break
                        else:
                            out_err = proc.stdout.read() if proc.stdout else ""
                            app.log_warning(f"Cú pháp câu lệnh Ngrok chưa tương thích, đang thử cú pháp khác... {out_err.strip()[:80]}")

                    if ngrok_success:
                        app.log_warning("⚠️ [4G / ONLINE] Đường truyền Ngrok đã dừng.")
                        return
                    else:
                        app.log_error("❌ Ngrok không thể khởi chạy. Tự động chuyển sang Cloudflare...")
                except Exception as e:
                    app.log_error(f"Lỗi khởi động Ngrok Tunnel: {e}")

        # 1. NẾU CÓ CLOUDFLARE TOKEN CỐ ĐỊNH -> CHẠY CLOUDFLARE STATIC TUNNEL
        bin_path = find_or_download_cloudflared(app)
        if cf_token and bin_path and os.path.exists(bin_path):
            try:
                cmd = [bin_path, "tunnel", "run", "--token", cf_token]
                app.log_info("🔑 [4G / ONLINE] Đang khởi chạy Cloudflare Tunnel với TOKEN CỐ ĐỊNH...")
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=creation_flags)
                app.cloudflared_proc = proc

                found_url = cf_domain if cf_domain.startswith("http") else f"https://{cf_domain}"
                app.public_web_url = found_url
                app.log_info(f"🚀 [4G / CLOUDFLARE STATIC LINK] Sẵn sàng: {found_url}")
                if hasattr(app, '_update_web_url_ui'):
                    app.after(0, app._update_web_url_ui, found_url, True)

                proc.wait()
                app.log_warning("⚠️ [4G / ONLINE] Đường truyền Cloudflare Tunnel đã dừng.")
                if hasattr(app, '_on_tunnel_failed'):
                    app.after(0, app._on_tunnel_failed)
                return
            except Exception as e:
                app.log_error(f"Lỗi khởi động Cloudflare Tunnel Token: {e}")

        # 2. CHẾ ĐỘ CLOUDFLARE QUICK TUNNEL (TÊN MIỀN RANDOM trycloudflare.com)
        if bin_path and os.path.exists(bin_path):
            try:
                app.log_info("🌐 [4G / ONLINE] Đang khởi tạo đường truyền Cloudflare Quick Tunnel (Tên miền ngẫu nhiên)...")
                cmd = [bin_path, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=creation_flags
                )
                app.cloudflared_proc = proc

                found_url = None
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    if not found_url:
                        match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
                        if match:
                            found_url = match.group(1)
                            app.public_web_url = found_url
                            app.log_info(f"🚀 [4G / CLOUDFLARE LINK] Sẵn sàng: {found_url}")
                            if hasattr(app, '_update_web_url_ui'):
                                app.after(0, app._update_web_url_ui, found_url, True)

                proc.poll()
                app.log_warning("⚠️ [4G / ONLINE] Đường truyền Cloudflare Tunnel đã dừng.")
                if hasattr(app, '_on_tunnel_failed'):
                    app.after(0, app._on_tunnel_failed)
                return
            except Exception as e:
                app.log_error(f"Lỗi khởi động Cloudflare Tunnel: {e}")

        # 3. DỰ PHÒNG CUỐI: SSH Tunnel (Localhost.run / Pinggy) nếu Cloudflared không khả dụng
        ssh_bin = shutil.which("ssh") or "ssh"
        ssh_configs = [
            (
                "Localhost.run",
                [ssh_bin, "-T", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=6", "-o", "TCPKeepAlive=yes", "-R", f"80:127.0.0.1:{port}", "nokey@localhost.run"],
                r'(https://[a-zA-Z0-9-]+\.lhr\.life)'
            ),
            (
                "Pinggy",
                [ssh_bin, "-p", "443", "-R0:localhost:" + str(port), "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=6", "-o", "TCPKeepAlive=yes", "a.pinggy.io"],
                r'(https://[a-zA-Z0-9-]+\.free\.pinggy\.link|https://[a-zA-Z0-9-]+\.a\.pinggy\.link)'
            )
        ]

        for s_name, cmd, regex_pattern in ssh_configs:
            try:
                app.log_info(f"🌐 [4G / ONLINE] Đang khởi tạo đường truyền {s_name}...")
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=creation_flags
                )
                app.cloudflared_proc = proc
                found_url = None

                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    if not found_url:
                        match = re.search(regex_pattern, line)
                        if match:
                            found_url = match.group(1)
                            app.public_web_url = found_url
                            app.log_info(f"🚀 [4G / {s_name.upper()} LINK] Sẵn sàng: {found_url}")
                            if hasattr(app, '_update_web_url_ui'):
                                app.after(0, app._update_web_url_ui, found_url, True)

                if found_url:
                    app.log_warning(f"⚠️ [4G / ONLINE] Đường truyền {s_name} đã ngắt kết nối.")
                    if hasattr(app, '_on_tunnel_failed'):
                        app.after(0, app._on_tunnel_failed)
                    return
            except Exception as e:
                app.log_error(f"Lỗi kết nối {s_name}: {e}")

        if hasattr(app, '_on_tunnel_failed'):
            app.after(0, app._on_tunnel_failed)

    threading.Thread(target=_tunnel_worker, daemon=True).start()
