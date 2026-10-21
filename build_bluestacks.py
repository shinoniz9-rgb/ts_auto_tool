# -*- coding: utf-8 -*-
"""
Script đóng gói TS_Origin_Control_BlueStacks.exe từ main_bluestacks.py.
Xuất file vào thư mục dist_bluestacks/ và dọn dẹp sạch sẽ 100% file rác sau khi build xong
(theo chuẩn của buff_train_bluestacks/build_exe.py).
"""
import os
import sys
import shutil
import subprocess
import json

base_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(base_dir)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def build():
    print("============================================================")
    print("  ĐANG TIẾN HÀNH ĐÓNG GÓI TS_Origin_Control_BlueStacks.exe   ")
    print("============================================================")

    # 1. Tắt tiến trình cũ nếu đang mở để tránh PermissionError WinError 5
    try:
        subprocess.run(["taskkill", "/F", "/IM", "TS_Origin_Control_BlueStacks.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    target_script = os.path.join(base_dir, "main_bluestacks.py")
    dist_dir = os.path.join(base_dir, "dist_bluestacks")
    work_dir = os.path.join(base_dir, "build_bluestacks")
    spec_dir = os.path.join(base_dir, "build_bluestacks")
    assets_dir = os.path.join(base_dir, "assets")
    icon_path = os.path.join(assets_dir, "app_icon.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name", "TS_Origin_Control_BlueStacks",
        "--distpath", dist_dir,
        "--workpath", work_dir,
        "--specpath", spec_dir,
        "--collect-all", "customtkinter",
        "--collect-all", "rapidocr_onnxruntime",
        "--collect-all", "onnxruntime",
        "--collect-all", "pyclipper",
        "--collect-all", "shapely",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "web_server_v3",
        "--hidden-import", "version",
        "--hidden-import", "updater",
        "--paths", base_dir,
        "--add-data", f"{assets_dir};assets",
        target_script
    ]
    if os.path.exists(icon_path):
        cmd.insert(cmd.index(target_script), f"--icon={icon_path}")

    print("[1/4] Khởi chạy PyInstaller...")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[!] Đóng gói thất bại với mã lỗi:", res.returncode)
        return False

    print("[2/4] Chuẩn bị thư mục dist_bluestacks...")
    os.makedirs(dist_dir, exist_ok=True)

    # 1. Sao chép bộ công cụ ADB (adb.exe, AdbWinApi.dll, AdbWinUsbApi.dll)
    adb_src_dirs = [
        os.path.join(base_dir, "buff_train_bluestacks"),
        base_dir
    ]
    for adb_file in ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]:
        for sdir in adb_src_dirs:
            src = os.path.join(sdir, adb_file)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, os.path.join(dist_dir, adb_file))
                    break
                except Exception:
                    pass

    # 2. Sao chép cloudflared.exe (Loại bỏ hoàn toàn ngrok.exe theo quy tắc tương tự dist_share)
    cf_src = os.path.join(base_dir, "cloudflared.exe")
    if os.path.exists(cf_src):
        try:
            shutil.copy2(cf_src, os.path.join(dist_dir, "cloudflared.exe"))
        except Exception:
            pass

    # Xóa bỏ ngrok.exe nếu vô tình còn tồn đọng trong dist_bluestacks
    dist_ngrok = os.path.join(dist_dir, "ngrok.exe")
    if os.path.exists(dist_ngrok):
        try:
            os.remove(dist_ngrok)
        except Exception:
            pass

    # 3. Tạo file config.json sạch (Loại bỏ Telegram token và Ngrok tương tự bản dist_share)
    clean_cfg_src = os.path.join(base_dir, "dist_share", "config.json")
    if not os.path.exists(clean_cfg_src):
        clean_cfg_src = os.path.join(base_dir, "config.json")
    if os.path.exists(clean_cfg_src):
        try:
            with open(clean_cfg_src, "r", encoding="utf-8") as f:
                cfg_obj = json.load(f)
            cfg_obj["enable_telegram"] = False
            for k in ["telegram_bot_token", "telegram_bot_token_2", "telegram_chat_id", "telegram_chat_id_2", "ngrok_authtoken", "ngrok_domain"]:
                cfg_obj.pop(k, None)
            with open(os.path.join(dist_dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg_obj, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    # 3. Sao chép thư mục assets đầy đủ
    dist_assets = os.path.join(dist_dir, "assets")
    if os.path.exists(dist_assets):
        shutil.rmtree(dist_assets, ignore_errors=True)
    if os.path.exists(assets_dir):
        shutil.copytree(assets_dir, dist_assets)

    print("[3/4] Dọn dẹp sạch sẽ toàn bộ file rác phát sinh khi đóng gói...")
    # Xóa thư mục build_bluestacks
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)

    # Xóa thư mục build thông thường nếu phát sinh
    build_plain = os.path.join(base_dir, "build")
    if os.path.exists(build_plain):
        shutil.rmtree(build_plain, ignore_errors=True)

    # Xóa file spec
    for s_file in [
        os.path.join(base_dir, "TS_Origin_Control_BlueStacks.spec"),
        os.path.join(work_dir, "TS_Origin_Control_BlueStacks.spec")
    ]:
        if os.path.exists(s_file):
            try:
                os.remove(s_file)
            except Exception:
                pass

    # Xóa toàn bộ __pycache__ trong base_dir
    pycache_dir = os.path.join(base_dir, "__pycache__")
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir, ignore_errors=True)

    print("[4/4] Kiểm tra kết quả đóng gói...")
    exe_path = os.path.join(dist_dir, "TS_Origin_Control_BlueStacks.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("============================================================")
        print("  [THÀNH CÔNG] ĐÃ ĐÓNG GÓI XONG TS_Origin_Control_BlueStacks!")
        print(f"  -> File: {exe_path} ({size_mb:.1f} MB)")
        print(f"  -> Thư mục: {dist_dir}")
        print("  -> Đã dọn dẹp sạch 100% file rác (build/, .spec, __pycache__)")
        print("============================================================")
        return True
    else:
        print("[!] Không tìm thấy file exe sau khi đóng gói!")
        return False

if __name__ == "__main__":
    success = build()
    if not success:
        sys.exit(1)
