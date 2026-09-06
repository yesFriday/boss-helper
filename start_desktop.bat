@echo off
chcp 65001 >nul
title bosshelper-desktop-dev
cd /d "%~dp0"
set "PATH=E:\nvm\nodejs;E:\.cargo\bin;C:\Users\19257\.cargo\bin;%PATH%"
echo ==========================================
echo   正在启动 BOSS直聘智能求职助手 桌面端 (Dev)...
echo ==========================================
echo.
npm run tauri:dev
