@echo off
title BOSS直聘智能求职助手 - 桌面端
cd /d "E:\aower\boss\bossHelper"
set "PATH=E:\nvm\nodejs;E:\.cargo\bin;C:\Users\19257\.cargo\bin;%PATH%"
echo ==========================================
echo   正在启动 BOSS直聘智能求职助手 桌面端...
echo ==========================================
echo.
npm run tauri:dev

