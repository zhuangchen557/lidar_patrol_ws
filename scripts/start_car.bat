@echo off
rem ============================================
rem  Patrol Car One-Click Start (run as Admin)
rem  1) attach lidar USB to WSL  2) launch bringup
rem ============================================
echo ============================================
echo   Patrol Car One-Click Start
echo ============================================

echo [1/3] Keep WSL running ...
start /b "" wsl -d Ubuntu -u root -e bash -c "sleep 7200"
timeout /t 3 >nul

echo [1.5/3] Clean old forwarder processes ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*forward_5578*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 1 >nul

echo [2/3] Attach lidar USB (busid 1-10) to WSL ...
usbipd bind --busid 1-10 2>nul
if %errorlevel% neq 0 (
    echo   WARNING: bind failed - lidar not plugged in?
)
usbipd attach --wsl Ubuntu --busid 1-10
if %errorlevel% neq 0 (
    echo   WARNING: attach failed - lidar not plugged or already attached
)
timeout /t 2 >nul

echo [3/4] Start TCP relay 127.0.0.1:5578 -> CAN115 192.168.0.7:5578 ...
start /b "" python "%~dp0forward_5578.py"
timeout /t 2 >nul

echo [4/4] Start bringup (chassis + lidar + TF), Ctrl+C to stop ...
wsl -d Ubuntu -e bash -c "~/lidar_patrol_ws/scripts/start_car.sh"

pause