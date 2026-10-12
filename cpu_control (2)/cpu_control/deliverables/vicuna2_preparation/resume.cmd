@echo off
wsl.exe -d Ubuntu-22.04 -e python3 "/mnt/d/code/FPGA1/cpu_control (2)/cpu_control/scripts/run_vicuna_small.py" --run-tests
pause
