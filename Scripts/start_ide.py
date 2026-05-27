import os
import sys

# Ensure parent directory is in sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, parent_dir)

import uvicorn
from src.ui.web_server import app

if __name__ == "__main__":
    print("==================================================")
    print("DeepGravity Sovereign IDE - Starting Web Server")
    print("URL: http://127.0.0.1:8000")
    print("==================================================")
    uvicorn.run(app, host="0.0.0.0", port=8000)
