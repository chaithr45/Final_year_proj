@echo off
rem Build the KV260 bitstream on Windows:  double-click, or run  vivado\build.bat  from the kit folder.
rem Needs Vivado (2022.1 - 2025.2, free Standard edition with Zynq UltraScale+ / Kria devices).
cd /d "%~dp0.."
if not exist out mkdir out
set "VIV="
for /d %%D in ("C:\Xilinx\Vivado\*" "C:\Xilinx\*\Vivado" "C:\AMDDesignTools\*\Vivado") do (
  if exist "%%~D\bin\vivado.bat" set "VIV=%%~D\bin\vivado.bat"
)
if "%VIV%"=="" (
  echo Vivado not found in C:\Xilinx or C:\AMDDesignTools.
  echo Open the "Vivado Tcl Shell" from the Start menu, cd to this folder and run:
  echo     vivado -mode batch -source vivado/build_kv260.tcl
  pause
  exit /b 1
)
echo Using %VIV%
call "%VIV%" -mode batch -nojournal -log out\vivado_build.log -source vivado\build_kv260.tcl -tclargs %*
where python >nul 2>nul && python tools\parse_reports.py
echo.
echo Done. Copy out\seizelut.bit and out\seizelut.hwh into board\ and follow README.md, part C.
pause
