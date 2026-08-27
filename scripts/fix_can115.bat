@echo off
rem ============================================
rem  CAN115 底盘网卡一键修复（管理员运行）
rem  1) 找到 ASIX USB 网卡
rem  2) 设静态 IP 192.168.0.100/24
rem  3) 验证 CAN115 (192.168.0.7:5578)
rem ============================================
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ad = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like 'ASIX*' }; " ^
 "if (-not $ad) { Write-Host '[X] ASIX 网卡未识别 - 请检查 USB 网卡是否插紧/换口'; exit 1 }; " ^
 "Write-Host ('[OK] ASIX 网卡: ' + $ad.Name + ' status=' + $ad.Status); " ^
 "$idx = $ad.ifIndex; " ^
 "$idxR = (Get-NetAdapter | Where-Object { $_.InterfaceDescription -like 'Realtek*' }).ifIndex; " ^
 "if ($idxR) { netsh interface ip set address name=$idxR source=dhcp | Out-Null }; " ^
 "netsh interface ip set address name=$idx static 192.168.0.100 255.255.255.0 | Out-Null; " ^
 "$ip = (Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; " ^
 "Write-Host ('[OK] IP: ' + $ip); " ^
 "$r = Test-NetConnection -ComputerName 192.168.0.7 -Port 5578 -WarningAction SilentlyContinue; " ^
 "if ($r.TcpTestSucceeded) { Write-Host '[OK] CAN115 192.168.0.7:5578 可达!' } else { Write-Host '[X] CAN115 不可达 - 检查网线/CAN115 电源' }"

pause
