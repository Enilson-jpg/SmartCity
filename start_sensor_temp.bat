@echo off
wsl -d Ubuntu -- bash -c "cd /mnt/c/Users/Usuario/Desktop/projeto/SmartCity/fontes && ./sensor_temperatura 192.168.1.60 6002"
pause
