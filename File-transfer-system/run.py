import sys
import os
import subprocess

# Ensure we run under Python 3.13, because the pre-compiled 'original_app.pyc' module requires it.
if sys.version_info[:2] != (3, 13):
    print(f"[*] FileBridge detected Python {sys.version_info.major}.{sys.version_info.minor}, but Python 3.13 is required.")
    print("[*] Attempting to auto-relaunch using Python 3.13...")
    try:
        launcher = ["py", "-3.13"] if sys.platform == "win32" else ["python3.13"]
        result = subprocess.run(launcher + ["--version"], capture_output=True, text=True)
        if result.returncode == 0:
            args = launcher + sys.argv
            proc = subprocess.run(args)
            sys.exit(proc.returncode)
    except Exception as e:
        pass
        
    print("\n" + "="*80)
    print("CRITICAL ERROR: Python 3.13 is required to run FileBridge!")
    print("The pre-compiled core component 'original_app.pyc' was built with Python 3.13.")
    print("Current Python version in use: " + sys.version)
    print("\nTo start the server, please use the Python 3.13 launcher:")
    print("    py -3.13 run.py")
    print("="*80 + "\n")
    sys.exit(1)

from app import app, socketio, start_scheduler

if __name__ == "__main__":
    start_scheduler()
    socketio.run(app, host="172.100.30.191", port=5001, debug=app.config["APP_ENV"] != "production", ssl_context=('cert.pem', 'key.pem'), allow_unsafe_werkzeug=True)

