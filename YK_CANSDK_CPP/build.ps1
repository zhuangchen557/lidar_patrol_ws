# Build helper for the YK_CANSDK_CPP C++17 port.
#
#   .\build.ps1              configure + build (CMake if available)
#   .\build.ps1 -RunTests    build and run the offline selftest
#
# If CMake is not installed, the script prints the plain compiler commands:
#   MinGW:  g++ -std=c++17 -Wall -Wextra -Iinclude src/main.cpp -lws2_32 -o ykcan_ctl
#   MSVC:   cl /std:c++17 /W4 /Iinclude src\main.cpp /link ws2_32.lib

param(
    [switch]$RunTests
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Find-Command([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (Find-Command 'cmake') {
    $buildDir = Join-Path $root 'build'
    New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    Push-Location $buildDir
    try {
        cmake -S $root -B $buildDir
        cmake --build $buildDir --config Release
        if ($RunTests) {
            $test = Get-ChildItem -Path $buildDir -Recurse -Filter 'ykcan_selftest.exe' | Select-Object -First 1
            if ($test) {
                Push-Location $root
                try { & $test.FullName } finally { Pop-Location }
            }
        }
    } finally {
        Pop-Location
    }
    Write-Host ""
    Write-Host "Built. Binaries:"
    Get-ChildItem -Path $buildDir -Recurse -Filter 'ykcan_*.exe' | ForEach-Object { Write-Host "  $($_.FullName)" }
    exit 0
}

Write-Host "cmake not found on PATH. Install CMake, or compile directly with one of:"
Write-Host ""
Write-Host "MinGW (g++) or MSYS2/UCRT64:"
Write-Host "  g++ -std=c++17 -Wall -Wextra -Iinclude src/main.cpp -lws2_32 -o ykcan_ctl"
Write-Host "  g++ -std=c++17 -Wall -Wextra -Iinclude examples/selftest.cpp -o ykcan_selftest"
Write-Host ""
Write-Host "MSVC (Visual Studio Developer Prompt):"
Write-Host "  cl /std:c++17 /W4 /Iinclude src\main.cpp /link ws2_32.lib"
Write-Host "  cl /std:c++17 /W4 /Iinclude examples\selftest.cpp /link ws2_32.lib"
exit 1
