@echo off
chcp 65001 >nul
cd /d "E:\aower\boss\bossHelper"
echo ========================================== >> "E:\aower\boss\logs\task_debug.log"
echo [%date% %time%] 正在启动后台服务... >> "E:\aower\boss\logs\task_debug.log"
"C:\Users\19257\AppData\Local\Python\pythoncore-3.14-64\python.exe" backend\app.py --port 8010 >> "E:\aower\boss\logs\task_debug.log" 2>&1
echo [%date% %time%] 退出码: %errorlevel% >> "E:\aower\boss\logs\task_debug.log"
