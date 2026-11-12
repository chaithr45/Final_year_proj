@echo off
rem Rehearse the demo on Windows without WSL (needs Python 3 with numpy on Windows). Double-click or run from cmd.
rem If this fails, use WSL instead:  bash rehearse_laptop.sh
cd /d "%~dp0"
python -c "import numpy" || (echo numpy missing: pip install numpy & pause & exit /b 1)
start "" http://localhost:8080
python seizelut_demo.py --backend emu --demo 1 --no-board-leds --port 8080
pause
