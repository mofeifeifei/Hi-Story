from __future__ import annotations

import traceback
import sys
from datetime import datetime
from pathlib import Path


if __name__ == "__main__":
    try:
        from app.web.server import run

        run(open_browser="--no-browser" not in sys.argv)
    except Exception as exc:  # noqa: BLE001
        log_dir = Path(__file__).resolve().parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "startup.log").open("a", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(datetime.now().isoformat(timespec="seconds") + "\n")
            f.write("Hi Story 启动失败\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write("\n")
        raise
