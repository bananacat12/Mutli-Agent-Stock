from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PARENT_DIR = PACKAGE_DIR.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
