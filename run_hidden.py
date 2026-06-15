import subprocess
import sys
import os
import time
import webbrowser

script = os.path.join(os.path.dirname(__file__), "dashboard.py")

proc = subprocess.Popen(
    [sys.executable, script],
    cwd=os.path.dirname(__file__),
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

time.sleep(3)

# Check if running
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(("127.0.0.1", 8765))
    s.close()
    print("=" * 55)
    print("  WebScraper Dashboard is running!")
    print("  Open: http://localhost:8765")
    print("  PID: %d" % proc.pid)
    print("=" * 55)
    try:
        webbrowser.open("http://localhost:8765")
    except Exception:
        pass
except ConnectionRefusedError:
    print("Server failed to start")
    sys.exit(1)
