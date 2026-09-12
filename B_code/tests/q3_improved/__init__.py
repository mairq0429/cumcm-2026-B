"""Q3-improved-v1 tests.

Keep source submodules visible when unittest discovery imports this directory
as the top-level ``q3_improved`` package.
"""

from pathlib import Path


SOURCE_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "q3_improved"
if str(SOURCE_PACKAGE) not in __path__:
    __path__.append(str(SOURCE_PACKAGE))
