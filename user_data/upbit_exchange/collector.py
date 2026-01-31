#!/usr/bin/env python3
# collector.py (래퍼)
# 실제 구현은 cloud/collector.py에 있음

import sys
from pathlib import Path

# cloud 디렉토리를 Python path에 추가
PARENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PARENT_DIR))

from cloud.collector import main

if __name__ == "__main__":
    main()
