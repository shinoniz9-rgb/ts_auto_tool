@echo off
chcp 65001 >nul
title Phat Hanh Ban Cap Nhat Moi - TS Auto Tool
cd /d "%~dp0"
echo ========================================================
echo   CONG CU PHAT HANH BAN CAP NHAT 1-CLICK (RELEASE)
echo ========================================================
echo.
set /p VER="Nhap so phien ban moi (de trong de tu dong tang so): "
set /p LOG="Nhap noi dung ghi chu cap nhat (de trong se dung mac dinh): "
echo.
if "%VER%"=="" (
    if "%LOG%"=="" (
        python publish_release.py
    ) else (
        python publish_release.py "" "%LOG%"
    )
) else (
    if "%LOG%"=="" (
        python publish_release.py "%VER%"
    ) else (
        python publish_release.py "%VER%" "%LOG%"
    )
)
echo.
pause
