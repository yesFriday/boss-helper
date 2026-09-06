@echo off
chcp 65001 >nul
title bosshelper-desktop
cd /d "%~dp0src-tauri\target\release"
echo ==========================================
echo   正在启动 BOSS直聘智能求职助手 桌面端...
echo ==========================================
start "" "%~dp0src-tauri\target\release\bosshelper-desktop.exe"
