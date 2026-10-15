@echo off
chcp 65001 >nul
title Tao Loi Tat TS Origin Mobile App V3 Ra Desktop
echo ============================================================
echo   DANG TAO HOAC CAP NHAT LOI TAT V3 RA MAN HINH DESKTOP...
echo ============================================================
echo.

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

set "VBS_FILE=%CURRENT_DIR%\launch_app.vbs"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "SHORTCUT_PATH=%DESKTOP_DIR%\TS Origin Mobile App V3.lnk"
set "OLD_SHORTCUT=%DESKTOP_DIR%\TS Origin Mobile App.lnk"

REM Tu dong chon icon hop ly (TS_Origin_Control_V3.exe -> Chrome -> Edge)
set "ICON_LOC=%CURRENT_DIR%\dist\TS_Origin_Control_V3.exe,0"
if exist "%CURRENT_DIR%\TS_Origin_Control_V3.exe" (
    set "ICON_LOC=%CURRENT_DIR%\TS_Origin_Control_V3.exe,0"
) else if exist "%CURRENT_DIR%\dist\TS_Origin_Control_V3.exe" (
    set "ICON_LOC=%CURRENT_DIR%\dist\TS_Origin_Control_V3.exe,0"
) else if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "ICON_LOC=C:\Program Files\Google\Chrome\Application\chrome.exe,0"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "ICON_LOC=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe,0"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "ICON_LOC=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe,0"
)

(
echo Set oWS = CreateObject("WScript.Shell"^)
echo Set oLink = oWS.CreateShortcut("%SHORTCUT_PATH%"^)
echo oLink.TargetPath = "wscript.exe"
echo oLink.Arguments = """%VBS_FILE%"""
echo oLink.WorkingDirectory = "%CURRENT_DIR%"
echo oLink.IconLocation = "%ICON_LOC%"
echo oLink.Description = "TS Origin Mobile App V3 1-Click"
echo oLink.Save
) > "%TEMP%\_create_sc.vbs"

cscript //nologo "%TEMP%\_create_sc.vbs"
if exist "%TEMP%\_create_sc.vbs" del "%TEMP%\_create_sc.vbs"

REM Dong thoi cap nhat shortcut ten cu neu nguoi dung da co tren Desktop
if exist "%OLD_SHORTCUT%" (
    (
    echo Set oWS = CreateObject("WScript.Shell"^)
    echo Set oLink = oWS.CreateShortcut("%OLD_SHORTCUT%"^)
    echo oLink.TargetPath = "wscript.exe"
    echo oLink.Arguments = """%VBS_FILE%"""
    echo oLink.WorkingDirectory = "%CURRENT_DIR%"
    echo oLink.IconLocation = "%ICON_LOC%"
    echo oLink.Description = "TS Origin Mobile App V3 1-Click"
    echo oLink.Save
    ) > "%TEMP%\_create_sc2.vbs"
    cscript //nologo "%TEMP%\_create_sc2.vbs"
    if exist "%TEMP%\_create_sc2.vbs" del "%TEMP%\_create_sc2.vbs"
)

echo [OK] Thu muc hien tai: %CURRENT_DIR%
echo [OK] Da tao / cap nhat thanh cong bieu tuong tai Desktop:
echo      %SHORTCUT_PATH%
echo.
echo ============================================================
echo   HOAN TAT! TU NAY BAN CO THE MO APP V3 TRUC TIEP TU DESKTOP!
echo ============================================================
ping 127.0.0.1 -n 2 >nul
exit
