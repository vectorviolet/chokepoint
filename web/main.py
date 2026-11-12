# /// script
# dependencies = [
#   "pygame-ce",
#   "pytmx",
# ]
# ///
"""Entry point of the web build (pygbag), staged as `main.py` at the root of
the bundle next to `src/`, `assets/` and `config/`. The desktop entry point is
`__main__.py`; this one runs the game's loop through `run_async()` so the
browser gets control back after every frame."""

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "src" / "pygamine"))
os.chdir(_ROOT)

from app.game import Game  # noqa: E402


async def main() -> None:
    await Game().run_async()


asyncio.run(main())
