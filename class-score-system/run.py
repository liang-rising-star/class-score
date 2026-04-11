import sys
import os

# 支持命令行参数：python run.py --reset
if "--reset" in sys.argv:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reset import reset
    reset()
    sys.exit(0)

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
