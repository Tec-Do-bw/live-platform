import sys
from pathlib import Path

# 添加 app 目录到 sys.path，允许测试直接 import app.services.login_monitor
sys.path.insert(0, str(Path(__file__).parent / "app"))
