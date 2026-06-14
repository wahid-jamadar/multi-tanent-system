@echo off
echo Building FileBridge Agent Executable...
pip install -r requirements.txt
pyinstaller --onefile --noconsole --add-data "config.yaml;." agent.py
echo Build complete. Check the 'dist' folder for agent.exe.
