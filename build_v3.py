# -*- coding: utf-8 -*-
"""Build TS_Origin_Control_V3.exe từ main_v3.py (chạy độc lập tại thư mục gốc)."""
import os
import sys
import shutil
import subprocess

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

print("============================================================")
print("  ĐANG TIẾN HÀNH ĐÓNG GÓI TS_Origin_Control_V3 SANG .EXE    ")
print("============================================================")

# Tắt tiến trình cũ nếu đang mở để tránh lỗi PermissionError WinError 5 khóa file
try:
    subprocess.run(["taskkill", "/F", "/IM", "TS_Origin_Control_V3.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except Exception:
    pass

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconsole", "--onefile", "--clean",
    "--name", "TS_Origin_Control_V3",
    "--distpath", "dist", "--workpath", "build_v3", "--specpath", "build_v3",
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
    "--add-data", os.path.join(base_dir, "assets") + ";assets",
    os.path.join(base_dir, "main_v3.py"),
]
res = subprocess.run(cmd)
if res.returncode == 0:
    dist = os.path.join(base_dir, "dist")
    for f in ("config.json", "cloudflared.exe", "ngrok.exe", "launch_app.vbs", "Tao_Loi_Tat_Desktop.bat"):
        src = os.path.join(base_dir, f)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(dist, f))
            except Exception:
                pass
    dist_assets = os.path.join(dist, "assets")
    if os.path.exists(dist_assets):
        shutil.rmtree(dist_assets)
    shutil.copytree("assets", dist_assets)
    shutil.rmtree("build_v3", ignore_errors=True)
    print("✅ Đóng gói thành công:", os.path.join(dist, "TS_Origin_Control_V3.exe"))
else:
    sys.exit(res.returncode)
