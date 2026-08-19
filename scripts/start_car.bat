@echo off
rem ============================================
rem  巡检车一键启动（Windows 侧，需管理员运行）
rem  双击运行即可：挂载雷达USB + 启动底盘/雷达
rem ============================================
chcp 65001 >nul
echo ============================================
echo   巡检车一键启动
echo ============================================

echo [1/3] 保持 WSL 运行 ...
start /b "" wsl -d Ubuntu -u root -e bash -c "sleep 7200"
timeout /t 3 >nul

echo [2/3] 挂载雷达 USB 到 WSL (busid 1-9) ...
usbipd attach --wsl --busid 1-9
if %errorlevel% neq 0 (
    echo   警告: attach 失败，可能未插雷达或已挂载
)
timeout /t 2 >nul

echo [3/3] 启动巡检车（底盘+雷达+TF），Ctrl+C 停止 ...
wsl -d Ubuntu -e bash ~/lidar_patrol_ws/scripts/start_car.sh

pause