# -*- coding: utf-8 -*-
"""
Script 1-Click phát hành bản cập nhật mới (Release Publisher) cho TS Auto Tool.
Quy trình tự động:
1. Nâng số phiên bản (version.py)
2. Tự động đóng gói TS_Origin_Control_V3.exe qua build_v3.py
3. Tự động tạo Release trên GitHub và upload file .exe lên GitHub Releases
4. Đẩy commit & tag lên Git (sau khi upload thành công — FIX M1)

Fixes v2:
  [C1] Stream upload trực tiếp từ đĩa, không đọc toàn bộ .exe vào RAM.
  [M1] sync_git chạy SAU khi upload thành công.
  [M2] Rollback version.py nếu build hoặc upload thất bại.
  [N3] Upload retry 3 lần khi mạng không ổn định.
       Nhúng SHA256 checksum vào release body (phối hợp với updater.py).
"""

import os
import sys
import re
import json
import time
import hashlib
import http.client
import ssl
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

def compute_sha256(file_path: str) -> str:
    """Tính SHA256 của file .exe để nhúng vào release body (updater.py sẽ verify khi tải)."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(128 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_exe() -> str:
    print("\n[Build] Đang tiến hành đóng gói TS_Origin_Control_V3.exe...")
    build_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_v3.py")
    res = subprocess.run([sys.executable, build_script])
    if res.returncode != 0:
        raise RuntimeError("Quá trình đóng gói build_v3.py thất bại!")

    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TS_Origin_Control_V3.exe")
    if not os.path.exists(exe_path) or os.path.getsize(exe_path) < 5 * 1024 * 1024:
        raise RuntimeError(f"File {exe_path} không tồn tại hoặc kích thước không hợp lệ!")
    print(f"✅ Đóng gói thành công: {exe_path} ({os.path.getsize(exe_path) / (1024*1024):.1f} MB)")

    # Đồng bộ sang dist_share nếu thư mục này tồn tại trên máy bạn
    dist_share = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist_share")
    if os.path.exists(dist_share):
        try:
            import shutil
            shutil.copy2(exe_path, os.path.join(dist_share, "TS_Origin_Control_V3.exe"))
            print(f"-> Đã đồng bộ file .exe sang dist_share/ (giữ nguyên config.json sạch)")
        except Exception:
            pass

    return exe_path

def _upload_asset_stream(upload_url: str, exe_path: str, headers: dict) -> dict:
    """
    [FIX C1] Upload file .exe bằng streaming qua http.client — không đọc toàn bộ vào RAM.
    [FIX N3] Tự động thử lại tối đa 3 lần khi mạng không ổn định.
    """
    parsed = urllib.parse.urlparse(upload_url)
    file_size = os.path.getsize(exe_path)
    upload_headers = {
        **headers,
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size)
    }

    for attempt in range(1, 4):  # [N3] Retry 3 lần
        try:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(parsed.netloc, context=ctx, timeout=300)
            with open(exe_path, "rb") as f:
                conn.request(
                    "POST",
                    parsed.path + ("?" + parsed.query if parsed.query else ""),
                    body=f,
                    headers=upload_headers
                )
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            conn.close()
            if resp.status in (200, 201):
                return json.loads(body)
            raise RuntimeError(f"GitHub trả HTTP {resp.status}: {body[:200]}")
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  ⚠️ Lần thử {attempt}/3 thất bại: {exc}. Thử lại sau 5 giây...")
            time.sleep(5)


def create_and_upload_release(new_ver: str, changelog: str, exe_path: str, token: str):
    tag_name = f"v{new_ver}"
    print(f"\n[Release] Đang kết nối GitHub và tạo Release {tag_name}...")
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

    # 2. Tính SHA256 của exe để nhúng vào release body
    print("   Tính SHA256 của file .exe... (dùng để updater.py xác minh sau khi tải)")
    sha256_hash = compute_sha256(exe_path)
    print(f"   SHA256: {sha256_hash}")
    body_with_hash = f"{changelog}\n\n**SHA256**: `{sha256_hash}`"

    # 3. Nếu chưa có thì tạo mới Release
    if not release_data:
        create_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
        payload = json.dumps({
            "tag_name": tag_name,
            "target_commitish": "main",
            "name": f"TS Origin Control V3 - {tag_name}",
            "body": body_with_hash,
            "draft": False,
            "prerelease": False
        }).encode('utf-8')

        req = urllib.request.Request(create_url, data=payload, headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode('utf-8'))
            print(f"✅ Đã tạo Release mới: {tag_name} (ID: {release_data.get('id')})")
    else:
        # Cập nhật body (sha256 mới) cho release đã tồn tại
        patch_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/{release_data['id']}"
        patch_payload = json.dumps({"body": body_with_hash}).encode('utf-8')
        patch_req = urllib.request.Request(
            patch_url, data=patch_payload,
            headers={**headers, "Content-Type": "application/json"},
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(patch_req):
                pass
        except Exception:
            pass

    release_id = release_data.get("id")

    # 4. Xóa asset cũ nếu đã có file trùng tên
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

    # 5. [FIX C1 + N3] Upload file bằng streaming với retry
    file_size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print(f"\n[Upload] Đang tải file lên GitHub Releases ({file_size_mb:.1f} MB, streaming, retry 3 lần)...")
    upload_url = (
        f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}"
        f"/assets?name=TS_Origin_Control_V3.exe"
    )
    upload_res = _upload_asset_stream(upload_url, exe_path, headers)
    print(f"✅ Tải lên thành công! Download URL: {upload_res.get('browser_download_url')}")

def sync_git(new_ver, changelog):
    """Tự động commit và push phiên bản mới lên Git."""
    print(f"\n[3/4] Đang đồng bộ commit và push lên GitHub (main)...")
    try:
        files_to_add = [
            "version.py", "main_v3.py", "publish_release.py", "updater.py",
            "Tao_Loi_Tat_Desktop.bat", "launch_app.vbs", "AGENTS.md",
            "assets/card_d/nhikieu/", "assets/card_e/"
        ]
        subprocess.run(["git", "add"] + files_to_add, check=False)
        commit_res = subprocess.run(
            ["git", "commit", "-m", f"release: cap nhat phien ban v{new_ver} - {changelog}"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if commit_res.stdout.strip():
            print(f"-> Git commit: {commit_res.stdout.strip()}")
        push_res = subprocess.run(
            ["git", "push", "github", "main"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if push_res.stdout.strip() or push_res.stderr.strip():
            print(f"-> Git push: {push_res.stdout.strip()} {push_res.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ Lỗi đồng bộ Git: {e}")

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

    old_ver = APP_VERSION  # [FIX M2] Lưu phiên bản cũ để rollback nếu cần
    exe_path = None
    try:
        # 1. Cập nhật version.py
        update_version_file(new_ver)
        print(f"-> Đã cập nhật version.py sang v{new_ver}")

        # 2. Đóng gói EXE
        exe_path = build_exe()

        # 3. Tạo Release và Upload (.exe + SHA256)
        # [FIX M1] Upload TRƯỚC, rồi mới sync_git — tránh tag mồ côi khi upload lỗi
        create_and_upload_release(new_ver, changelog, exe_path, token)

        # 4. Đồng bộ Git SAU khi upload thành công
        sync_git(new_ver, changelog)

        # 5. Kéo tag mới về repo local
        try:
            subprocess.run(["git", "fetch", "github", "--tags"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    except Exception as err:
        # [FIX M2] Rollback version.py về phiên bản cũ nếu bất kỳ bước nào thất bại
        print(f"\n❌ LỖI: {err}")
        try:
            update_version_file(old_ver)
            print(f"-> Đã rollback version.py về v{old_ver}")
        except Exception as re_err:
            print(f"   (Rollback thất bại: {re_err})")
        sys.exit(1)

    print("\n" + "=" * 66)
    print(f"🎉 CHÚC MỮNG! BẢN v{new_ver} ĐÃ ĐƯỢC PHÁT HÀNH THÀNH CÔNG LÊN GITHUB!")
    print("-> Tất cả máy tính của bạn bè khi mở Tool lên sẽ TỰ ĐỘNG CẬP NHẬT bản này.")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
