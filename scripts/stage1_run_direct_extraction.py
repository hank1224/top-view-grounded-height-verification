#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from top_view_grounded_height_verification.stage1.runner import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main("direct_extraction"))

