@echo off
wsl -d Ubuntu -- bash -c "cd /mnt/c/Users/Usuario/Desktop/projeto/SmartCity/fontes && ./sensor_temperatura; exec bash"
pause
