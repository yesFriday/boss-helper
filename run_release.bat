@echo off
title BOSS直聘智能求职助手 - 桌面客户端
cd /d "%~dp0src-tauri\target\release"
echo ==========================================
echo   正在启动 BOSS直聘智能求职助手 桌面端...
echo ==========================================
start "" "bosshelper-desktop.exe"
