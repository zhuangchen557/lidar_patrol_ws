@echo off
rem ============================================
rem  CAN115 底盘网卡一键修复（管理员运行）
rem  1) 自动找已连接的以太网口（ASIX USB 网卡 或 主板 Realtek 网口）
rem  2) 设静态 IP 192.168.0.100/24
rem  3) 验证 CAN115 (192.168.0.7:5578)
rem ============================================
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ad = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like 'ASIX*' -or ($_.InterfaceDescription -like 'Realtek*' -and $_.Status -eq 'Up') }; " ^
 "if (-not $ad) { Write-Host '[X] 未找到已连接的以太网口'; Write-Host '    请插好 ASIX USB 网卡，或把网线直接插主板网口'; exit 1 }; " ^
 "$sel = $ad | Select-Object -First 1; " ^
 "Write-Host ('[OK] 使用网卡: ' + $sel.Name + ' (' + $sel.InterfaceDescription + ')'); " ^
 "$idx = $sel.ifIndex; " ^
 "foreach ($a in (Get-NetAdapter | Where-Object { $_.ifIndex -ne $idx -and $_.PhysicalMediaType -eq '802.3' })) { " ^
 "  netsh interface ip set address name=$($a.ifIndex) source=dhcp 2>$null | Out-Null }; " ^
 "netsh interface ip set address name=$idx static 192.168.0.100 255.255.255.0 | Out-Null; " ^
 "Start-Sleep -Seconds 1; " ^
 "$ip = (Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; " ^
 "Write-Host ('[OK] IP: ' + $ip); " ^
 "$r = Test-NetConnection -ComputerName 192.168.0.7 -Port 5578 -WarningAction SilentlyContinue; " ^
 "if ($r.TcpTestSucceeded) { Write-Host '[OK] CAN115 192.168.0.7:5578 可达!' } else { Write-Host '[X] CAN115 不可达 - 检查网线/CAN115 电源' }"

pause
