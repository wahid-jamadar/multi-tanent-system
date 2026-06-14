@echo off
echo Starting long running task...
ping 172.100.31.40 -n 16 > nul
echo Task finished!
