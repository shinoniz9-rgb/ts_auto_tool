# -*- coding: utf-8 -*-
"""
Script 1-Click phát hành bản cập nhật mới (Release Publisher) cho TS Auto Tool.
Quy trình tự động:
1. Nâng số phiên bản (version.py)
2. Tự động đóng gói TS_Origin_Control_V3.exe qua build_v3.py
3. Tự động tạo Release trên GitHub và upload file .exe lên GitHub Releases
4. Đẩy commit & tag lên Git (nếu muốn)
"""

import os
import sys
import re
import json
import time
import subprocess
import urllib.request
import urllib.parse
from version import APP_VERSION, GITHUB_REPO

def get_token():
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github_token")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            t = f.read().strip()
            if t:
                return t
    t = os.environ.get("GITHUB_TOKEN", "").strip()
    if t:
        return t
    raise ValueError("Không tìm thấy GitHub Token! Vui lòng tạo file .github_token chứa mã token.")

def bump_version(ver_str):
    nums = [int(n) for n in re.findall(r'\d+', ver_str)]
    if len(nums) >= 3:
        nums[2] += 1
        return f"{nums[0]}.{nums[1]}.{nums[2]}"
    elif len(nums) == 2:
        return f"{nums[0]}.{nums[1]}.1"
    return f"{ver_str}.1"

def update_version_file(new_ver):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.py")
    content = f'''# -*- coding: utf-8 -*-
"""Định nghĩa phiên bản và thông tin repository GitHub cho TS Auto Tool."""
APP_VERSION = "{new_ver}"
GITHUB_REPO = "{GITHUB_REPO}"
'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def build_exe():
    print("\n[1/3] Đang tiến hành đóng gói TS_Origin_Control_V3.exe...")
    build_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_v3.py")
    res = subprocess.run([sys.executable, build_script])
    if res.returncode != 0:
        raise RuntimeError("Quá trình đóng gói build_v3.py thất bại!")
    
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TS_Origin_Control_V3.exe")
    if not os.path.exists(exe_path) or os.path.getsize(exe_path) < 5 * 1024 * 1024:
        raise RuntimeError(f"File {exe_path} không tồn tại hoặc kích thước không hợp lệ!")
    print(f"✅ Đóng gói thành công: {exe_path} ({os.path.getsize(exe_path) / (1024*1024):.1f} MB)")
    return exe_path

def create_and_upload_release(new_ver, changelog, exe_path, token):
    tag_name = f"v{new_ver}"
    print(f"\n[2/3] Đang kết nối GitHub và tạo Release {tag_name}...")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TS_Release_Publisher"
    }

    # 1. Kiểm tra xem release này đã tồn tại chưa
    check_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag_name}"
    req = urllib.request.Request(check_url, headers=headers)
    release_data = None
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                release_data = json.loads(resp.read().decode('utf-8'))
                print(f"⚠️ Bản Release {tag_name} đã tồn tại (ID: {release_data.get('id')}).")
    except Exception:
        pass

    # 2. Nếu chưa có thì tạo mới Release
    if not release_data:
        create_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
        payload = json.dumps({
            "tag_name": tag_name,
            "target_commitish": "main",
            "name": f"TS Origin Control V3 - {tag_name}",
            "body": changelog,
            "draft": False,
            "prerelease": False
        }).encode('utf-8')
        
        req = urllib.request.Request(create_url, data=payload, headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode('utf-8'))
            print(f"✅ Đã tạo Release mới: {tag_name} (ID: {release_data.get('id')})")

    release_id = release_data.get("id")

    # 3. Xóa asset cũ nếu đã có file trùng tên
    for asset in release_data.get("assets", []):
        if asset.get("name", "").lower() == "ts_origin_control_v3.exe":
            asset_id = asset.get("id")
            del_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/assets/{asset_id}"
            del_req = urllib.request.Request(del_url, headers=headers, method="DELETE")
            try:
                with urllib.request.urlopen(del_req):
                    print("  - Đã xóa file asset cũ trên Release.")
            except Exception:
                pass

    # 4. Upload file TS_Origin_Control_V3.exe lên Release
    file_size = os.path.getsize(exe_path)
    file_size_mb = file_size / (1024 * 1024)
    print(f"\n[3/3] Đang tải file lên GitHub Releases ({file_size_mb:.1f} MB)... Vui lòng đợi trong giây lát...")
    
    upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets?name=TS_Origin_Control_V3.exe"
    
    with open(exe_path, "rb") as f:
        file_bytes = f.read()

    upload_req = urllib.request.Request(
        upload_url,
        data=file_bytes,
        headers={
            **headers,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_size)
        }
    )

    with urllib.request.urlopen(upload_req, timeout=180) as resp:
        if resp.status in (200, 201):
            upload_res = json.loads(resp.read().decode('utf-8'))
            print(f"✅ Tải lên thành công! Download URL: {upload_res.get('browser_download_url')}")
        else:
            raise RuntimeError(f"Lỗi tải lên GitHub: HTTP {resp.status}")

def sync_git(new_ver, changelog):
    """Tự động commit và push phiên bản mới lên Git."""
    try:
        subprocess.run(["git", "add", "version.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", f"release: cap nhat phien ban v{new_ver} - {changelog}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "github", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def main():
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    token = get_token()
    
    # Xác định số phiên bản mới
    if len(sys.argv) > 1 and sys.argv[1].strip():
        new_ver = sys.argv[1].strip().lstrip("vV")
    else:
        new_ver = bump_version(APP_VERSION)
    
    if len(sys.argv) > 2 and sys.argv[2].strip():
        changelog = sys.argv[2].strip()
    else:
        changelog = f"Bản cập nhật v{new_ver}: Cải tiến hiệu năng và sửa lỗi."

    print("==================================================================")
    print(f"  PHÁT HÀNH BẢN CẬP NHẬT TỰ ĐỘNG CHO TS ORIGIN CONTROL V3")
    print(f"  Phiên bản hiện tại : v{APP_VERSION}")
    print(f"  Phiên bản phát hành: v{new_ver}")
    print(f"  Nội dung cập nhật  : {changelog}")
    print("==================================================================")

    # 1. Cập nhật version.py
    update_version_file(new_ver)
    print(f"-> Đã cập nhật version.py sang v{new_ver}")

    # 2. Đóng gói EXE
    exe_path = build_exe()

    # 3. Tạo Release và Upload
    create_and_upload_release(new_ver, changelog, exe_path, token)

    # 4. Đồng bộ Git
    sync_git(new_ver, changelog)

    print("\n" + "=" * 66)
    print(f"🎉 CHÚC MỪNG! BẢN v{new_ver} ĐÃ ĐƯỢC PHÁT HÀNH THÀNH CÔNG LÊN GITHUB!")
    print("-> Tất cả máy tính của bạn bè khi mở Tool lên sẽ TỰ ĐỘNG CẬP NHẬT bản này.")
    print("=" * 66 + "\n")

if __name__ == "__main__":
    main()
