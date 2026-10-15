# -*- coding: utf-8 -*-
"""
Module tự động kiểm tra và cập nhật (Auto-Updater) cho TS Origin Control V3.
Hỗ trợ tải ngầm từ GitHub Releases và tự khởi động lại app an toàn trên Windows.
"""

import os
import sys
import re
import json
import time
import urllib.request
import urllib.parse
import subprocess
import threading
from version import APP_VERSION, GITHUB_REPO

def get_app_dir():
    """Lấy đường dẫn thư mục thực tế chứa file .exe (hoặc script main_v3.py)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def parse_version_tuple(ver_str):
    """Chuyển chuỗi version 'v3.1.2' hoặc '3.1.2' thành tuple số (3, 1, 2) để so sánh."""
    nums = re.findall(r'\d+', str(ver_str))
    return tuple(int(n) for n in nums) if nums else (0, 0, 0)

def is_newer_version(remote_ver, local_ver):
    """Kiểm tra remote_ver có lớn hơn local_ver hay không."""
    return parse_version_tuple(remote_ver) > parse_version_tuple(local_ver)

def check_for_updates(current_version=None):
    """
    Gọi GitHub API để kiểm tra phiên bản mới nhất từ GitHub Releases.
    Trả về dict thông tin nếu có bản mới, hoặc None nếu đã là bản mới nhất/lỗi.
    """
    local_ver = current_version if current_version is not None else APP_VERSION
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "TS_Origin_AutoUpdater",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode('utf-8'))
            remote_tag = data.get("tag_name", "")
            if not remote_tag:
                return None

            if not is_newer_version(remote_tag, local_ver):
                return {
                    "has_update": False,
                    "current_version": local_ver,
                    "latest_version": remote_tag
                }

            # Tìm file tài nguyên cần tải: TS_Origin_Control_V3.exe
            download_url = None
            asset_size = 0
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.lower() == "ts_origin_control_v3.exe":
                    download_url = asset.get("browser_download_url")
                    asset_size = asset.get("size", 0)
                    break

            if not download_url:
                return None

            return {
                "has_update": True,
                "current_version": APP_VERSION,
                "latest_version": remote_tag,
                "download_url": download_url,
                "size": asset_size,
                "changelog": data.get("body", "Bản cập nhật mới.")
            }
    except Exception as e:
        # Nếu mất mạng hoặc chưa có release thì âm thầm bỏ qua
        return None

def download_and_apply_update(download_url, progress_callback=None, app=None):
    """
    Tải file TS_Origin_Control_V3.exe về thư mục tạm _update_temp
    và kích hoạt script apply_update.bat chạy ngầm để ghi đè file cũ.
    """
    app_dir = get_app_dir()
    temp_dir = os.path.join(app_dir, "_update_temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_file = os.path.join(temp_dir, "TS_Origin_Control_V3.exe")

    # Tải file từ GitHub CDN (tự động theo redirect 302 của GitHub Releases)
    req = urllib.request.Request(download_url, headers={"User-Agent": "TS_Origin_AutoUpdater"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(temp_file, "wb") as f:
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 128 * 1024  # 128 KB

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total_size > 0:
                percent = int(downloaded * 100 / total_size)
                progress_callback(percent, downloaded, total_size)

    # Đảm bảo file tải về có dung lượng hợp lệ (> 10MB)
    if os.path.getsize(temp_file) < 10 * 1024 * 1024:
        raise ValueError("File tải về không hoàn chỉnh (kích thước quá nhỏ)!")

    # Tạo file batch apply_update.bat với cơ chế chống khóa file (File Lock Retry Loop)
    bat_file = os.path.join(app_dir, "apply_update.bat")
    bat_content = f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cap Nhat TS Origin Control V3...

echo ========================================================
echo   HE THONG TU DONG CAP NHAT TS ORIGIN CONTROL V3
echo ========================================================
echo [1/3] Dang dong cac tien trinh cu de giai phong file...
taskkill /F /IM "TS_Origin_Control_V3.exe" >nul 2>nul
ping 127.0.0.1 -n 3 >nul

echo [2/3] Dang ghi de ban cap nhat moi...
set RETRY_COUNT=0
:COPY_LOOP
copy /y "_update_temp\\TS_Origin_Control_V3.exe" "TS_Origin_Control_V3.exe" >nul
if errorlevel 1 (
    set /a RETRY_COUNT+=1
    if %RETRY_COUNT% leq 20 (
        echo   - File dang ban, dang thu lai lan %RETRY_COUNT%/20...
        taskkill /F /IM "TS_Origin_Control_V3.exe" >nul 2>nul
        ping 127.0.0.1 -n 2 >nul
        goto COPY_LOOP
    ) else (
        echo [LOI] Khong the ghi de file sau 20 lan thu. Vui long thu lai bang quyen Administrator!
        ping 127.0.0.1 -n 5 >nul
        exit /b 1
    )
)

echo [3/3] Ghi de thanh cong! Dang don dep va khoi dong lai Tool...
rmdir /s /q "_update_temp" >nul 2>nul
ping 127.0.0.1 -n 2 >nul

REM Xoa sach tat ca cac bien moi truong noi bo PyInstaller
set _MEIPASS=
set _MEIPASS2=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_ARCHIVE_FILE=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_SPLASH_IPC=
set PYINSTALLER_RESET_ENVIRONMENT=

if exist "launch_app.vbs" (
    start "" wscript "launch_app.vbs"
) else (
    start "" "TS_Origin_Control_V3.exe"
)

ping 127.0.0.1 -n 2 >nul
(goto) 2>nul & del "%~f0"
"""
    with open(bat_file, "w", encoding="utf-8") as bf:
        bf.write(bat_content)

    # Xóa sạch các biến môi trường nội bộ của PyInstaller để tiến trình con không bị dính môi trường cũ
    clean_env = os.environ.copy()
    for key in list(clean_env.keys()):
        if key.startswith("_MEI") or key.startswith("_PYI") or key.startswith("PYI"):
            clean_env.pop(key, None)

    # Chạy batch file trong cửa sổ console độc lập (CREATE_NEW_CONSOLE = 0x00000010)
    CREATE_NEW_CONSOLE = 0x00000010
    subprocess.Popen(
        ["cmd.exe", "/c", bat_file],
        cwd=app_dir,
        env=clean_env,
        creationflags=CREATE_NEW_CONSOLE,
        close_fds=True
    )

    # Thoát tiến trình hiện tại để giải phóng file .exe
    if app and hasattr(app, 'log_info'):
        app.after(0, app.log_info, "🔄 [Auto-Update] Tải hoàn tất! Đang khởi động lại để áp dụng bản mới...")
    time.sleep(1.0)
    os._exit(0)

def start_background_updater(app):
    """
    Chạy thread kiểm tra cập nhật ngầm khi mở Tool.
    Nếu đang chạy từ file .exe và có bản mới: tự động tải và cập nhật.
    Nếu đang chạy từ mã nguồn Python (môi trường lập trình của bạn): bỏ qua.
    """
    def _worker():
        # Đợi 3 giây để hệ thống chính và Web UI sẵn sàng
        time.sleep(3)

        # Kiểm tra xem có đang chạy từ file đóng gói .exe không
        is_frozen = getattr(sys, 'frozen', False)
        if not is_frozen:
            print(f"[Updater] Dang chay tu ma nguon Python (v{APP_VERSION}). Khong tu dong cap nhat de tranh ghi de file lap trinh.")
            if hasattr(app, 'update_info'):
                app.update_info = {
                    "status": "dev_mode",
                    "current_version": APP_VERSION
                }
            return

        print(f"[Updater] Dang kiem tra ban cap nhat tren GitHub (Hien tai: v{APP_VERSION})...")
        update = check_for_updates()
        if not update or not update.get("has_update"):
            print("[Updater] Ban dang su dung phien ban moi nhat.")
            if hasattr(app, 'update_info'):
                app.update_info = {
                    "status": "up_to_date",
                    "current_version": APP_VERSION
                }
            return

        latest_ver = update.get("latest_version")
        download_url = update.get("download_url")
        print(f"[Updater] Phat hien ban cap nhat moi: {latest_ver}! Dang tien hanh tu dong tai ve...")
        if hasattr(app, 'log_info'):
            app.after(0, app.log_info, f"🚀 [Auto-Update] Phát hiện bản mới {latest_ver}! Đang tự động tải về ngầm...")

        # Cập nhật trạng thái cho Web UI và App
        if hasattr(app, 'update_info'):
            app.update_info = {
                "status": "downloading",
                "current_version": APP_VERSION,
                "latest_version": latest_ver,
                "progress": 0,
                "changelog": update.get("changelog", "")
            }

        def on_progress(percent, downloaded, total):
            if hasattr(app, 'update_info'):
                app.update_info["progress"] = percent

        try:
            download_and_apply_update(download_url, progress_callback=on_progress, app=app)
        except Exception as e:
            print(f"[Updater] Loi trong qua trinh tu dong cap nhat: {e}")
            if hasattr(app, 'log_warning'):
                app.after(0, app.log_warning, f"⚠️ [Auto-Update] Không thể tự cập nhật: {e}")
            if hasattr(app, 'update_info'):
                app.update_info = {
                    "status": "error",
                    "error": str(e),
                    "current_version": APP_VERSION
                }

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
